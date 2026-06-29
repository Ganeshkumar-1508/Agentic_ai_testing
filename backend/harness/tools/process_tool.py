"""Process tool — manage background command lifecycle.

Ported from Hermes (Nous Research, MIT License).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


@dataclass
class ProcessSession:
    id: str
    proc: subprocess.Popen
    created_at: float
    stdout_chunks: list[str]
    lock: threading.Lock
    finished: bool = False
    returncode: int | None = None


_processes: dict[str, ProcessSession] = {}
_processes_lock = threading.Lock()


def _spawn(command: str, *, cwd: str = "", env: dict | None = None) -> ProcessSession:
    """Spawn a background process. Returns a ProcessSession immediately."""
    session_id = f"proc_{uuid.uuid4().hex[:12]}"
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd or os.getcwd(),
        env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    session = ProcessSession(
        id=session_id,
        proc=proc,
        created_at=time.time(),
        stdout_chunks=[],
        lock=threading.Lock(),
    )

    def _reader():
        for line in iter(proc.stdout.readline, ""):
            with session.lock:
                session.stdout_chunks.append(line)
        proc.wait()
        with session.lock:
            session.finished = True
            session.returncode = proc.returncode

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    with _processes_lock:
        _processes[session_id] = session
    return session


def _get(session_id: str) -> ProcessSession | None:
    with _processes_lock:
        return _processes.get(session_id)


def _poll(session_id: str) -> dict:
    session = _get(session_id)
    if session is None:
        return {"status": "not_found", "error": f"No process {session_id}"}
    with session.lock:
        return {
            "status": "completed" if session.finished else "running",
            "running": not session.finished,
            "returncode": session.returncode,
            "uptime_seconds": int(time.time() - session.created_at),
        }


def _read_log(session_id: str, tail: int = 0) -> dict:
    session = _get(session_id)
    if session is None:
        return {"status": "not_found", "error": f"No process {session_id}"}
    with session.lock:
        output = "".join(session.stdout_chunks)
    if tail > 0:
        lines = output.splitlines()
        output = "\n".join(lines[-tail:])
    return {"output": output, "bytes": len(output)}


def _wait(session_id: str, timeout: float = 0) -> dict:
    session = _get(session_id)
    if session is None:
        return {"status": "not_found", "error": f"No process {session_id}"}
    try:
        session.proc.wait(timeout=timeout if timeout > 0 else None)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "running": True}
    with session.lock:
        session.finished = True
        session.returncode = session.proc.returncode
    return {"status": "completed", "returncode": session.proc.returncode}


def _kill(session_id: str) -> dict:
    session = _get(session_id)
    if session is None:
        return {"status": "not_found", "error": f"No process {session_id}"}
    if os.name == "nt":
        session.proc.terminate()
    else:
        try:
            pgid = os.getpgid(session.proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    with session.lock:
        session.finished = True
        session.returncode = session.proc.returncode
    return {"status": "killed", "returncode": session.proc.returncode}


def _write_stdin(session_id: str, data: str) -> dict:
    session = _get(session_id)
    if session is None:
        return {"status": "not_found", "error": f"No process {session_id}"}
    try:
        session.proc.stdin.write(data)
        session.proc.stdin.flush()
        return {"status": "ok", "bytes": len(data)}
    except (BrokenPipeError, OSError) as e:
        return {"status": "error", "error": str(e)}


def _list() -> dict:
    with _processes_lock:
        return {
            "count": len(_processes),
            "processes": [
                {
                    "id": sid,
                    "running": not s.finished,
                    "uptime_seconds": int(time.time() - s.created_at),
                    "returncode": s.returncode,
                }
                for sid, s in _processes.items()
            ],
        }


def _kill_all() -> int:
    count = 0
    with _processes_lock:
        ids = list(_processes.keys())
    for sid in ids:
        _kill(sid)
        count += 1
    return count


class ProcessTool(BaseTool):
    name = "process"
    default_level = "allow"
    description = (
        "Manage background processes started via `bash` with `&` or the `process` tool. "
        "Actions: spawn, poll, wait, log, kill, list, write_stdin. "
        "Uses shell=True for compatibility. For long-running servers or watchers, "
        "spawn in background then poll for readiness."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["spawn", "poll", "wait", "log", "kill", "list", "write_stdin", "kill_all"],
                        "description": "Action to perform",
                    },
                    "command": {
                        "type": "string",
                        "description": "Command to spawn (required for spawn action)",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Process session ID (required for poll, wait, log, kill, write_stdin)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Wait timeout in seconds (for wait action, 0 = no timeout)",
                        "default": 0,
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Show only last N lines of output (for log action, 0 = all)",
                        "default": 0,
                    },
                    "data": {
                        "type": "string",
                        "description": "Data to write to stdin (for write_stdin action)",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (for spawn action)",
                    },
                },
                "required": ["action"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        if action == "spawn":
            command = kwargs.get("command", "")
            if not command:
                return ToolResult(success=False, output="`command` is required for spawn", error="missing_arg")
            session = _spawn(command, cwd=kwargs.get("cwd", ""))
            return ToolResult(
                success=True,
                output=f"Spawned process {session.id} (pid={session.proc.pid})",
                data={"session_id": session.id, "pid": session.proc.pid},
            )
        elif action == "poll":
            sid = kwargs.get("session_id", "")
            result = _poll(sid)
            ok = result.get("status") != "not_found"
            return ToolResult(success=ok, output=str(result), data=result)
        elif action == "wait":
            sid = kwargs.get("session_id", "")
            timeout = int(kwargs.get("timeout", 0))
            result = _wait(sid, timeout)
            ok = result.get("status") != "not_found"
            return ToolResult(success=ok, output=str(result), data=result)
        elif action == "log":
            sid = kwargs.get("session_id", "")
            tail = int(kwargs.get("tail", 0))
            result = _read_log(sid, tail)
            ok = result.get("status") != "not_found"
            return ToolResult(success=ok, output=result.get("output", ""), data=result)
        elif action == "kill":
            sid = kwargs.get("session_id", "")
            result = _kill(sid)
            ok = result.get("status") != "not_found"
            return ToolResult(success=ok, output=str(result), data=result)
        elif action == "write_stdin":
            sid = kwargs.get("session_id", "")
            data = kwargs.get("data", "")
            result = _write_stdin(sid, data)
            return ToolResult(success=result.get("status") == "ok", output=str(result), data=result)
        elif action == "list":
            result = _list()
            return ToolResult(success=True, output=str(result), data=result)
        elif action == "kill_all":
            count = _kill_all()
            return ToolResult(success=True, output=f"Killed {count} process(es)", data={"killed": count})
        return ToolResult(success=False, output=f"Unknown action: {action}", error="invalid_action")


registry.register(ProcessTool(), toolset="read")
