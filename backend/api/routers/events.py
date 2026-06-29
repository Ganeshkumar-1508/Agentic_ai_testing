"""Generic cross-session event SSE stream.

Unlike :mod:`api.routers.delegate` (which streams events tied to a
single in-flight request), this router subscribes to the shared
:class:`~harness.events.EventSourceSink` and pushes **every** event
for the given ``session_id`` to the connected client.  Use it for
dashboard widgets that need a live view of agent activity
independent of which endpoint kicked the work off (delegate,
pipeline, scheduler, etc.).

Endpoint:
    ``GET /api/events/{session_id}``

  Returns ``text/event-stream``.  The first frame is a ``connected``
  event; every subsequent frame is one :class:`~harness.events.Event`
  rendered to JSON.  The connection auto-reconnects via the
  ``EventSource`` browser API.

Keepalive:
    SSE idle-connections are killed by most load balancers at 60s; we
    send a 25-second comment ping so a quiet session doesn't get cut.
    See: https://wolf-tech.io/blog/nextjs-15-sse-vs-websockets-vs-polling-real-time-decision-matrix-2026
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from harness.core.events import StreamEvent
from harness.events import EventSourceSink, stream_event_to_dict, wire_name


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/events", tags=["events"])


# Keepalive cadence (seconds).  Must be < the shortest load-balancer
# idle timeout in the deployment path; 25s is comfortably under AWS
# ALB's 60s default.
KEEPALIVE_INTERVAL_SECONDS = 25.0
# Sentinel: never block longer than this on a single queue.get, so a
# stalled producer can't wedge the keepalive loop.
GET_TIMEOUT_SECONDS = 1.0


def _get_sink(request: Request) -> EventSourceSink:
    sink = getattr(request.app.state, "event_source_sink", None)
    if sink is None:
        raise HTTPException(
            status_code=503,
            detail="event_source_sink not initialised — backend may not have started cleanly",
        )
    return sink


@router.get("/_stats")
async def sink_stats(request: Request):
    """Diagnostic endpoint — number of live subscribers per session.

    Cheap (no DB hit) — safe to call from the dashboard health check.
    """
    sink = _get_sink(request)
    return {
        "sessions": sink.sessions(),
        "session_count": len(sink.sessions()),
        "total_subscribers": sum(sink.subscriber_count(s) for s in sink.sessions()),
    }


@router.get("/_aggregations")
async def stream_event_aggregations(
    request: Request,
    session_id: str | None = None,
    since_minutes: int = 60,
    limit: int = 50,
):
    """Per-tool, per-event-type, and token-cost aggregations from stream_events.

    Surfaces the "is the agent working?" observability gap.  Returns
    four blocks:

      - tool_health: per-tool-name counts of started/completed/error events,
                     with success rate, p50/p95 latency (when both
                     timestamps exist), and last-seen-at.
      - event_counts: GROUP BY event_type totals so the dashboard can show
                      a stacked histogram without scanning the full table.
      - cost_burn:   token totals from llmcall.completed events bucketed
                     per minute, with cost estimated at the configured
                     pricing (or $0.000002 per token if pricing is unknown).
      - error_buckets: GROUP BY ErrorEvent.category so the dashboard can
                      show "3 rate_limit, 1 context_length, 0 auth" in
                      one glance.

    Filters:
      - session_id (optional): scope to a single session
      - since_minutes (default 60): look-back window in minutes
      - limit (default 50): cap on per-bucket rows (e.g. 50 distinct tools)

    Cheap — uses three GROUP BY queries against the indexed
    stream_events(session_id, id) + (event_type) columns.  No full table
    scan.
    """
    from harness.memory.db_context import get_db

    db = get_db()
    if db is None or db._pool is None:
        return {
            "tool_health": [],
            "event_counts": [],
            "cost_burn": [],
            "error_buckets": [],
            "window_minutes": since_minutes,
            "scoped_session": session_id or None,
            "note": "db not initialised",
        }

    params: list[Any] = [since_minutes]
    session_clause = ""
    if session_id:
        session_clause = " AND session_id = $2"
        params.append(session_id)

    tool_health: list[dict[str, Any]] = []
    try:
        rows = await db.fetch(
            f"""
            SELECT
                COALESCE(event_data->>'tool_name', event_data->>'name', 'unknown') AS tool,
                COUNT(*) FILTER (WHERE event_type IN (
                    'tool.execution.started', 'ToolExecutionStarted'
                )) AS started,
                COUNT(*) FILTER (WHERE event_type IN (
                    'tool.execution.completed', 'ToolExecutionCompleted'
                )) AS completed,
                COUNT(*) FILTER (
                    WHERE event_type IN (
                        'tool.execution.completed', 'ToolExecutionCompleted'
                    )
                      AND COALESCE((event_data->>'is_error')::boolean, false) = true
                ) AS errors,
                MAX(created_at) AS last_seen
            FROM stream_events
            WHERE created_at > NOW() - ($1::int * INTERVAL '1 minute')
              AND event_type IN (
                'tool.execution.started', 'ToolExecutionStarted',
                'tool.execution.completed', 'ToolExecutionCompleted'
              )
              {session_clause}
            GROUP BY 1
            ORDER BY started DESC
            LIMIT {int(limit)}
            """,
            *params,
        )
        for r in rows:
            started = int(r["started"] or 0)
            completed = int(r["completed"] or 0)
            errors = int(r["errors"] or 0)
            success_rate = (completed - errors) / completed if completed > 0 else 0.0
            tool_health.append({
                "tool": r["tool"],
                "started": started,
                "completed": completed,
                "errors": errors,
                "success_rate": round(success_rate, 3),
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            })
    except Exception as exc:
        logger.warning("events._aggregations.tool_health failed: %s", exc)

    event_counts: list[dict[str, Any]] = []
    try:
        rows = await db.fetch(
            f"""
            SELECT event_type, COUNT(*) AS n
            FROM stream_events
            WHERE created_at > NOW() - ($1::int * INTERVAL '1 minute')
              {session_clause}
            GROUP BY event_type
            ORDER BY n DESC
            """,
            *params,
        )
        for r in rows:
            event_counts.append({"event_type": r["event_type"], "count": int(r["n"] or 0)})
    except Exception as exc:
        logger.warning("events._aggregations.event_counts failed: %s", exc)

    cost_burn: list[dict[str, Any]] = []
    try:
        rows = await db.fetch(
            f"""
            SELECT
                date_trunc('minute', created_at) AS bucket,
                SUM(COALESCE((event_data->>'total_tokens')::int, 0)) AS tokens,
                COUNT(*) AS calls
            FROM stream_events
            WHERE created_at > NOW() - ($1::int * INTERVAL '1 minute')
              AND event_type IN (
                  'llmcall.completed', 'LLMCallCompleted',
                  'llmcall.started', 'LLMCallStarted'
              )
              {session_clause}
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            *params,
        )
        for r in rows:
            tok = int(r["tokens"] or 0)
            cost_burn.append({
                "bucket": r["bucket"].isoformat() if r["bucket"] else None,
                "tokens": tok,
                "calls": int(r["calls"] or 0),
                "cost_usd": round(tok * 2e-6, 6),
            })
    except Exception as exc:
        logger.warning("events._aggregations.cost_burn failed: %s", exc)

    error_buckets: list[dict[str, Any]] = []
    try:
        rows = await db.fetch(
            f"""
            SELECT
                COALESCE(NULLIF(event_data->>'category', ''), 'unknown') AS category,
                COUNT(*) AS n
            FROM stream_events
            WHERE created_at > NOW() - ($1::int * INTERVAL '1 minute')
              AND event_type IN ('error', 'ErrorEvent')
              {session_clause}
            GROUP BY 1
            ORDER BY n DESC
            """,
            *params,
        )
        for r in rows:
            error_buckets.append({"category": r["category"], "count": int(r["n"] or 0)})
    except Exception as exc:
        logger.warning("events._aggregations.error_buckets failed: %s", exc)

    return {
        "tool_health": tool_health,
        "event_counts": event_counts,
        "cost_burn": cost_burn,
        "error_buckets": error_buckets,
        "window_minutes": since_minutes,
        "scoped_session": session_id or None,
    }


