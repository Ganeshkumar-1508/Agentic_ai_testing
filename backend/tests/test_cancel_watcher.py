"""Tests for the C08 cancel watcher.

The cancel watcher polls the spec's status and cancels the
running task when the user calls ``JobSpecStore.cancel``. These
tests cover the polling loop, the cancel trigger, the
``run_with_cancel`` wrapper, and defensive behavior.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.services.cancel_watcher import (
    DEFAULT_CANCEL_POLL_INTERVAL_SECONDS,
    TERMINAL_STATUSES,
    CancelWatchOutcome,
    run_with_cancel,
    watch_for_cancel,
)
from harness.services.team_service import (
    MemberRole,
    MemberStatus,
    TeamNotFoundError,
    TeamService,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# In-memory store mirroring the JobSpecStore protocol
# ---------------------------------------------------------------------------


class _FakeStore:
    """In-memory store with mutable status for cancel testing.

    Mirrors the subset of ``JobSpecStore`` that the watcher
    needs (the rest is exercised by ``test_c08_jobs.py``).
    """

    def __init__(self) -> None:
        self.status: str = "running"
        self.get_status_calls: int = 0

    async def get_status(self, spec_id: str) -> Any:
        self.get_status_calls += 1
        # Mimic JobStatus: a small object with a ``status`` field.
        return MagicMock(status=self.status)

    async def set_status(self, status: str) -> None:
        self.status = status


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants() -> None:
    assert DEFAULT_CANCEL_POLL_INTERVAL_SECONDS == 2.0
    assert "cancelled" in TERMINAL_STATUSES
    assert "paused" in TERMINAL_STATUSES
    assert "failed" in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Outcome dataclass
# ---------------------------------------------------------------------------


def test_outcome_repr() -> None:
    o = CancelWatchOutcome(
        spec_id="spec-1", polled_until_status="cancelled",
        triggered_cancel=True, triggered_pause=False,
        elapsed_seconds=12.3, interval=2.0,
    )
    r = repr(o)
    assert "spec-1" in r
    assert "cancelled" in r
    assert "True" in r


# ---------------------------------------------------------------------------
# watch_for_cancel: basic behavior
# ---------------------------------------------------------------------------


async def test_watcher_exits_when_running_task_completes_first() -> None:
    """If the task finishes before any cancel is issued, the watcher
    exits cleanly with ``triggered_cancel=False``.
    """
    store = _FakeStore()

    async def quick_task() -> str:
        await asyncio.sleep(0.01)
        return "done"

    task = asyncio.create_task(quick_task())
    outcome = await watch_for_cancel(
        "spec-1", task, store, interval=0.05,
    )
    assert outcome.triggered_cancel is False
    assert task.result() == "done"


async def test_watcher_cancels_when_status_becomes_cancelled() -> None:
    """If the spec's status flips to ``cancelled``, the watcher
    cancels the running task.
    """
    store = _FakeStore()

    async def long_task() -> None:
        await asyncio.sleep(10)  # never completes in test window

    async def flip_status() -> None:
        await asyncio.sleep(0.1)
        await store.set_status("cancelled")

    flip_task = asyncio.create_task(flip_status())
    long = asyncio.create_task(long_task())
    try:
        outcome = await watch_for_cancel(
            "spec-1", long, store, interval=0.05,
        )
        # The watcher should have observed the cancel and triggered.
        assert outcome.triggered_cancel is True
        assert outcome.polled_until_status == "cancelled"
        # The long task should be cancelled (not still running).
        assert long.cancelled() or long.done()
    finally:
        if not flip_task.done():
            flip_task.cancel()
            try:
                await flip_task
            except asyncio.CancelledError:
                pass


async def test_watcher_signals_pause_when_status_is_paused() -> None:
    """``paused`` is a soft status for the watcher — it sets the
    pause signal and waits for the running task to acknowledge
    (graceful exit, with a JobCheckpoint saved). It does NOT
    cancel the task. (The orchestrator distinguishes pause from
    cancel via the polled status + the triggered_pause flag.)
    """
    from harness.services.pause_signal import (
        _reset_all_signals,
        check_pause_signal,
    )
    _reset_all_signals()

    store = _FakeStore()

    async def long_task() -> None:
        # Acknowledge the pause signal after a short delay,
        # simulating a well-behaved orchestrator.
        for _ in range(200):
            if check_pause_signal("spec-1"):
                return
            await asyncio.sleep(0.01)

    async def pause_flip() -> None:
        await asyncio.sleep(0.1)
        await store.set_status("paused")

    flip = asyncio.create_task(pause_flip())
    long = asyncio.create_task(long_task())
    try:
        outcome = await watch_for_cancel(
            "spec-1", long, store, interval=0.05,
        )
        # The watcher should have observed the pause status and
        # set the signal (NOT cancelled the task).
        assert outcome.triggered_pause is True
        assert outcome.triggered_cancel is False
        assert outcome.polled_until_status == "paused"
        # The long task should have observed the signal and
        # returned gracefully (not been cancelled).
        assert long.done()
        assert not long.cancelled()
    finally:
        if not flip.done():
            flip.cancel()
            try:
                await flip
            except asyncio.CancelledError:
                pass
        _reset_all_signals()
        assert outcome.polled_until_status == "paused"


async def test_watcher_does_not_cancel_on_running_status() -> None:
    """``running`` is NOT a terminal status — the watcher leaves
    the task alone.
    """
    store = _FakeStore()  # status="running" by default

    async def quick() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    task = asyncio.create_task(quick())
    outcome = await watch_for_cancel("spec-1", task, store, interval=0.02)
    assert outcome.triggered_cancel is False


# ---------------------------------------------------------------------------
# watch_for_cancel: defensive behavior
# ---------------------------------------------------------------------------


async def test_watcher_survives_get_status_failures() -> None:
    """A transient ``get_status`` exception doesn't kill the
    watcher — it logs and continues.
    """
    store = _FakeStore()
    call_count = [0]

    async def flaky_get_status(spec_id: str) -> Any:
        call_count[0] += 1
        if call_count[0] <= 2:
            raise RuntimeError("transient db error")
        return MagicMock(status="running")  # eventually fine

    async def slow_quick() -> str:
        # Long enough for the watcher to make several polls
        # (interval=0.02s × 4 = 80ms; this task runs for 200ms).
        await asyncio.sleep(0.2)
        return "ok"

    # Replace the store's get_status.
    store.get_status = flaky_get_status  # type: ignore[assignment]

    task = asyncio.create_task(slow_quick())
    outcome = await watch_for_cancel("spec-1", task, store, interval=0.02)
    assert outcome.triggered_cancel is False
    # We polled at least 3 times (2 failures + 1+ success).
    assert call_count[0] >= 3


async def test_watcher_handles_none_status_object() -> None:
    """If ``get_status`` returns ``None`` (spec not found), the
    watcher treats it as no-terminal and keeps polling.
    """
    store = _FakeStore()

    async def returns_none(spec_id: str) -> None:
        return None

    store.get_status = returns_none  # type: ignore[assignment]

    async def quick() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    task = asyncio.create_task(quick())
    outcome = await watch_for_cancel("spec-1", task, store, interval=0.02)
    assert outcome.triggered_cancel is False
    assert outcome.polled_until_status is None


async def test_watcher_stop_event_exits_early() -> None:
    """The ``stop_event`` argument lets tests (and other callers)
    short-circuit the watcher without waiting for the task.
    """
    store = _FakeStore()

    async def long_task() -> None:
        await asyncio.sleep(10)

    stop = asyncio.Event()
    stop.set()  # pre-set so the watcher exits on the first cycle
    task = asyncio.create_task(long_task())
    outcome = await watch_for_cancel(
        "spec-1", task, store, interval=10.0, stop_event=stop,
    )
    assert outcome.triggered_cancel is False
    # The task wasn't cancelled.
    assert not task.cancelled()
    # Cleanup.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# run_with_cancel wrapper
# ---------------------------------------------------------------------------


async def test_run_with_cancel_returns_result_when_not_cancelled() -> None:
    store = _FakeStore()

    async def my_run() -> dict:
        await asyncio.sleep(0.01)
        return {"status": "completed", "result": "ok"}

    result, outcome = await run_with_cancel(
        "spec-1", store, my_run(), interval=0.05,
    )
    assert result == {"status": "completed", "result": "ok"}
    assert outcome.triggered_cancel is False


async def test_run_with_cancel_returns_none_when_cancelled() -> None:
    store = _FakeStore()

    async def long_run() -> None:
        await asyncio.sleep(10)

    async def cancel_after_delay() -> None:
        await asyncio.sleep(0.1)
        await store.set_status("cancelled")

    flip = asyncio.create_task(cancel_after_delay())
    try:
        result, outcome = await run_with_cancel(
            "spec-1", store, long_run(), interval=0.05,
        )
        # The watcher observed the cancel; the wrapper returns
        # ``None`` for the result (caller can inspect
        # ``outcome.triggered_cancel``).
        assert result is None
        assert outcome.triggered_cancel is True
        assert outcome.polled_until_status == "cancelled"
    finally:
        if not flip.done():
            flip.cancel()
            try:
                await flip
            except asyncio.CancelledError:
                pass


async def test_run_with_cancel_propagates_return_value() -> None:
    store = _FakeStore()

    async def my_run() -> int:
        await asyncio.sleep(0.01)
        return 42

    result, outcome = await run_with_cancel(
        "spec-1", store, my_run(), interval=0.05,
    )
    assert result == 42


# ---------------------------------------------------------------------------
# Integration with JobSpecStore (real protocol, in-memory)
# ---------------------------------------------------------------------------


class _RealProtocolStore:
    """Implements the full JobSpecStore protocol with the same
    in-memory semantics as the one in ``test_c08_jobs.py``.
    """

    def __init__(self) -> None:
        from harness.store.protocols import JobComment, JobSpecRecord, JobStatus, JobSummary
        self._records: dict[str, JobSpecRecord] = {}
        self._comments: dict[str, list[JobComment]] = {}

    async def save(self, record: Any) -> None:
        self._records[record.spec_id] = record

    async def get(self, spec_id: str) -> Any:
        return self._records.get(spec_id)

    async def update_status(
        self, spec_id: str, status: str, **kwargs: Any
    ) -> None:
        rec = self._records.get(spec_id)
        if rec is not None:
            rec.status = status

    async def list_pending(self, limit: int = 50) -> list[Any]:
        return [r for r in self._records.values() if r.status == "pending"][:limit]

    async def cancel(self, spec_id: str) -> bool:
        rec = self._records.get(spec_id)
        if rec is None or rec.status in ("completed", "failed", "cancelled"):
            return False
        rec.status = "cancelled"
        return True

    async def get_status(self, spec_id: str) -> Any:
        from harness.store.protocols import JobStatus
        rec = self._records.get(spec_id)
        if rec is None:
            return None
        return JobStatus(
            spec_id=rec.spec_id, status=rec.status,
            started_at=rec.started_at, completed_at=rec.completed_at,
            error=rec.error, run_id=rec.run_id,
        )

    # Stubs for the rest of the protocol.
    async def list_by_session(self, *a: Any, **kw: Any) -> list[Any]: return []
    async def pause(self, *a: Any, **kw: Any) -> bool: return False
    async def resume(self, *a: Any, **kw: Any) -> bool: return False
    async def add_comment(self, *a: Any, **kw: Any) -> None: pass
    async def get_output(self, *a: Any, **kw: Any) -> Any: return None
    async def list_comments(self, *a: Any, **kw: Any) -> list[Any]: return []


async def test_full_protocol_integration() -> None:
    """End-to-end: real JobSpecStore + watcher + cancel() call."""
    from harness.store.protocols import JobSpecRecord
    from datetime import datetime, timezone

    store = _RealProtocolStore()
    rec = JobSpecRecord(
        spec_id="spec-1", run_id="run-1", source="api", prompt="x",
    )
    rec.status = "running"
    await store.save(rec)

    async def long_task() -> None:
        await asyncio.sleep(10)

    async def user_cancels() -> None:
        await asyncio.sleep(0.1)
        await store.cancel("spec-1")  # user clicks "Cancel"

    flip = asyncio.create_task(user_cancels())
    task = asyncio.create_task(long_task())
    try:
        result, outcome = await run_with_cancel(
            "spec-1", store, long_task(), interval=0.05,
        )
        assert outcome.triggered_cancel is True
        assert outcome.polled_until_status == "cancelled"
        # The DB status was actually updated to "cancelled".
        assert (await store.get_status("spec-1")).status == "cancelled"
    finally:
        if not flip.done():
            flip.cancel()
            try:
                await flip
            except asyncio.CancelledError:
                pass
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
