"""Tests for the lazy ``DeliveryRouter`` + class-based adapter registry.

Covers:
  * Registry shape (built-in 5 platforms).
  * Lazy construction (no adapter is instantiated until first use).
  * Per-platform instance caching (second call returns the same instance).
  * Custom registry + ``register_platform`` / ``unregister_platform``.
  * Config loading from a fake DB (row, missing row, malformed JSON,
    DB error).
  * End-to-end ``deliver()`` against ``local`` and platform targets,
    including the oversized-content overflow path.
  * Failure isolation — one bad target does not abort the others.
  * ``pr_manager.py`` no-arg construction path.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Optional

import pytest

from harness.delivery.adapters import ADAPTER_REGISTRY
from harness.delivery.adapters.base import AdapterConfig, BaseAdapter, DeliveryTarget
from harness.delivery.router import (
    MAX_CONTENT_CHARS,
    OUTPUT_DIR,
    DeliveryRouter,
)


# ---------------------------------------------------------------------------
# Test double adapters
# ---------------------------------------------------------------------------


class _EchoAdapter(BaseAdapter):
    """Adapter that records the last call and echoes the chat_id."""

    name = "echo"

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__(config)
        self.calls: list[tuple[str, str, Optional[dict]]] = []

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((chat_id, content, metadata))
        return {"ok": True, "echoed": content, "chat_id": chat_id}

    async def health(self) -> bool:
        return True


class _BoomAdapter(BaseAdapter):
    """Adapter that always raises — used to verify failure isolation."""

    name = "boom"

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    async def health(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fake DB
# ---------------------------------------------------------------------------


class _FakeDB:
    """Minimal async DB double. ``fetch`` is a method, returns a list of dicts."""

    def __init__(self, rows: list[dict] | None = None, raises: bool = False):
        self.rows = rows or []
        self.raises = raises
        self.calls: list[tuple] = []

    async def fetch(self, query: str, *args):
        self.calls.append((query, args))
        if self.raises:
            raise RuntimeError("db unavailable")
        # Honor the platform WHERE clause
        if "platform_configs" in query and args:
            return [r for r in self.rows if r.get("platform") == args[0]]
        return self.rows


# ---------------------------------------------------------------------------
# Registry + construction
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_built_in_registry_has_five_platforms(self):
        assert set(ADAPTER_REGISTRY) == {
            "slack", "teams", "telegram", "email", "custom_notifier",
        }

    def test_router_uses_built_in_registry_by_default(self):
        r = DeliveryRouter()
        assert r.known_platforms() == sorted(ADAPTER_REGISTRY)

    def test_router_with_no_db_constructs(self):
        # Mirrors the pr_manager.py:350 call site
        r = DeliveryRouter()
        assert r._db is None
        assert r.cached_platforms() == []

    def test_router_with_custom_registry(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        assert r.known_platforms() == ["echo"]
        assert "slack" not in r.known_platforms()


class TestRegisterPlatform:
    def test_register_new_platform(self):
        r = DeliveryRouter()
        r.register_platform("echo", _EchoAdapter)
        assert "echo" in r.known_platforms()

    def test_register_overrides_existing(self):
        r = DeliveryRouter()
        r.register_platform("slack", _EchoAdapter)
        assert r._registry["slack"] is _EchoAdapter

    def test_register_drops_cached_instance(self):
        r = DeliveryRouter(db=_FakeDB([{
            "platform": "echo", "config": {"api_token": "old"},
        }]))
        r.register_platform("echo", _EchoAdapter)
        first = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert isinstance(first, _EchoAdapter)
        # Now switch to a different class — cached instance must be dropped.
        class _OtherEcho(BaseAdapter):
            name = "other_echo"
            async def send(self, chat_id, content, metadata=None): return {}
            async def health(self): return True
        r.register_platform("echo", _OtherEcho)
        second = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert isinstance(second, _OtherEcho)

    def test_unregister(self):
        r = DeliveryRouter()
        r.register_platform("echo", _EchoAdapter)
        r.unregister_platform("echo")
        assert "echo" not in r.known_platforms()


# ---------------------------------------------------------------------------
# Lazy loading
# ---------------------------------------------------------------------------


class TestLazyLoading:
    def test_no_adapter_instantiated_until_first_use(self):
        """Constructor must not touch the DB at all."""
        db = _FakeDB([{"platform": "echo", "config": {"api_token": "x"}}])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        assert db.calls == []
        assert r.cached_platforms() == []

    def test_first_use_loads_config_from_db(self):
        db = _FakeDB([{
            "platform": "echo",
            "config": {"api_token": "abc", "webhook_url": "https://hook"},
        }])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert isinstance(adapter, _EchoAdapter)
        assert adapter.config.api_token == "abc"
        assert adapter.config.webhook_url == "https://hook"
        assert len(db.calls) == 1

    def test_second_use_returns_cached_instance(self):
        db = _FakeDB([{"platform": "echo", "config": {"api_token": "x"}}])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        a1 = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        a2 = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert a1 is a2
        # Only one DB hit — the second call hit the cache.
        assert len(db.calls) == 1
        assert r.cached_platforms() == ["echo"]

    def test_unknown_platform_raises(self):
        r = DeliveryRouter(registry={})
        with pytest.raises(ValueError, match="Unknown delivery platform"):
            asyncio.get_event_loop().run_until_complete(r._get_adapter("nope"))

    def test_db_error_falls_back_to_empty_config(self):
        """A failing DB should not break deliveries; default config is OK."""
        db = _FakeDB(raises=True)
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert isinstance(adapter, _EchoAdapter)
        assert adapter.config == AdapterConfig()  # all fields default

    def test_missing_row_falls_back_to_empty_config(self):
        db = _FakeDB(rows=[])  # no rows
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert isinstance(adapter, _EchoAdapter)
        assert adapter.config == AdapterConfig()

    def test_malformed_json_config_falls_back_to_empty(self):
        db = _FakeDB([{"platform": "echo", "config": "{not json"}])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert adapter.config == AdapterConfig()

    def test_no_db_means_empty_config(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert adapter.config == AdapterConfig()

    def test_string_config_field_parsed(self):
        """Some DB layers return JSON-as-string in the row."""
        db = _FakeDB([{
            "platform": "echo",
            "config": json.dumps({"api_token": "from-string", "webhook_url": "w"}),
        }])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert adapter.config.api_token == "from-string"

    def test_dict_like_row_with_get(self):
        """Support both dict and asyncpg-style Record rows."""

        class _Record(dict):
            pass

        rec = _Record(platform="echo", config={"api_token": "x"})
        db = _FakeDB([rec])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        adapter = asyncio.get_event_loop().run_until_complete(r._get_adapter("echo"))
        assert adapter.config.api_token == "x"


# ---------------------------------------------------------------------------
# End-to-end deliver()
# ---------------------------------------------------------------------------


class TestDeliver:
    def test_local_target_writes_to_disk(self, tmp_path):
        r = DeliveryRouter(output_dir=tmp_path / "delivery")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("hello world", [DeliveryTarget(platform="local")], job_id="j1", job_name="Job 1")
        )
        assert "local" in results
        assert results["local"]["success"] is True
        written = list((tmp_path / "delivery" / "j1").glob("*.md"))
        assert len(written) == 1
        text = written[0].read_text()
        assert "hello world" in text
        assert "Job 1" in text

    def test_platform_target_routes_to_adapter(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        target = DeliveryTarget(platform="echo", chat_id="C123")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("payload", [target])
        )
        assert "echo:C123" in results
        assert results["echo:C123"]["success"] is True
        assert results["echo:C123"]["result"]["echoed"] == "payload"
        adapter = r._instances["echo"]
        assert adapter.calls == [("C123", "payload", None)]

    def test_failure_isolation(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter, "boom": _BoomAdapter})
        targets = [
            DeliveryTarget(platform="echo", chat_id="C1"),
            DeliveryTarget(platform="boom", chat_id="C2"),
            DeliveryTarget(platform="echo", chat_id="C3"),
        ]
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("hello", targets)
        )
        assert results["echo:C1"]["success"] is True
        assert results["boom:C2"]["success"] is False
        assert "kaboom" in results["boom:C2"]["error"]
        assert results["echo:C3"]["success"] is True  # not aborted by boom

    def test_missing_chat_id_raises(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        target = DeliveryTarget(platform="echo", chat_id=None)
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("x", [target])
        )
        assert results["echo"]["success"] is False
        assert "chat_id" in results["echo"]["error"]

    def test_oversized_content_truncated_and_local_stored(self, tmp_path):
        r = DeliveryRouter(
            registry={"echo": _EchoAdapter},
            output_dir=tmp_path / "delivery",
        )
        target = DeliveryTarget(platform="echo", chat_id="C1")
        big = "x" * (MAX_CONTENT_CHARS + 100)
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver(big, [target], job_id="j2", job_name="Big Job")
        )
        assert results["echo:C1"]["success"] is True
        adapter = r._instances["echo"]
        # Sent content was truncated
        assert len(adapter.calls[0][1]) < len(big)
        assert "truncated" in adapter.calls[0][1]
        # Full content stored locally
        stored = list((tmp_path / "delivery" / "misc").glob("*.md"))
        assert any("x" * 100 in p.read_text() for p in stored)

    def test_unknown_platform_returns_failure(self):
        r = DeliveryRouter(registry={})  # empty registry
        target = DeliveryTarget(platform="phantom", chat_id="C1")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("x", [target])
        )
        assert results["phantom:C1"]["success"] is False
        assert "Unknown delivery platform" in results["phantom:C1"]["error"]


class TestDeliverExtended:
    """Additional edge-case tests for the DeliveryRouter."""

    def test_deliver_empty_targets(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("hello", [])
        )
        assert results == {}

    def test_deliver_no_content(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        target = DeliveryTarget(platform="echo", chat_id="C1")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("", [target])
        )
        assert results["echo:C1"]["success"] is True
        adapter = r._instances["echo"]
        assert adapter.calls[0][1] == ""

    def test_deliver_none_content(self):
        """None content causes a TypeError in len(); verify failure is caught."""
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        target = DeliveryTarget(platform="echo", chat_id="C1")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver(None, [target])
        )
        assert results["echo:C1"]["success"] is False

    def test_deliver_with_metadata(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        target = DeliveryTarget(platform="echo", chat_id="C1")
        meta = {"run_id": "r-1", "status": "completed"}
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("result", [target], metadata=meta)
        )
        adapter = r._instances["echo"]
        _, _, passed_meta = adapter.calls[0]
        assert passed_meta == meta

    def test_deliver_same_target_twice_uses_cached_adapter(self):
        db = _FakeDB([{"platform": "echo", "config": {"api_token": "x"}}])
        r = DeliveryRouter(db=db, registry={"echo": _EchoAdapter})
        t = DeliveryTarget(platform="echo", chat_id="C1")
        asyncio.get_event_loop().run_until_complete(r.deliver("a", [t]))
        asyncio.get_event_loop().run_until_complete(r.deliver("b", [t]))
        assert len(db.calls) == 1  # Only one DB hit

    def test_deliver_content_just_under_limit(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        t = DeliveryTarget(platform="echo", chat_id="C1")
        just_under = "x" * (MAX_CONTENT_CHARS - 1)
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver(just_under, [t])
        )
        adapter = r._instances["echo"]
        assert len(adapter.calls[0][1]) == MAX_CONTENT_CHARS - 1
        assert "truncated" not in adapter.calls[0][1]
        assert results["echo:C1"]["success"] is True

    def test_deliver_content_at_limit(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        t = DeliveryTarget(platform="echo", chat_id="C1")
        at_limit = "x" * MAX_CONTENT_CHARS
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver(at_limit, [t])
        )
        assert results["echo:C1"]["success"] is True
        assert "truncated" not in results["echo:C1"]["result"]["echoed"]

    def test_deliver_local_without_job_id(self, tmp_path):
        r = DeliveryRouter(output_dir=tmp_path / "delivery")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("content", [DeliveryTarget(platform="local")])
        )
        assert "local" in results
        assert results["local"]["success"] is True
        stored = list((tmp_path / "delivery" / "misc").glob("*.md"))
        assert len(stored) == 1

    def test_deliver_local_with_full_metadata(self, tmp_path):
        r = DeliveryRouter(output_dir=tmp_path / "delivery")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver(
                "content",
                [DeliveryTarget(platform="local")],
                job_id="j42",
                job_name="Test Job",
                metadata={"env": "staging"},
            )
        )
        text = (tmp_path / "delivery" / "j42").glob("*").__next__().read_text()
        assert "Test Job" in text
        assert "j42" in text
        assert "staging" in text

    def test_deliver_local_creates_output_dir(self, tmp_path):
        deep_dir = tmp_path / "a" / "b" / "c" / "delivery"
        r = DeliveryRouter(output_dir=deep_dir)
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("x", [DeliveryTarget(platform="local")])
        )
        assert deep_dir.exists()
        assert results["local"]["success"] is True

    def test_deliver_multiple_platforms(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        targets = [
            DeliveryTarget(platform="local"),
            DeliveryTarget(platform="echo", chat_id="C1"),
        ]
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("multi", targets)
        )
        assert "local" in results
        assert "echo:C1" in results
        assert results["local"]["success"] is True
        assert results["echo:C1"]["success"] is True

    def test_register_platform_after_delivery(self):
        r = DeliveryRouter()
        class LateAdapter(BaseAdapter):
            name = "late"
            async def send(self, chat_id, content, metadata=None):
                return {"ok": True}
            async def health(self):
                return True
        r.register_platform("late", LateAdapter)
        t = DeliveryTarget(platform="late", chat_id="C1")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("late binding", [t])
        )
        assert results["late:C1"]["success"] is True

    def test_unregister_platform_makes_it_unavailable(self):
        r = DeliveryRouter(registry={"echo": _EchoAdapter})
        r.unregister_platform("echo")
        t = DeliveryTarget(platform="echo", chat_id="C1")
        results = asyncio.get_event_loop().run_until_complete(
            r.deliver("gone", [t])
        )
        assert results["echo:C1"]["success"] is False


class TestDeliveryTargetParse:
    def test_local(self):
        t = DeliveryTarget.parse("local")
        assert t.platform == "local"

    def test_origin(self):
        t = DeliveryTarget.parse("origin", origin="slack")
        assert t.is_origin is True
        assert t.platform == "slack"

    def test_explicit_chat(self):
        t = DeliveryTarget.parse("slack:#general")
        assert t.platform == "slack"
        assert t.chat_id == "#general"
        assert t.is_explicit is True

    def test_explicit_chat_with_thread(self):
        t = DeliveryTarget.parse("slack:#general:thread-1")
        assert t.thread_id == "thread-1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
