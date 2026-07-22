"""Ops service — DB queries for ops/analytics endpoints.
Extracted from api/routers/ops.py to isolate SQL from routing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from harness.memory.database import Database

logger = logging.getLogger(__name__)


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _safe_event_data(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
    return value if value is not None else {}


class OpsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_active_session(self) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT s.id, s.status, s.created_at, "
            "COALESCE(tu.tokens, 0) AS total_tokens, "
            "COALESCE(tu.cost, 0.0) AS total_cost "
            "FROM sessions s "
            "LEFT JOIN ("
            "  SELECT session_id, SUM(input_tokens + output_tokens) AS tokens, "
            "  SUM(estimated_cost_usd) AS cost "
            "  FROM token_usage GROUP BY session_id"
            ") tu ON tu.session_id = s.id "
            "WHERE s.status IN ('running', 'completed') "
            "AND s.created_at > NOW() - INTERVAL '30 minutes' "
            "ORDER BY s.created_at DESC LIMIT 1"
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "total_tokens": row["total_tokens"] or 0,
            "total_cost": float(row["total_cost"] or 0),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

    async def get_active_session_id(self) -> str | None:
        """Return the most recent active session ID, or None."""
        row = await self.db.fetchrow(
            "SELECT id FROM sessions WHERE status IN ('running', 'completed') "
            "ORDER BY created_at DESC LIMIT 1"
        )
        return row["id"] if row else None

    async def get_tool_call_count(self) -> int:
        row = await self.db.fetchrow(
            "SELECT COUNT(*) AS count FROM trace_events "
            "WHERE event_type IN ('tool.execution.started','tool.execution.completed','round.started','round.completed','llmcall.completed')"

            "WHERE event_type IN ('tool.execution.started','tool.execution.completed','llmcall.completed','round.started','agent.started','agent.completed') "
            "GROUP BY event_type"
        )
        total_tool_calls = await self.db.fetchval(
            "SELECT COUNT(*) FROM trace_events WHERE event_type LIKE 'delegate.tool_%'"
        )
        return {
            "sessions_total": session_row["total"] if session_row else 0,
            "total_tokens": session_row["total_tokens"] if session_row else 0,
            "total_cost": float(session_row["total_cost"]) if session_row and session_row["total_cost"] else 0.0,
            "delegate_event_counts": {r["event_type"]: r["count"] for r in delegate_counts},
            "total_tool_calls": total_tool_calls or 0,
        }

    async def get_pipeline_metrics(self, limit: int = 20) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT * FROM pipeline_metrics ORDER BY created_at DESC LIMIT $1", limit,
        )
        return [dict(r) for r in rows]

    async def get_agent_delegations(self, session_id: str = "", limit: int = 50) -> list[dict]:
        if session_id:
            rows = await self.db.fetch(
                "SELECT * FROM agent_delegations WHERE session_id = $1 ORDER BY started_at DESC LIMIT $2",
                session_id, limit,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM agent_delegations ORDER BY started_at DESC LIMIT $1", limit,
            )
        return [dict(r) for r in rows]

    async def get_sandbox_metrics(self, session_id: str = "", limit: int = 20) -> list[dict]:
        if session_id:
            rows = await self.db.fetch(
                "SELECT * FROM sandbox_metrics WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2",
                session_id, limit,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM sandbox_metrics ORDER BY created_at DESC LIMIT $1", limit,
            )
        return [dict(r) for r in rows]
