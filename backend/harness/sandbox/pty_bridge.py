"""PTY bridge for sandbox terminal streaming.

Wraps docker exec behind a pseudo-terminal so ANSI output can be
streamed to a browser-side terminal emulator (xterm.js) and typed
keystrokes can be fed back in.

Adapted from hermes-agent pty_bridge.py (MIT License).

Design:
  - PtyBridge wraps ptyprocess.PtyProcess for byte streaming
  - Spawns `docker exec -it container_id sh` as the PTY process
  - WebSocket handler reads PTY output → sends to client
  - Client keystrokes → WebSocket → written to PTY stdin

POSIX-only: depends on fcntl, termios, ptyprocess.
On Windows, falls back to SSE-based streaming (no interactive input).
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import logging
import os
import select
import signal
import struct
import sys
import termios
import time
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

try:
    import ptyprocess
    _PTY_AVAILABLE = not sys.platform.startswith("win")
except ImportError:
    ptyprocess = None
    _PTY_AVAILABLE = False

_MIN_DIMENSION = 1
_MAX_COLS = 2000
_MAX_ROWS = 1000


def _clamp_dimension(value: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return _MIN_DIMENSION
    return max(_MIN_DIMENSION, min(n, maximum))


class PtyUnavailableError(RuntimeError):
    pass


class PtyBridge:
    """Thin wrapper around ptyprocess for docker exec PTY streaming.

    Spawns `docker exec -it container_id sh` behind a PTY so ANSI
    output streams to the browser and keystrokes feed back in.
    """

    def __init__(self, proc: "ptyprocess.PtyProcess"):
        self._proc = proc
        self._fd: int = proc.fd
        self._closed = False

    @classmethod
    def is_available(cls) -> bool:
        return bool(_PTY_AVAILABLE)

    @classmethod
    def spawn(
        cls,
        container_id: str,
        *,
        command: str = "sh",
        cols: int = 80,
        rows: int = 24,
    ) -> "PtyBridge":
        """Spawn docker exec -it behind a new PTY."""
        if not _PTY_AVAILABLE:
            if sys.platform.startswith("win"):
                raise PtyUnavailableError(
                    "PTY unavailable on Windows. Use WSL or SSE fallback."
                )
            raise PtyUnavailableError(
                "ptyprocess package missing. Install: pip install ptyprocess"
            )

        spawn_env = os.environ.copy()
        if not spawn_env.get("TERM"):
            spawn_env["TERM"] = "xterm-256color"

        argv = ["docker", "exec", "-it", container_id, command]
        proc = ptyprocess.PtyProcess.spawn(
            argv,
            env=spawn_env,
            dimensions=(rows, cols),
        )
        return cls(proc)

    @property
    def pid(self) -> int:
        return int(self._proc.pid)

    def is_alive(self) -> bool:
        if self._closed:
            return False
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def read(self, timeout: float = 0.2) -> Optional[bytes]:
        """Read up to 64KiB from PTY master. Returns bytes, empty bytes, or None (EOF)."""
        if self._closed:
            return None
        try:
            readable, _, _ = select.select([self._fd], [], [], timeout)
        except (OSError, ValueError):
            return None
        if not readable:
            return b""
        try:
            data = os.read(self._fd, 65536)
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                return None
            raise
        return data if data else None

    def write(self, data: bytes) -> None:
        """Write raw bytes to PTY master (child's stdin)."""
        if self._closed or not data:
            return
        view = memoryview(data)
        while view:
            try:
                n = os.write(self._fd, view)
            except OSError as exc:
                if exc.errno in {errno.EIO, errno.EBADF, errno.EPIPE}:
                    return
                raise
            if n <= 0:
                return
            view = view[n:]

    def resize(self, cols: int, rows: int) -> None:
        """Forward terminal resize via TIOCSWINSZ."""
        if self._closed:
            return
        cols = _clamp_dimension(cols, _MAX_COLS)
        rows = _clamp_dimension(rows, _MAX_ROWS)
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def close(self) -> None:
        """Terminate child and close fds. Idempotent."""
        if self._closed:
            return
        self._closed = True

        try:
            pgid = os.getpgid(self._proc.pid)
        except Exception:
            pgid = None

        for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL):
            if not self._proc.isalive():
                break
            try:
                if pgid is not None:
                    os.killpg(pgid, sig)
                else:
                    self._proc.kill(sig)
            except Exception:
                pass
            deadline = time.monotonic() + 0.5
            while self._proc.isalive() and time.monotonic() < deadline:
                time.sleep(0.02)

        try:
            self._proc.close(force=True)
        except Exception:
            pass

    def __enter__(self) -> "PtyBridge":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
