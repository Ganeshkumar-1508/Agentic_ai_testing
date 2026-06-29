"""Tests for the GET /api/observability/status endpoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.observability import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class TestObservabilityStatus:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("OTEL_ENABLED", raising=False)
        from harness import trace as trace_mod
        importlib_reload = __import__("importlib").reload
        importlib_reload(trace_mod)
        client = TestClient(_make_app())
        r = client.get("/api/observability/status")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is False
        assert "endpoint" in data
        assert "service_name" in data
        assert "span_counts" in data
        assert "last_span_at" in data

    def test_returns_expected_shape(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        from harness import trace as trace_mod
        __import__("importlib").reload(trace_mod)
        client = TestClient(_make_app())
        r = client.get("/api/observability/status")
        data = r.json()
        assert set(data.keys()) == {
            "enabled",
            "available",
            "endpoint",
            "service_name",
            "service_version",
            "span_counts",
            "last_span_at",
        }

    def test_endpoint_reflects_env(self, monkeypatch):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel.example:4317")
        monkeypatch.setenv("OTEL_SERVICE_NAME", "testai-prod")
        from harness import trace as trace_mod
        __import__("importlib").reload(trace_mod)
        client = TestClient(_make_app())
        data = client.get("/api/observability/status").json()
        assert data["endpoint"] == "http://otel.example:4317"
        assert data["service_name"] == "testai-prod"

    def test_span_counts_reflect_handler_state(self, monkeypatch):
        from harness import trace as trace_mod
        monkeypatch.setenv("OTEL_ENABLED", "false")
        __import__("importlib").reload(trace_mod)
        handler = trace_mod.get_otel_handler()
        handler._span_counts["chat"] = 12
        handler._span_counts["subagent_invoke"] = 3
        client = TestClient(_make_app())
        data = client.get("/api/observability/status").json()
        assert data["span_counts"]["chat"] == 12
        assert data["span_counts"]["subagent_invoke"] == 3
