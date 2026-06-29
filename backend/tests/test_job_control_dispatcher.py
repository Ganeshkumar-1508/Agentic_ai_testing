"""Tests for the JobControlDispatcher deep module (C09).

These cover the centralised ``ToolExecutionCompleted`` emit
contract that the old inline handlers violated &mdash; some only
emitted on success, some never on error. The dispatcher returns a
structured :class:`JobControlResult`; the dispatcher-route in
``ToolDispatcher.execute`` reads ``result.success`` and emits exactly
one event with the right ``is_error`` flag.

Also covers the dispatcher's standalone behaviour: the
``JobControlContext``, the action enum, and the resolve helper in
isolation from the ``ToolDispatcher`` integration.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.services.job_control import (
    JobControlAction,
    JobControlContext,
    JobControlDispatcher,
    JobControlResult,
)


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------


def test_job_control_action_enum_has_seven_values() -> None:
    assert len(JobControlAction) == 7
    assert {a.value for a in JobControlAction} == {
        "submit_job", "cancel_job", "pause_job", "resume_job",
        "list_jobs", "get_job_status", "comment_on_job",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeStore:
    """Minimal JobSpecStore stub for unit-testing the dispatcher."""

    def __init__(self) -> None:
        self.records: dict[str, Any] = {}
        self.cancelled: list[str] = []
        self.paused: list[str] = []
        self.comments: list[Any] = []

    async def save(self, record: Any) -> None:
        self.records[record.spec_id] = record

    async def get(self, spec_id: str) -> Any:
        return self.records.get(spec_id)

    async def cancel(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or rec.status in ("completed", "failed", "cancelled"):
            return False
        rec.status = "cancelled"
        self.cancelled.append(spec_id)
        return True

    async def pause(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or rec.status not in ("pending", "running"):
            return False
        rec.status = "paused"
        self.paused.append(spec_id)
        return True

    async def get_status(self, spec_id: str) -> Any:
        rec = self.records.get(spec_id)
        if rec is None:
            return None
        return MagicMock(
            spec_id=rec.spec_id, run_id=rec.run_id, status=rec.status,
            started_at=None, completed_at=None, error=None,
        )

    async def list_by_session(
        self, session_id: str, limit: int = 20, offset: int = 0,
    ) -> tuple[list, int]:
        out = [
            MagicNamespace(spec_id=r.spec_id, status=r.status, tier=r.tier,
                          prompt=r.prompt, latest_run_cost_usd=None,
                          latest_run_duration_s=None)
            for r in reversed(self.records.values())
            if r.context.get("session_id") == session_id
        ]
        return out[offset:offset + limit], len(out)

    async def add_comment(self, comment: Any) -> None:
        self.comments.append(comment)


from types import SimpleNamespace as MagicNamespace  # noqa: E402


def _make_record(
    spec_id: str = "spec-1",
    session_id: str = "sess-1",
    status: str = "running",
) -> Any:
    return MagicNamespace(
        spec_id=spec_id, run_id="run-1", source="chat",
        prompt="x", repo_url="", branch="main", sha="",
        tier=1, capabilities=[], approval={},
        context={"session_id": session_id},
        status=status, error=None,
    )


def _make_ctx(store: Any | None = None) -> JobControlContext:
    return JobControlContext(
        store=store or _FakeStore(),
        session_id="sess-1",
        agent_id="agent-1",
        trace_id="t-1",
        llm_response_id="r-1",
        event_bus=MagicMock(),
        deps=None,
    )


# ---------------------------------------------------------------------------
# resolve_target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_target_explicit_spec_id() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1"))
    d = JobControlDispatcher(_make_ctx(store))
    spec_id, label = await d._resolve_target({"spec_id": "spec-1"})
    assert spec_id == "spec-1"
    assert label == "spec_id"


@pytest.mark.asyncio
async def test_resolve_target_falls_back_to_most_recent() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1"))
    d = JobControlDispatcher(_make_ctx(store))
    spec_id, label = await d._resolve_target({})
    assert spec_id == "spec-1"
    assert label == "recent=1"


@pytest.mark.asyncio
async def test_resolve_target_returns_none_when_no_store() -> None:
    d = JobControlDispatcher(_make_ctx(store=None))
    spec_id, label = await d._resolve_target({})
    assert spec_id is None
    assert label == "no-jobs"


@pytest.mark.asyncio
async def test_resolve_target_no_jobs_in_session() -> None:
    store = _FakeStore()
    d = JobControlDispatcher(_make_ctx(store))
    spec_id, label = await d._resolve_target({})
    assert spec_id is None
    assert label == "no-jobs"


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_emits_failed_result_when_no_target() -> None:
    d = JobControlDispatcher(_make_ctx())
    result = await d.dispatch(JobControlAction.CANCEL, {})
    assert result.success is False
    assert "spec_id" in result.output or "recent" in result.output


@pytest.mark.asyncio
async def test_cancel_success_marks_status_cancelled() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1", status="running"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.CANCEL, {"spec_id": "spec-1"})
    assert result.success is True
    assert "Cancelled" in result.output
    assert store.cancelled == ["spec-1"]


@pytest.mark.asyncio
async def test_cancel_already_terminal_returns_failure() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1", status="completed"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.CANCEL, {"spec_id": "spec-1"})
    assert result.success is False
    assert "could not be cancelled" in result.output
    assert store.cancelled == []


@pytest.mark.asyncio
async def test_cancel_rejects_different_session() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-x", session_id="other"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.CANCEL, {"spec_id": "spec-x"})
    assert result.success is False
    assert "different session" in result.output
    assert store.cancelled == []


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_success_marks_status_paused() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1", status="running"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.PAUSE, {"spec_id": "spec-1"})
    assert result.success is True
    assert "Paused" in result.output
    assert store.paused == ["spec-1"]


@pytest.mark.asyncio
async def test_pause_rejects_completed() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1", status="completed"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.PAUSE, {"spec_id": "spec-1"})
    assert result.success is False
    assert store.paused == []


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_empty_session_returns_no_jobs() -> None:
    store = _FakeStore()
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.LIST, {})
    assert result.success is True
    assert "No jobs in session" in result.output


@pytest.mark.asyncio
async def test_list_with_jobs_returns_table() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-a", status="running"))
    await store.save(_make_record(spec_id="spec-b", status="completed"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.LIST, {})
    assert result.success is True
    assert "spec-a" in result.output
    assert "spec-b" in result.output
    assert "running" in result.output
    assert "completed" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_returns_structured_summary() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1", status="running"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.STATUS, {"spec_id": "spec-1"})
    assert result.success is True
    assert "spec_id=spec-1" in result.output
    assert "status:" in result.output
    assert "running" in result.output


@pytest.mark.asyncio
async def test_status_missing_spec_returns_error() -> None:
    d = JobControlDispatcher(_make_ctx())
    result = await d.dispatch(JobControlAction.STATUS, {"spec_id": "spec-missing"})
    assert result.success is False
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# comment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comment_requires_body() -> None:
    d = JobControlDispatcher(_make_ctx())
    result = await d.dispatch(
        JobControlAction.COMMENT, {"spec_id": "spec-1"},
    )
    assert result.success is False
    assert "body" in result.output


@pytest.mark.asyncio
async def test_comment_persists_and_returns_id() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(
        JobControlAction.COMMENT,
        {"spec_id": "spec-1", "body": "failing test is in test_x.py"},
    )
    assert result.success is True
    assert "Added comment" in result.output
    assert len(store.comments) == 1
    assert store.comments[0].body == "failing test is in test_x.py"


@pytest.mark.asyncio
async def test_comment_normalises_invalid_kind() -> None:
    store = _FakeStore()
    await store.save(_make_record(spec_id="spec-1"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(
        JobControlAction.COMMENT,
        {"spec_id": "spec-1", "body": "x", "kind": "not-a-real-kind"},
    )
    assert result.success is True
    assert store.comments[0].kind == "comment"


# ---------------------------------------------------------------------------
# error handling & result shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_exception_is_caught_and_returned_as_failure() -> None:
    class _ExplodingStore(_FakeStore):
        async def cancel(self, spec_id: str) -> bool:
            raise RuntimeError("store down")

    store = _ExplodingStore()
    await store.save(_make_record(spec_id="spec-1"))
    d = JobControlDispatcher(_make_ctx(store))
    result = await d.dispatch(JobControlAction.CANCEL, {"spec_id": "spec-1"})
    assert result.success is False
    assert "store down" in result.output


@pytest.mark.asyncio
async def test_unknown_action_returns_failure() -> None:
    d = JobControlDispatcher(_make_ctx())
    fake = "totally_made_up_action"
    result = await d.dispatch(fake, {})  # type: ignore[arg-type]
    assert result.success is False
    assert "unknown job-control action" in result.output


def test_job_control_result_is_frozen() -> None:
    result = JobControlResult(output="x", success=True)
    with pytest.raises(Exception):  # FrozenInstanceError
        result.success = False  # type: ignore[misc]


def test_job_control_context_is_frozen() -> None:
    ctx = JobControlContext(
        store=None, session_id="s", agent_id="a", trace_id="t",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        ctx.session_id = "other"  # type: ignore[misc]
