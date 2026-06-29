"""EventBus + EventSink — single seam for cross-cutting agent events.

The bus is for the concerns that span multiple agents or that need a
fan-out to multiple consumers (DB, OTel, log, SSE stream). Per-agent
callbacks that are local to a single instance are called directly from
Agent, not through the bus.

All events are typed StreamEvent subtypes (from harness.core.events).
Sinks dispatch via isinstance() — never check string-typed type fields.

Sinks:
  - TraceCallbackSink: writes to DB + OTel
  - EventSourceSink: pushes to per-session SSE queues
  - LogSink: structured logging
  - StreamEventsDBSink: persists to stream_events table

Public surface (stable):
  EventBus, EventSink, TraceCallbackSink, EventSourceSink, LogSink,
  StreamEventsDBSink, stream_event_to_dict.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import logging
import time
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from harness.core.events import StreamEvent
from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)


# Default max events buffered per session queue.  Once exceeded the
# oldest event is dropped (with a warn-log) so a slow SSE client
# cannot stall a fast producer.
DEFAULT_SSE_QUEUE_MAX = 1024


# ---------------------------------------------------------------------------
# Sink protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EventSink(Protocol):
    """A consumer of StreamEvent subtypes. Sinks own their own delivery.

    Implementations may be sync (return None) or async (return a coroutine).
    The bus awaits any returned coroutine; sync returns are no-ops.
    Sinks MUST NOT raise — exceptions are caught and logged by the bus.
    """
    name: str

    def emit(self, event: StreamEvent) -> Awaitable[None] | None:
        ...


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBus:
    """In-process pub/sub for cross-cutting agent events. Fan-out is parallel."""

    def __init__(self) -> None:
        self._sinks: list[EventSink] = []
        self._lock = asyncio.Lock()

    def add_sink(self, sink: EventSink) -> None:
        if sink in self._sinks:
            return
        self._sinks.append(sink)
        logger.debug("event_bus.add_sink name=%s", sink.name)

    def remove_sink(self, sink: EventSink) -> None:
        if sink in self._sinks:
            self._sinks.remove(sink)
            logger.debug("event_bus.remove_sink name=%s", sink.name)

    def sinks(self) -> list[EventSink]:
        return list(self._sinks)

    async def emit(self, event: StreamEvent) -> None:
        """Emit a typed StreamEvent to all sinks."""
        if not self._sinks:
            return
        await asyncio.gather(
            *(self._dispatch(s, event) for s in self._sinks),
            return_exceptions=True,
        )

    def emit_sync(self, event: StreamEvent) -> None:
        """Sync fire-and-forget for rare sync producers.

        Schedules the async emit as a task on the running loop. If there
        is no running loop, drops the event and logs a warning.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "event_bus.emit_sync dropped (no running loop) type=%s", event.type_name,
            )
            return
        loop.create_task(self.emit(event))

    async def _dispatch(self, sink: EventSink, event: StreamEvent) -> None:
        try:
            result = sink.emit(event)
        except Exception:  # noqa: BLE001
            logger.exception("event_bus.sink.emit raised name=%s type=%s", sink.name, event.type_name)
            return
        if inspect.isawaitable(result):
            try:
                await result
            except Exception:  # noqa: BLE001
                logger.exception("event_bus.sink.awaitable raised name=%s type=%s", sink.name, event.type_name)

    def close(self) -> None:
        """Detach all sinks. Useful in tests."""
        self._sinks.clear()


# ---------------------------------------------------------------------------
# Built-in sinks
# ---------------------------------------------------------------------------


class TraceCallbackSink:
    """Forwards StreamEvent to a ``async def cb(event_type, data)`` callback.

    The wire shape is ``(event_type: str, data: dict)`` — same as the old
    ``_emit_trace`` contract.  The callback receives the StreamEvent's
    ``type_name`` and fields as a dict.
    """
    name = "trace_callback"

    def __init__(self, callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None) -> None:
        self._cb = callback

    def emit(self, event: StreamEvent) -> Awaitable[None] | None:
        if self._cb is None:
            return None
        return self._cb(event.type_name, stream_event_to_dict(event))


