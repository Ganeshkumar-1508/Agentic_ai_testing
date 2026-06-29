from __future__ import annotations

import base64
import os
import shlex
import subprocess
from glob import glob
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

_deps_ref: dict = {}


def set_backend_factory(factory) -> None:
    _deps_ref["backend_factory"] = factory


def _backend_factory():
    return _deps_ref.get("backend_factory")


async def _create_backend(backend_factory, session_id):
    if not backend_factory or not session_id:
        return None
    try:
        return backend_factory(session_id)
    except Exception:
        return None


def _host_path(path: str) -> str:
    if not os.path.isabs(path):
        cwd = os.environ.get("PWD", os.environ.get("INIT_CWD", os.getcwd()))
        path = os.path.join(cwd, path)
    return os.path.normpath(path)


def _posix_norm(path: str) -> str:
    """Normalize a path using POSIX semantics regardless of host OS.

    `os.path.normpath` on Windows converts forward slashes to backslashes
    and resolves `..` differently, which breaks paths destined for a Linux
    sandbox container. Windows backslashes are treated as forward slashes
    so paths like `\\workspace\\foo.py` from a Windows host resolve to
    `/workspace/foo.py` inside the Linux container.
    """
    if not path:
        return "."
    normalized = path.replace("\\", "/")
    parts: list[str] = []
    is_abs = normalized.startswith("/")
    for seg in normalized.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not is_abs:
                parts.append("..")
        else:
            parts.append(seg)
    out = ("/" if is_abs else "") + "/".join(parts)
    return out or ("/" if is_abs else ".")


def _sandbox_path(path: str, workdir: str = "/workspace") -> str:
    if not path.startswith("/") and not path.startswith("\\"):
        path = f"{workdir.rstrip('/')}/{path}"
    return _posix_norm(path)


def _b64_write(path: str, content: str) -> str:
    """Render a `mkdir + base64 -d > file` shell snippet for writing content
    to `path` inside a sandbox container. base64 avoids every shell-escape
    pitfall (quotes, newlines, dollar signs, backticks, etc.)."""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return (
        f"mkdir -p $(dirname {shlex.quote(path)}) && "
        f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}"
    )


