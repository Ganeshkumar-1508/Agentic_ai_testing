"""Tests for StreamEventsDBSink — verifies events are persisted correctly.

The sink was dropping events with empty session_id, causing the frontend
to show "No events yet" even when the pipeline was running.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeEvent:
    """Minimal StreamEvent stand-in."""
    session_id: str = ""
    subagent_id: str = ""
    agent_id: str = ""
    parent_subagent_id: str = ""
    type_name: str = "test.event"


@dataclass
class _FakeEventWithData:
    """Event with a data dict (GenericStreamEvent pattern)."""
    session_id: str = ""
    data: dict | None = None
    type_name: str = "test.event"


class _FakeDB:
    def __init__(self):
        self.inserted: list[tuple] = []
        self._pool = object()

    async def execute(self, sql: str, *args) -> str:
        self.inserted.append(args)
        return "INSERT 0 1"


# ---------------------------------------------------------------------------
# Tests — session_id extraction
# ---------------------------------------------------------------------------


async def test_event_with_session_id_is_persisted():
    """Events with session_id set are stored normally."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEvent(session_id="session-123", subagent_id="sa-001")
        await sink.emit(event)

    assert len(db.inserted) == 1
    assert db.inserted[0][0] == "session-123"


async def test_event_without_session_id_extracts_from_subagent_id():
    """Events with empty session_id extract it from subagent_id."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEvent(session_id="", subagent_id="sa-001")
        await sink.emit(event)

    assert len(db.inserted) == 1
    assert db.inserted[0][0] == "subagent-sa-001"


async def test_event_without_session_id_extracts_from_data():
    """Events with empty session_id extract it from data dict."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEventWithData(
            session_id="",
            data={"session_id": "session-456", "goal": "test"},
        )
        await sink.emit(event)

    assert len(db.inserted) == 1
    assert db.inserted[0][0] == "session-456"


async def test_event_with_no_session_id_anywhere_is_dropped():
    """Events with no session_id anywhere are still dropped."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEvent(session_id="", subagent_id="")
        await sink.emit(event)

    assert len(db.inserted) == 0


async def test_event_with_none_session_id_extracts_from_subagent():
    """Events with session_id=None extract from subagent_id."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEvent(session_id=None, subagent_id="sa-999")
        await sink.emit(event)

    assert len(db.inserted) == 1
    assert db.inserted[0][0] == "subagent-sa-999"


async def test_event_with_no_db_is_silent():
    """Events with no DB connection are silently ignored."""
    from harness.events import StreamEventsDBSink

    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=None):
        event = _FakeEvent(session_id="session-123")
        await sink.emit(event)  # Should not raise


async def test_event_with_no_pool_is_silent():
    """Events with DB but no pool are silently ignored."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    db._pool = None
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEvent(session_id="session-123")
        await sink.emit(event)  # Should not raise

    assert len(db.inserted) == 0


async def test_event_data_dict_is_stored():
    """GenericStreamEvent data dict is stored as JSON payload."""
    from harness.events import StreamEventsDBSink

    db = _FakeDB()
    sink = StreamEventsDBSink()

    with patch("harness.events.get_db", return_value=db):
        event = _FakeEventWithData(
            session_id="session-789",
            data={"goal": "write tests", "model": "deepseek-v4-flash"},
        )
        await sink.emit(event)

    assert len(db.inserted) == 1
    payload = json.loads(db.inserted[0][2])
    assert payload["goal"] == "write tests"
    assert payload["model"] == "deepseek-v4-flash"
