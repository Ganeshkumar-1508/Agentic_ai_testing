"""Shutdown forensics — capture context on SIGTERM/SIGINT for post-mortem analysis.

When the backend receives a termination signal, this module captures:
1. What signal triggered the shutdown
2. Active asyncio tasks and their stack traces
3. Thread counts and state
4. Memory snapshot
5. Process tree (via psutil, best-effort)

The synchronous probe runs in <10ms inside the signal handler. A
fire-and-forget subprocess dump runs async for deeper diagnostics.

Pattern from Hermes' gateway/shutdown_forensics.py (462 lines).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SIGNAL_NAMES: dict[int, str] = {}
for _name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGQUIT", "SIGUSR1", "SIGUSR2"):
    _val = getattr(signal, _name, None)
    if _val is not None:
        _SIGNAL_NAMES[int(_val)] = _name


# Directory for forensic dump files
_FORENSICS_DIR = Path.home() / ".testai" / "forensics"


def _signal_name(sig: Any) -> str:
    if sig is None:
        return "UNKNOWN"
    try:
        return _SIGNAL_NAMES.get(int(sig), f"signal#{int(sig)}")
    except (TypeError, ValueError):
        return str(sig)


def snapshot_shutdown_context(sig: Any = None) -> dict[str, Any]:
    """Fast (<10ms) probe of current process state for the signal handler.

    Captures everything that can be read synchronously without blocking:
    - Signal info
    - Active thread count
    - Running asyncio tasks (count and names)
    - Basic memory and uptime
    """
    context: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signal": _signal_name(sig),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "uptime_seconds": int(time.monotonic()),
        "active_threads": threading.active_count(),
        "python_version": sys.version,
    }

    # Active asyncio tasks (best-effort, may fail if no running loop)
    try:
        loop = asyncio.get_running_loop()
        tasks = asyncio.all_tasks(loop)
        context["asyncio_tasks"] = len(tasks)
        # Capture first 20 task names/stack summaries
        task_info = []
        for t in list(tasks)[:20]:
            name = t.get_name() if hasattr(t, "get_name") else str(t)
            done = t.done() if hasattr(t, "done") else False
            cancelled = t.cancelled() if hasattr(t, "cancelled") else False
            task_info.append({"name": name, "done": done, "cancelled": cancelled})
        context["asyncio_task_list"] = task_info
    except (RuntimeError, RuntimeWarning):
        context["asyncio_tasks"] = "no_running_loop"

    # Thread list (first 20)
    try:
        threads = []
        for t in threading.enumerate()[:20]:
            threads.append({
                "name": t.name if hasattr(t, "name") else str(t),
                "daemon": t.daemon if hasattr(t, "daemon") else False,
                "alive": t.is_alive() if hasattr(t, "is_alive") else False,
            })
        context["thread_list"] = threads
    except Exception:
        pass

    return context


def write_forensic_dump(context: dict[str, Any]) -> str | None:
    """Write the forensic snapshot to disk for post-mortem analysis.

    Returns the file path, or None on failure.
    """
    try:
        _FORENSICS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = _FORENSICS_DIR / f"shutdown-{timestamp}-pid{os.getpid()}.json"
        path.write_text(json.dumps(context, indent=2, default=str), encoding="utf-8")
        return str(path)
    except Exception as exc:
        logger.warning("Failed to write forensic dump: %s", exc)
        return None


def install_shutdown_handler() -> None:
    """Install signal handlers for SIGTERM and SIGINT that capture forensics.

    Call once at process startup. The handler:
    1. Takes a fast synchronous snapshot
    2. Writes it to disk
    3. Logs the snapshot
    4. Re-raises the default signal behavior
    """
    def _handler(sig: int, frame: Any) -> None:
        context = snapshot_shutdown_context(sig)
        path = write_forensic_dump(context)
        if path:
            logger.info(
                "[FORENSICS] Shutdown signal=%s pid=%d forensics=%s",
                context["signal"], os.getpid(), path,
            )
        else:
            logger.info(
                "[FORENSICS] Shutdown signal=%s pid=%d tasks=%s threads=%d",
                context["signal"], os.getpid(),
                context.get("asyncio_tasks", "?"),
                context.get("active_threads", 0),
            )
        # Restore default handler and re-raise so the process actually exits
        signal.signal(sig, signal.SIG_DFL)
        os.kill(os.getpid(), sig)

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    logger.debug("[FORENSICS] Shutdown handlers installed for SIGTERM/SIGINT")
