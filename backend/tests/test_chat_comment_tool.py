"""Tests for the chat-side comment_on_job tool.

The chat can leave a note on a job (e.g. "the failing test is
in tests/auth/test_login.py"). The comment goes through the
store's ``add_comment`` and surfaces in the Job Detail page.

Public surface tested:
  - _handle_comment_on_job with explicit spec_id
  - _handle_comment_on_job with most-recent resolution
  - Session scoping (can't comment on a different session's job)
  - Missing body error
  - Missing spec error
  - Default author is the chat session_id
  - Custom author + kind override
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

import harness.agent.tool_dispatch as td
import harness.jobs.spec as spec_mod
from harness.jobs.spec import set_job_spec_store
from harness.store.protocols import JobComment, JobSpecRecord
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
    def __init__(self) -> None:
        self.records: dict[str, JobSpecRecord] = {}
        self.comments: list[dict[str, Any]] = []
        self._comment_id = 0

    async def save(self, record: JobSpecRecord) -> None:
        self.records[record.spec_id] = record

    async def get(self, spec_id: str):
        return self.records.get(spec_id)

    async def update_status(self, *a, **kw): pass
    async def cancel(self, *a, **kw): return False
    async def pause(self, *a, **kw): return False
    async def resume(self, *a, **kw): return False
    async def get_status(self, *a, **kw): return None

    async def list_by_session(self, session_id: str, limit: int = 20, offset: int = 0):
        all_summaries = list(reversed(list(self.records.values())))
        out = []
        for r in all_summaries:
            ctx = r.context or {}
            sid = ctx.get("session_id") if isinstance(ctx, dict) else None
            if sid == session_id:
                out.append(type("S", (), {
                    "spec_id": r.spec_id, "prompt": r.prompt,
                    "repo_url": r.repo_url, "tier": r.tier,
                    "status": r.status, "created_at": r.created_at,
                })())
        return out[offset:offset + limit], len(out)

    async def add_comment(self, comment: JobComment):
        self._comment_id += 1
        record = {
            "comment_id": comment.comment_id,
            "spec_id": comment.spec_id,
            "author": comment.author,
            "body": comment.body,
            "kind": comment.kind,
            "created_at": "2026-06-21T00:00:00Z",
        }
        self.comments.append(record)

    async def get_output(self, *a, **kw): return None
    async def list_comments(self, spec_id: str, *, limit: int = 50, offset: int = 0):
        items = [c for c in self.comments if c["spec_id"] == spec_id]
        return items[offset:offset + limit], len(items)
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
        event_bus=bus, permissions=perms, mode="chat",
        session_id=session_id, agent_id="agent-1",
        delegation=delegation, allowed_tools=allowed_tools,
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
    status: str = "running",
) -> JobSpecRecord:
    return JobSpecRecord(
        spec_id=spec_id, run_id="run-1", source="chat",
        prompt="x", repo_url="", branch="main", sha="",
        tier=1, capabilities=[], approval={},
        context={"session_id": session_id},
        status=status, created_at="2026-06-21T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# comment_on_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comment_on_job_with_explicit_spec_id(fake_store):
    await fake_store.save(_make_record(spec_id="spec-1"))
    dispatcher = _build_dispatcher(allowed_tools=["comment_on_job"])

    out = await _dispatch(dispatcher, "comment_on_job",
        {"spec_id": "spec-1", "body": "failing test is in test_login.py"})

    assert "Added comment" in out
    assert "spec-1" in out
    assert "resolved via spec_id" in out
    assert len(fake_store.comments) == 1
    assert fake_store.comments[0]["body"] == "failing test is in test_login.py"


@pytest.mark.asyncio
async def test_comment_on_job_resolves_to_most_recent(fake_store):
    await fake_store.save(_make_record(spec_id="spec-old", status="completed"))
    await fake_store.save(_make_record(spec_id="spec-new", status="running"))
    dispatcher = _build_dispatcher(allowed_tools=["comment_on_job"])

    out = await _dispatch(dispatcher, "comment_on_job", {"body": "check this"})

    assert "spec-new" in out
    assert fake_store.comments[0]["spec_id"] == "spec-new"


@pytest.mark.asyncio
async def test_comment_on_job_enforces_session_scoping(fake_store):
    await fake_store.save(_make_record(
        spec_id="spec-other", session_id="sess-OTHER",
    ))
    dispatcher = _build_dispatcher(
        allowed_tools=["comment_on_job"], session_id="sess-1",
    )

    out = await _dispatch(dispatcher, "comment_on_job",
        {"spec_id": "spec-other", "body": "x"})

    assert "different session" in out
    assert len(fake_store.comments) == 0


@pytest.mark.asyncio
async def test_comment_on_job_rejects_empty_body(fake_store):
    await fake_store.save(_make_record())
    dispatcher = _build_dispatcher(allowed_tools=["comment_on_job"])

    out = await _dispatch(dispatcher, "comment_on_job",
        {"spec_id": "spec-1", "body": ""})

    assert "body" in out and "required" in out
    assert len(fake_store.comments) == 0


@pytest.mark.asyncio
async def test_comment_on_job_rejects_missing_spec(fake_store):
    dispatcher = _build_dispatcher(allowed_tools=["comment_on_job"])

    out = await _dispatch(dispatcher, "comment_on_job",
        {"spec_id": "spec-missing", "body": "x"})

    assert "not found" in out
    assert len(fake_store.comments) == 0


@pytest.mark.asyncio
async def test_comment_on_job_default_author_is_session_id(fake_store):
    await fake_store.save(_make_record(session_id="sess-XYZ"))
    dispatcher = _build_dispatcher(
        allowed_tools=["comment_on_job"], session_id="sess-XYZ",
    )

    out = await _dispatch(dispatcher, "comment_on_job",
        {"spec_id": "spec-1", "body": "hello"})

    assert "author=sess-XYZ" in out
    assert fake_store.comments[0]["author"] == "sess-XYZ"


@pytest.mark.asyncio
async def test_comment_on_job_custom_author_and_kind(fake_store):
    await fake_store.save(_make_record())
    dispatcher = _build_dispatcher(allowed_tools=["comment_on_job"])

    out = await _dispatch(dispatcher, "comment_on_job",
        {
            "spec_id": "spec-1", "body": "needs approval",
            "author": "alice@example.com", "kind": "approval",
        })

    assert "Added approval comment" in out
    assert fake_store.comments[0]["author"] == "alice@example.com"
    assert fake_store.comments[0]["kind"] == "approval"


# ---------------------------------------------------------------------------
# Toolsets
# ---------------------------------------------------------------------------


def test_comment_on_job_in_chat_toolset():
    assert "comment_on_job" in CHAT_READONLY_TOOLSET


def test_dispatcher_routes_to_comment_handler():
    from harness.agent.tool_dispatch import _JOB_CONTROL_ACTION_BY_NAME
    from harness.services.job_control import JobControlAction
    assert _JOB_CONTROL_ACTION_BY_NAME["comment_on_job"] is JobControlAction.COMMENT
