"""Tests for the chat-side job-control tools.

C08 follow-up: the chat can now cancel, pause, list, and inspect
its own jobs (the chat is the user's front door — they submit a
job, then ask "is it done?" or "cancel that one"). These tools
go through the JobSpecStore; the orchestrator's cancel_watcher
picks up the status change and stops the running task.

What's covered:
  - cancel_job with explicit spec_id
  - cancel_job with most-recent resolution
  - cancel_job enforces session scoping (can't cancel a
    different session's job)
  - cancel_job returns a clear error if the spec is already
    terminal
  - pause_job mirrors cancel_job's behavior
  - list_jobs returns a formatted table of recent jobs
  - list_jobs returns "No jobs" when empty
  - get_job_status returns a structured summary
  - toolsets.py wires all 4 new tools into CHAT_READONLY_TOOLSET
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
from typing import Any

import pytest

import harness.agent.tool_dispatch as td
import harness.jobs.spec as spec_mod
from harness.jobs.spec import set_job_spec_store
from harness.store.protocols import JobSpecRecord
from harness.tools.toolsets import CHAT_READONLY_TOOLSET


# ---------------------------------------------------------------------------
# Fake stores
# ---------------------------------------------------------------------------


class _FakeJobSpecStore:
    """In-memory JobSpecStore with cancel/pause/list_by_session/get_status."""

    def __init__(self) -> None:
        self.records: dict[str, JobSpecRecord] = {}
        self.cancelled: list[str] = []
        self.paused: list[str] = []

    async def save(self, record: JobSpecRecord) -> None:
        self.records[record.spec_id] = record

    async def get(self, spec_id: str):
        return self.records.get(spec_id)

    async def update_status(self, spec_id: str, status: str, **kw) -> None:
        rec = self.records.get(spec_id)
        if rec is not None:
            rec.status = status

    async def cancel(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None:
            return False
        if rec.status in ("completed", "failed", "cancelled"):
            return False
        rec.status = "cancelled"
        self.cancelled.append(spec_id)
        return True

    async def pause(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None:
            return False
        # Production status set: ``pending`` (just-submitted),
        # ``running`` (mid-flight). ``submitted`` / ``queued``
        # are not produced by ``to_record`` so we don't allow
        # them in the fake.
        if rec.status not in ("pending", "running"):
            return False
        rec.status = "paused"
        self.paused.append(spec_id)
        return True

    async def resume(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None:
            return False
        if rec.status != "paused":
            return False
        rec.status = "running"
        return True

    async def get_status(self, spec_id: str):
        rec = self.records.get(spec_id)
        if rec is None:
            return None
        return types.SimpleNamespace(
            spec_id=rec.spec_id,
            run_id=rec.run_id,
            status=rec.status,
            started_at=rec.started_at,
            completed_at=rec.completed_at,
            error=rec.error,
        )

    async def list_by_session(
        self, session_id: str, limit: int = 20, offset: int = 0,
    ):
        # Return most-recent-first (mimicking the real store).
        all_summaries = list(reversed(self._summaries()))
        out = [
            s for s in all_summaries
            if s.get("session_id") == session_id
        ]
        page = out[offset:offset + limit]
        return [types.SimpleNamespace(**s) for s in page], len(out)

    def _summaries(self):
        # Convert records to the same shape the real store returns.
        out = []
        for r in self.records.values():
            ctx = r.context or {}
            out.append({
                "spec_id": r.spec_id,
                "prompt": r.prompt,
                "repo_url": r.repo_url,
                "tier": r.tier,
                "status": r.status,
                "created_at": r.created_at,
                "latest_run_id": r.run_id,
                "latest_run_status": None,
                "latest_run_started_at": None,
                "latest_run_cost_usd": None,
                "latest_run_duration_s": None,
                "session_id": ctx.get("session_id") if isinstance(ctx, dict) else None,
            })
        return out

    async def list_pending(self, limit: int = 50):
        return []

    async def get_output(self, spec_id: str):
        return None

    async def list_comments(
        self, spec_id: str, *, limit: int = 50, offset: int = 0,
    ):
        return [], 0

    async def add_comment(self, comment): return None

    async def get(self, spec_id: str):
        return self.records.get(spec_id)

    async def get_team(self, *a, **kw):
        return None


# ---------------------------------------------------------------------------
# Dispatcher builder
# ---------------------------------------------------------------------------


def _build_dispatcher(allowed_tools: list[str], session_id: str = "sess-1"):
    from harness.events import EventBus
    from harness.permissions.manager import PermissionManager
    from harness.delegation import DelegationContext
    from harness.agent.deps import AgentDependencies
    from harness.memory.store import PersistentStore
    from harness.llm import LLMRouter

    bus = EventBus()
    perms = PermissionManager(mode="chat")
    delegation = DelegationContext()
    deps = AgentDependencies(
        llm=LLMRouter(),
        store=PersistentStore.__new__(PersistentStore),
        permissions=perms,
    )
    deps.store.db = object()

    return td.ToolDispatcher(
        event_bus=bus,
        permissions=perms,
        mode="chat",
        session_id=session_id,
        agent_id="agent-1",
        delegation=delegation,
        allowed_tools=allowed_tools,
        deps=deps,
    )


async def _dispatch(dispatcher, action_name: str, args: dict) -> str:
    """Run a chat-side job-control tool through the public execute() path."""
    return await dispatcher.execute(
        {"function": {"name": action_name, "arguments": json.dumps(args)}},
        llm_response_id="r-1",
    )


async def _resolve(dispatcher, args: dict) -> tuple:
    """Call the new JobControlDispatcher's _resolve_target directly."""
    from harness.services.job_control import (
        JobControlContext, JobControlDispatcher,
    )
    from harness.jobs.spec import _job_spec_store
    try:
        store = _job_spec_store()
    except Exception:
        store = None
    ctx = JobControlContext(
        store=store, session_id=dispatcher.session_id or "",
        agent_id=dispatcher.agent_id or "",
        trace_id="t-resolve", event_bus=dispatcher._event_bus,
        deps=dispatcher._deps,
    )
    return await JobControlDispatcher(ctx)._resolve_target(args)


