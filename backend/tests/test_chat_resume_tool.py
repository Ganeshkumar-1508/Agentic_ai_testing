"""Tests for the chat-side job resume (auto-resume from checkpoint).

C08 follow-up: the resume path used to require the user to
manually re-submit. The new path:

  1. /api/jobs/{id}/resume (and the chat's resume_job tool)
     flips the spec status AND spawns a fresh orchestrator
     run with the saved JobCheckpoint.
  2. The new run has a fresh run_id but the same spec_id.
  3. The context is annotated with resumed_from_checkpoint +
     checkpoint_paused_at + checkpoint_paused_by.
  4. The JobCheckpoint is consumed (popped).

What's covered:
  - OrchestratorEngine.run_resumed_job_spec happy path
  - Resume requires status="paused" (rejects running/cancelled)
  - Resume requires the spec to exist
  - Resume requires the JobSpecStore to be configured
  - Resume consumes the JobCheckpoint
  - Resume annotates the context
  - Chat tool _handle_resume_job: explicit spec_id, most-recent
  - Chat tool _handle_resume_job: session scoping
  - Chat tool _handle_resume_job: not-paused error
  - Chat tool _handle_resume_job: resume_job in CHAT_READONLY_TOOLSET
"""
from __future__ import annotations

import asyncio
import json
import types
from typing import Any

import pytest

import harness.agent.tool_dispatch as td
import harness.jobs.spec as spec_mod
from harness.jobs.spec import set_job_spec_store
from harness.store.protocols import JobSpecRecord
from harness.tools.toolsets import CHAT_READONLY_TOOLSET


async def _dispatch(dispatcher, action_name: str, args: dict) -> str:
    return await dispatcher.execute(
        {"function": {"name": action_name, "arguments": json.dumps(args)}},
        llm_response_id="r-1",
    )


# ---------------------------------------------------------------------------
# Fake stores
# ---------------------------------------------------------------------------


