"""Process Registry — In-memory registry for managed background processes.

Tracks processes spawned via background mode, providing:
  - Output buffering (rolling 200KB window)
  - Status polling and log retrieval
  - Blocking wait with interrupt support
  - Process killing
  - Crash recovery via JSON checkpoint file

Adapted from: reference/hermes-agent/tools/process_registry.py (Apache 2.0)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Limits
MAX_OUTPUT_CHARS = 200_000      # 200KB rolling output buffer
FINISHED_TTL_SECONDS = 1800     # Keep finished processes for 30 minutes
MAX_PROCESSES = 64              # Max concurrent tracked processes


@dataclass
class ProcessSession:
    """Represents a managed background process."""
    id: str
    command: str
    task_id: str = ""
    status: str = "pending"  # pending, running, completed, failed, killed
    started_at: float = 0.0
    finished_at: float = 0.0
    exit_code: int = 0
    output: str = ""
    error: str = ""
    _process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_output(self, last_n: int = 100) -> str:
        """Get last N lines of output."""
        lines = self.output.split("\n")
        return "\n".join(lines[-last_n:])

    def to_dict(self) -> dict:
        """Serialize for checkpoint."""
        return {
            "id": self.id,
            "command": self.command,
            "task_id": self.task_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "output": self.output[-MAX_OUTPUT_CHARS:],  # Truncate
            "error": self.error,
        }


class ProcessRegistry:
    """In-memory registry for managed background processes.

    Usage:
        registry = ProcessRegistry()
        session = registry.spawn("pytest -v", task_id="task_123")
        result = registry.poll(session.id)
        registry.kill(session.id)
    """

    def __init__(self, checkpoint_path: Optional[str] = None):
        self._processes: Dict[str, ProcessSession] = {}
        self._checkpoint_path = checkpoint_path
        self._lock = threading.Lock()

        # Load checkpoint if exists
        if checkpoint_path and os.path.exists(checkpoint_path):
            self._load_checkpoint()

    def spawn(
        self,
        command: str,
        task_id: str = "",
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> ProcessSession:
        """Spawn a background process with tracking."""
        with self._lock:
            # Enforce max processes
            if len(self._processes) >= MAX_PROCESSES:
                self._prune_finished()

            session = ProcessSession(
                id=str(uuid.uuid4())[:12],
                command=command,
                task_id=task_id,
                status="running",
                started_at=time.time(),
            )

            try:
                # Start process
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=cwd,
                    env=env,
                )
                session._process = proc
                self._processes[session.id] = session
                self._save_checkpoint()

                # Start output reader thread
                threading.Thread(
                    target=self._read_output,
                    args=(session,),
                    daemon=True,
                ).start()

                logger.info("Spawned process %s: %s", session.id, command[:100])
                return session

            except Exception as e:
                session.status = "failed"
                session.error = str(e)
                session.finished_at = time.time()
                logger.warning("Failed to spawn process: %s", e)
                return session

    def _read_output(self, session: ProcessSession) -> None:
        """Read output from process in background thread."""
        try:
            proc = session._process
            if not proc or not proc.stdout:
                return

            for line in proc.stdout:
                with session._lock:
                    session.output += line
                    # Keep rolling window
                    if len(session.output) > MAX_OUTPUT_CHARS:
                        session.output = session.output[-MAX_OUTPUT_CHARS:]

            proc.wait()
            session.exit_code = proc.returncode or 0
            session.status = "completed" if session.exit_code == 0 else "failed"
            session.finished_at = time.time()
            self._save_checkpoint()

        except Exception as e:
            session.status = "failed"
            session.error = str(e)
            session.finished_at = time.time()
            logger.warning("Process output reader failed: %s", e)

    def poll(self, session_id: str) -> Optional[dict]:
        """Get process status."""
        with self._lock:
            session = self._processes.get(session_id)
            if not session:
                return None
            return {
                "id": session.id,
                "status": session.status,
                "exit_code": session.exit_code,
                "output_preview": session.get_output(20),
                "uptime": time.time() - session.started_at if session.started_at else 0,
            }

    def wait(self, session_id: str, timeout: float = 300) -> Optional[dict]:
        """Block until process completes or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            result = self.poll(session_id)
            if not result:
                return None
            if result["status"] in ("completed", "failed", "killed"):
                return result
            time.sleep(0.5)
        return {"status": "timeout", "id": session_id}

    def kill(self, session_id: str) -> bool:
        """Kill a running process."""
        with self._lock:
            session = self._processes.get(session_id)
            if not session:
                return False
            if session._process:
                try:
                    session._process.kill()
                    session.status = "killed"
                    session.finished_at = time.time()
                    self._save_checkpoint()
                    logger.info("Killed process %s", session_id)
                    return True
                except Exception as e:
                    logger.warning("Failed to kill process %s: %s", session_id, e)
            return False

    def list_active(self) -> List[dict]:
        """List all active processes."""
        with self._lock:
            return [
                {
                    "id": s.id,
                    "command": s.command[:100],
                    "status": s.status,
                    "task_id": s.task_id,
                    "uptime": time.time() - s.started_at if s.started_at else 0,
                }
                for s in self._processes.values()
                if s.status in ("running", "pending")
            ]

    def cleanup_finished(self) -> int:
        """Remove finished processes older than TTL. Returns count removed."""
        cutoff = time.time() - FINISHED_TTL_SECONDS
        removed = 0
        with self._lock:
            to_remove = [
                sid for sid, s in self._processes.items()
                if s.status in ("completed", "failed", "killed")
                and s.finished_at < cutoff
            ]
            for sid in to_remove:
                del self._processes[sid]
                removed += 1
            if removed:
                self._save_checkpoint()
        return removed

    def _prune_finished(self) -> None:
        """Remove oldest finished processes to make room."""
        finished = [
            (sid, s) for sid, s in self._processes.items()
            if s.status in ("completed", "failed", "killed")
        ]
        finished.sort(key=lambda x: x[1].finished_at)
        to_remove = len(finished) - (MAX_PROCESSES // 2)
        for sid, _ in finished[:to_remove]:
            del self._processes[sid]

    def _save_checkpoint(self) -> None:
        """Save state to JSON for crash recovery."""
        if not self._checkpoint_path:
            return
        try:
            state = {sid: s.to_dict() for sid, s in self._processes.items()}
            with open(self._checkpoint_path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.debug("Failed to save checkpoint: %s", e)

    def _load_checkpoint(self) -> None:
        """Load state from JSON checkpoint."""
        try:
            with open(self._checkpoint_path, 'r') as f:
                state = json.load(f)
            for sid, data in state.items():
                session = ProcessSession(
                    id=data["id"],
                    command=data["command"],
                    task_id=data.get("task_id", ""),
                    status="failed",  # Assume crashed processes failed
                    started_at=data.get("started_at", 0),
                    finished_at=data.get("finished_at", 0),
                    exit_code=data.get("exit_code", 0),
                    output=data.get("output", ""),
                    error=data.get("error", "crashed"),
                )
                self._processes[sid] = session
            logger.info("Loaded %d processes from checkpoint", len(state))
        except Exception as e:
            logger.warning("Failed to load checkpoint: %s", e)


# Module-level singleton
_process_registry: Optional[ProcessRegistry] = None


def get_process_registry() -> ProcessRegistry:
    """Get or create the global process registry."""
    global _process_registry
    if _process_registry is None:
        checkpoint_path = os.path.expanduser("~/.testai/processes.json")
        _process_registry = ProcessRegistry(checkpoint_path)
    return _process_registry
