"""Integration tests for the pause path.

Exercises the end-to-end flow:
  1. User calls POST /api/jobs/{id}/pause (or chat tool).
  2. JobSpecStore.pause() flips the spec status to "paused".
  3. cancel_watcher observes the flip.
  4. cancel_watcher sets the pause signal (does NOT cancel).
  5. Orchestrator's _check_pause_for_spec sees the signal.
  6. Orchestrator saves a JobCheckpoint.
  7. Orchestrator returns status="paused" to the caller.
  8. CancelWatchOutcome.triggered_pause is True.
"""
from __future__ import annotations

import asyncio
import types
from typing import Any

import pytest

from harness.services.cancel_watcher import (
    CANCEL_STATUSES,
    PAUSE_STATUSES,
    watch_for_cancel,
)
from harness.services.job_checkpoint import (
    clear_checkpoints,
    get_checkpoint,
)
from harness.services.pause_signal import (
    _reset_all_signals,
    check_pause_signal,
)


@pytest.fixture(autouse=True)
def _clean():
    _reset_all_signals()
    clear_checkpoints()
    yield
    _reset_all_signals()
    clear_checkpoints()


# ---------------------------------------------------------------------------
# Status set semantics
# ---------------------------------------------------------------------------


def test_pause_status_is_not_in_cancel_set():
    """``paused`` is a pause status, not a cancel status.
    The two paths are independent.
    """
    assert "paused" in PAUSE_STATUSES
    assert "paused" not in CANCEL_STATUSES


def test_cancelled_is_a_cancel_status():
    assert "cancelled" in CANCEL_STATUSES
    assert "cancelled" not in PAUSE_STATUSES


def test_failed_is_a_cancel_status():
    """``failed`` from the store (e.g. via update_status) cancels
    the running task - same as ``cancelled`` from the user's
    perspective.
    """
    assert "failed" in CANCEL_STATUSES
    assert "failed" not in PAUSE_STATUSES


# ---------------------------------------------------------------------------
# Watcher integration with pause signal + checkpoint
# ---------------------------------------------------------------------------


class _FakeStore:
    """Minimal JobSpecStore that records what the watcher sees."""

    def __init__(self) -> None:
        self._status: str = "running"

    async def get_status(self, spec_id: str):
        return types.SimpleNamespace(spec_id=spec_id, status=self._status)

    async def set_status(self, status: str) -> None:
        self._status = status


@pytest.mark.asyncio
async def test_full_pause_path_signals_and_saves_checkpoint():
    """User clicks pause -> store flips to "paused" -> watcher
    sets the signal -> orchestrator observes the signal ->
    orchestrator saves a JobCheckpoint.
    """
    store = _FakeStore()

    # Simulate the orchestrator's "acknowledge the pause" loop.
    async def orchestrator_run() -> dict:
        # Run for a bounded time, polling the pause signal.
        for _ in range(200):
            if check_pause_signal("spec-1"):
                # Simulate saving the checkpoint.
                from harness.services.job_checkpoint import save_checkpoint
                save_checkpoint(
                    spec_id="spec-1",
                    run_id="run-1",
                    last_result={"phase": "during_run"},
                    paused_by="sess-1",
                )
                return {"status": "paused", "checkpoint_saved": True}
            await asyncio.sleep(0.01)
        return {"status": "completed"}  # ran to natural end

    async def flip_pause() -> None:
        await asyncio.sleep(0.1)
        await store.set_status("paused")

    flip = asyncio.create_task(flip_pause())
    run_task = asyncio.create_task(orchestrator_run())
    try:
        outcome = await watch_for_cancel("spec-1", run_task, store, interval=0.05)
        result = await run_task

        # The watcher should have signalled pause (not cancelled).
        assert outcome.triggered_pause is True
        assert outcome.triggered_cancel is False
        assert outcome.polled_until_status == "paused"

        # The orchestrator should have observed the signal and
        # saved a checkpoint.
        ckpt = get_checkpoint("spec-1")
        assert ckpt is not None
        assert ckpt.spec_id == "spec-1"
        assert ckpt.run_id == "run-1"
        assert ckpt.last_result == {"phase": "during_run"}
        assert ckpt.paused_by == "sess-1"

        # The orchestrator's run should have returned a paused
        # result.
        assert result["status"] == "paused"
        assert result["checkpoint_saved"] is True
    finally:
        if not flip.done():
            flip.cancel()
            try:
                await flip
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_cancel_path_does_not_set_pause_signal():
    """A cancel is distinct from a pause. The watcher should
    cancel the task and NOT set the pause signal.
    """
    store = _FakeStore()

    async def long_task() -> None:
        await asyncio.sleep(10)

    async def flip_cancel() -> None:
        await asyncio.sleep(0.1)
        await store.set_status("cancelled")

    flip = asyncio.create_task(flip_cancel())
    long = asyncio.create_task(long_task())
    try:
        outcome = await watch_for_cancel("spec-1", long, store, interval=0.05)
        assert outcome.triggered_cancel is True
        assert outcome.triggered_pause is False
        assert outcome.polled_until_status == "cancelled"
        # The pause signal should NOT be set for a cancel.
        assert check_pause_signal("spec-1") is False
    finally:
        if not flip.done():
            flip.cancel()
            try:
                await flip
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_pause_falls_back_to_cancel_when_orchestrator_unresponsive():
    """If the orchestrator's run_single doesn't acknowledge the
    pause signal within PAUSE_GRACE_SECONDS, the watcher falls
    back to cancelling the task. The user still gets a stopped
    run, just not as gracefully.
    """
    from harness.services.cancel_watcher import PAUSE_GRACE_SECONDS
    store = _FakeStore()

    # Use a very short grace for the test by patching.
    import harness.services.cancel_watcher as cw
    original = cw.PAUSE_GRACE_SECONDS
    cw.PAUSE_GRACE_SECONDS = 0.5  # 500ms for the test

    try:
        async def unresponsive_task() -> None:
            # Pretend to be busy and never check the pause signal.
            await asyncio.sleep(10)

        async def flip_pause() -> None:
            await asyncio.sleep(0.1)
            await store.set_status("paused")

        flip = asyncio.create_task(flip_pause())
        task = asyncio.create_task(unresponsive_task())
        try:
            outcome = await watch_for_cancel("spec-1", task, store, interval=0.05)
            # The watcher should have fallen back to cancel.
            assert outcome.triggered_pause is True
            assert outcome.triggered_cancel is True
            # The task should be cancelled (or done) by now.
            assert task.done()
        finally:
            if not flip.done():
                flip.cancel()
                try:
                    await flip
                except asyncio.CancelledError:
                    pass
    finally:
        cw.PAUSE_GRACE_SECONDS = original