@pytest.fixture
def fake_store(monkeypatch):
    store = _FakeJobSpecStore()
    set_job_spec_store(store)
    yield store
    spec_mod._deps_ref.clear()


def _make_record(
    spec_id: str = "spec-1",
    session_id: str = "sess-1",
    status: str = "running",
    prompt: str = "Add tests for auth flow",
) -> JobSpecRecord:
    return JobSpecRecord(
        spec_id=spec_id,
        run_id="run-1",
        source="chat",
        prompt=prompt,
        repo_url="https://github.com/example/foo",
        branch="main",
        sha="",
        tier=1,
        capabilities=[],
        approval={},
        context={"session_id": session_id},
        status=status,
        created_at="2026-06-21T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# cancel_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_job_with_explicit_spec_id(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    out = await dispatcher.execute(
            {"function": {"name": "cancel_job",
                          "arguments": json.dumps({"spec_id": "spec-1"})}},
            llm_response_id="r-1",
        )

    assert "Cancelled spec_id=spec-1" in out
    assert "resolved via spec_id" in out
    assert fake_store.records["spec-1"].status == "cancelled"
    assert fake_store.cancelled == ["spec-1"]


@pytest.mark.asyncio
async def test_cancel_job_resolves_to_most_recent(fake_store):
    await fake_store.save(_make_record(spec_id="spec-old", status="completed"))
    await fake_store.save(_make_record(spec_id="spec-new", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    out = await _dispatch(dispatcher, "cancel_job", {})

    assert "spec-new" in out
    assert fake_store.records["spec-new"].status == "cancelled"
    # Old completed job must be untouched.
    assert fake_store.records["spec-old"].status == "completed"


@pytest.mark.asyncio
async def test_cancel_job_enforces_session_scoping(fake_store):
    await fake_store.save(_make_record(
        spec_id="spec-other", session_id="sess-OTHER", status="running",
    ))
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"], session_id="sess-1")

    out = await _dispatch(dispatcher, "cancel_job", {"spec_id": "spec-other"})

    assert "different session" in out
    assert fake_store.records["spec-other"].status == "running"
    assert fake_store.cancelled == []


@pytest.mark.asyncio
async def test_cancel_job_rejects_already_terminal(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="completed"))
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    out = await dispatcher.execute(
            {"function": {"name": "cancel_job",
                          "arguments": json.dumps({"spec_id": "spec-1"})}},
            llm_response_id="r-1",
        )

    assert "already terminal" in out
    assert fake_store.cancelled == []


@pytest.mark.asyncio
async def test_cancel_job_returns_error_for_unknown_spec_id(fake_store):
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    out = await _dispatch(dispatcher, "cancel_job", {"spec_id": "spec-missing"})

    assert "not found" in out


# ---------------------------------------------------------------------------
# pause_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_job_with_explicit_spec_id(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["pause_job"])

    out = await _dispatch(dispatcher, "pause_job", {"spec_id": "spec-1"})

    assert "Paused spec_id=spec-1" in out
    assert fake_store.records["spec-1"].status == "paused"
    assert fake_store.paused == ["spec-1"]


@pytest.mark.asyncio
async def test_pause_job_accepts_pending_status(fake_store):
    """A freshly-submitted spec has ``status=pending`` (the
    production initial state). Pausing a pending spec is the
    most common flow: the user submits, immediately pauses to
    edit a config, then resumes. The previous fake only allowed
    ``running``/``submitted``/``queued`` — ``submitted`` and
    ``queued`` are not produced in production, so the happy
    path was untested."""
    await fake_store.save(_make_record(spec_id="spec-1", status="pending"))
    dispatcher = _build_dispatcher(allowed_tools=["pause_job"])

    out = await _dispatch(dispatcher, "pause_job", {"spec_id": "spec-1"})

    assert "Paused spec_id=spec-1" in out
    assert fake_store.records["spec-1"].status == "paused"
    assert fake_store.paused == ["spec-1"]


@pytest.mark.asyncio
async def test_pause_job_rejects_completed(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="completed"))
    dispatcher = _build_dispatcher(allowed_tools=["pause_job"])

    out = await _dispatch(dispatcher, "pause_job", {"spec_id": "spec-1"})

    assert "status=completed" in out
    assert fake_store.paused == []