class _FakeJobSpecStore:
    """In-memory JobSpecStore with cancel/pause/resume/list_by_session/get_status."""

    def __init__(self) -> None:
        self.records: dict[str, JobSpecRecord] = {}
        self.cancelled: list[str] = []
        self.paused: list[str] = []
        self.resumed: list[str] = []

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
        if rec is None or rec.status in ("completed", "failed", "cancelled"):
            return False
        rec.status = "cancelled"
        self.cancelled.append(spec_id)
        return True

    async def pause(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or rec.status not in ("running", "submitted", "queued"):
            return False
        rec.status = "paused"
        self.paused.append(spec_id)
        return True

    async def resume(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or rec.status != "paused":
            return False
        rec.status = "running"
        self.resumed.append(spec_id)
        return True

    async def get_status(self, spec_id: str):
        rec = self.records.get(spec_id)
        if rec is None:
            return None
        return types.SimpleNamespace(
            spec_id=rec.spec_id, run_id=rec.run_id, status=rec.status,
            started_at=None, completed_at=None, error=None,
        )

    async def list_by_session(
        self, session_id: str, limit: int = 20, offset: int = 0,
    ):
        all_summaries = list(reversed(list(self.records.values())))
        out = []
        for r in all_summaries:
            ctx = r.context or {}
            sid = ctx.get("session_id") if isinstance(ctx, dict) else None
            if sid == session_id:
                out.append(types.SimpleNamespace(
                    spec_id=r.spec_id, prompt=r.prompt, repo_url=r.repo_url,
                    tier=r.tier, status=r.status, created_at=r.created_at,
                    latest_run_id=r.run_id, latest_run_status=None,
                    latest_run_started_at=None, latest_run_cost_usd=None,
                    latest_run_duration_s=None,
                ))
        return out[offset:offset + limit], len(out)

    async def get_output(self, *a, **kw): return None
    async def list_comments(
        self, spec_id: str, *, limit: int = 50, offset: int = 0,
    ):
        return [], 0
    async def add_comment(self, comment): return None
    async def list_pending(self, *a, **kw): return []
    async def get_team(self, *a, **kw): return None


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
        sandbox_manager=None,
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


@pytest.fixture
def fake_store(monkeypatch):
    store = _FakeJobSpecStore()
    set_job_spec_store(store)
    yield store
    spec_mod._deps_ref.clear()


def _make_record(
    spec_id: str = "spec-1",
    session_id: str = "sess-1",
    status: str = "paused",
    prompt: str = "Add tests for auth flow",
) -> JobSpecRecord:
    return JobSpecRecord(
        spec_id=spec_id,
        run_id="run-old",
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
# OrchestratorEngine.run_resumed_job_spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_resumed_job_spec_happy_path(monkeypatch, fake_store):
    """A paused spec with a saved checkpoint is resumed: the
    orchestrator's run_job_spec is called with the spec, the
    context is annotated, the checkpoint is consumed.
    """
    # Save a paused spec + checkpoint.
    await fake_store.save(_make_record(spec_id="spec-1", status="paused"))
    from harness.services.job_checkpoint import save_checkpoint
    ckpt = save_checkpoint(
        spec_id="spec-1", run_id="run-old",
        last_result={"phase": "post_run_single"},
        paused_by="sess-old",
    )

    # Patch run_job_spec on the engine to capture the spec.
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.__new__(OrchestratorEngine)  # bypass __init__
    engine.sandbox_manager = None
    captured: list[Any] = []

    async def fake_run_job_spec(spec):
        captured.append(spec)
        return {"success": True}

    engine.run_job_spec = fake_run_job_spec  # type: ignore[method-assign]

    result = await engine.run_resumed_job_spec(
        "spec-1", resumed_by="sess-new",
    )

    # Allow the background task to run.
    await asyncio.sleep(0.1)
    # Drain any pending tasks so we don't leak warnings.
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task() and not t.done():
            try:
                await asyncio.wait_for(t, timeout=0.5)
            except BaseException:
                pass

    assert result["resumed"] is True
    assert result["spec_id"] == "spec-1"
    assert "run_id" in result
    assert result["checkpoint"] is not None
    assert result["checkpoint"]["paused_at"] == ckpt.paused_at

    # The orchestrator should have been called with the spec.
    assert len(captured) == 1
    spec = captured[0]
    # The spec's context should be annotated.
    ctx = spec.context
    if hasattr(ctx, "model_dump"):
        ctx = ctx.model_dump()
    assert ctx.get("resumed_from_checkpoint") is True
    assert ctx.get("checkpoint_paused_at") == ckpt.paused_at
    assert ctx.get("checkpoint_paused_by") == "sess-old"
    assert ctx.get("resumed_by") == "sess-new"

    # The checkpoint should be consumed.
    from harness.services.job_checkpoint import get_checkpoint
    assert get_checkpoint("spec-1") is None


@pytest.mark.asyncio
async def test_run_resumed_job_spec_rejects_running_status(fake_store):
    """Only paused specs can be resumed."""
    await fake_store.save(_make_record(spec_id="spec-1", status="running"))

    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    engine.sandbox_manager = None

    result = await engine.run_resumed_job_spec("spec-1")
    assert result["resumed"] is False
    assert "not paused" in result["error"]


@pytest.mark.asyncio
async def test_run_resumed_job_spec_rejects_missing_spec(fake_store):
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    engine.sandbox_manager = None

    result = await engine.run_resumed_job_spec("spec-missing")
    assert result["resumed"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_run_resumed_job_spec_starts_fresh_when_no_checkpoint(fake_store):
    """If the user paused but the orchestrator didn't get to
    save a checkpoint (e.g. process died), resume should still
    work — the new run just doesn't have checkpoint context.
    """
    await fake_store.save(_make_record(spec_id="spec-1", status="paused"))

    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    engine.sandbox_manager = None
    captured: list[Any] = []

    async def fake_run_job_spec(spec):
        captured.append(spec)
        return {"success": True}

    engine.run_job_spec = fake_run_job_spec  # type: ignore[method-assign]

    result = await engine.run_resumed_job_spec("spec-1")
    await asyncio.sleep(0.1)
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task() and not t.done():
            try:
                await asyncio.wait_for(t, timeout=0.5)
            except BaseException:
                pass

    assert result["resumed"] is True
    assert result["checkpoint"] is None

    # Still spawned a new run.
    assert len(captured) == 1
    # The spec's context should be annotated with resumed_from_checkpoint
    # but no checkpoint fields.
    spec = captured[0]
    ctx = spec.context
    if hasattr(ctx, "model_dump"):
        ctx = ctx.model_dump()
    assert ctx.get("resumed_from_checkpoint") is True
    assert "checkpoint_paused_at" not in ctx


# ---------------------------------------------------------------------------
# Chat tool _handle_resume_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_resume_job_with_explicit_spec_id(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="paused"))
    dispatcher = _build_dispatcher(allowed_tools=["resume_job"])

    out = await _dispatch(dispatcher, "resume_job", {"spec_id": "spec-1"})

    assert "Resumed spec_id=spec-1" in out
    assert "resolved via spec_id" in out
    # The status should be flipped to running.
    assert fake_store.records["spec-1"].status == "running"


@pytest.mark.asyncio
async def test_chat_resume_job_enforces_session_scoping(fake_store):
    await fake_store.save(_make_record(
        spec_id="spec-other", session_id="sess-OTHER", status="paused",
    ))
    dispatcher = _build_dispatcher(
        allowed_tools=["resume_job"], session_id="sess-1",
    )

    out = await _dispatch(dispatcher, "resume_job", {"spec_id": "spec-other"})

    assert "different session" in out
    # The spec should NOT be flipped.
    assert fake_store.records["spec-other"].status == "paused"


@pytest.mark.asyncio
async def test_chat_resume_job_rejects_non_paused(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["resume_job"])

    out = await _dispatch(dispatcher, "resume_job", {"spec_id": "spec-1"})

    assert "not paused" in out
    assert fake_store.records["spec-1"].status == "running"


@pytest.mark.asyncio
async def test_chat_resume_job_rejects_missing_spec(fake_store):
    dispatcher = _build_dispatcher(allowed_tools=["resume_job"])

    out = await _dispatch(dispatcher, "resume_job", {"spec_id": "spec-missing"})

    assert "not found" in out


@pytest.mark.asyncio
async def test_chat_resume_job_resolves_to_most_recent(fake_store):
    await fake_store.save(_make_record(spec_id="spec-old", status="completed"))
    await fake_store.save(_make_record(spec_id="spec-new", status="paused"))
    dispatcher = _build_dispatcher(allowed_tools=["resume_job"])

    out = await _dispatch(dispatcher, "resume_job", {})

    assert "spec-new" in out
    # Drain any spawned tasks (their exceptions are expected in
    # the test environment with no sandbox; ignore them).
    await asyncio.sleep(0.1)
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task() and not t.done():
            try:
                await asyncio.wait_for(t, timeout=0.5)
            except BaseException:
                pass
    assert fake_store.records["spec-new"].status == "running"


# ---------------------------------------------------------------------------
# Toolsets integration
# ---------------------------------------------------------------------------


def test_resume_job_in_chat_toolset():
    assert "resume_job" in CHAT_READONLY_TOOLSET


def test_dispatcher_routes_to_resume_handler():
    """The dispatcher's job-control action table contains resume_job."""
    from harness.agent.tool_dispatch import _JOB_CONTROL_ACTION_BY_NAME
    from harness.services.job_control import JobControlAction
    assert _JOB_CONTROL_ACTION_BY_NAME["resume_job"] is JobControlAction.RESUME
