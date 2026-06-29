"""Tests for C08: JobSpec, JobContext, shared submitter, and the
``POST /api/jobs`` router.

C08 (per docs/2026-06-21-architecture-decision-tree.md#c08):
  Q3: JobContext is a Pydantic ``extra='allow'`` sub-model
  Q4: from-requirements 30+ extras live in ``context.test_config``
  Q5: all submission paths route through ``submit_job_to_orchestrator``
  Q6: new ``POST /api/jobs`` accepts a JobSpec directly
  Q8: chat-facing 8-tool surface (list/get/cancel/pause/resume/
      comment/output)
  Q9: JobSpecStore protocol extended with 7 new methods
  Q10: list_jobs returns ``JobSummary`` (spec summary + latest run)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.jobs.spec import (
    DEFAULT_CAPABILITIES,
    JobContext,
    JobSpec,
    TestConfig,
    _build_context,
    set_job_spec_store,
    to_record,
)
from harness.jobs.submitter import (
    new_spec_id,
    submit_job_to_orchestrator,
)
from harness.store.protocols import (
    JobComment,
    JobOutput,
    JobSpecRecord,
    JobSpecStore,
    JobStatus,
    JobSummary,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# In-memory store for tests
# ---------------------------------------------------------------------------


class _InMemoryStore:
    """Implements the C08-extended JobSpecStore protocol."""

    def __init__(self) -> None:
        self.records: dict[str, JobSpecRecord] = {}
        self.comments: dict[str, list[JobComment]] = {}
        self.outputs: dict[str, JobOutput] = {}
        # Lifecycle transitions.
        self.paused: set[str] = set()
        self.cancelled: set[str] = set()
        # Denormalized ``latest_run_*`` columns (mirrors the
        # Postgres ``latest_run_status`` / ``latest_run_cost_usd``
        # / ``latest_run_duration_s`` columns the chat's
        # ``list_jobs`` summary view reads).
        self.latest_run_status: dict[str, str] = {}
        self.latest_run_cost_usd: dict[str, float] = {}
        self.latest_run_duration_s: dict[str, float] = {}

    async def save(self, record: JobSpecRecord) -> None:
        self.records[record.spec_id] = record

    async def get(self, spec_id: str) -> JobSpecRecord | None:
        return self.records.get(spec_id)

    async def update_status(
        self, spec_id: str, status: str, *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        run_id: str | None = None,
        cost_usd: float | None = None,
        duration_s: float | None = None,
    ) -> None:
        rec = self.records.get(spec_id)
        if rec is None:
            return
        rec.status = status
        if started_at is not None:
            rec.started_at = started_at
        if completed_at is not None:
            rec.completed_at = completed_at
        if error is not None:
            rec.error = error
        if run_id is not None:
            rec.run_id = run_id
        if cost_usd is not None:
            self.latest_run_cost_usd[spec_id] = cost_usd
        if duration_s is not None:
            self.latest_run_duration_s[spec_id] = duration_s
        if status:
            self.latest_run_status[spec_id] = status

    async def list_pending(self, limit: int = 50) -> list[JobSpecRecord]:
        return [r for r in self.records.values() if r.status == "pending"][:limit]

    # ----- C08 chat-facing surface (Q9) -----

    async def list_by_session(
        self, session_id: str, *, limit: int = 20, offset: int = 0,
    ) -> tuple[list[JobSummary], int]:
        results: list[JobSummary] = []
        for rec in self.records.values():
            ctx = rec.context or {}
            if ctx.get("session_id") == session_id:
                results.append(JobSummary(
                    spec_id=rec.spec_id,
                    prompt=rec.prompt[:200],
                    repo_url=rec.repo_url,
                    tier=rec.tier,
                    status=rec.status,
                    created_at=rec.created_at,
                ))
        total = len(results)
        return results[offset:offset + limit], total

    async def get_status(self, spec_id: str) -> JobStatus | None:
        rec = self.records.get(spec_id)
        if rec is None:
            return None
        return JobStatus(
            spec_id=rec.spec_id, status=rec.status,
            started_at=rec.started_at, completed_at=rec.completed_at,
            error=rec.error, run_id=rec.run_id,
        )

    async def cancel(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or rec.status in ("completed", "failed"):
            return False
        self.cancelled.add(spec_id)
        rec.status = "cancelled"
        return True

    async def pause(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or rec.status in ("completed", "failed", "cancelled"):
            return False
        self.paused.add(spec_id)
        rec.status = "paused"
        return True

    async def resume(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if rec is None or spec_id not in self.paused:
            return False
        self.paused.discard(spec_id)
        rec.status = "running"
        return True

    async def add_comment(self, comment: JobComment) -> None:
        self.comments.setdefault(comment.spec_id, []).append(comment)

    async def get_output(self, spec_id: str) -> JobOutput | None:
        return self.outputs.get(spec_id)

    async def list_comments(
        self, spec_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[JobComment], int]:
        all_items = list(self.comments.get(spec_id, []))
        total = len(all_items)
        return all_items[offset:offset + limit], total


@pytest.fixture
def store() -> _InMemoryStore:
    return _InMemoryStore()


# ---------------------------------------------------------------------------
# JobContext (Pydantic with extra='allow') — C08 Q4
# ---------------------------------------------------------------------------


def test_job_context_accepts_well_known_fields() -> None:
    ctx = JobContext(
        session_id="sess-1",
        agent_id="agent-1",
        request_metadata={"source": "web"},
    )
    assert ctx.session_id == "sess-1"
    assert ctx.agent_id == "agent-1"
    assert ctx.request_metadata == {"source": "web"}


def test_job_context_extra_allow_accepts_unknown_fields() -> None:
    """Pydantic ``extra='allow'`` — the chat can pass arbitrary
    fields without a schema migration.
    """
    ctx = JobContext.model_validate({
        "session_id": "sess-1",
        "custom_field": "anything",
        "another_one": [1, 2, 3],
    })
    # ``to_payload`` returns all fields including extras.
    payload = ctx.to_payload()
    assert payload["session_id"] == "sess-1"
    assert payload["custom_field"] == "anything"
    assert payload["another_one"] == [1, 2, 3]


def test_test_config_accepts_known_and_extra_fields() -> None:
    cfg = TestConfig.model_validate({
        "pre_commands": ["echo hi"],
        "browser": "chrome",
        "future_field": "x",
    })
    assert cfg.pre_commands == ["echo hi"]
    assert cfg.browser == "chrome"
    # The extra field is preserved.
    payload = cfg.to_payload() if hasattr(cfg, "to_payload") else cfg.model_dump()
    assert payload["future_field"] == "x"


def test_job_context_nests_test_config() -> None:
    cfg = TestConfig(browser="chrome", timeout_seconds=60)
    ctx = JobContext(session_id="sess-1", test_config=cfg)
    payload = ctx.to_payload()
    assert payload["test_config"]["browser"] == "chrome"
    assert payload["test_config"]["timeout_seconds"] == 60


def test_job_spec_with_typed_context_roundtrips() -> None:
    spec = JobSpec(
        spec_id="spec-1",
        run_id="run-1",
        source="api",
        prompt="test me",
        context=_build_context(session_id="sess-1", agent_id="agent-1"),
    )
    # The spec's context is a JobContext.
    assert hasattr(spec.context, "session_id")
    # Roundtrip via to_dict + from_dict.
    record = to_record(spec)
    assert record.context["session_id"] == "sess-1"
    assert record.context["agent_id"] == "agent-1"
    # Re-hydrate from a dict.
    spec2 = JobSpec.from_dict({
        "spec_id": "spec-1",
        "run_id": "run-1",
        "source": "api",
        "prompt": "test me",
        "context": {"session_id": "sess-1", "agent_id": "agent-1"},
    })
    assert hasattr(spec2.context, "session_id")
    assert spec2.context.session_id == "sess-1"


# ---------------------------------------------------------------------------
# JobSpecStore protocol extension (C08 Q9)
# ---------------------------------------------------------------------------


async def test_list_by_session_filters_and_truncates(
    store: _InMemoryStore,
) -> None:
    for i in range(5):
        rec = JobSpecRecord(
            spec_id=f"spec-{i}",
            run_id=f"run-{i}",
            source="api",
            prompt=f"x" * 500,
            context={"session_id": "sess-A" if i % 2 == 0 else "sess-B"},
        )
        await store.save(rec)
    a, total = await store.list_by_session("sess-A")
    assert len(a) == 3
    assert total == 3
    for s in a:
        assert s.prompt == "x" * 200  # truncated
    b = await store.list_by_session("sess-B")
    assert len(b) == 2


async def test_get_status_returns_snapshot(store: _InMemoryStore) -> None:
    rec = JobSpecRecord(spec_id="spec-1", run_id="run-1", source="api", prompt="x")
    rec.status = "running"
    rec.started_at = datetime(2026, 6, 21, 14, 0, tzinfo=timezone.utc)
    await store.save(rec)
    s = await store.get_status("spec-1")
    assert s.status == "running"
    assert s.run_id == "run-1"
    assert s.started_at == datetime(2026, 6, 21, 14, 0, tzinfo=timezone.utc)
    # Missing
    assert await store.get_status("nope") is None


async def test_cancel_returns_true_for_running(store: _InMemoryStore) -> None:
    rec = JobSpecRecord(spec_id="spec-1", run_id="run-1", source="api", prompt="x")
    rec.status = "running"
    await store.save(rec)
    ok = await store.cancel("spec-1")
    assert ok is True
    assert "spec-1" in store.cancelled


async def test_cancel_returns_false_for_completed(store: _InMemoryStore) -> None:
    rec = JobSpecRecord(spec_id="spec-1", run_id="run-1", source="api", prompt="x")
    rec.status = "completed"
    await store.save(rec)
    assert await store.cancel("spec-1") is False


async def test_pause_and_resume_roundtrip(store: _InMemoryStore) -> None:
    rec = JobSpecRecord(spec_id="spec-1", run_id="run-1", source="api", prompt="x")
    rec.status = "running"
    await store.save(rec)
    assert (await store.pause("spec-1")) is True
    assert "spec-1" in store.paused
    assert (await store.resume("spec-1")) is True
    assert "spec-1" not in store.paused


async def test_resume_returns_false_when_not_paused(store: _InMemoryStore) -> None:
    rec = JobSpecRecord(spec_id="spec-1", run_id="run-1", source="api", prompt="x")
    rec.status = "running"
    await store.save(rec)
    # Not paused — can't resume.
    assert (await store.resume("spec-1")) is False


async def test_add_comment_and_list(store: _InMemoryStore) -> None:
    rec = JobSpecRecord(spec_id="spec-1", run_id="run-1", source="api", prompt="x")
    await store.save(rec)
    c = JobComment(
        comment_id="c-1", spec_id="spec-1",
        author="alice", body="looks good", kind="approval",
    )
    await store.add_comment(c)
    cs, total = await store.list_comments("spec-1")
    assert len(cs) == 1
    assert total == 1
    assert cs[0].author == "alice"


async def test_get_output_returns_none_when_missing(store: _InMemoryStore) -> None:
    assert await store.get_output("nope") is None


async def test_get_output_returns_stored(store: _InMemoryStore) -> None:
    out = JobOutput(
        spec_id="spec-1", status="completed",
        summary="all green", pr_url="https://github.com/foo/bar/pull/1",
        cost_usd=0.42, duration_s=120.0,
    )
    store.outputs["spec-1"] = out
    got = await store.get_output("spec-1")
    assert got.pr_url == "https://github.com/foo/bar/pull/1"


# ---------------------------------------------------------------------------
# Shared submitter (C08 Q5)
# ---------------------------------------------------------------------------


class _FakeEngine:
    """Minimal OrchestratorEngine stand-in."""

    def __init__(self, run_id: str = "run-x", should_raise: bool = False) -> None:
        self.run_id = run_id
        self.should_raise = should_raise
        self.received: JobSpec | None = None

    async def run_job_spec(self, spec: JobSpec) -> dict[str, Any]:
        self.received = spec
        if self.should_raise:
            raise RuntimeError("dispatch failed")
        return {"run_id": self.run_id, "success": True}


async def test_submit_persists_and_dispatches(store: _InMemoryStore) -> None:
    spec = JobSpec(
        spec_id="spec-1",
        run_id="placeholder",
        source="chat-submission",
        prompt="run the tests",
        repo_url="github.com/foo/bar",
        branch="main",
        tier=1,
        context=_build_context(session_id="sess-1"),
    )
    engine = _FakeEngine(run_id="run-99")
    run_id = await submit_job_to_orchestrator(
        spec, job_spec_store=store,
        orchestrator_engine_factory=lambda: engine,
    )
    assert run_id == "run-99"
    # Spec was persisted.
    rec = await store.get("spec-1")
    assert rec is not None
    assert rec.status == "running"  # orchestrator set it
    # Engine received the spec.
    assert engine.received is spec


async def test_submit_dispatch_failure_returns_empty_but_persists(
    store: _InMemoryStore,
) -> None:
    spec = JobSpec(
        spec_id="spec-1",
        run_id="placeholder",
        source="api",
        prompt="x",
        context={},
    )
    engine = _FakeEngine(should_raise=True)
    run_id = await submit_job_to_orchestrator(
        spec, job_spec_store=store,
        orchestrator_engine_factory=lambda: engine,
    )
    assert run_id == ""
    # But the spec is still persisted (durable).
    assert (await store.get("spec-1")) is not None


async def test_submit_no_store_returns_empty_run_id() -> None:
    spec = JobSpec(
        spec_id="spec-1", run_id="placeholder", source="api", prompt="x",
    )
    engine = _FakeEngine(run_id="run-99")
    run_id = await submit_job_to_orchestrator(
        spec, job_spec_store=None,
        orchestrator_engine_factory=lambda: engine,
    )
    # No store → no persistence. But dispatch still works.
    assert run_id == "run-99"


async def test_submit_no_orchestrator_persists_only() -> None:
    """No orchestrator factory + a store = spec persisted, empty
    run_id returned (soft error)."""
    store = _InMemoryStore()
    spec = JobSpec(
        spec_id="spec-1", run_id="placeholder", source="api", prompt="x",
    )
    run_id = await submit_job_to_orchestrator(
        spec, job_spec_store=store,
        orchestrator_engine_factory=lambda: None,
    )
    assert run_id == ""
    rec = await store.get("spec-1")
    assert rec is not None
    assert rec.status == "pending"  # no orchestrator → no update


async def test_new_spec_id_returns_uuid() -> None:
    a = new_spec_id()
    b = new_spec_id()
    assert a != b
    # 36 chars (8-4-4-4-12 with dashes)
    assert len(a) == 36
    assert a[8] == "-"


async def test_submit_with_module_level_store() -> None:
    """Wires the module-level store (the chat's default)."""
    store = _InMemoryStore()
    set_job_spec_store(store)
    spec = JobSpec(
        spec_id="spec-1", run_id="placeholder", source="api", prompt="x",
    )
    engine = _FakeEngine(run_id="run-99")
    run_id = await submit_job_to_orchestrator(
        spec, job_spec_store=None,
        orchestrator_engine_factory=lambda: engine,
    )
    assert run_id == "run-99"
    # Reset.
    set_job_spec_store(None)
    assert (await store.get("spec-1")) is not None


# ---------------------------------------------------------------------------
# FastAPI router tests
# ---------------------------------------------------------------------------


def _make_request(app: Any) -> Any:
    """Build a minimal Request stub for the router endpoints."""
    from fastapi import Request as FastAPIRequest

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/jobs",
        "headers": [],
        "query_string": b"",
    }
    return FastAPIRequest(scope, receive=AsyncMock())