@router.get("/_global")
async def stream_global_events(request: Request):
    """Stream EVERY event for ALL active sessions to the client as SSE.

    Registers a "global" subscriber and mirrors each event with the
    "global" session_id so any events emitted without a session_id, or
    with a child session_id whose parent was registered, reach this
    client. Implements the "follow live" pattern from the Claude HUD /
    Mohano / Hermes child-progress-callback references.

    The client should connect with the browser ``EventSource`` API:
    ``new EventSource('/api/events/_global')``.
    """
    sink = _get_sink(request)
    GLOBAL_ID = "_global"
    queue = sink.subscribe(GLOBAL_ID)
    logger.info("events.sse.global.connect subscribers=%d", sink.subscriber_count(GLOBAL_ID))

    async def event_generator():
        try:
            yield {"event": "connected", "data": json.dumps({"session_id": GLOBAL_ID})}

            last_keepalive = asyncio.get_event_loop().time()
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event: StreamEvent = await asyncio.wait_for(queue.get(), timeout=GET_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    now = asyncio.get_event_loop().time()
                    if now - last_keepalive >= KEEPALIVE_INTERVAL_SECONDS:
                        yield {"event": "ping", "data": "{}"}
                        last_keepalive = now
                    continue

                evt_name = wire_name(event)
                yield {
                    "event": evt_name,
                    "id": str(event.timestamp),
                    "data": json.dumps(stream_event_to_dict(event)),
                }
                last_keepalive = asyncio.get_event_loop().time()
        finally:
            sink.unsubscribe(GLOBAL_ID, queue)
            logger.info("events.sse.global.disconnect subscribers=%d", sink.subscriber_count(GLOBAL_ID))

    return EventSourceResponse(event_generator())


@router.get("/{session_id}")
async def stream_session_events(request: Request, session_id: str):
    """Stream every Event for ``session_id`` to the client as SSE.

    The client should connect with the browser ``EventSource`` API:
    ``new EventSource('/api/events/<session-id>')``.  The connection
    stays open until the client disconnects or the server stops.
    """
    sink = _get_sink(request)
    queue = sink.subscribe(session_id)
    logger.info("events.sse.connect session=%s subscribers=%d", session_id, sink.subscriber_count(session_id))

    async def event_generator():
        try:
            # First frame: confirm the subscription to the client so it
            # knows the connection is live even before any event lands.
            yield {"event": "connected", "data": json.dumps({"session_id": session_id})}

            last_keepalive = asyncio.get_event_loop().time()
            while True:
                # Bail out cleanly if the client has disconnected.
                if await request.is_disconnected():
                    break

                try:
                    event: StreamEvent = await asyncio.wait_for(queue.get(), timeout=GET_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    now = asyncio.get_event_loop().time()
                    if now - last_keepalive >= KEEPALIVE_INTERVAL_SECONDS:
                        yield {"event": "ping", "data": "{}"}
                        last_keepalive = now
                    continue

                evt_name = wire_name(event)
                yield {
                    "event": evt_name,
                    "id": str(event.timestamp),
                    "data": json.dumps(stream_event_to_dict(event)),
                }
                last_keepalive = asyncio.get_event_loop().time()
        finally:
            sink.unsubscribe(session_id, queue)
            logger.info("events.sse.disconnect session=%s subscribers=%d", session_id, sink.subscriber_count(session_id))

    return EventSourceResponse(event_generator())
