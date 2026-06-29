"""Tests for the GET /api/observability/compaction endpoint."""
from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.observability import router


def _make_app(*, context_compressor) -> FastAPI:
    app = FastAPI()
    app.state.context_compressor = context_compressor
    app.include_router(router)
    return app


class _FakeCompressor:
    def __init__(self, model: str, context_length: int, threshold_percent: float) -> None:
        self.model = model
        self.context_length = context_length
        self.threshold_percent = threshold_percent


class TestCompactionEndpoint:
    def test_default_threshold(self, monkeypatch):
        monkeypatch.delenv("TESTAI_COMPACTION_THRESHOLD", raising=False)
        from harness import _compressor_utils
        importlib.reload(_compressor_utils)
        from harness.context_compressor import compressor as compressor_mod
        importlib.reload(compressor_mod)
        from api.routers import observability
        importlib.reload(observability)

        from api.routers.observability import router as r
        app = FastAPI()
        app.include_router(r)
        client = TestClient(app)
        data = client.get("/api/observability/compaction").json()
        assert data["threshold_percent"] == 0.85
        assert data["default_threshold_percent"] == 0.85
        assert data["env_var"] == "TESTAI_COMPACTION_THRESHOLD"
        assert data["context_length"] is None
        assert data["compactions_total"] == 0

    def test_with_compressor_attached(self, monkeypatch):
        monkeypatch.delenv("TESTAI_COMPACTION_THRESHOLD", raising=False)
        from api.routers.observability import router as r
        app = FastAPI()
        app.include_router(r)
        app.state.context_compressor = _FakeCompressor(
            model="hermes-grok-4.3",
            context_length=1_048_576,
            threshold_percent=0.85,
        )
        client = TestClient(app)
        data = client.get("/api/observability/compaction").json()
        assert data["context_length"] == 1_048_576
        assert data["model"] == "hermes-grok-4.3"
        assert data["threshold_tokens"] == int(1_048_576 * 0.85)

    def test_threshold_override_reflected(self, monkeypatch):
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "0.92")
        from api.routers.observability import router as r
        app = FastAPI()
        app.include_router(r)
        app.state.context_compressor = _FakeCompressor(
            model="gpt-4o",
            context_length=128_000,
            threshold_percent=0.92,
        )
        client = TestClient(app)
        data = client.get("/api/observability/compaction").json()
        assert data["threshold_percent"] == 0.92
        assert data["threshold_tokens"] == int(128_000 * 0.92)

    def test_compactions_total_and_saved_tokens(self, monkeypatch):
        monkeypatch.delenv("TESTAI_COMPACTION_THRESHOLD", raising=False)
        from harness.context_compressor.compressor import record_compaction
        record_compaction(
            before_tokens=900_000,
            after_tokens=180_000,
            threshold_percent=0.85,
            context_length=1_000_000,
        )
        from api.routers.observability import router as r
        app = FastAPI()
        app.include_router(r)
        app.state.context_compressor = _FakeCompressor(
            model="hermes-grok-4.3",
            context_length=1_000_000,
            threshold_percent=0.85,
        )
        client = TestClient(app)
        data = client.get("/api/observability/compaction").json()
        assert data["compactions_total"] >= 1
        assert data["last_before_tokens"] == 900_000
        assert data["last_after_tokens"] == 180_000
        assert data["last_saved_tokens"] == 720_000
        assert data["last_at"] is not None
