"""Stream event helpers — all events flow through EventBus → sinks.

New code should emit typed StreamEvent subtypes directly via ``EventBus.emit()``.
``emit_stream_event()`` is a convenience for callers (pipeline routers, etc.)
that still pass string event types — it wraps them in a typed event internally.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from harness.core.events import StreamEvent
from harness.events import EventBus, EventSourceSink, stream_event_to_dict
from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)

_shared_bus: EventBus | None = None
_shared_event_source_sink: EventSourceSink | None = None
_agent_factory: Any | None = None
_llm_router: Any | None = None


def set_event_bus(bus: EventBus | None) -> None:
    global _shared_bus
    _shared_bus = bus


def set_event_source_sink(sink: EventSourceSink | None) -> None:
    """Register the shared EventSourceSink for non-FastAPI callers.

    The SSE router in ``api/routers/events.py`` reads the sink from
    ``app.state.event_source_sink``. Background workers (e.g. the
    orchestrator's :class:`BoardWaiter`) need a process-wide handle
    because they don't carry a ``Request`` object.

    C03 added this seam so the orchestrator can subscribe to
    ``board.completed`` / ``subagent.completed`` events without
    having to receive them via the SSE HTTP path.
    """
    global _shared_event_source_sink
    _shared_event_source_sink = sink


def get_event_source_sink() -> EventSourceSink | None:
    """Return the shared :class:`EventSourceSink`, or None if the app
    hasn't been initialized (e.g. in pure unit tests).
    """
    return _shared_event_source_sink


def set_agent_factory(factory: Any | None) -> None:
    global _agent_factory
    _agent_factory = factory
    logger.info("Agent factory set to: %s", "callable" if factory else "None")


def get_agent_factory() -> Any | None:
    return _agent_factory


def set_llm(llm: Any | None) -> None:
    """Set the shared LLMRouter instance."""
    global _llm_router
    _llm_router = llm
    logger.info("Shared LLM router set to: %s", "configured" if llm else "None")


def get_llm() -> Any | None:
    """Get the shared LLMRouter instance."""
    return _llm_router


@dataclass(frozen=True)
class GenericStreamEvent(StreamEvent):
    """Typed wrapper for legacy string-typed event emissions.

    Carries the original event_type string in the ``event_type`` field
    and the payload in ``data`` so downstream sinks receive a proper
    StreamEvent with all the metadata they need.
    """
    session_id: str = ""
    event_type: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    subagent_id: str | None = None
    parent_subagent_id: str | None = None


async def emit_stream_event(session_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Emit a stream event to the bus via a typed wrapper.

    Wraps legacy string-typed event data in a ``GenericStreamEvent``
    so the entire pipeline stays on typed StreamEvent subtypes.
    Falls back to direct DB write if no EventBus is available.

    All events are stamped with an ``actor`` field for audit trail
    compliance. ``actor`` defaults to ``"agent"``. Callers that
    represent human actions (approvals, steer, manual overrides)
    set ``payload["actor"] = "human"`` explicitly.
    """
    if "actor" not in payload:
        payload["actor"] = "agent"
    bus = _shared_bus
    if bus is not None:
        await bus.emit(GenericStreamEvent(
            session_id=session_id,
            event_type=event_type,
            data=payload,
        ))
        return
    try:
        db = get_db()
        if db is not None and db._pool is not None:
            await db.execute(
                "INSERT INTO stream_events (session_id, event_type, event_data) VALUES ($1, $2, $3)",
                session_id, event_type, json.dumps(payload),
            )
    except Exception:
        pass


async def poll_stream_events(session_id: str, after_id: int = 0) -> list[dict[str, Any]]:
    """Poll for new stream events since the given ID."""
    try:
        db = get_db()
        if db is not None and db._pool is not None:
            rows = await db.fetch(
                "SELECT id, event_type, event_data FROM stream_events "
                "WHERE session_id = $1 AND id > $2 ORDER BY id",
                session_id, after_id,
            )
            result = []
            for r in rows:
                row = dict(r)
                try:
                    row["payload"] = json.loads(row.get("event_data", "{}"))
                except (json.JSONDecodeError, TypeError):
                    row["payload"] = {}
                result.append(row)
            return result
    except Exception:
        pass
    return []
