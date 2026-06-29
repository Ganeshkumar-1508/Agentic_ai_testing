"""Audit Trail API — paginated, filterable access to stream_events for compliance.

Endpoints:
  GET /api/audit        → paginated audit log (cross-session)
  GET /api/audit/export → CSV/JSON download of filtered results
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])

EVENT_TYPE_CATEGORIES = {
    "tool": ["ToolExecutionStarted", "ToolExecutionCompleted", "tool.execution.started", "tool.execution.completed", "tool:start", "tool:end"],
    "llm": ["LLMCallStarted", "LLMCallCompleted", "llmcall.started", "llmcall.completed", "TokenGenerated", "ReasoningGenerated"],
    "subagent": ["subagent.spawned", "subagent.completed", "subagent.failed", "SubagentSpawned", "SubagentCompleted"],
    "session": ["session.started", "session.completed", "session.failed", "session.cancelled"],
    "approval": ["ApprovalRequired", "approval:required", "approval:denied", "approval:blocked", "approval.resolved"],
    "error": ["ErrorEvent", "error"],
    "guardrail": ["guardrail:denied", "tool:blocked"],
}


@router.get("")
async def list_audit_events(
    request: Request,
    event_type: str = Query("", description="Filter by event type or category (tool/llm/subagent/session/approval/error/guardrail)"),
    agent_id: str = Query("", description="Filter by agent ID"),
    session_id: str = Query("", description="Filter by session ID"),
    subagent_id: str = Query("", description="Filter by subagent ID"),
    status: str = Query("", description="Filter by status from event_data"),
    search: str = Query("", description="Full-text search in event_data"),
    days: int = Query(30, description="Look back N days"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Paginated audit log with filters. Returns events sorted by newest first."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    if not db or not hasattr(db, "fetch"):
        return {"events": [], "total": 0, "limit": limit, "offset": offset}

    where_clauses: list[str] = ["created_at >= $1"]
    params: list[Any] = [datetime.now(timezone.utc) - timedelta(days=days)]
    param_idx = 2

    # Resolve event type filter (category expansion)
    if event_type:
        expanded = EVENT_TYPE_CATEGORIES.get(event_type, [event_type])
        placeholders = ", ".join(f"${param_idx + i}" for i in range(len(expanded)))
        where_clauses.append(f"event_type IN ({placeholders})")
        params.extend(expanded)
        param_idx += len(expanded)

    if agent_id:
        where_clauses.append(f"agent_id = ${param_idx}")
        params.append(agent_id)
        param_idx += 1

    if session_id:
        where_clauses.append(f"session_id = ${param_idx}")
        params.append(session_id)
        param_idx += 1

    if subagent_id:
        where_clauses.append(f"subagent_id = ${param_idx}")
        params.append(subagent_id)
        param_idx += 1

    if search:
        where_clauses.append(f"event_data::text ILIKE ${param_idx}")
        params.append(f"%{search}%")
        param_idx += 1

    if status:
        where_clauses.append(f"event_data->>'status' = ${param_idx}")
        params.append(status)
        param_idx += 1

    where = " AND ".join(where_clauses)
    count_sql = f"SELECT COUNT(*) as cnt FROM stream_events WHERE {where}"
    data_sql = f"SELECT id, session_id, event_type, event_data, parent_id, agent_id, subagent_id, created_at FROM stream_events WHERE {where} ORDER BY id DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"

    try:
        count_row = await db.fetchrow(count_sql, *params)
        total = count_row["cnt"] if count_row else 0

        data_params = params + [limit, offset]
        rows = await db.fetch(data_sql, *data_params)
    except Exception as exc:
        logger.warning("audit query failed: %s", exc)
        return {"events": [], "total": 0, "limit": limit, "offset": offset}

    # Enrich events with derived fields for the frontend
    events = []
    for r in rows:
        ev = {
            "id": r["id"],
            "session_id": r["session_id"],
            "event_type": r["event_type"],
            "event_data": r["event_data"] if isinstance(r["event_data"], dict) else {},
            "parent_id": r["parent_id"],
            "agent_id": r["agent_id"],
            "subagent_id": r["subagent_id"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        # Derive summary fields
        ed = ev["event_data"]
        ev["tool_name"] = ed.get("tool_name") or ed.get("name") or ""
        ev["status_label"] = ed.get("status") or ed.get("success") and "completed" or ""
        ev["input_preview"] = str(ed.get("tool_input") or ed.get("input") or "")[:150]
        ev["output_preview"] = str(ed.get("output_preview") or ed.get("output") or ed.get("result") or "")[:200]
        ev["duration_ms"] = ed.get("duration_ms") or ed.get("duration_sec", 0) * 1000 if ed.get("duration_sec") else 0
        ev["cost_usd"] = ed.get("cost_usd") or ed.get("estimated_cost_usd") or 0
        ev["actor"] = ed.get("actor", "agent")
        events.append(ev)

    return {"events": events, "total": total, "limit": limit, "offset": offset}


@router.get("/export")
async def export_audit_events(
    request: Request,
    fmt: str = Query("csv", regex="^(csv|json)$"),
    event_type: str = Query(""),
    agent_id: str = Query(""),
    session_id: str = Query(""),
    days: int = Query(30),
):
    """Export audit events as CSV or JSON download."""
    result = await list_audit_events(request, event_type=event_type, agent_id=agent_id, session_id=session_id, days=days, limit=5000, offset=0)
    events = result.get("events", [])

    if fmt == "json":
        content = json.dumps(events, indent=2, default=str)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=audit-export-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "event_type", "session_id", "agent_id", "subagent_id", "tool_name", "status", "input_preview", "output_preview", "duration_ms", "cost_usd", "actor"])
    for ev in events:
        writer.writerow([
            ev["id"], ev["created_at"], ev["event_type"], ev["session_id"],
            ev["agent_id"], ev["subagent_id"], ev["tool_name"], ev["status_label"],
            ev["input_preview"], ev["output_preview"], ev["duration_ms"], ev["cost_usd"], ev["actor"],
        ])
    content = output.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-export-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"},
    )
