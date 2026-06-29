"""Periodic process memory monitoring for the web backend.

Pattern from Hermes gateway/memory_monitor.py (which ports from cline#10343).
Emits structured memory stats every N minutes so operators can track RSS
over time and detect slow leaks.

Runs as a background daemon thread. Logs a single grep-friendly line:
  [MEMORY] rss=123.4MB gc_obj=45678 gc_col0=123 gc_col1=45 gc_col2=67 uptime=12345s
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_MONITOR_THREAD: threading.Thread | None = None
_STOP_EVENT: threading.Event | None = None
_START_TIME: float = 0.0
_INTERVAL: float = 300.0  # 5 minutes
_BYTES_TO_MB = 1024 * 1024


def _get_rss_mb() -> float:
    """Get current RSS in MB. Uses /proc/self/status on Linux, psutil fallback."""
    try:
        # Linux: /proc/self/status
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except (FileNotFoundError, IOError, ValueError, IndexError):
        pass
    try:
        import psutil
        proc = psutil.Process()
        return proc.memory_info().rss / _BYTES_TO_MB
    except ImportError:
        return 0.0


def _collect_stats() -> dict[str, Any]:
    """Collect current memory and GC stats."""
    gc.collect()
    stats = gc.get_stats()
    return {
        "rss_mb": round(_get_rss_mb(), 1),
        "gc_objects": len(gc.get_objects()),
        "gc_col0": stats[0].get("collections", 0) if len(stats) > 0 else 0,
        "gc_col1": stats[1].get("collections", 0) if len(stats) > 1 else 0,
        "gc_col2": stats[2].get("collections", 0) if len(stats) > 2 else 0,
        "uptime_s": int(time.time() - _START_TIME),
    }


def _log_snapshot() -> None:
    stats = _collect_stats()
    logger.info(
        "[MEMORY] rss=%(rss_mb)sMB gc_obj=%(gc_objects)d "
        "gc_col0=%(gc_col0)d gc_col1=%(gc_col1)d gc_col2=%(gc_col2)d "
        "uptime=%(uptime_s)ds",
        stats,
    )


def _run() -> None:
    global _STOP_EVENT
    _log_snapshot()  # Baseline immediately
    while _STOP_EVENT is not None and not _STOP_EVENT.is_set():
        if _STOP_EVENT.wait(_INTERVAL):
            break
        try:
            _log_snapshot()
        except Exception:
            logger.debug("[MEMORY] snapshot failed", exc_info=True)
    # Final snapshot on shutdown
    try:
        _log_snapshot()
    except Exception:
        pass


def start(interval_seconds: int = 300) -> None:
    """Start the memory monitor in a background daemon thread."""
    global _MONITOR_THREAD, _STOP_EVENT, _START_TIME, _INTERVAL
    if _MONITOR_THREAD is not None and _MONITOR_THREAD.is_alive():
        return  # Already running
    _INTERVAL = max(60, interval_seconds)
    _START_TIME = time.time()
    _STOP_EVENT = threading.Event()
    _MONITOR_THREAD = threading.Thread(target=_run, daemon=True, name="memory-monitor")
    _MONITOR_THREAD.start()
    logger.info("[MEMORY] monitor started (interval=%ds)", _INTERVAL)


def stop() -> None:
    """Stop the memory monitor."""
    global _STOP_EVENT
    if _STOP_EVENT is not None:
        _STOP_EVENT.set()
    logger.info("[MEMORY] monitor stopped")