class EventSourceSink:
    """Forwards StreamEvent to per-session asyncio queues for SSE consumers.

    Each SSE client calls :meth:`subscribe` to register a queue for a
    given session id; the sink then routes every StreamEvent whose
    ``session_id`` matches into that queue. Events with no session_id
    are broadcast to **every** subscribed session.

    Subagent events are also forwarded to the parent session via the
    ``register_child`` side-table (Hermes ``_build_child_progress_callback``
    pattern). This is what makes the orchestrator's UI see its
    subagents' tool calls in real-time without forcing the user to
    drill into every subagent manually.

    Backpressure: if a subscriber's queue is full, the oldest event
    is dropped and a warning is logged.
    """
    name = "event_source"

    def __init__(self, queue_max: int = DEFAULT_SSE_QUEUE_MAX) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[StreamEvent]]] = {}
        self._child_to_parent: dict[str, str] = {}
        self._queue_max = queue_max

    def register_child(self, child_session_id: str, parent_session_id: str) -> None:
        self._child_to_parent[child_session_id] = parent_session_id

    def unregister_child(self, child_session_id: str) -> None:
        self._child_to_parent.pop(child_session_id, None)

    def subscribe(self, session_id: str) -> asyncio.Queue[StreamEvent]:
        q: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=self._queue_max)
        self._subscribers.setdefault(session_id, set()).add(q)
        logger.debug("event_source.subscribe session=%s subscribers=%d", session_id, len(self._subscribers[session_id]))
        return q

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[StreamEvent]) -> None:
        qs = self._subscribers.get(session_id)
        if qs is None:
            return
        qs.discard(queue)
        if not qs:
            self._subscribers.pop(session_id, None)
        logger.debug("event_source.unsubscribe session=%s subscribers=%d", session_id, len(qs) if qs else 0)

    def sessions(self) -> list[str]:
        return list(self._subscribers)

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, ()))

    def emit(self, event: StreamEvent) -> None:
        sid = getattr(event, "session_id", None)
        if sid is not None:
            qs = self._subscribers.get(sid)
            if qs:
                for q in qs:
                    self._enqueue(q, event)
            parent_sid = self._child_to_parent.get(sid)
            if parent_sid and parent_sid != sid:
                pqs = self._subscribers.get(parent_sid)
                if pqs:
                    for q in pqs:
                        self._enqueue(q, event)
            gqs = self._subscribers.get("_global")
            if gqs:
                for q in gqs:
                    self._enqueue(q, event)
            return
        for qs in self._subscribers.values():
            for q in qs:
                self._enqueue(q, event)

    def _enqueue(self, q: asyncio.Queue[StreamEvent], event: StreamEvent) -> None:
        if q.full():
            try:
                q.get_nowait()
                logger.warning(
                    "event_source queue full, dropping oldest type=%s session=%s",
                    event.type_name, getattr(event, "session_id", None) or "-",
                )
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "event_source queue still full after eviction, dropping type=%s session=%s",
                event.type_name, getattr(event, "session_id", None) or "-",
            )


class LogSink:
    """Logs every event at INFO. Useful for debugging and as a final fallback."""
    name = "log"

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level

    def emit(self, event: StreamEvent) -> None:
        logger.log(
            self._level,
            "event type=%s session=%s fields=%s",
            event.type_name,
            getattr(event, "session_id", None) or "-",
            sorted(f.name for f in dataclasses.fields(event) if f.name != "timestamp"),
        )