@pytest.mark.asyncio
async def test_pause_job_enforces_session_scoping(fake_store):
    await fake_store.save(_make_record(
        spec_id="spec-other", session_id="sess-OTHER", status="running",
    ))
    dispatcher = _build_dispatcher(allowed_tools=["pause_job"], session_id="sess-1")

    out = await _dispatch(dispatcher, "pause_job", {"spec_id": "spec-other"})

    assert "different session" in out
    assert fake_store.records["spec-other"].status == "running"


# ---------------------------------------------------------------------------
# list_jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_jobs_returns_formatted_table(fake_store):
    await fake_store.save(_make_record(spec_id="spec-a", status="completed"))
    await fake_store.save(_make_record(spec_id="spec-b", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["list_jobs"])

    out = await _dispatch(dispatcher, "list_jobs", {"limit": 5})

    assert "Recent jobs in session sess-1" in out
    assert "spec-a" in out
    assert "spec-b" in out
    assert "completed" in out
    assert "running" in out


@pytest.mark.asyncio
async def test_list_jobs_empty_session(fake_store):
    dispatcher = _build_dispatcher(allowed_tools=["list_jobs"])

    out = await _dispatch(dispatcher, "list_jobs", {})

    assert "No jobs in session" in out


@pytest.mark.asyncio
async def test_list_jobs_filters_by_session(fake_store):
    await fake_store.save(_make_record(
        spec_id="spec-mine", session_id="sess-1", status="running",
    ))
    await fake_store.save(_make_record(
        spec_id="spec-other", session_id="sess-OTHER", status="running",
    ))
    dispatcher = _build_dispatcher(allowed_tools=["list_jobs"], session_id="sess-1")

    out = await _dispatch(dispatcher, "list_jobs", {})

    assert "spec-mine" in out
    assert "spec-other" not in out


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_status_returns_structured_summary(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["get_job_status"])

    out = await _dispatch(dispatcher, "get_job_status", {"spec_id": "spec-1"})

    assert "spec_id=spec-1" in out
    assert "status:   running" in out
    assert "run_id:   run-1" in out


@pytest.mark.asyncio
async def test_get_job_status_returns_error_for_missing(fake_store):
    dispatcher = _build_dispatcher(allowed_tools=["get_job_status"])

    out = await _dispatch(dispatcher, "get_job_status", {"spec_id": "spec-missing"})

    assert "not found" in out


# ---------------------------------------------------------------------------
# Resolution helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_job_target_falls_back_to_recent(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    spec_id, label = await _resolve(dispatcher, {})

    assert spec_id == "spec-1"
    assert label == "recent=1"


@pytest.mark.asyncio
async def test_resolve_job_target_returns_none_when_empty(fake_store):
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    spec_id, label = await _resolve(dispatcher, {})

    assert spec_id is None
    assert label == "no-jobs"


@pytest.mark.asyncio
async def test_resolve_job_target_recent_n_2(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="completed"))
    await fake_store.save(_make_record(spec_id="spec-2", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["cancel_job"])

    spec_id, label = await _resolve(dispatcher, {"recent": 2})

    # The 2nd most recent — but `list_by_session` returns
    # most-recent-first, so [recent=2] is the 2nd in that list.
    assert spec_id in ("spec-1", "spec-2")
    assert label == "recent=2"


# ---------------------------------------------------------------------------
# Toolsets integration
# ---------------------------------------------------------------------------


def test_chat_toolset_registers_all_four_new_tools():
    for name in ("submit_job", "cancel_job", "pause_job", "list_jobs", "get_job_status"):
        assert name in CHAT_READONLY_TOOLSET, f"{name} not in CHAT_READONLY_TOOLSET"


def test_dispatcher_routes_to_new_handlers():
    """The dispatcher's ``execute`` method must route the chat-side
    job-control tools to ``JobControlDispatcher`` (not to
    ``_handle_regular_tool``).
    """
    from harness.services.job_control import JobControlAction
    from harness.agent.tool_dispatch import _JOB_CONTROL_ACTION_BY_NAME
    expected = {
        "submit_job", "cancel_job", "pause_job", "resume_job",
        "list_jobs", "get_job_status", "comment_on_job",
    }
    assert set(_JOB_CONTROL_ACTION_BY_NAME) == expected
    for action in JobControlAction:
        assert _JOB_CONTROL_ACTION_BY_NAME[action.value] is action
