"""Tests for BackendFactory, resolve_backend_type, and backend_configs."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from harness.backends.factory import (
    _BACKEND_REGISTRY,
    clear_backend_cache,
    get_backend,
    get_backend_class,
    register_backend,
    resolve_backend_type,
)
from harness.backends.local import LocalEnvironment


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_backend_cache()


class FakeDB:
    def __init__(self):
        self.rows: dict[str, list] = {}

    def fetchone(self, query: str, params: list | None = None) -> tuple | None:
        key = query.split("FROM")[-1].strip().split("WHERE")[0].strip() if "FROM" in query else ""
        if "sessions" in query.lower():
            return (self.rows.get("sessions", "local"),)
        if "sandbox_config" in query.lower():
            return (self.rows.get("sandbox_config"),)
        return None

    def execute(self, query: str, params: list | None = None) -> None:
        pass


class TestRegisterBackend:
    def test_register_new_backend(self):
        class FakeBackend:
            pass
        register_backend("fake", FakeBackend)
        assert "fake" in _BACKEND_REGISTRY
        assert _BACKEND_REGISTRY["fake"] is FakeBackend

    def test_register_overwrites_existing(self):
        class B1:
            pass
        class B2:
            pass
        register_backend("overwrite_test", B1)
        register_backend("overwrite_test", B2)
        assert _BACKEND_REGISTRY["overwrite_test"] is B2

    def test_registry_contains_local_docker_ssh(self):
        assert "local" in _BACKEND_REGISTRY
        assert "docker" in _BACKEND_REGISTRY
        assert "ssh" in _BACKEND_REGISTRY


class TestGetBackendClass:
    def test_returns_local_class(self):
        cls = get_backend_class("local")
        assert cls is LocalEnvironment

    def test_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown backend_type"):
            get_backend_class("nonexistent")


class TestResolveBackendType:
    def test_returns_from_sessions_table(self):
        db = FakeDB()
        db.rows["sessions"] = "docker"
        assert resolve_backend_type(db, "sess-1") == "docker"

    def test_returns_from_sandbox_config(self):
        db = FakeDB()
        db.rows["sessions"] = ""
        db.rows["sandbox_config"] = "ssh"
        assert resolve_backend_type(db, "sess-1") == "ssh"

    def test_returns_default_when_none_set(self):
        db = FakeDB()
        assert resolve_backend_type(db, "sess-1", default="local") == "local"

    def test_returns_default_when_db_returns_none(self):
        db = MagicMock()
        db.fetchone.return_value = None
        assert resolve_backend_type(db, "sess-1", default="local") == "local"


class TestGetBackend:
    def test_returns_local_backend(self):
        db = FakeDB()
        backend = get_backend(db, "sess-1", backend_type="local")
        assert isinstance(backend, LocalEnvironment)
        assert backend.session_id == "sess-1"

    def test_backend_type_resolved_from_db(self):
        db = FakeDB()
        db.rows["sessions"] = "local"
        backend = get_backend(db, "sess-1")
        assert isinstance(backend, LocalEnvironment)

    def test_passes_cwd_and_timeout(self):
        db = FakeDB()
        backend = get_backend(db, "sess-1", backend_type="local", cwd="/tmp", timeout=60)
        assert backend.cwd == "/tmp"
        assert backend.timeout == 60

    def test_passes_env(self):
        db = FakeDB()
        backend = get_backend(db, "sess-1", backend_type="local", env={"KEY": "val"})
        assert backend.env.get("KEY") == "val"

    def test_raises_on_unknown_backend_type(self):
        db = FakeDB()
        with pytest.raises(ValueError, match="Unknown backend_type"):
            get_backend(db, "sess-1", backend_type="nonexistent")


class TestBackendConfigs:
    def test_get_backend_config_empty_when_no_row(self):
        db = MagicMock()
        db.fetchone.return_value = None
        from harness.backends.backend_configs import get_backend_config
        assert get_backend_config(db, "sess-1") == {}

    def test_get_backend_config_returns_dict(self):
        db = MagicMock()
        db.fetchone.return_value = ({"host": "example.com", "port": 2222},)
        from harness.backends.backend_configs import get_backend_config
        cfg = get_backend_config(db, "sess-1")
        assert cfg["host"] == "example.com"
        assert cfg["port"] == 2222

    def test_get_backend_config_parses_json_string(self):
        db = MagicMock()
        db.fetchone.return_value = (json.dumps({"user": "admin"}),)
        from harness.backends.backend_configs import get_backend_config
        cfg = get_backend_config(db, "sess-1")
        assert cfg["user"] == "admin"

    def test_upsert_backend_config_calls_execute(self):
        db = MagicMock()
        from harness.backends.backend_configs import upsert_backend_config
        upsert_backend_config(db, "sess-1", {"host": "x", "port": 22})
        assert db.execute.called
        call_args = db.execute.call_args[0]
        assert "session_backend_configs" in call_args[0]
        assert "ON CONFLICT" in call_args[0]
