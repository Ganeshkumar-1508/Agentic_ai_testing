"""Per-thread interrupt signaling.

Thread-safe interrupt tracking. The agent sets interrupt on its thread,
tools check is_interrupted() on the current thread.
"""
from __future__ import annotations

import threading

_interrupted_threads: set[int] = set()
_lock = threading.Lock()


def set_interrupt(active: bool, thread_id: int | None = None) -> None:
    tid = thread_id if thread_id is not None else threading.current_thread().ident
    with _lock:
        if active:
            _interrupted_threads.add(tid)
        else:
            _interrupted_threads.discard(tid)


def is_interrupted() -> bool:
    with _lock:
        return threading.current_thread().ident in _interrupted_threads


def clear_interrupt(thread_id: int | None = None) -> None:
    set_interrupt(False, thread_id)
