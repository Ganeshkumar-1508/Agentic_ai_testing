"""Tests for the multiple-pause-checkpoints path (item 4).

The orchestrator's :meth:`run_single` now checks the pause
signal at 4 natural pause points:
  - post_bootstrap (after sandbox deps install)
  - post_kg_index (after knowledge graph sync)
  - post_worktree (after per-session worktree creation)
  - pre_coordinator (just before the long-running dt.run call)

Each check calls :meth:`OrchestratorEngine.pause_checkpoint`,
which reads the active spec_id from the contextvar set by
:meth:`run_job_spec` and checks the pause signal.

Public surface tested:
  - pause_checkpoint returns None when signal is not set
  - pause_checkpoint returns a paused result when signal is set
  - The returned result includes the phase name
  - The JobCheckpoint is saved with the correct phase
  - The contextvar is reset after run_job_spec
  - The pause signal is cleared after the checkpoint is saved
"""
from __future__ import annotations

import asyncio

import pytest

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
    from harness.services.job_checkpoint import _reset_all_trackers
    _reset_all_trackers()
    _reset_all_signals()
    clear_checkpoints()
    yield
    _reset_all_trackers()
    _reset_all_signals()
    clear_checkpoints()


# ---------------------------------------------------------------------------
# pause_checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_checkpoint_returns_none_when_no_signal():
    """Without a spec_id in the contextvar (i.e. not running
    through run_job_spec), pause_checkpoint is a no-op.
    """
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    result = await engine.pause_checkpoint(
        run_id="run-1", session_id="sess-1", phase="post_bootstrap",
    )
    assert result is None


@pytest.mark.asyncio
async def test_pause_checkpoint_returns_none_when_signal_not_set():
    """With a spec_id in the contextvar but no pause signal,
    pause_checkpoint is a no-op.
    """
    from harness.orchestrator import OrchestratorEngine
    from harness.services.pause_signal import set_current_spec_id, reset_current_spec_id
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    token = set_current_spec_id("spec-1")
    try:
        result = await engine.pause_checkpoint(
            run_id="run-1", session_id="sess-1", phase="post_bootstrap",
        )
        assert result is None
        assert get_checkpoint("spec-1") is None
    finally:
        reset_current_spec_id(token)


@pytest.mark.asyncio
async def test_pause_checkpoint_returns_paused_result_when_signal_set():
    """With a spec_id in the contextvar AND a pause signal set,
    pause_checkpoint returns a paused result and saves a
    JobCheckpoint.
    """
    from harness.orchestrator import OrchestratorEngine
    from harness.services.pause_signal import (
        set_current_spec_id, reset_current_spec_id, set_pause_signal,
    )
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    set_pause_signal("spec-1")
    token = set_current_spec_id("spec-1")
    try:
        result = await engine.pause_checkpoint(
            run_id="run-1", session_id="sess-1", phase="post_bootstrap",
        )
        assert result is not None
        assert result["status"] == "paused"
        assert result["paused"] is True
        assert result["checkpoint_saved"] is True
        assert result["paused_at_phase"] == "post_bootstrap"

        # The checkpoint should be saved.
        ckpt = get_checkpoint("spec-1")
        assert ckpt is not None
        assert ckpt.last_result == {"phase": "post_bootstrap"}
        assert ckpt.subagent_state == {"paused_at_phase": "post_bootstrap"}

        # The signal should be cleared (the orchestrator
        # observed it and saved the checkpoint; the next run
        # starts fresh).
        assert not check_pause_signal("spec-1")
    finally:
        reset_current_spec_id(token)


@pytest.mark.asyncio
async def test_pause_checkpoint_different_phases_save_different_checkpoints():
    """Each phase name produces a distinct checkpoint record.
    (Note: there's only one checkpoint per spec at a time;
    a new pause overwrites the old. This test verifies the
    phase metadata flows through.)
    """
    from harness.orchestrator import OrchestratorEngine
    from harness.services.pause_signal import (
        set_current_spec_id, reset_current_spec_id, set_pause_signal,
    )
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    token = set_current_spec_id("spec-1")
    try:
        # First pause at post_bootstrap
        set_pause_signal("spec-1")
        r1 = await engine.pause_checkpoint(
            run_id="run-1", session_id="sess-1", phase="post_bootstrap",
        )
        assert r1["paused_at_phase"] == "post_bootstrap"
        ckpt1 = get_checkpoint("spec-1")
        assert ckpt1.last_result["phase"] == "post_bootstrap"

        # Simulate a second run that pauses at a different phase
        set_pause_signal("spec-1")
        r2 = await engine.pause_checkpoint(
            run_id="run-2", session_id="sess-2", phase="post_kg_index",
        )
        assert r2["paused_at_phase"] == "post_kg_index"
        ckpt2 = get_checkpoint("spec-1")
        # The second checkpoint overwrites the first (only one
        # checkpoint per spec at a time).
        assert ckpt2.last_result["phase"] == "post_kg_index"
    finally:
        reset_current_spec_id(token)


