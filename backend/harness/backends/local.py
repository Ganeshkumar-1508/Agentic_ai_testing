"""Local execution backend: spawn-per-call on the host machine.

No isolation, no chroot, no bwrap. Default backend. Used for:
- Development on the host without Docker setup
- CI runners that already provide isolation
- Test environments where container overhead is unwanted

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .base import BaseEnvironment, ProcessHandle, _pipe_stdin

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform.startswith("win")

# ---------------------------------------------------------------------------
# Env blocklist — prevents provider API keys from leaking into subprocesses.
# ---------------------------------------------------------------------------
_TESTAI_PROVIDER_ENV_BLOCKLIST: frozenset = frozenset({
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY",
    "TOGETHER_API_KEY", "PERPLEXITY_API_KEY", "COHERE_API_KEY",
    "FIREWORKS_API_KEY", "XAI_API_KEY", "HELICONE_API_KEY",
    "PARALLEL_API_KEY", "FIRECRAWL_API_KEY", "FIRECRAWL_API_URL",
    "OPENROUTER_API_KEY", "LLM_MODEL", "GH_TOKEN", "GITHUB_TOKEN",
    "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH",
    "GITHUB_APP_INSTALLATION_ID",
})


def _sanitize_env(run_env: dict, extra_env: dict | None = None) -> dict:
    """Strip provider API keys from subprocess environment.

    Respects env_passthrough allowlist — vars registered there
    bypass the blocklist even if they match a blocked name.
    """
    blocked = _TESTAI_PROVIDER_ENV_BLOCKLIST
    try:
        from harness.tools.env_passthrough import is_env_passthrough as _is_passthrough
    except Exception:
        _is_passthrough = lambda _: False
    sanitized: dict[str, str] = {}
    for key, value in (run_env or {}).items():
        if key not in blocked or _is_passthrough(key):
            sanitized[key] = value
    for key, value in (extra_env or {}).items():
        if key not in blocked or _is_passthrough(key):
            sanitized[key] = value
    return sanitized


# ---------------------------------------------------------------------------
# Bash resolution (cross-platform)
# ---------------------------------------------------------------------------


def _find_bash() -> str:
    if not _IS_WINDOWS:
        return (
            shutil.which("bash")
            or ("/usr/bin/bash" if os.path.isfile("/usr/bin/bash") else None)
            or ("/bin/bash" if os.path.isfile("/bin/bash") else None)
            or os.environ.get("SHELL")
            or "/bin/sh"
        )
    custom = os.environ.get("TESTAI_BASH_PATH")
    if custom and os.path.isfile(custom):
        return custom
    for candidate in (
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Git", "bin", "bash.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "bin", "bash.exe"),
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    found = shutil.which("bash")
    if found:
        return found
    raise RuntimeError(
        "Bash not found. On Windows, install Git for Windows or set TESTAI_BASH_PATH."
    )


# ---------------------------------------------------------------------------
# MSYS-to-Windows path translation
# ---------------------------------------------------------------------------


def _msys_to_windows_path(cwd: str) -> str:
    """Translate Git Bash / MSYS POSIX path (``/c/Users/x``) to native
    Windows form (``C:\\Users\\x``). No-ops on non-Windows or non-MSYS paths."""
    if not _IS_WINDOWS or not cwd:
        return cwd
    import re
    m = re.match(r'^/([a-zA-Z])(/.*)?$', cwd)
    if not m:
        return cwd
    drive = m.group(1).upper()
    tail = (m.group(2) or "").replace('/', '\\')
    return f"{drive}:{tail or chr(92)}"


# ---------------------------------------------------------------------------
# Safe CWD resolution
# ---------------------------------------------------------------------------


def _resolve_safe_cwd(cwd: str) -> str:
    cwd = _msys_to_windows_path(cwd) if _IS_WINDOWS else cwd
    if cwd and os.path.isdir(cwd):
        return cwd
    parent = os.path.dirname(cwd) if cwd else ""
    while parent:
        if os.path.isdir(parent):
            return parent
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent
    return os.getcwd()


# ---------------------------------------------------------------------------
# Shell init files (bashrc/profile sourcing)
# ---------------------------------------------------------------------------

_TESTAI_SHELL_INIT_FILES: list[str] | None = None


def _read_shell_init_config() -> tuple[list[str], bool]:
    files_env = os.environ.get("TESTAI_SHELL_INIT_FILES", "")
    if files_env:
        return [f.strip() for f in files_env.split(",") if f.strip()], False
    override = os.environ.get("TESTAI_AUTO_SOURCE_BASHRC", "true")
    return [], override.lower() != "false"


def _resolve_shell_init_files() -> list[str]:
    global _TESTAI_SHELL_INIT_FILES
    if _TESTAI_SHELL_INIT_FILES is not None:
        return _TESTAI_SHELL_INIT_FILES
    explicit, auto_bashrc = _read_shell_init_config()
    candidates: list[str] = []
    if explicit:
        candidates.extend(explicit)
    elif auto_bashrc and not _IS_WINDOWS:
        candidates.extend(["~/.profile", "~/.bash_profile", "~/.bashrc"])
    resolved: list[str] = []
    for raw in candidates:
        try:
            path = os.path.expandvars(os.path.expanduser(raw))
        except Exception:
            continue
        if path and os.path.isfile(path):
            resolved.append(path)
    _TESTAI_SHELL_INIT_FILES = resolved
    return resolved


def _prepend_shell_init(cmd_string: str, files: list[str]) -> str:
    if not files:
        return cmd_string
    prelude_parts = ["set +e"]
    for path in files:
        safe = path.replace("'", "'\\''")
        prelude_parts.append(f"[ -r '{safe}' ] && . '{safe}' 2>/dev/null || true")
    return "\n".join(prelude_parts) + "\n" + cmd_string


# ---------------------------------------------------------------------------
# Compound background rewrite (shell safety)
# ---------------------------------------------------------------------------


def _rewrite_compound_background(command: str) -> str:
    """Rewrite ``A && B &`` patterns to prevent subshell-wait traps.

    When a user writes ``cd foo && npm run dev &``, bash's parser
    attaches the ``&`` to the entire ``&&`` chain, backgrounding the
    whole compound command. Subsequent tool calls that expect a clean
    shell instead find a backgrounded process still holding the stdout
    pipe, causing hangs. We rewrite the final segment to use a
    subshell wrapper so only the intended command is backgrounded.
    """
    import re
    # Match: optional prefix + `&&` + last command + optional whitespace + `&`
    pattern = r'((?:.*?\s+&&\s+)?)([^&]+?)\s*&\s*$'
    m = re.match(pattern, command.strip())
    if not m:
        return command
    prefix, last_cmd = m.group(1), m.group(2).strip()
    if not prefix:
        return command
    return f"{prefix} ( {last_cmd} & disown )"


# ---------------------------------------------------------------------------
# LocalEnvironment
# ---------------------------------------------------------------------------


class LocalEnvironment(BaseEnvironment):
    def __init__(self, session_id: str, cwd: str = "", timeout: int = 120, env: dict | None = None):
        if cwd:
            cwd = os.path.expanduser(cwd)
            if _IS_WINDOWS:
                cwd = _msys_to_windows_path(cwd)
        super().__init__(session_id=session_id, cwd=cwd or os.getcwd(), timeout=timeout, env=env)

    def _run_bash(
        self,
        cmd_string: str,
        *,
        login: bool = False,
        timeout: int = 120,
        stdin_data: str | None = None,
    ) -> ProcessHandle:
        bash = _find_bash()
        cmd_string = _rewrite_compound_background(cmd_string)
        if login:
            init_files = _resolve_shell_init_files()
            if init_files:
                cmd_string = _prepend_shell_init(cmd_string, init_files)
            args = [bash, "-l", "-c", cmd_string]
        else:
            args = [bash, "-c", cmd_string]
        run_env = _sanitize_env(dict(os.environ), self.env)
        safe_cwd = _resolve_safe_cwd(self.cwd)
        if safe_cwd != self.cwd:
            logger.warning(
                "LocalEnvironment cwd %r missing; falling back to %r",
                self.cwd, safe_cwd,
            )
            self.cwd = safe_cwd

        kwargs: dict = {}
        if not _IS_WINDOWS:
            kwargs["preexec_fn"] = os.setsid

        proc = subprocess.Popen(
            args,
            text=True,
            env=run_env,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            cwd=self.cwd,
            **kwargs,
        )
        if not _IS_WINDOWS:
            try:
                proc._testai_pgid = os.getpgid(proc.pid)
            except ProcessLookupError:
                pass
        if stdin_data is not None:
            _pipe_stdin(proc, stdin_data)
        return proc

    def get_temp_dir(self) -> str:
        if _IS_WINDOWS:
            cache_dir = Path.home() / ".testai" / "cache" / "terminal"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return str(cache_dir).replace("\\", "/")
        for env_var in ("TMPDIR", "TMP", "TEMP"):
            candidate = os.environ.get(env_var)
            if candidate and candidate.startswith("/"):
                return candidate.rstrip("/") or "/"
        if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK | os.X_OK):
            return "/tmp"
        return "/tmp"

    def _kill_process(self, proc):
        import signal
        if _IS_WINDOWS:
            try:
                proc.terminate()
            except Exception:
                pass
            return
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            pgid = getattr(proc, "_testai_pgid", None)
            if pgid is None:
                return

        def _group_alive(pgid: int) -> bool:
            try:
                os.killpg(pgid, 0)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                return True

        def _wait_for_group_exit(pgid: int, timeout: float) -> bool:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    proc.poll()
                except Exception:
                    pass
                if not _group_alive(pgid):
                    return True
                time.sleep(0.05)
            return not _group_alive(pgid)

        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        if _wait_for_group_exit(pgid, 1.0):
            return
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return
        _wait_for_group_exit(pgid, 2.0)
        try:
            proc.wait(timeout=0.2)
        except (subprocess.TimeoutExpired, OSError):
            pass

    def _update_cwd(self, result: dict):
        try:
            with open(self._cwd_file, encoding="utf-8") as f:
                cwd_path = f.read().strip()
            if _IS_WINDOWS:
                cwd_path = _msys_to_windows_path(cwd_path)
            if cwd_path and os.path.isdir(cwd_path):
                self.cwd = cwd_path
        except (OSError, FileNotFoundError):
            pass
        self._extract_cwd_from_output(result)

    def _extract_cwd_from_output(self, result: dict):
        prev_cwd = self.cwd
        super()._extract_cwd_from_output(result)
        if self.cwd != prev_cwd:
            normalized = _msys_to_windows_path(self.cwd) if _IS_WINDOWS else self.cwd
            if normalized and os.path.isdir(normalized):
                self.cwd = normalized
            else:
                self.cwd = prev_cwd

    def cleanup(self) -> None:
        for f in (self._snapshot_path, self._cwd_file):
            try:
                os.unlink(f)
            except OSError:
                pass
