"""Tests for `harness.a2a.server` — Agent Card + JSON-RPC methods.

These tests exercise the HTTP surface end-to-end through
FastAPI's TestClient. The store / orchestrator / sink are
stubbed at the `app.state` level so we can drive the routes
without a real database.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.a2a.server import a2a_router, agent_card_router, build_agent_card


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeStore:
    """In-memory JobSpecStore stand-in for tests.

    Mirrors the JobSpecStore protocol surface (save, get,
    cancel, get_output) the A2A router touches. Records are
    plain dicts so the tests can construct them without the
    full Pydantic model.
    """

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self._outputs: dict[str, dict[str, Any]] = {}
        self._cancel_calls: list[str] = []

    async def save(self, record: Any) -> None:
        if isinstance(record, dict):
            self.records[record["spec_id"]] = record
        else:
            self.records[record.spec_id] = record

    async def get(self, spec_id: str) -> dict[str, Any] | None:
        return self.records.get(spec_id)

    async def cancel(self, spec_id: str) -> bool:
        rec = self.records.get(spec_id)
        if not rec:
            return False
        if rec.get("status") in ("completed", "failed", "cancelled"):
            return False
        self._cancel_calls.append(spec_id)
        rec["status"] = "cancelled"
        rec["completed_at"] = "2026-06-21T00:00:00Z"
        return True

    async def get_output(self, spec_id: str) -> dict[str, Any] | None:
        return self._outputs.get(spec_id)

    def put_output(self, spec_id: str, output: dict[str, Any]) -> None:
        self._outputs[spec_id] = output


class _FakeOrchestrator:
    """No-op orchestrator that records its inputs.

    `run_job_spec` returns a deterministic `run_id` so the
    JSON-RPC response can be asserted.
    """

    def __init__(self) -> None:
        self.submissions: list[Any] = []

    async def run_job_spec(self, spec: Any, **_kwargs: Any) -> dict[str, Any]:
        self.submissions.append(spec)
        return {"run_id": "run-fake-1", "spec_id": spec.spec_id}


def _make_app(store: _FakeStore, sink: Any = None) -> FastAPI:
    """Build a minimal FastAPI app with the A2A router wired."""
    app = FastAPI()
    app.state.job_spec_store = store
    # The factory returns a fresh orchestrator on each call.
    app.state.orchestrator_engine_factory = lambda: _FakeOrchestrator()
    if sink is not None:
        app.state.event_source_sink = sink
    app.include_router(agent_card_router)
    app.include_router(a2a_router)
    return app


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


class TestAgentCard:
    def test_root_well_known_returns_card(self):
        app = _make_app(_FakeStore())
        with TestClient(app) as client:
            r = client.get("/.well-known/agent.json")
        assert r.status_code == 200
        card = r.json()
        assert card["name"] == "TestAI Agent"
        assert card["version"] == "1.0.0"
        assert "a2a/jsonrpc" in card["url"]
        assert card["capabilities"]["streaming"] is True
        assert len(card["skills"]) >= 1
        assert "bearer" in card["authentication"]["schemes"]

    def test_a2a_prefixed_well_known_returns_same_card(self):
        app = _make_app(_FakeStore())
        with TestClient(app) as client:
            r1 = client.get("/.well-known/agent.json")
            r2 = client.get("/a2a/.well-known/agent.json")
        assert r1.json() == r2.json()

    def test_build_agent_card_helper(self):
        card = build_agent_card(url="https://x.example.com/a2a/jsonrpc")
        assert card.url == "https://x.example.com/a2a/jsonrpc"
        assert card.capabilities.streaming is True


# ---------------------------------------------------------------------------
# SendMessage
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_text_message_submits_job(self):
        store = _FakeStore()
        app = _make_app(store)
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": "m-1",
                    "parts": [{"text": "Write tests for the auth module"}],
                }
            },
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        assert r.status_code == 200
        parsed = r.json()
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "req-1"
        task = parsed["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_SUBMITTED"
        assert task["id"]
        # Store has the record. The C08 `submit_job_to_orchestrator`
        # stores a real `JobSpecRecord` dataclass, not a dict —
        # so we use attribute access.
        assert len(store.records) == 1
        rec = next(iter(store.records.values()))
        assert rec.prompt == "Write tests for the auth module"
        assert rec.source == "a2a"

    def test_message_with_url_part_sets_repo_url(self):
        store = _FakeStore()
        app = _make_app(store)
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": "m-1",
                    "parts": [
                        {"text": "Add tests for "},
                        {"url": "https://github.com/acme/api"},
                    ],
                }
            },
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        assert r.status_code == 200
        rec = next(iter(store.records.values()))
        assert rec.repo_url == "https://github.com/acme/api"

    def test_missing_message_returns_invalid_params(self):
        app = _make_app(_FakeStore())
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "SendMessage",
            "params": {},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert parsed["error"]["code"] == -32602  # INVALID_PARAMS

    def test_unknown_method_returns_method_not_found(self):
        app = _make_app(_FakeStore())
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "DoSomethingWeird",
            "params": {},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert parsed["error"]["code"] == -32601  # METHOD_NOT_FOUND

    def test_streaming_method_on_jsonrpc_returns_unsupported(self):
        # SendStreamingMessage requires the SSE endpoint;
        # the JSON-RPC endpoint returns a clean error.
        app = _make_app(_FakeStore())
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "SendStreamingMessage",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": "m-1",
                    "parts": [{"text": "x"}],
                }
            },
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert parsed["error"]["code"] == -32003  # UNSUPPORTED_OPERATION


# ---------------------------------------------------------------------------
# GetTask
# ---------------------------------------------------------------------------


class TestGetTask:
    def test_get_existing_task(self):
        from datetime import datetime, timezone
        store = _FakeStore()
        store.records["spec-1"] = {
            "spec_id": "spec-1",
            "run_id": "run-1",
            "source": "a2a",
            "prompt": "test",
            "repo_url": "",
            "branch": "main",
            "sha": "",
            "tier": 1,
            "capabilities": [],
            "approval": {},
            "context": {"session_id": "ctx-x"},
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
        }
        app = _make_app(store)
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "GetTask",
            "params": {"id": "spec-1"},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert "error" not in parsed
        task = parsed["result"]["task"]
        assert task["id"] == "spec-1"
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert task["contextId"] == "ctx-x"

    def test_get_with_output_attaches_artifacts(self):
        from datetime import datetime, timezone
        store = _FakeStore()
        store.records["spec-1"] = {
            "spec_id": "spec-1",
            "run_id": "run-1",
            "source": "a2a",
            "prompt": "test",
            "repo_url": "",
            "branch": "main",
            "sha": "",
            "tier": 1,
            "capabilities": [],
            "approval": {},
            "context": {},
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
        }
        store.put_output("spec-1", {
            "spec_id": "spec-1",
            "status": "completed",
            "summary": "All done",
            "pr_url": "https://github.com/x/y/pull/1",
            "artifacts": [],
        })
        app = _make_app(store)
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "GetTask",
            "params": {"id": "spec-1"},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        task = r.json()["result"]["task"]
        names = {a["name"] for a in task["artifacts"]}
        assert "summary" in names
        assert "pull_request" in names

    def test_get_unknown_task_returns_not_found(self):
        app = _make_app(_FakeStore())
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "GetTask",
            "params": {"id": "does-not-exist"},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert parsed["error"]["code"] == -32001  # TASK_NOT_FOUND


# ---------------------------------------------------------------------------
# CancelTask
# ---------------------------------------------------------------------------


class TestCancelTask:
    def _seed(self, store: _FakeStore, status: str = "running") -> str:
        spec_id = "spec-cancel"
        store.records[spec_id] = {
            "spec_id": spec_id,
            "run_id": "run-cancel",
            "source": "a2a",
            "prompt": "x",
            "repo_url": "",
            "branch": "main",
            "sha": "",
            "tier": 1,
            "capabilities": [],
            "approval": {},
            "context": {},
            "status": status,
        }
        return spec_id

    def test_cancel_running_task(self):
        store = _FakeStore()
        self._seed(store, status="running")
        app = _make_app(store)
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "CancelTask",
            "params": {"id": "spec-cancel"},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        task = parsed["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_CANCELED"
        assert "spec-cancel" in store._cancel_calls

    def test_cancel_completed_task_returns_not_cancellable(self):
        store = _FakeStore()
        self._seed(store, status="completed")
        app = _make_app(store)
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "CancelTask",
            "params": {"id": "spec-cancel"},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert parsed["error"]["code"] == -32002  # TASK_NOT_CANCELABLE

    def test_cancel_unknown_task(self):
        app = _make_app(_FakeStore())
        body = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "CancelTask",
            "params": {"id": "nope"},
        }
        with TestClient(app) as client:
            r = client.post("/a2a/jsonrpc", json=body)
        parsed = r.json()
        assert parsed["error"]["code"] == -32001  # TASK_NOT_FOUND