class StreamEventsDBSink:
    """Bridges ALL StreamEvents to the stream_events DB table for SSE polling.

    Single persistence path.  Filtering happens at the consumer (SSE endpoint).
    """
    name = "stream_events_db"

    def __init__(self) -> None:
        self._counter = 0

    async def emit(self, event: StreamEvent) -> None:
        sid = getattr(event, "session_id", None)
        if not sid:
            return
        try:
            import json as _json
            db = get_db()
            if db is None or db._pool is None:
                return
            # Wire name follows the dot-notation used by the frontend
            # activity feed filters.  GenericStreamEvent already carries
            # the right string in ``event_type``; typed events are
            # mapped via :func:`wire_name`.
            orig_type = wire_name(event)
            # For GenericStreamEvent, store the data dict, not the wrapper fields
            if hasattr(event, "data") and isinstance(getattr(event, "data", None), dict):
                event_data = getattr(event, "data")
            else:
                event_data = stream_event_to_dict(event)
            payload = _json.dumps(event_data)
            aid = getattr(event, "agent_id", None)
            pid = getattr(event, "parent_subagent_id", None)
            sub_id = getattr(event, "subagent_id", None) or getattr(event, "agent_id", None)
            await db.execute(
                "INSERT INTO stream_events (session_id, event_type, event_data, parent_id, agent_id, subagent_id) VALUES ($1, $2, $3, $4, $5, $6)",
                sid, orig_type, payload, pid, aid, sub_id,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Event-name normalization (typed class name → dot-notation wire name)
# ---------------------------------------------------------------------------
#
# Typed StreamEvent subclasses expose their class name as ``type_name``
# (e.g. ``ToolExecutionStarted``).  The frontend's activity feed filters
# by *dot-notation* names (``tool.execution.started``) so the SSE wire
# name has to match — otherwise the substring filter never matches and
# the event is invisible in the UI.
#
# This table is the single source of truth.  GenericStreamEvent is
# handled separately (its ``event_type`` field is already the wire
# name); this table only governs typed StreamEvent subclasses.
#
# Naming convention (mirrors AG-UI / A2A spec shapes):
#   - lifecycle: agent.started, agent.completed, round.started, …
#   - tool:      tool.execution.started, tool.execution.completed, …
#   - llm:       llmcall.started, llmcall.completed
#   - error:     error  (no dot — short, single keyword)
#   - status:    status (no dot)
#   - subagent:  subagent.spawned, subagent.completed, subagent.heartbeat
#                (subagent events use string-typed GenericStreamEvent
#                 so this table doesn't carry them)
#
# When a new typed event is added to ``core/events.py``, add its
# wire-name to this table — the SSE endpoint reads it via
# :func:`wire_name`.
_EVENT_WIRE_NAMES: dict[str, str] = {
    "AgentStarted": "agent.started",
    "AgentCompleted": "agent.completed",
    "RoundStarted": "round.started",
    "RoundCompleted": "round.completed",
    "LLMCallStarted": "llmcall.started",
    "LLMCallCompleted": "llmcall.completed",
    "ToolExecutionStarted": "tool.execution.started",
    "ToolExecutionCompleted": "tool.execution.completed",
    "ToolProgress": "tool.progress",
    "SubagentSpawned": "subagent.spawned",
    "SubagentCompleted": "subagent.completed",
    "ApprovalRequired": "approval.required",
    "ReflexionInjected": "reflexion.injected",
    "ErrorEvent": "error",
    "StatusEvent": "status",
    "BudgetThrottled": "budget.throttled",
    "TokenGenerated": "token.generated",
    "ReasoningGenerated": "reasoning.generated",
}


def wire_name(event: "StreamEvent") -> str:
    """Return the SSE wire name for a typed StreamEvent.

    Falls back to the class name if the table has no entry.  The
    fallback is loud (it logs once per unknown class) so a missing
    mapping doesn't silently break the UI.
    """
    cls_name = type(event).__name__
    mapped = _EVENT_WIRE_NAMES.get(cls_name)
    if mapped is not None:
        return mapped
    # GenericStreamEvent carries its own event_type string; never
    # fall through to the class name (which would be "GenericStreamEvent").
    if hasattr(event, "event_type") and isinstance(getattr(event, "event_type", None), str):
        return event.event_type
    logger.warning(
        "events.wire_name.no_mapping class=%s — frontend filter will not match. "
        "Add an entry to _EVENT_WIRE_NAMES in harness/events.py.",
        cls_name,
    )
    return cls_name


# ---------------------------------------------------------------------------
# StreamEvent conversion helpers
# ---------------------------------------------------------------------------


def stream_event_to_dict(event: StreamEvent) -> dict[str, Any]:
    """Convert a typed StreamEvent to a plain dict, excluding timestamp.

    Useful for sinks that need raw field access without dataclass overhead.
    """
    return {
        f.name: getattr(event, f.name)
        for f in dataclasses.fields(event)
        if f.name != "timestamp"
    }