@pytest.mark.asyncio
async def test_pause_checkpoint_handles_save_failure_gracefully():
    """If saving the checkpoint fails, pause_checkpoint still
    returns the paused result (the run is paused either way).
    """
    from harness.orchestrator import OrchestratorEngine
    from harness.services import job_checkpoint
    from harness.services.pause_signal import (
        set_current_spec_id, reset_current_spec_id, set_pause_signal,
    )

    # Patch save_checkpoint to raise.
    original_save = job_checkpoint.save_checkpoint

    def boom(*a, **kw):
        raise RuntimeError("simulated save failure")

    job_checkpoint.save_checkpoint = boom
    set_pause_signal("spec-1")
    token = set_current_spec_id("spec-1")
    try:
        engine = OrchestratorEngine.__new__(OrchestratorEngine)
        result = await engine.pause_checkpoint(
            run_id="run-1", session_id="sess-1", phase="post_bootstrap",
        )
        # The paused result is still returned even if save failed.
        assert result is not None
        assert result["status"] == "paused"
    finally:
        job_checkpoint.save_checkpoint = original_save
        reset_current_spec_id(token)


# ---------------------------------------------------------------------------
# Subagent tracker integration (item 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_checkpoint_merges_tracker_snapshot():
    """When a subagent tracker is active, the checkpoint's
    subagent_state merges the tracker's snapshot (item 5:
    true replay). The LLM can see which subagents completed
    and skip re-doing work.
    """
    from harness.orchestrator import OrchestratorEngine
    from harness.services import job_checkpoint
    from harness.services.pause_signal import (
        set_current_spec_id, reset_current_spec_id, set_pause_signal,
    )

    # Manually populate a tracker's state by injecting a
    # fake tracker. Real trackers are started by run_job_spec;
    # here we just verify the merge logic.
    class _FakeTracker:
        def snapshot(self):
            return {
                "completed_subagents": ["sa-1", "sa-3"],
                "in_flight_subagents": ["sa-7"],
                "completed_count": 2,
                "in_flight_count": 1,
            }

    set_pause_signal("spec-1")
    token = set_current_spec_id("spec-1")
    try:
        # Inject the fake tracker.
        from harness.services.job_checkpoint import _trackers
        _trackers["spec-1"] = _FakeTracker()
        try:
            engine = OrchestratorEngine.__new__(OrchestratorEngine)
            await engine.pause_checkpoint(
                run_id="run-1", session_id="sess-1", phase="pre_coordinator",
            )
            ckpt = get_checkpoint("spec-1")
            assert ckpt is not None
            # The phase marker is included.
            assert ckpt.subagent_state["paused_at_phase"] == "pre_coordinator"
            # The tracker's snapshot is merged in.
            assert ckpt.subagent_state["completed_subagents"] == ["sa-1", "sa-3"]
            assert ckpt.subagent_state["in_flight_subagents"] == ["sa-7"]
            assert ckpt.subagent_state["completed_count"] == 2
            assert ckpt.subagent_state["in_flight_count"] == 1
        finally:
            _trackers.pop("spec-1", None)
    finally:
        reset_current_spec_id(token)


@pytest.mark.asyncio
async def test_pause_checkpoint_handles_missing_tracker():
    """If no tracker is active (e.g. pause before run_job_spec
    wires the tracker), the checkpoint still saves with just
    the phase marker.
    """
    from harness.orchestrator import OrchestratorEngine
    from harness.services.pause_signal import (
        set_current_spec_id, reset_current_spec_id, set_pause_signal,
    )
    set_pause_signal("spec-1")
    token = set_current_spec_id("spec-1")
    try:
        engine = OrchestratorEngine.__new__(OrchestratorEngine)
        result = await engine.pause_checkpoint(
            run_id="run-1", session_id="sess-1", phase="post_bootstrap",
        )
        assert result is not None
        ckpt = get_checkpoint("spec-1")
        assert ckpt is not None
        # Just the phase marker, no tracker data.
        assert ckpt.subagent_state == {"paused_at_phase": "post_bootstrap"}
    finally:
        reset_current_spec_id(token)


# ---------------------------------------------------------------------------
# Contextvar integration
# ---------------------------------------------------------------------------


def test_current_spec_id_default_is_none():
    """When no run_job_spec is in flight, the contextvar is None."""
    from harness.services.pause_signal import get_current_spec_id
    # In a fresh test context, this should be None.
    assert get_current_spec_id() is None


@pytest.mark.asyncio
async def test_current_spec_id_can_be_set_and_reset():
    """set/reset pattern works like other contextvars."""
    from harness.services.pause_signal import (
        set_current_spec_id, get_current_spec_id, reset_current_spec_id,
    )
    assert get_current_spec_id() is None
    token = set_current_spec_id("spec-1")
    try:
        assert get_current_spec_id() == "spec-1"
    finally:
        reset_current_spec_id(token)
    assert get_current_spec_id() is None
