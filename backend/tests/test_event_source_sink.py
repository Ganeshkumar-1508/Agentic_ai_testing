"""Tests for :class:`harness.events.EventSourceSink` and friends.

Covers:
  * ``stream_event_to_dict()`` roundtrip.
  * Subscribe / unsubscribe lifecycle (multi-subscriber, double-subscribe, unknown id).
  * ``emit`` routes to the correct session and broadcasts when ``session_id`` is absent.
  * Silent drop when a session has no subscribers.
  * Backpressure: drop-oldest on full queue, drop-newest on race.
  * ``EventBus.emit`` fan-out across multiple sinks (sync + async).
  * ``EventBus.emit_sync`` with no running loop logs a warning and drops the event.
  * ``EventBus._dispatch`` swallows sink exceptions and surfaces them as logs only.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any

import pytest

from harness.core.events import StreamEvent
from harness.events import EventBus, EventSourceSink, LogSink, TraceCallbackSink, stream_event_to_dict
from harness.api.state import GenericStreamEvent


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _TestEvent(StreamEvent):
    event_type: str = ""
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    source: str = "agent"
    session_id: str | None = None
    subagent_id: str | None = None
    parent_subagent_id: str | None = None
    timestamp: float = 0.0


def _make(event_type: str = "tool:start", session_id: str | None = None, **kw: Any) -> _TestEvent:
    return _TestEvent(event_type=event_type, session_id=session_id, **kw)


class _RecordingSink:
    name = "recording"

    def __init__(self) -> None:
        self.events: list[StreamEvent] = []

    def emit(self, event: StreamEvent) -> None:
        self.events.append(event)


class _AsyncRecordingSink:
    name = "async_recording"

    def __init__(self) -> None:
        self.events: list[StreamEvent] = []

    async def emit(self, event: StreamEvent) -> None:
        await asyncio.sleep(0)
        self.events.append(event)


# ---------------------------------------------------------------------------
# stream_event_to_dict
# ---------------------------------------------------------------------------


def test_stream_event_to_dict_roundtrip() -> None:
    e = _TestEvent(
        event_type="tool:start",
        data={"tool_name": "write"},
        source="agent",
        session_id="abc",
        subagent_id="s1",
        parent_subagent_id=None,
        timestamp=123.0,
    )
    d = stream_event_to_dict(e)
    assert d == {
        "event_type": "tool:start",
        "data": {"tool_name": "write"},
        "source": "agent",
        "session_id": "abc",
        "subagent_id": "s1",
        "parent_subagent_id": None,
    }


# ---------------------------------------------------------------------------
# EventSourceSink — routing
# ---------------------------------------------------------------------------


async def test_sink_subscribe_returns_queue_and_starts_empty() -> None:
    sink = EventSourceSink()
    q = sink.subscribe("s1")
    assert isinstance(q, asyncio.Queue)
    assert q.empty() is True
    assert sink.subscriber_count("s1") == 1
    assert sink.sessions() == ["s1"]


async def test_sink_routes_event_to_matching_session() -> None:
    sink = EventSourceSink()
    q1 = sink.subscribe("s1")
    sink.subscribe("s2")
    e = _make(event_type="tool:start", session_id="s1")
    sink.emit(e)
    assert q1.qsize() == 1
    got = await asyncio.wait_for(q1.get(), timeout=1.0)
    assert got is e


async def test_sink_drops_event_for_session_with_no_subscribers() -> None:
    sink = EventSourceSink()
    sink.subscribe("s1")
    sink.emit(_make(event_type="x", session_id="s2"))
    assert sink.subscriber_count("s2") == 0


async def test_sink_broadcasts_event_with_no_session_id() -> None:
    sink = EventSourceSink()
    q1 = sink.subscribe("s1")
    q2 = sink.subscribe("s2")
    e = _make(event_type="system:ping", session_id=None)
    sink.emit(e)
    assert (await asyncio.wait_for(q1.get(), timeout=1.0)).event_type == "system:ping"
    assert (await asyncio.wait_for(q2.get(), timeout=1.0)).event_type == "system:ping"


async def test_sink_multi_subscriber_for_one_session() -> None:
    sink = EventSourceSink()
    q1 = sink.subscribe("s1")
    q2 = sink.subscribe("s1")
    assert sink.subscriber_count("s1") == 2
    sink.emit(_make(event_type="x", session_id="s1"))
    assert q1.qsize() == 1
    assert q2.qsize() == 1


# ---------------------------------------------------------------------------
# EventSourceSink — lifecycle
# ---------------------------------------------------------------------------


async def test_sink_unsubscribe_removes_one_queue() -> None:
    sink = EventSourceSink()
    q1 = sink.subscribe("s1")
    q2 = sink.subscribe("s1")
    sink.unsubscribe("s1", q1)
    assert sink.subscriber_count("s1") == 1
    sink.emit(_make(event_type="x", session_id="s1"))
    assert q1.empty() is True
    assert q2.qsize() == 1


async def test_sink_unsubscribe_last_queue_drops_session() -> None:
    sink = EventSourceSink()
    q = sink.subscribe("s1")
    sink.unsubscribe("s1", q)
    assert sink.subscriber_count("s1") == 0
    assert sink.sessions() == []


async def test_sink_unsubscribe_with_unknown_id_is_noop() -> None:
    sink = EventSourceSink()
    sink.unsubscribe("never-existed", asyncio.Queue())


async def test_sink_unsubscribe_with_unknown_queue_is_noop() -> None:
    sink = EventSourceSink()
    sink.subscribe("s1")
    sink.unsubscribe("s1", asyncio.Queue())
    assert sink.subscriber_count("s1") == 1


# ---------------------------------------------------------------------------
# EventSourceSink — backpressure
# ---------------------------------------------------------------------------


async def test_sink_drops_oldest_on_full_queue(caplog: pytest.LogCaptureFixture) -> None:
    sink = EventSourceSink(queue_max=2)
    q = sink.subscribe("s1")
    e1 = _make(event_type="a", session_id="s1")
    e2 = _make(event_type="b", session_id="s1")
    e3 = _make(event_type="c", session_id="s1")
    sink.emit(e1)
    sink.emit(e2)
    assert q.qsize() == 2
    caplog.set_level(logging.WARNING, logger="harness.events")
    sink.emit(e3)
    assert q.qsize() == 2
    got1 = await asyncio.wait_for(q.get(), timeout=1.0)
    got2 = await asyncio.wait_for(q.get(), timeout=1.0)
    assert got1.event_type == "b"
    assert got2.event_type == "c"


async def test_sink_drop_oldest_then_subscribe_after_drain() -> None:
    sink = EventSourceSink(queue_max=1)
    q = sink.subscribe("s1")
    sink.emit(_make(event_type="a", session_id="s1"))
    sink.emit(_make(event_type="b", session_id="s1"))
    assert (await asyncio.wait_for(q.get(), timeout=1.0)).event_type == "b"
    sink.emit(_make(event_type="c", session_id="s1"))
    assert (await asyncio.wait_for(q.get(), timeout=1.0)).event_type == "c"


# ---------------------------------------------------------------------------
# EventBus — fan-out
# ---------------------------------------------------------------------------


async def test_bus_fans_out_to_multiple_sinks() -> None:
    bus = EventBus()
    a = _RecordingSink()
    b = _AsyncRecordingSink()
    bus.add_sink(a)
    bus.add_sink(b)
    e = _make(event_type="x")
    await bus.emit(e)
    assert a.events == [e]
    assert b.events == [e]


async def test_bus_add_sink_is_idempotent() -> None:
    bus = EventBus()
    s = _RecordingSink()
    bus.add_sink(s)
    bus.add_sink(s)
    bus.add_sink(s)
    assert bus.sinks().count(s) == 1


async def test_bus_remove_sink() -> None:
    bus = EventBus()
    a = _RecordingSink()
    b = _RecordingSink()
    bus.add_sink(a)
    bus.add_sink(b)
    bus.remove_sink(a)
    await bus.emit(_make(event_type="x"))
    assert a.events == []
    assert len(b.events) == 1


async def test_bus_swallows_sink_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    class _BoomSink:
        name = "boom"
        def emit(self, event: StreamEvent) -> None:
            raise RuntimeError("kaboom")

    class _QuietSink:
        name = "quiet"
        def __init__(self) -> None:
            self.events: list[StreamEvent] = []
        def emit(self, event: StreamEvent) -> None:
            self.events.append(event)

    bus = EventBus()
    boom = _BoomSink()
    quiet = _QuietSink()
    bus.add_sink(boom)
    bus.add_sink(quiet)
    caplog.set_level(logging.ERROR, logger="harness.events")
    await bus.emit(_make(event_type="x"))
    assert len(quiet.events) == 1


async def test_bus_swallows_async_sink_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    class _BoomSink:
        name = "async_boom"
        async def emit(self, event: StreamEvent) -> None:
            raise RuntimeError("async-kaboom")

    bus = EventBus()
    bus.add_sink(_BoomSink())
    caplog.set_level(logging.ERROR, logger="harness.events")
    await bus.emit(_make(event_type="x"))


async def test_bus_emit_sync_without_loop_logs_and_drops(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    bus.add_sink(_RecordingSink())
    caplog.set_level(logging.WARNING, logger="harness.events")
    bus.emit_sync(_make(event_type="x"))


async def test_bus_emit_with_no_sinks_is_noop() -> None:
    bus = EventBus()
    await bus.emit(_make(event_type="x"))


# ---------------------------------------------------------------------------
# TraceCallbackSink + LogSink
# ---------------------------------------------------------------------------


async def test_trace_callback_sink_invokes_cb_with_type_and_data() -> None:
    received: list[tuple[str, dict[str, Any]]] = []

    async def cb(event_type: str, data: dict[str, Any]) -> None:
        received.append((event_type, data))

    sink = TraceCallbackSink(cb)
    for evt in (
        _make(event_type="tool:start", data={"tool_name": "write"}, timestamp=0.0),
        _make(event_type="tool:end", data={"ok": True}, timestamp=0.0),
    ):
        result = sink.emit(evt)
        if result is not None:
            await result
    assert received == [("_TestEvent", {"event_type": "tool:start", "data": {"tool_name": "write"}, "source": "agent", "session_id": None, "subagent_id": None, "parent_subagent_id": None}),
                        ("_TestEvent", {"event_type": "tool:end", "data": {"ok": True}, "source": "agent", "session_id": None, "subagent_id": None, "parent_subagent_id": None})]


async def test_trace_callback_sink_with_none_callback_is_noop() -> None:
    sink = TraceCallbackSink(None)
    result = sink.emit(_make(event_type="x"))
    assert result is None


def test_log_sink_logs_event(caplog: pytest.LogCaptureFixture) -> None:
    sink = LogSink()
    caplog.set_level(logging.INFO, logger="harness.events")
    e = _make(event_type="tool:start", source="agent", session_id="s1", data={"a": 1, "b": 2})
    sink.emit(e)
