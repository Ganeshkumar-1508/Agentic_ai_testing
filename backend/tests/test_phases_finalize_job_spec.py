"""Tests for FinalizeJobSpecPhase (C09)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.finalize_job_spec import FinalizeJobSpecPhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


@pytest.mark.asyncio
async def test_finalize_skips_when_no_spec_id() -> None:
    ctx = _ctx(spec_id="")
    result = await FinalizeJobSpecPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_finalize_writes_status_and_output_to_store() -> None:
    started_at = datetime.now(timezone.utc) - __import__("datetime").timedelta(seconds=10)
    fake_store = MagicMock()
    fake_store.update_status = AsyncMock()
    fake_store.add_output = AsyncMock()
    update_calls: list = []
    add_output_calls: list = []
    fake_store.update_status.side_effect = (
        lambda *a, **kw: update_calls.append((a, kw))
    )
    fake_store.add_output.side_effect = (
        lambda *a, **kw: add_output_calls.append((a, kw))
    )
    orchestrator = MagicMock()
    orchestrator._derive_run_success = MagicMock(return_value=(True, ""))
    with pytest.MonkeyPatch.context() as mp:
        from harness.jobs import spec as spec_mod
        mp.setattr(spec_mod, "_job_spec_store", lambda: fake_store)
        ctx = _ctx(
            run_started_at=started_at.isoformat(),
            coordinator_result={
                "raw_result": "ok",
                "budget_snapshot": {"spent_usd": 1.23},
                "evidence_summary": "### Files Changed\n- a.py\n",
            },
        )
        ctx = ctx.__class__(
            **{**ctx.__dict__, "orchestrator": orchestrator},
        ) if False else ctx  # preserve immutability; orchestrator on dict
        result_ctx = RunContext(
            **{
                **{k: v for k, v in ctx.__dict__.items() if k != "orchestrator"},
                "orchestrator": orchestrator,
            },
        )
        await FinalizeJobSpecPhase().execute(result_ctx)
    assert len(update_calls) == 1
    assert update_calls[0][0][0] == "spec-1"
    assert update_calls[0][0][1] == "completed"
    assert update_calls[0][1]["cost_usd"] == 1.23
    assert update_calls[0][1]["error"] is None
    # Duration should be ~10s (between started_at and now).
    duration = update_calls[0][1]["duration_s"]
    assert 9.0 < duration < 11.0
    assert len(add_output_calls) == 1
    job_output = add_output_calls[0][0][0]
    assert job_output.spec_id == "spec-1"
    assert "Files Changed" in job_output.summary


@pytest.mark.asyncio
async def test_finalize_records_failure_status() -> None:
    fake_store = MagicMock()
    fake_store.update_status = AsyncMock()
    fake_store.add_output = AsyncMock()
    update_calls: list = []
    fake_store.update_status.side_effect = (
        lambda *a, **kw: update_calls.append((a, kw))
    )
    orchestrator = MagicMock()
    orchestrator._derive_run_success = MagicMock(
        return_value=(False, "max tool rounds reached"),
    )
    with pytest.MonkeyPatch.context() as mp:
        from harness.jobs import spec as spec_mod
        mp.setattr(spec_mod, "_job_spec_store", lambda: fake_store)
        ctx = _ctx(
            run_started_at=datetime.now(timezone.utc).isoformat(),
            coordinator_result={"raw_result": "stuck"},
        )
        result_ctx = RunContext(
            **{**ctx.__dict__, "orchestrator": orchestrator},
        )
        await FinalizeJobSpecPhase().execute(result_ctx)
    assert update_calls[0][0][1] == "failed"
    assert update_calls[0][1]["error"] == "max tool rounds reached"


@pytest.mark.asyncio
async def test_finalize_no_op_when_store_is_none() -> None:
    orchestrator = MagicMock()
    orchestrator._derive_run_success = MagicMock(return_value=(True, ""))
    with pytest.MonkeyPatch.context() as mp:
        from harness.jobs import spec as spec_mod
        mp.setattr(spec_mod, "_job_spec_store", lambda: None)
        ctx = _ctx(
            run_started_at=datetime.now(timezone.utc).isoformat(),
            coordinator_result={"raw_result": "ok"},
        )
        result_ctx = RunContext(
            **{**ctx.__dict__, "orchestrator": orchestrator},
        )
        result = await FinalizeJobSpecPhase().execute(result_ctx)
    assert result is result_ctx


@pytest.mark.asyncio
async def test_finalize_swallows_exception() -> None:
    fake_store = MagicMock()
    fake_store.update_status = AsyncMock(
        side_effect=RuntimeError("db down"),
    )
    with pytest.MonkeyPatch.context() as mp:
        from harness.jobs import spec as spec_mod
        mp.setattr(spec_mod, "_job_spec_store", lambda: fake_store)
        ctx = _ctx(
            run_started_at=datetime.now(timezone.utc).isoformat(),
            coordinator_result={"raw_result": "ok"},
        )
        result = await FinalizeJobSpecPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_finalize_succeeds_when_orchestrator_missing() -> None:
    """Defensive: if no orchestrator is wired, default to
    (False, 'no orchestrator') and continue."""
    fake_store = MagicMock()
    fake_store.update_status = AsyncMock()
    fake_store.add_output = AsyncMock()
    with pytest.MonkeyPatch.context() as mp:
        from harness.jobs import spec as spec_mod
        mp.setattr(spec_mod, "_job_spec_store", lambda: fake_store)
        ctx = _ctx(
            run_started_at=datetime.now(timezone.utc).isoformat(),
            coordinator_result={"raw_result": "ok"},
        )
        result = await FinalizeJobSpecPhase().execute(ctx)
    assert result is ctx


def test_finalize_has_can_skip_true() -> None:
    assert FinalizeJobSpecPhase.can_skip is True


def test_finalize_phase_name() -> None:
    assert FinalizeJobSpecPhase.phase_name == "finalize_job_spec"
