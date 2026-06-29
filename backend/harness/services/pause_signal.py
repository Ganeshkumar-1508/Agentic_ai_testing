"""Pause signal — in-memory flag for orchestrators to observe "paused".

The cancel_watcher (in ``harness/services/cancel_watcher.py``) treats
``paused`` as distinct from ``cancelled``: it sets this signal
instead of cancelling the running task. The orchestrator's
``run_single`` polls this signal at safe points and, when set,
saves a :class:`JobCheckpoint` and returns cleanly with
``status="paused"``.

Why in-memory (not DB-backed):

  - Pause is a process-local concern. The orchestrator that
    started the run is the one that should observe the pause
    signal. Cross-process pause (e.g. pause from a different
    uvicorn worker) is out of scope for the MVP.
  - If the orchestrator process dies, the run is dead anyway.
    The user re-submits and the new orchestrator starts fresh.
  - A future sprint can swap this for a Redis-backed signal if
    multi-worker pause becomes a requirement.

Public surface (stable):
  - set_pause_signal(spec_id)
  - check_pause_signal(spec_id) -> bool
  - clear_pause_signal(spec_id)
  - pause_signal_event(spec_id) -> asyncio.Event
  - signal_count(spec_id) -> int   (for tests + observability)
  - set_current_spec_id / get_current_spec_id / reset_current_spec_id
    — contextvar so ``run_single`` (which doesn't have a
    ``spec_id`` parameter) can read the active spec for
    multiple-pause-checkpoints (item 4).
"""
from __future__ import annotations

import asyncio
import contextvars
from typing import Dict, Optional


# Process-local state. Tests can ``_reset_all_signals()`` to
# clear between test cases.
_signals: Dict[str, asyncio.Event] = {}
_count: Dict[str, int] = {}
_lock = asyncio.Lock()

# Contextvar for the "currently-running spec_id". Set by
# ``OrchestratorEngine.run_job_spec`` before it calls
# ``run_single``; read by ``OrchestratorEngine.pause_checkpoint``
# inside ``run_single``. ``None`` when no run is in flight.
_current_spec_id: contextvars.ContextVar[Optional[str]] = (
    contextvars.ContextVar("_current_spec_id", default=None)
)


def pause_signal_event(spec_id: str) -> asyncio.Event:
    """Return (and lazily create) the ``asyncio.Event`` for this spec.

    The event is a thin wrapper around the boolean state — the
    orchestrator can ``await event.wait()`` if it wants to block
    on the signal, or use :func:`check_pause_signal` for a
    non-blocking poll.
    """
    ev = _signals.get(spec_id)
    if ev is None:
        ev = asyncio.Event()
        _signals[spec_id] = ev
    return ev


def set_pause_signal(spec_id: str) -> None:
    """Set the pause signal for ``spec_id``.

    Idempotent. Wakes any coroutine blocked in
    ``pause_signal_event(spec_id).wait()``.
    """
    ev = pause_signal_event(spec_id)
    if not ev.is_set():
        ev.set()
        _count[spec_id] = _count.get(spec_id, 0) + 1


def check_pause_signal(spec_id: str) -> bool:
    """Return True iff the pause signal is set for ``spec_id``."""
    ev = _signals.get(spec_id)
    return ev.is_set() if ev is not None else False


def clear_pause_signal(spec_id: str) -> None:
    """Clear the pause signal for ``spec_id``.

    Called by the orchestrator after it observes the signal and
    saves the checkpoint, so the next run starts with a clean
    state. Idempotent.
    """
    ev = _signals.get(spec_id)
    if ev is not None and ev.is_set():
        ev.clear()
    _count.pop(spec_id, None)


def signal_count(spec_id: str) -> int:
    """Number of times the signal has been set for ``spec_id``.

    For tests and observability. Returns 0 if the signal has
    never been set.
    """
    return _count.get(spec_id, 0)


def _reset_all_signals() -> None:
    """Clear all signals + counts. Test-only.

    Production code should never call this — a stuck signal is a
    real bug that needs investigating. The cancel_watcher clears
    the signal after a graceful exit, so production state should
    be self-healing.
    """
    _signals.clear()
    _count.clear()


def set_current_spec_id(spec_id: str) -> contextvars.Token:
    """Set the active spec_id (the spec the current run_single
    call is processing). Returns a token for :func:`reset_current_spec_id`.

    Used by the orchestrator to thread the spec_id into
    :meth:`OrchestratorEngine.pause_checkpoint` (which is called
    from inside ``run_single`` where the spec_id isn't a
    parameter).
    """
    return _current_spec_id.set(spec_id)


def get_current_spec_id() -> Optional[str]:
    """Return the active spec_id, or None if no run is in flight."""
    return _current_spec_id.get()


def reset_current_spec_id(token: contextvars.Token) -> None:
    """Restore the previous spec_id (use after ``run_single`` returns)."""
    _current_spec_id.reset(token)


__all__ = [
    "pause_signal_event",
    "set_pause_signal",
    "check_pause_signal",
    "clear_pause_signal",
    "signal_count",
    "_reset_all_signals",
    "set_current_spec_id",
    "get_current_spec_id",
    "reset_current_spec_id",
]
