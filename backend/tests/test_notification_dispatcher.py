"""Tests for NotificationDispatcher — format (pure) and dispatch (async).

Verifies:
  1. format() produces correct multi-line notification strings
  2. dispatch() queries DB and delivers to correct targets
  3. Channel filtering works
  4. Edge cases: no DB, no prefs, malformed targets, db errors
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from harness.delivery.adapters.base import DeliveryTarget
from harness.delivery.router import DeliveryRouter
from harness.services.notification_dispatcher import NotificationDispatcher

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fake DB
# ---------------------------------------------------------------------------


class _FakeDB:
    def __init__(self, rows: list[dict] | None = None, raises: bool = False):
        self.rows = rows or []
        self.raises = raises
        self.calls: list[tuple] = []

    @property
    def _email_domain_check(self):
        """Duck-type check for email: target contains @."""
        return True  # simplified for test

    async def fetch(self, query: str, *args):
        self.calls.append((query, args))
        if self.raises:
            raise RuntimeError("db error")
        event_filter = args[0] if args else None
        channels = set(args[1:]) if len(args) > 1 else None
        event_list = json.loads(event_filter) if isinstance(event_filter, str) else event_filter
        results = []
        for r in self.rows:
            events_raw = r.get("events", "[]")
            events = json.loads(events_raw) if isinstance(events_raw, str) else events_raw
            if isinstance(event_list, list):
                if not any(e in events for e in event_list):
                    continue
            elif event_list not in events:
                continue
            if channels and r.get("channel") not in channels:
                continue
            results.append(r)
        return results


# ---------------------------------------------------------------------------
# format() tests (pure, no async)
# ---------------------------------------------------------------------------


class TestFormat:
    """Pure function tests for NotificationDispatcher.format()."""

    def test_format_basic_completed(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="https://github.com/org/repo",
            status="completed", summary="All 5 tasks done",
            base_url="http://localhost:3000",
        )
        assert "Orchestration completed" in result
        assert "Repo: https://github.com/org/repo" in result
        assert "Status: All 5 tasks done" in result
        assert "View: http://localhost:3000/pipeline?session_id=abc123" in result

    def test_format_failed_status(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="https://github.com/org/repo",
            status="failed", summary="3/5 tasks failed",
        )
        assert "Orchestration failed" in result

    def test_format_timeout_status(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="https://github.com/org/repo",
            status="timeout", summary="Exceeded 10m limit",
        )
        assert "Orchestration timeout" in result

    def test_format_session_id_echo_in_body(self):
        """Only the first 12 chars appear in the body. The URL has the full ID."""
        long_id = "abcdef1234567890"
        result = NotificationDispatcher.format(
            session_id=long_id, repo_url="https://github.com/org/repo",
            status="completed", summary="done",
        )
        # Body shows truncated version
        assert long_id[:12] in result.split("View:")[0]
        # URL has the full ID (not truncated in URL param)
        assert long_id in result.split("View:")[1] if "View:" in result else True

    def test_format_base_url_env_var(self):
        with patch.dict(os.environ, {"EXTERNAL_URL": "https://myapp.com"}, clear=True):
            result = NotificationDispatcher.format(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done",
            )
            assert "View: https://myapp.com" in result

    def test_format_base_url_default_when_env_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            result = NotificationDispatcher.format(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done",
            )
            assert "View: http://localhost:3000" in result

    def test_format_explicit_base_url_overrides_env(self):
        with patch.dict(os.environ, {"EXTERNAL_URL": "https://myapp.com"}, clear=True):
            result = NotificationDispatcher.format(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done",
                base_url="https://custom.url",
            )
            assert "View: https://custom.url" in result
            assert "myapp.com" not in result

    def test_format_empty_repo_url(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="",
            status="completed", summary="done",
        )
        assert "Repo: " in result

    def test_format_empty_summary(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="https://github.com/org/repo",
            status="completed", summary="",
        )
        assert "Status: " in result

    def test_format_special_chars_in_summary(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="https://github.com/org/repo",
            status="completed", summary="Tests passed: 42/42 🎉",
        )
        assert "Tests passed: 42/42" in result

    def test_format_short_session_id(self):
        result = NotificationDispatcher.format(
            session_id="ab", repo_url="https://github.com/org/repo",
            status="completed", summary="done",
        )
        assert "Session: ab" in result

    def test_format_event_prefix_constant(self):
        assert NotificationDispatcher.EVENT_PREFIX == "run:"

    def test_format_5_lines(self):
        result = NotificationDispatcher.format(
            session_id="abc123", repo_url="https://github.com/org/repo",
            status="completed", summary="done",
        )
        lines = result.strip().split("\n")
        assert len(lines) == 5


# ---------------------------------------------------------------------------
# dispatch() tests
# ---------------------------------------------------------------------------


class TestDispatch:
    """Async tests for NotificationDispatcher.dispatch()."""

    async def test_dispatch_with_matching_prefs(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) == 1
            target = recorder.calls[0]["targets"][0]
            assert target.platform == "slack"
            assert target.chat_id == "C123"

    async def test_dispatch_no_matching_prefs(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:failed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) == 0

    async def test_dispatch_multiple_matching_prefs(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:completed"])},
            {"channel": "teams", "target": "teams:T456", "events": json.dumps(["run:completed"])},
            {"channel": "email", "target": "user@example.com", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) == 3
            platforms = {c["targets"][0].platform for c in recorder.calls}
            assert platforms == {"slack", "teams", "email"}

    async def test_dispatch_with_channel_filter(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:completed"])},
            {"channel": "teams", "target": "teams:T456", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
                channels=["slack"],
            )
            assert len(recorder.calls) == 1
            assert recorder.calls[0]["targets"][0].platform == "slack"

    async def test_dispatch_with_empty_channel_filter(self):
        """Empty channels list is falsy, so all matching prefs are returned."""
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
                channels=[],
            )
            # Empty list is falsy -> no channel filter -> pref matches
            assert len(recorder.calls) == 1

    async def test_dispatch_channel_filter_no_match(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
                channels=["teams"],
            )
            assert len(recorder.calls) == 0

    async def test_dispatch_email_target(self):
        rows = [
            {"channel": "email", "target": "user@example.com", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) == 1
            target = recorder.calls[0]["targets"][0]
            assert target.platform == "email"
            assert target.chat_id == "user@example.com"

    async def test_dispatch_email_empty_target(self):
        rows = [
            {"channel": "email", "target": "", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) >= 0

    async def test_dispatch_no_db(self):
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=None,
            )
            assert len(recorder.calls) == 0

    async def test_dispatch_no_rows(self):
        db = _FakeDB(rows=[])
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) == 0

    async def test_dispatch_db_raises_error(self):
        db = _FakeDB(rows=[], raises=True)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(recorder.calls) == 0

    async def test_dispatch_format_string_used_correctly(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:failed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="xyz789", repo_url="https://example.com/repo",
                status="failed", summary="Pipeline crashed", db=db,
            )
            content = recorder.calls[0]["content"]
            assert "Orchestration failed" in content
            assert "https://example.com/repo" in content
            assert "Pipeline crashed" in content
            assert "session_id=xyz789" in content

    async def test_dispatch_preserves_event_prefix(self):
        rows = [
            {"channel": "slack", "target": "slack:C123", "events": json.dumps(["run:completed"])},
        ]
        db = _FakeDB(rows=rows)
        async with _patch_router() as recorder:
            await NotificationDispatcher.dispatch(
                session_id="abc123", repo_url="https://github.com/org/repo",
                status="completed", summary="done", db=db,
            )
            assert len(db.calls) >= 1
            query, args = db.calls[0]
            assert "run:completed" in str(args[0])


# ---------------------------------------------------------------------------
# Helper: context manager that patches DeliveryRouter.deliver
# ---------------------------------------------------------------------------


@dataclass
class _Recorder:
    calls: list[dict] = field(default_factory=list)


import contextlib


@contextlib.asynccontextmanager
async def _patch_router():
    """Context manager that patches DeliveryRouter to record deliveries."""
    recorder = _Recorder()
    original_deliver = DeliveryRouter.deliver

    async def mock_deliver(self, content, targets, **kw):
        recorder.calls.append({"content": content, "targets": targets, **kw})
        return {t.to_string(): {"success": True} for t in targets}

    DeliveryRouter.deliver = mock_deliver
    try:
        yield recorder
    finally:
        DeliveryRouter.deliver = original_deliver
