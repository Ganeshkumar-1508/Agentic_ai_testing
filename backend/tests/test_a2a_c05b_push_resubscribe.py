"""Tests for C05-b: A2A ``tasks/resubscribe`` + push-notification-config methods."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.a2a.server import a2a_router, _push_configs


def _make_app() -> FastAPI:
    from harness.store.protocols import JobSpecRecord, JobSummary, JobStatus

    class _FakeStore:
        def __init__(self):
            self.records: dict[str, JobSpecRecord] = {}
            self.records["spec-resub"] = JobSpecRecord(
                spec_id="spec-resub",
                run_id="run-1",
                source="a2a",
                prompt="p",
                context={"session_id": "ctx-x"},
                status="completed",
            )

        async def save(self, rec):
            self.records[rec.spec_id] = rec

        async def get(self, spec_id):
            return self.records.get(spec_id)

        async def get_status(self, spec_id):
            rec = self.records.get(spec_id)
            if rec is None:
                return None
            return JobStatus(
                spec_id=rec.spec_id, status=rec.status,
                run_id=rec.run_id,
            )

        async def cancel(self, spec_id):
            return True

        async def pause(self, spec_id):
            return True

        async def resume(self, spec_id):
            return True

        async def get_output(self, spec_id):
            return None

        async def list_by_session(self, session_id, *, limit=20, offset=0):
            return [], 0

        async def list_comments(self, spec_id, *, limit=50, offset=0):
            return [], 0

        async def list_pending(self, limit=50):
            return []

        async def add_comment(self, comment):
            pass

        async def update_status(self, *args, **kwargs):
            pass

    store = _FakeStore()

    class _FakeEngine:
        async def run_job_spec(self, spec):
            return None

    app = FastAPI()
    app.state.job_spec_store = store
    app.state.orchestrator_engine_factory = lambda: _FakeEngine()
    app.include_router(a2a_router)
    return app


@pytest.fixture
def client():
    _push_configs.clear()
    with TestClient(_make_app()) as c:
        yield c


def _post(client, method, params):
    return client.post(
        "/a2a/jsonrpc",
        json={"jsonrpc": "2.0", "id": "1", "method": method, "params": params},
    )


class TestResubscribe:
    def test_terminal_task_returns_task_object(self, client):
        r = _post(client, "tasks/resubscribe", {"id": "spec-resub"})
        assert r.status_code == 200
        body = r.json()
        assert "error" not in body
        task = body["result"]["task"]
        assert task["id"] == "spec-resub"
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert body["result"]["hint"].startswith("Task is terminal")

    def test_unknown_task_returns_not_found(self, client):
        r = _post(client, "tasks/resubscribe", {"id": "does-not-exist"})
        body = r.json()
        assert body["error"]["code"] == -32001

    def test_missing_id_returns_invalid_params(self, client):
        r = _post(client, "tasks/resubscribe", {})
        body = r.json()
        assert body["error"]["code"] == -32602


class TestPushConfig:
    def test_set_then_list(self, client):
        r1 = _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://example.com/hook",
        })
        assert r1.status_code == 200
        config = r1.json()["result"]["config"]
        assert config["url"] == "https://example.com/hook"
        assert config["task_id"] == "spec-pn"
        assert "config_id" in config

        r2 = _post(client, "tasks/pushNotificationConfig/list", {"id": "spec-pn"})
        configs = r2.json()["result"]["configs"]
        assert len(configs) == 1
        assert configs[0]["config_id"] == config["config_id"]

    def test_set_with_custom_config_id(self, client):
        r = _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://example.com/hook",
            "config_id": "pn-custom",
        })
        assert r.json()["result"]["config"]["config_id"] == "pn-custom"

    def test_set_existing_url_updates_in_place(self, client):
        _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://example.com/hook",
            "auth_token": "v1",
        })
        r = _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://example.com/hook",
            "auth_token": "v2",
        })
        configs = _post(client, "tasks/pushNotificationConfig/list", {"id": "spec-pn"}).json()["result"]["configs"]
        assert len(configs) == 1
        assert configs[0]["auth_token"] == "v2"

    def test_get_specific_config(self, client):
        _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://a.example.com/hook",
            "config_id": "pn-a",
        })
        _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://b.example.com/hook",
            "config_id": "pn-b",
        })
        r = _post(client, "tasks/pushNotificationConfig/get", {
            "id": "spec-pn",
            "config_id": "pn-b",
        })
        assert r.json()["result"]["config"]["url"] == "https://b.example.com/hook"

    def test_get_missing_returns_not_found(self, client):
        r = _post(client, "tasks/pushNotificationConfig/get", {"id": "spec-pn"})
        body = r.json()
        assert body["error"]["code"] == -32001

    def test_delete_specific(self, client):
        _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://a.example.com/hook",
            "config_id": "pn-a",
        })
        _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://b.example.com/hook",
            "config_id": "pn-b",
        })
        r = _post(client, "tasks/pushNotificationConfig/delete", {
            "id": "spec-pn",
            "config_id": "pn-a",
        })
        assert r.json()["result"]["deleted"] is True
        configs = _post(client, "tasks/pushNotificationConfig/list", {"id": "spec-pn"}).json()["result"]["configs"]
        assert len(configs) == 1
        assert configs[0]["config_id"] == "pn-b"

    def test_delete_all_when_no_config_id(self, client):
        _post(client, "tasks/pushNotificationConfig/set", {
            "id": "spec-pn",
            "url": "https://a.example.com/hook",
        })
        r = _post(client, "tasks/pushNotificationConfig/delete", {"id": "spec-pn"})
        assert r.json()["result"]["deleted"] is True
        configs = _post(client, "tasks/pushNotificationConfig/list", {"id": "spec-pn"}).json()["result"]["configs"]
        assert len(configs) == 0

    def test_delete_missing_returns_not_found(self, client):
        r = _post(client, "tasks/pushNotificationConfig/delete", {"id": "spec-pn"})
        body = r.json()
        assert body["error"]["code"] == -32001

    def test_set_requires_url(self, client):
        r = _post(client, "tasks/pushNotificationConfig/set", {"id": "spec-pn"})
        body = r.json()
        assert body["error"]["code"] == -32602

    def test_set_requires_id(self, client):
        r = _post(client, "tasks/pushNotificationConfig/set", {"url": "https://x"})
        body = r.json()
        assert body["error"]["code"] == -32602
