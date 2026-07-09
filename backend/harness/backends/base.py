"""Base class for all TestAI execution environment backends.

Unified spawn-per-call model: every command spawns a fresh ``bash -c`` process.
A session snapshot (env vars, functions, aliases) is captured once at init and
re-sourced before each command. CWD persists via in-band stdout markers (remote)
or a temp file (local).

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import asyncio
import codecs
import logging
import os
import shlex
import subprocess
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable, Protocol

logger = logging.getLogger(__name__)

# Thread-local activity callback for long-running process liveness.
_activity_callback_local = threading.local()


def set_activity_callback(cb: Callable[[str], None] | None) -> None:
    _activity_callback_local.callback = cb


def _get_activity_callback() -> Callable[[str], None] | None:
    return getattr(_activity_callback_local, "callback", None)


def touch_activity_if_due(state: dict, label: str) -> None:
    now = time.monotonic()
    interval = state.get("interval", 10.0)
    if now - state["last_touch"] < interval:
        return
    state["last_touch"] = now
    try:
        cb = _get_activity_callback()
        if cb:
            elapsed = int(now - state["start"])
            cb(f"{label} ({elapsed}s elapsed)")
    except Exception:
        pass


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


class ProcessHandle(Protocol):
    def poll(self) -> int | None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    @property
    def stdout(self) -> IO[str] | None: ...
    @property
    def returncode(self) -> int | None: ...


class _ThreadedProcessHandle:
    def __init__(
        self,
        exec_fn: Callable[[], tuple[str, int]],
        cancel_fn: Callable[[], None] | None = None,
    ):
        self._cancel_fn = cancel_fn
        self._done = threading.Event()
        self._returncode: int | None = None
        self._error: Exception | None = None

        read_fd, write_fd = os.pipe()
        self._stdout = os.fdopen(read_fd, "r", encoding="utf-8", errors="replace")
        self._write_fd = write_fd

        def _worker():
            try:
                output, exit_code = exec_fn()
                self._returncode = exit_code
                try:
                    os.write(self._write_fd, output.encode("utf-8", errors="replace"))
                except OSError:
                    pass
            except Exception as exc:
                self._error = exc
                self._returncode = 1
            finally:
                try:
                    os.close(self._write_fd)
                except OSError:
                    pass
                self._done.set()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @property
    def stdout(self):
        return self._stdout

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def poll(self) -> int | None:
        return self._returncode if self._done.is_set() else None

    def kill(self):
        if self._cancel_fn:
            try:
                self._cancel_fn()
            except Exception:
                pass

    def wait(self, timeout: float | None = None) -> int:
        self._done.wait(timeout=timeout)
        return self._returncode


class _InterruptEvent:
    def is_set(self) -> bool:
        return False


_DEFAULT_INTERRUPT = _InterruptEvent()


def _pipe_stdin(proc: subprocess.Popen, data: str) -> None:
    def _write():
        try:
            raw = data.encode("utf-8") if isinstance(data, str) else data
            target = getattr(proc.stdin, "buffer", proc.stdin)
            target.write(raw)
            target.close()
        except (BrokenPipeError, OSError):
            pass

    threading.Thread(target=_write, daemon=True).start()


def _popen_bash(cmd: list[str], stdin_data: str | None = None, **kwargs) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        text=True,
        **kwargs,
    )
    if stdin_data is not None:
        _pipe_stdin(proc, stdin_data)
    return proc


def _load_json_store(path: Path) -> dict:
    if path.exists():
        try:
            import json
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_json_store(path: Path, data: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _file_mtime_key(host_path: str) -> tuple[float, int] | None:
    try:
        st = Path(host_path).stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def get_sandbox_dir() -> Path:
    custom = os.getenv("TESTAI_SANDBOX_DIR")
    if custom:
        p = Path(custom)
    else:
        home = Path.home() / ".testai" / "sandboxes"
        p = home
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cwd_marker(session_id: str) -> str:
    return f"__TESTAI_CWD_{session_id}__"


def _wait_for_process(
    proc: ProcessHandle,
    timeout: int = 120,
    interrupt: _InterruptEvent | None = None,
) -> dict:
    interrupt = interrupt or _DEFAULT_INTERRUPT
    output_chunks: list[str] = []
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def _drain():
        stream = proc.stdout
        if stream is None:
            return
        fileno = getattr(stream, "fileno", None)
        try:
            fd = fileno() if callable(fileno) else None
        except Exception:
            fd = None
        if not isinstance(fd, int) or fd < 0:
            try:
                for piece in stream:
                    if piece is None:
                        continue
                    if isinstance(piece, bytes):
                        output_chunks.append(decoder.decode(piece))
                    else:
                        output_chunks.append(str(piece))
            except Exception:
                pass
            try:
                tail = decoder.decode(b"", final=True)
                if tail:
                    output_chunks.append(tail)
            except Exception:
                pass
            return

        if os.name == "nt":
            try:
                while True:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    output_chunks.append(decoder.decode(chunk))
            except (ValueError, OSError):
                pass
            try:
                tail = decoder.decode(b"", final=True)
                if tail:
                    output_chunks.append(tail)
            except Exception:
                pass
            return

        idle_after_exit = 0
        import select
        while True:
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
            except (ValueError, OSError):
                break
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except (ValueError, OSError):
                    break
                if not chunk:
                    break
                output_chunks.append(decoder.decode(chunk))
                idle_after_exit = 0
            elif proc.poll() is not None:
                idle_after_exit += 1
                if idle_after_exit >= 3:
                    break
        try:
            tail = decoder.decode(b"", final=True)
            if tail:
                output_chunks.append(tail)
        except Exception:
            pass

    drain_thread = threading.Thread(target=_drain, daemon=True)
    drain_thread.start()
    deadline = time.monotonic() + timeout
    _now = time.monotonic()
    _activity_state = {"last_touch": _now, "start": _now}
    _poll_sleep = 0.005
    try:
        while proc.poll() is None:
            touch_activity_if_due(_activity_state, "command running")
            if interrupt.is_set():
                proc.kill()
                drain_thread.join(timeout=2)
                return {
                    "output": "".join(output_chunks) + "\n[Command interrupted]",
                    "returncode": 130,
                }
            if time.monotonic() > deadline:
                proc.kill()
                drain_thread.join(timeout=2)
                partial = "".join(output_chunks)
                timeout_msg = f"\n[Command timed out after {timeout}s]"
                return {
                    "output": partial + timeout_msg if partial else timeout_msg.lstrip(),
                    "returncode": 124,
                }
            time.sleep(_poll_sleep)
            if _poll_sleep < 0.2:
                _poll_sleep = min(_poll_sleep * 1.5, 0.2)
    except (KeyboardInterrupt, SystemExit):
        try:
            proc.kill()
            drain_thread.join(timeout=2)
        except Exception:
            pass
        raise
    drain_thread.join(timeout=2)
    try:
        proc.stdout.close()
    except Exception:
        pass
    return {"output": "".join(output_chunks), "returncode": proc.returncode}


import re as _re

_LONG_LIVED_FOREGROUND_PATTERNS = [
    _re.compile(p) for p in [
        r'\b(dev|start|serve|server|runserver|watch|watchman|webpack|vite|nodemon|ts-node)\b',
        r'\b(pytest|jest|vitest)\s.*--watch\b',
        r'\b(sleep|tail\s+-f|inotifywait|entr)\b',
        r'\b(pip|npm|yarn|pnpm)\s+(install|run)\s+(dev|start)\b',
        r'docker\s+(compose\s+)?up\b',
        r'\b(redis|postgres|mysql|mongod)\b',
    ]
]


def foreground_background_guidance(command: str) -> str | None:
    """Suggest background mode when a foreground command looks long-lived."""
    for pattern in _LONG_LIVED_FOREGROUND_PATTERNS:
        if pattern.search(command):
            return (
                "This command appears to start a long-lived process. "
                "Use `bash` with background=true or the `process` tool to manage it."
            )
    return None


def read_password_thread() -> str:
    """Read a password from the terminal without echo."""
    import sys
    password = ""
    try:
        if os.name == "nt":
            import msvcrt
            sys.stdout.write("Password: ")
            sys.stdout.flush()
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    break
                elif ch in ("\b", "\x7f"):
                    password = password[:-1]
                else:
                    password += ch
        else:
            tty_fd = os.open("/dev/tty", os.O_RDWR)
            try:
                import termios
                old = termios.tcgetattr(tty_fd)
                new = termios.tcgetattr(tty_fd)
                new[3] = new[3] & ~(termios.ECHO | termios.ICANON)
                try:
                    termios.tcsetattr(tty_fd, termios.TCSANOW, new)
                    os.write(tty_fd, b"Password: ")
                    password = os.read(tty_fd, 256).decode(errors="replace").strip()
                finally:
                    termios.tcsetattr(tty_fd, termios.TCSANOW, old)
            finally:
                os.close(tty_fd)
    except Exception:
        password = ""
    return password


def _kill_process_group(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            proc.terminate()
        except Exception:
            pass
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        import signal
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            proc.poll()
        except Exception:
            pass
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.05)
    try:
        import signal
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2.0)
    except Exception:
        pass


class BaseEnvironment(ABC):
    _stdin_mode: str = "pipe"
    _snapshot_timeout: int = 30

    def get_temp_dir(self) -> str:
        return "/tmp"

    def __init__(
        self,
        session_id: str,
        cwd: str = "",
        timeout: int = 120,
        env: dict | None = None,
    ):
        self.cwd = cwd or os.getcwd()
        self.timeout = timeout
        self.env = env or {}
        self.session_id = session_id
        self._session_uuid = uuid.uuid4().hex[:12]
        temp_dir = self.get_temp_dir().rstrip("/") or "/"
        self._snapshot_path = f"{temp_dir}/testai-snap-{self._session_uuid}.sh"
        self._cwd_file = f"{temp_dir}/testai-cwd-{self._session_uuid}.txt"
        self._cwd_marker = _cwd_marker(self._session_uuid)
        self._snapshot_ready = False

    @abstractmethod
    def _run_bash(
        self,
        cmd_string: str,
        *,
        login: bool = False,
        timeout: int = 120,
        stdin_data: str | None = None,
    ) -> ProcessHandle:
        raise NotImplementedError

    @abstractmethod
    def cleanup(self) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Session snapshot
    # ------------------------------------------------------------------

    def init_session(self):
        _quoted_cwd = shlex.quote(self.cwd)
        _quoted_snap = shlex.quote(self._snapshot_path)
        _quoted_cwd_file = shlex.quote(self._cwd_file)
        bootstrap = (
            f"export -p > {_quoted_snap}\n"
            f"declare -f | grep -vE '^_[^_]' >> {_quoted_snap}\n"
            f"alias -p >> {_quoted_snap}\n"
            f"echo 'shopt -s expand_aliases' >> {_quoted_snap}\n"
            f"echo 'set +e' >> {_quoted_snap}\n"
            f"echo 'set +u' >> {_quoted_snap}\n"
            f"builtin cd {_quoted_cwd} 2>/dev/null || true\n"
            f"pwd -P > {_quoted_cwd_file} 2>/dev/null || true\n"
            f"printf '\\n{self._cwd_marker}%s{self._cwd_marker}\\n' \"$(pwd -P)\"\n"
        )
        try:
            proc = self._run_bash(bootstrap, login=True, timeout=self._snapshot_timeout)
            result = _wait_for_process(proc, timeout=self._snapshot_timeout)
            self._snapshot_ready = True
            self._update_cwd(result)
        except Exception as exc:
            self._snapshot_ready = False

    # ------------------------------------------------------------------
    # Command wrapping
    # ------------------------------------------------------------------

    @staticmethod
    def _quote_cwd_for_cd(cwd: str) -> str:
        if cwd == "~":
            return cwd
        if cwd == "~/":
            return "$HOME"
        if cwd.startswith("~/"):
            return f"$HOME/{shlex.quote(cwd[2:])}"
        return shlex.quote(cwd)

    def _wrap_command(self, command: str, cwd: str) -> str:
        escaped = command.replace("'", "'\\''")
        _quoted_snap = shlex.quote(self._snapshot_path)
        _quoted_cwd_file = shlex.quote(self._cwd_file)
        parts = []
        if self._snapshot_ready:
            parts.append(f"source {_quoted_snap} >/dev/null 2>&1 || true")
        quoted_cwd = self._quote_cwd_for_cd(cwd)
        parts.append(f"builtin cd -- {quoted_cwd} || exit 126")
        parts.append(f"eval '{escaped}'")
        parts.append("__testai_ec=$?")
        if self._snapshot_ready:
            parts.append(f"export -p > {_quoted_snap} 2>/dev/null || true")
        parts.append(f"pwd -P > {_quoted_cwd_file} 2>/dev/null || true")
        parts.append(
            f"printf '\\n{self._cwd_marker}%s{self._cwd_marker}\\n' \"$(pwd -P)\""
        )
        parts.append("exit $__testai_ec")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # CWD extraction
    # ------------------------------------------------------------------

    def _update_cwd(self, result: dict):
        self._extract_cwd_from_output(result)

    def _extract_cwd_from_output(self, result: dict):
        output = result.get("output", "")
        marker = self._cwd_marker
        last = output.rfind(marker)
        if last == -1:
            return
        search_start = max(0, last - 4096)
        first = output.rfind(marker, search_start, last)
        if first == -1 or first == last:
            return
        cwd_path = output[first + len(marker): last].strip()
        if cwd_path:
            self.cwd = cwd_path
        line_start = output.rfind("\n", 0, first)
        if line_start == -1:
            line_start = first
        line_end = output.find("\n", last + len(marker))
        line_end = line_end + 1 if line_end != -1 else len(output)
        result["output"] = output[:line_start] + output[line_end:]

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def _before_execute(self) -> None:
        pass

    def _prepare_command(self, command: str) -> tuple[str, str | None]:
        """Transform sudo commands to use -S flag if a sudo password callback is set."""
        try:
            from .factory import get_sudo_password_callback
            cb = get_sudo_password_callback()
        except Exception:
            cb = None
        if cb is None:
            return command, None
        import re
        sudo_pw = cb()
        if not sudo_pw:
            return command, None
        if not re.search(r'(^|\s)sudo(\s|$)', command):
            return command, None
        transformed = re.sub(
            r'(^|\s)sudo(\s|$)',
            r'\1sudo -S -p \'\'\2',
            command,
        )
        return transformed, sudo_pw + "\n"

    # ------------------------------------------------------------------
    # Unified execute()
    # ------------------------------------------------------------------

    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> ExecResult:
        self._before_execute()
        exec_command, sudo_stdin = self._prepare_command(command)
        effective_timeout = timeout or self.timeout
        effective_cwd = cwd or self.cwd

        if sudo_stdin is not None and stdin_data is not None:
            effective_stdin = sudo_stdin + stdin_data
        elif sudo_stdin is not None:
            effective_stdin = sudo_stdin
        else:
            effective_stdin = stdin_data

        if effective_stdin and self._stdin_mode == "heredoc":
            exec_command = self._embed_stdin_heredoc(exec_command, effective_stdin)
            effective_stdin = None

        wrapped = self._wrap_command(exec_command, effective_cwd)
        login = not self._snapshot_ready
        start = time.monotonic()
        proc = self._run_bash(
            wrapped, login=login, timeout=effective_timeout, stdin_data=effective_stdin
        )
        result = _wait_for_process(proc, timeout=effective_timeout)
        self._update_cwd(result)
        return ExecResult(
            stdout=result.get("output", ""),
            stderr="",
            exit_code=result.get("returncode", 0) or 0,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    async def write_file(self, path: str, data: str) -> None:
        escaped = data.replace("'", "'\\''")
        cmd = (
            f"mkdir -p $(dirname '{path}') && cat > '{path}' << 'TESTAI_EOF'\n"
            f"{data}\n"
            f"TESTAI_EOF"
        )
        result = self.execute(cmd)
        if not result.success:
            raise RuntimeError(f"Failed to write {path}: {result.stdout}")

    async def read_file(self, path: str) -> str:
        result = self.execute(f"cat '{path}'")
        if not result.success:
            raise RuntimeError(f"Failed to read {path}: {result.stdout}")
        return result.stdout

    async def run(
        self, command: str, timeout: int = 60, cwd: str = "",
    ) -> subprocess.CompletedProcess:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.execute(command, cwd, timeout=timeout),
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    async def file_exists(self, path: str) -> bool:
        result = await self.run(f"test -f {shlex.quote(path)} && echo 'exists'", timeout=10)
        return result.stdout.strip() == "exists"

    def _embed_stdin_heredoc(self, command: str, stdin_data: str) -> str:
        delimiter = f"TESTAI_STDIN_{uuid.uuid4().hex[:12]}"
        return f"{command} << '{delimiter}'\n{stdin_data}\n{delimiter}"

    def _kill_process(self, proc: ProcessHandle) -> None:
        try:
            proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def stop(self) -> None:
        self.cleanup()

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass
