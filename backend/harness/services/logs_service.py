"""Logs service — session listing + event formatting with cursor pagination."""

from __future__ import annotations

import json
import base64
from datetime import datetime, timezone
from typing import Any

from harness.memory.database import Database


DISPLAY_TYPE_MAP: dict[str, str] = {
    "tool.execution.started": "tool_call", "tool.execution.completed": "tool_result", "error": "error",
    "llmcall.started": "llm", "llmcall.completed": "llm", "round.started": "round", "round.completed": "round",
    "agent.started": "agent", "agent.completed": "agent", "reasoning": "reasoning",
    "approval.required": "approval",
}


def normalize_type(raw: str) -> str:
    if raw.startswith("delegate."):
        return "delegate"
    return DISPLAY_TYPE_MAP.get(raw, raw)


def parse_event_data(raw: str | dict | None) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def decode_cursor(cursor: str | None) -> datetime | None:
    if not cursor:
        return None
    try:
        return datetime.fromisoformat(base64.b64decode(cursor.encode()).decode())
    except Exception:
        return None


def encode_cursor(dt: datetime) -> str:
    return base64.b64encode(dt.isoformat().encode()).decode()


def serialize_event(row: dict[str, Any], parsed: dict[str, Any] | None = None,
                    duration_ms: int | None = None, token_count: int | None = None,
                    depth: int = 0) -> dict[str, Any]:
    data = parsed or parse_event_data(row.get("event_data"))
    inner = data.get("data", data)
    raw_type = row["event_type"]
    display_type = normalize_type(raw_type)
    tool_name: str | None = None
    if raw_type in ("tool.execution.started", "tool.execution.completed", "error"):
        tool_name = inner.get("name")
    elif raw_type.startswith("delegate."):
        tool_name = inner.get("tool_name", inner.get("name"))
    content_preview: str | None = None
    if raw_type == "reasoning":
        content_preview = inner.get("content_preview", "")
    elif raw_type in ("tool.execution.started", "tool.execution.completed"):
        content_preview = inner.get("output_preview") or str(inner.get("arguments", ""))[:200]
    elif raw_type == "error":
        content_preview = inner.get("output_preview", inner.get("error", ""))
    elif raw_type.startswith("delegate."):
        content_preview = inner.get("preview", inner.get("goal", ""))
    elif raw_type in ("llmcall.started", "llmcall.completed"):
        content_preview = f"model: {inner.get('model', '?')}"
    if content_preview and isinstance(content_preview, str):
        content_preview = content_preview[:200]
    return {
        "id": row["id"], "type": display_type, "raw_type": raw_type,
        "agent_id": row.get("agent_id") or "", "parent_id": row.get("parent_id") or None,
        "depth": depth, "duration_ms": duration_ms, "token_count": token_count,
        "tool_name": tool_name, "content_preview": content_preview,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "payload": data,
    }


def build_events_response(rows: list[dict[str, Any]], limit: int,
                          root_agent_id: str | None = None) -> dict[str, Any]:
    open_spans: dict[str, dict] = {}
    events: list[dict] = []
    if not root_agent_id and rows:
        root_agent_id = rows[0].get("agent_id") or ""
    for r in rows:
        parsed = parse_event_data(r.get("event_data"))
        inner = parsed.get("data", parsed)
        data_id = inner.get("id")
        raw_type = r["event_type"]
        agent_id = r.get("agent_id") or ""
        depth = 0 if agent_id == root_agent_id or not root_agent_id else 1
        token_count: int | None = None
        duration_ms: int | None = None
        if raw_type == "llm:end":
            pt = inner.get("prompt_tokens", 0) or 0
            ct = inner.get("completion_tokens", 0) or 0
            tt = inner.get("total_tokens", 0) or 0
            token_count = tt if tt else (pt + ct)
        if data_id:
            if raw_type.endswith(":start") or raw_type == "agent:start":
                open_spans[data_id] = {"ts": inner.get("timestamp"), "row": r,
                                       "parsed": parsed, "depth": depth}
            elif raw_type.endswith(":end") or raw_type == "tool:error":
                start = open_spans.pop(data_id, None)
                if start and start["ts"] and inner.get("timestamp"):
                    duration_ms = int((inner["timestamp"] - start["ts"]) * 1000)
        events.append(serialize_event(r, parsed, duration_ms, token_count, depth))
    next_cursor = None
    has_more = len(rows) > limit
    if has_more:
        events = events[:limit]
        if events and events[-1].get("created_at"):
            next_cursor = encode_cursor(datetime.fromisoformat(events[-1]["created_at"]))
    return {"object": "list", "data": events, "has_more": has_more, "next_cursor": next_cursor}


class LogsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_sessions(self, status: str | None = None, search: str | None = None,
                            limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1
        if status:
            conditions.append(f"s.status = ${idx}"); params.append(status); idx += 1
        if search and search.strip():
            conditions.append(f"(s.id ILIKE ${idx} OR s.prompt ILIKE ${idx})")
            params.append(f"%{search.strip()}%"); idx += 1
        cursor_dt = decode_cursor(cursor)
        if cursor_dt:
            conditions.append(f"s.updated_at < ${idx}"); params.append(cursor_dt); idx += 1
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = await self.db.fetch(
            f"SELECT s.id, s.status, s.prompt, s.total_tokens, s.total_cost, "
            f"s.created_at, s.updated_at, (SELECT COUNT(*) FROM trace_events te WHERE te.run_id = s.id) as event_count "
            f"FROM sessions s{where} ORDER BY s.updated_at DESC LIMIT ${idx}", *params, limit + 1,
        )
        sessions_list = []
        has_more = len(rows) > limit
        for r in rows[:limit]:
            sessions_list.append({
                "object": "session", "id": r["id"], "status": r["status"],
                "prompt": (r["prompt"] or "")[:500], "total_tokens": r["total_tokens"] or 0,
                "total_cost": r["total_cost"] or 0.0, "event_count": r.get("event_count", 0),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            })
        next_cursor = None
        if has_more and sessions_list and sessions_list[-1].get("updated_at"):
            next_cursor = encode_cursor(datetime.fromisoformat(sessions_list[-1]["updated_at"]))
        return {"object": "list", "data": sessions_list, "has_more": has_more, "next_cursor": next_cursor}

    async def get_session(self, session_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
        if not row:
            return None
        event_rows = await self.db.fetch("SELECT event_type, event_data FROM trace_events WHERE run_id = $1", session_id)
        event_type_counts: dict[str, int] = {}
        total_tokens = 0
        total_cost = 0.0
        for r in event_rows:
            dt = normalize_type(r["event_type"])
            event_type_counts[dt] = event_type_counts.get(dt, 0) + 1
            if r["event_type"] == "llm:end":
                parsed = parse_event_data(r.get("event_data"))
                inner = parsed.get("data", parsed)
                pt = inner.get("prompt_tokens", 0) or 0
                ct = inner.get("completion_tokens", 0) or 0
                tt = inner.get("total_tokens", 0) or 0
                total_tokens += tt if tt else (pt + ct)
                total_cost += (pt * 0.000002) + (ct * 0.00001)
        return {
            "object": "session", "id": row["id"], "status": row["status"],
            "prompt": row["prompt"] or "", "total_tokens": max(row["total_tokens"] or 0, total_tokens),
            "total_cost": max(row["total_cost"] or 0.0, round(total_cost, 6)),
            "stats": {"event_count": len(event_rows), "event_type_counts": event_type_counts},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    async def list_events(self, session_id: str, event_type: str | None = None,
                          search: str | None = None, since: str | None = None,
                          until: str | None = None, limit: int = 50,
                          cursor: str | None = None) -> dict[str, Any]:
        session = await self.db.fetchrow("SELECT id FROM sessions WHERE id = $1", session_id)
        if not session:
            return {"error": "not_found"}
        conditions: list[str] = ["te.run_id = $1"]
        params: list[Any] = [session_id]
        param_idx = 2
        if event_type and event_type.strip():
            type_filters = [t.strip() for t in event_type.split(",") if t.strip()]
            type_conds = []
            for tf in type_filters:
                mapped = [k for k, v in DISPLAY_TYPE_MAP.items() if v == tf]
                if tf == "delegate":
                    mapped = ["delegate.%"]
                if tf == "error":
                    mapped = [k for k in DISPLAY_TYPE_MAP if k.startswith("tool:error") or k == "tool:error"]
                if mapped:
                    if any(m.endswith("%") for m in mapped):
                        for m in mapped:
                            type_conds.append(f"te.event_type LIKE ${param_idx}"); params.append(m); param_idx += 1
                    else:
                        ph = ", ".join(f"${param_idx + i}" for i in range(len(mapped)))
                        type_conds.append(f"te.event_type IN ({ph})")
                        params.extend(mapped); param_idx += len(mapped)
                else:
                    type_conds.append(f"te.event_type = ${param_idx}"); params.append(tf); param_idx += 1
            if type_conds:
                conditions.append("(" + " OR ".join(type_conds) + ")")
        if search and search.strip():
            conditions.append(f"te.event_data::text ILIKE ${param_idx}")
            params.append(f"%{search.strip()}%"); param_idx += 1
        cursor_dt = decode_cursor(cursor)
        if cursor_dt:
            conditions.append(f"te.created_at > ${param_idx}"); params.append(cursor_dt); param_idx += 1
        if since:
            try:
                conditions.append(f"te.created_at >= ${param_idx}"); params.append(datetime.fromisoformat(since)); param_idx += 1
            except ValueError:
                pass
        if until:
            try:
                conditions.append(f"te.created_at <= ${param_idx}"); params.append(datetime.fromisoformat(until)); param_idx += 1
            except ValueError:
                pass
        rows = await self.db.fetch(
            f"SELECT te.id, te.event_type, te.event_data, te.parent_id, te.agent_id, te.created_at "
            f"FROM trace_events te WHERE {' AND '.join(conditions)} ORDER BY te.created_at ASC LIMIT ${param_idx}",
            *params, limit + 1,
        )
        root_agent_id = None
        if rows:
            root_agent_id = rows[0].get("agent_id") or ""
        return build_events_response([dict(r) for r in rows], limit, root_agent_id=root_agent_id)