class _App:
    """Minimal FastAPI app stand-in for state injection."""

    def __init__(self, store: Any, factory: Any) -> None:
        self.state = MagicMock()
        self.state.job_spec_store = store
        self.state.orchestrator_engine_factory = factory


async def test_post_jobs_creates_and_dispatches(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    engine = _FakeEngine(run_id="run-77")
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: engine
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/jobs",
            json={
                "prompt": "fix the bug",
                "repo_url": "github.com/foo/bar",
                "tier": 1,
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["spec_id"]
    assert body["run_id"] == "run-77"
    assert body["status"] == "submitted"
    # Persisted.
    rec = await store.get(body["spec_id"])
    assert rec is not None
    assert rec.prompt == "fix the bug"


async def test_post_jobs_rejects_empty_prompt(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post("/api/jobs", json={"prompt": ""})
    assert resp.status_code == 400


async def test_post_jobs_returns_queued_when_dispatch_fails(
    store: _InMemoryStore,
) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine(should_raise=True)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post("/api/jobs", json={"prompt": "x"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["run_id"] == ""
    assert body["status"] == "queued"


async def test_get_job_returns_full_spec(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    rec = JobSpecRecord(
        spec_id="spec-x", run_id="run-x", source="api",
        prompt="do the thing", repo_url="github.com/foo/bar", tier=2,
    )
    await store.save(rec)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/jobs/spec-x")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prompt"] == "do the thing"
    assert body["tier"] == 2
    assert body["status"] == "pending"


async def test_get_job_404(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/jobs/nope")
    assert resp.status_code == 404


async def test_list_jobs_filters_by_session(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    for i in range(3):
        rec = JobSpecRecord(
            spec_id=f"spec-{i}",
            run_id=f"run-{i}",
            source="api",
            prompt=f"task {i}",
            context={"session_id": "sess-X" if i < 2 else "sess-Y"},
        )
        await store.save(rec)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/jobs?session_id=sess-X")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    # The summary shape (Q10).
    for s in body["items"]:
        assert "prompt" in s
        assert "tier" in s
        assert "latest_run_id" in s


async def test_list_jobs_requires_session_id(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/jobs")
    assert resp.status_code == 400


async def test_cancel_pause_resume(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    rec = JobSpecRecord(
        spec_id="spec-c", run_id="run-c", source="api", prompt="x",
    )
    rec.status = "running"
    await store.save(rec)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Pause.
        r1 = await client.post("/api/jobs/spec-c/pause")
        assert r1.status_code == 200
        assert r1.json()["paused"] is True
        # Resume.
        r2 = await client.post("/api/jobs/spec-c/resume")
        assert r2.json()["resumed"] is True
        # Cancel.
        r3 = await client.post("/api/jobs/spec-c/cancel")
        assert r3.json()["cancelled"] is True


async def test_add_comment_and_get_output(store: _InMemoryStore) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(router)

    rec = JobSpecRecord(
        spec_id="spec-c", run_id="run-c", source="api", prompt="x",
    )
    await store.save(rec)
    store.outputs["spec-c"] = JobOutput(
        spec_id="spec-c", status="completed",
        summary="all green", pr_url="https://github.com/foo/bar/pull/1",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Add a comment.
        r1 = await client.post(
            "/api/jobs/spec-c/comments",
            json={"author": "alice", "body": "lgtm", "kind": "approval"},
        )
        assert r1.status_code == 201
        # Get the spec — comments are returned inline.
        r2 = await client.get("/api/jobs/spec-c")
        assert len(r2.json()["comments"]) == 1
        # Get the output.
        r3 = await client.get("/api/jobs/spec-c/output")
        assert r3.json()["pr_url"] == "https://github.com/foo/bar/pull/1"


async def test_router_returns_503_when_no_store() -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers.jobs import router

    app = FastAPI()
    # No state.job_spec_store, no module-level store.
    # The router falls back to _job_spec_store() which returns None.
    set_job_spec_store(None)
    app.state.job_spec_store = None
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/jobs", json={"prompt": "x"},
        )
    assert resp.status_code == 503