class ReadFileTool(BaseTool):
    name = "read_file"
    concurrency_safe = True
    default_level = "allow"
    concurrency_safe = True
    description = (
        "Read the contents of a file. Use to inspect source code, config files, "
        "logs, and documentation. When a sandbox is active, the file is read "
        "from inside the per-session container."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "max_length": {"type": "integer", "description": "Max characters to return (default 10000)", "default": 10000},
                    "offset": {"type": "integer", "description": "Line number to start from (1-indexed)", "default": 1},
                    "limit": {"type": "integer", "description": "Number of lines to read", "default": 100},
                },
                "required": ["path"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        max_length = int(kwargs.get("max_length", 10000))
        offset = int(kwargs.get("offset", 1))
        limit = int(kwargs.get("limit", 100))
        task_id = kwargs.get("_session_id", "")
        if not path:
            return ToolResult(success=False, output="No path provided", error="missing_path")

        # Record read for file state tracking (Hermes pattern)
        from harness.permissions.file_state import record_read
        partial = offset > 1 or limit < 10000
        record_read(task_id, path, partial=partial)

        backend = await _create_backend(_backend_factory(), kwargs.get("_session_id"))
        if backend is not None:
            return await self._run_sandbox(backend, path, max_length, offset, limit)
        return self._run_host(path, max_length, offset, limit)

    async def _run_sandbox(self, backend, path, max_length, offset, limit) -> ToolResult:
        full = _sandbox_path(path)
        exists = await backend.file_exists(full)
        if not exists:
            return ToolResult(success=False, output=f"File not found: {full}", error="not_found")

        end_line = offset + limit - 1
        sed = await backend.run(
            f"sed -n '{offset},{end_line}p' {shlex.quote(full)}",
            timeout=10,
        )
        if sed.returncode != 0:
            return ToolResult(success=False, output=f"Failed to read: {sed.stderr}", error=str(sed.returncode))

        nl = await backend.run(
            f"printf '%s' {shlex.quote(sed.stdout)} | nl -ba -v {offset}",
            timeout=10,
        )
        numbered = nl.stdout
        if len(numbered) > max_length:
            numbered = numbered[:max_length] + "\n... [truncated]"

        wc = await backend.run(f"wc -l < {shlex.quote(full)}", timeout=10)
        try:
            total = int(wc.stdout.strip() or "0")
        except ValueError:
            total = 0
        end = min(total, end_line)
        output = f"--- {full} ({total} lines, showing {offset}-{end}) ---\n{numbered}"
        if end < total:
            output += f"\n... ({total - end} more lines)"
        return ToolResult(
            success=True, output=output,
            data={"path": full, "total_lines": total, "returned_lines": max(0, end - offset + 1)},
        )

    def _run_host(self, path, max_length, offset, limit) -> ToolResult:
        full = _host_path(path)
        if not os.path.exists(full):
            return ToolResult(success=False, output=f"File not found: {full}", error="not_found")
        if not os.path.isfile(full):
            return ToolResult(success=False, output=f"Not a file: {full}", error="not_a_file")
        try:
            with open(full, "r", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            start = max(0, offset - 1)
            end = min(total, start + limit)
            selected = lines[start:end]
            content = "".join(selected)
            if len(content) > max_length:
                content = content[:max_length] + "\n... [truncated]"
            numbered = "".join(f"{i+1}: {l}" for i, l in enumerate(selected, start=start + 1))
            output = f"--- {full} ({total} lines, showing {start+1}-{end}) ---\n{numbered}"
            if end < total:
                output += f"\n... ({total - end} more lines)"
            return ToolResult(
                success=True, output=self._redact(output),
                data={"path": full, "total_lines": total, "returned_lines": len(selected)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to read: {e}", error=str(e))

    def _redact(self, text: str) -> str:
        from harness.tools.credential_scanner import redact_credentials
        return redact_credentials(text)


class WriteFileTool(BaseTool):
    name = "write_file"
    default_level = "allow"
    description = (
        "Write content to a file, creating parent directories as needed. "
        "When a sandbox is active, the file is written inside the per-session "
        "container and persists on the host via the bind-mounted workspace."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        task_id = kwargs.get("_session_id", "")
        if not path:
            return ToolResult(success=False, output="No path provided", error="missing_path")

        # Check for stale write (Hermes pattern)
        from harness.permissions.file_state import check_stale, note_write
        stale_warning = check_stale(task_id, path)
        if stale_warning:
            # Log warning but don't block — agent decides
            logger.warning("Stale write detected: %s", stale_warning)

        backend = await _create_backend(_backend_factory(), kwargs.get("_session_id"))
        if backend is not None:
            result = await self._run_sandbox(backend, path, content)
        else:
            result = self._run_host(path, content)

        if result.success:
            note_write(task_id, path)

        return result

    async def _run_sandbox(self, backend, path, content) -> ToolResult:
        full = _sandbox_path(path)
        result = await backend.run(_b64_write(full, content), timeout=30)
        if result.returncode != 0:
            return ToolResult(success=False, output=f"Failed to write: {result.stderr}", error=str(result.returncode))
        return ToolResult(
            success=True, output=f"Wrote {len(content)} bytes to {full}",
            data={"path": full, "bytes": len(content)},
        )

    def _run_host(self, path, content) -> ToolResult:
        full = _host_path(path)
        try:
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(
                success=True, output=f"Wrote {len(content)} bytes to {full}",
                data={"path": full, "bytes": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to write: {e}", error=str(e))


class EditFileTool(BaseTool):
    name = "edit_file"
    default_level = "allow"
    description = (
        "Find and replace text in a file. The old_text must match exactly once. "
        "When a sandbox is active, the file is edited inside the per-session "
        "container."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "old_text": {"type": "string", "description": "Exact text to find (must be unique in file)"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        old_text = kwargs.get("old_text", "")
        new_text = kwargs.get("new_text", "")
        task_id = kwargs.get("_session_id", "")
        if not path:
            return ToolResult(success=False, output="No path provided", error="missing_path")
        if not old_text:
            return ToolResult(success=False, output="No old_text provided", error="missing_old_text")

        # Check for stale edit (Hermes pattern)
        from harness.permissions.file_state import check_stale, note_write
        stale_warning = check_stale(task_id, path)
        if stale_warning:
            logger.warning("Stale edit detected: %s", stale_warning)

        backend = await _create_backend(_backend_factory(), kwargs.get("_session_id"))
        if backend is not None:
            result = await self._run_sandbox(backend, path, old_text, new_text)
        else:
            result = self._run_host(path, old_text, new_text)

        if result.success:
            note_write(task_id, path)

        return result

    async def _run_sandbox(self, backend, path, old_text, new_text) -> ToolResult:
        full = _sandbox_path(path)
        if not await backend.file_exists(full):
            return ToolResult(success=False, output=f"File not found: {full}", error="not_found")
        read = await backend.read_file(full)
        occurrences = read.count(old_text)
        if occurrences == 0:
            return ToolResult(success=False, output=f"old_text not found in {full}", error="not_found")
        if occurrences > 1:
            return ToolResult(
                success=False,
                output=f"old_text matches {occurrences} locations (must be unique). Add more context.",
                error="ambiguous_match",
            )
        new_content = read.replace(old_text, new_text, 1)
        result = await backend.run(_b64_write(full, new_content), timeout=30)
        if result.returncode != 0:
            return ToolResult(success=False, output=f"Failed to write: {result.stderr}", error=str(result.returncode))
        return ToolResult(success=True, output=f"Edited {full}", data={"path": full, "occurrences": 1})

    def _run_host(self, path, old_text, new_text) -> ToolResult:
        full = _host_path(path)
        if not os.path.exists(full):
            return ToolResult(success=False, output=f"File not found: {full}", error="not_found")
        try:
            with open(full, "r", encoding="utf-8") as f:
                content = f.read()
            occurrences = content.count(old_text)
            if occurrences == 0:
                return ToolResult(success=False, output=f"old_text not found in {full}", error="not_found")
            if occurrences > 1:
                return ToolResult(
                    success=False,
                    output=f"old_text matches {occurrences} locations (must be unique). Add more context.",
                    error="ambiguous_match",
                )
            new_content = content.replace(old_text, new_text, 1)
            with open(full, "w", encoding="utf-8") as f:
                f.write(new_content)
            return ToolResult(success=True, output=f"Edited {full}", data={"path": full, "occurrences": 1})
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to edit: {e}", error=str(e))


class ListFilesTool(BaseTool):
    name = "list_files"
    concurrency_safe = True
    default_level = "allow"
    description = (
        "List files and directories under a path. Use to explore the workspace. "
        "When a sandbox is active, the listing is from inside the per-session "
        "container."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path (default: workspace root)", "default": "."},
                    "pattern": {"type": "string", "description": "Optional glob pattern to filter (e.g. '*.py')"},
                    "max_depth": {"type": "integer", "description": "Max directory depth (default 3, max 10)", "default": 3},
                },
                "required": [],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "")
        max_depth = min(int(kwargs.get("max_depth", 3)), 10)

        backend = await _create_backend(_backend_factory(), kwargs.get("_session_id"))
        if backend is not None:
            return await self._run_sandbox(backend, path, pattern, max_depth)
        return self._run_host(path, pattern, max_depth)

    async def _run_sandbox(self, backend, path, pattern, max_depth) -> ToolResult:
        full = _sandbox_path(path)
        if pattern:
            cmd = (
                f"find {shlex.quote(full)} -maxdepth {max_depth} "
                f"-name {shlex.quote(pattern)} -print"
            )
        else:
            cmd = f"find {shlex.quote(full)} -maxdepth {max_depth} -print"
        result = await backend.run(cmd, timeout=30)
        if result.returncode != 0 and "No such file" in result.stderr:
            return ToolResult(success=False, output=f"Path not found: {full}", error="not_found")
        if result.returncode != 0:
            return ToolResult(success=False, output=f"Failed to list: {result.stderr}", error=str(result.returncode))
        files = [f for f in (result.stdout or "").splitlines() if f and f != full]
        return ToolResult(
            success=True, output="\n".join(files),
            data={"path": full, "count": len(files), "files": files[:100]},
        )

    def _run_host(self, path, pattern, max_depth) -> ToolResult:
        full = _host_path(path)
        if not os.path.exists(full):
            return ToolResult(success=False, output=f"Path not found: {full}", error="not_found")
        files: list[str] = []
        if pattern:
            files = sorted(glob(os.path.join(full, "**", pattern), recursive=True))[:100]
        else:
            base_depth = full.rstrip(os.sep).count(os.sep)
            for root, dirs, filenames in os.walk(full):
                depth = root.count(os.sep) - base_depth
                if depth >= max_depth:
                    dirs.clear()
                    continue
                for fname in filenames:
                    files.append(os.path.join(root, fname))
                if len(files) >= 100:
                    break
        return ToolResult(
            success=True, output="\n".join(files),
            data={"path": full, "count": len(files), "files": files[:100]},
        )


class BashTool(BaseTool):
    name = "bash"
    default_level = "allow"
    description = (
        "Execute a shell command. Use to run git commands, install packages, "
        "run tests, inspect the environment, or run developer tools. When a "
        "sandbox is active, the command runs inside the per-session container "
        "with the host workspace bind-mounted at /workspace."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 120)", "default": 30},
                },
                "required": ["command"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = min(int(kwargs.get("timeout", 30)), 120)
        if not command:
            return ToolResult(success=False, output="No command provided", error="missing_command")

        # Pre-execution security check
        from harness.tools.credential_scanner import check_command_safety
        block_reason = check_command_safety(command)
        if block_reason:
            return ToolResult(success=False, output=block_reason, error="blocked_by_security")

        backend = await _create_backend(_backend_factory(), kwargs.get("_session_id"))
        if backend is not None:
            result = await self._run_sandbox(backend, command, timeout)
        else:
            result = self._run_host(command, timeout)

        from harness.tools.credential_scanner import redact_credentials
        result.output = redact_credentials(result.output)

        return result

    async def _run_sandbox(self, backend, command, timeout) -> ToolResult:
        result = await backend.run(command, timeout=timeout)
        output = (result.stdout or "") + (result.stderr or "")
        if len(output) > 10000:
            output = output[:10000] + "\n... [truncated]"
        return ToolResult(
            success=result.returncode == 0,
            output=output or "(no output)",
            data={"returncode": result.returncode},
        )

    def _run_host(self, command, timeout) -> ToolResult:
        shell = os.environ.get("SHELL", "bash") if os.name != "nt" else os.environ.get("ComSpec", "cmd.exe")
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, executable=shell if os.name == "posix" else None,
            )
            output = result.stdout + result.stderr
            if len(output) > 10000:
                output = output[:10000] + "\n... [truncated]"
            return ToolResult(
                success=result.returncode == 0,
                output=output or "(no output)",
                data={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output=f"Command timed out ({timeout}s)", error="timeout")
        except Exception as e:
            return ToolResult(success=False, output=str(e), error=str(e))


registry.register(ReadFileTool(), toolset="read")
registry.register(WriteFileTool(), toolset="write")
registry.register(EditFileTool(), toolset="write")
registry.register(ListFilesTool(), toolset="read")
registry.register(BashTool(), toolset="write")
