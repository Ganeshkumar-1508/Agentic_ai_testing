"""Agent Evaluation API — aggregated metrics for the evaluation dashboard.

Follows Arize's four-pillar model: Outcome, Cost, Safety, Behavior.
All data is aggregated from existing Postgres tables (sessions, token_usage,
stream_events, workflow_executions).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluate", tags=["evaluate"])


def _days_ago(days: int = 30) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/overview")
async def evaluate_overview(request: Request):
    """Aggregated agent evaluation metrics.

    Returns:
      outcome: success_rate, total/completed/failed/cancelled counts
      cost: total_spend, cost_per_completed, avg_cost_per_session, by_model
      safety: error_count, blocked_action_count
      behavior: avg_tool_calls_per_session, total_tool_calls, sessions_trend
    """
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    result: dict[str, Any] = {
        "outcome": {"success_rate": 0, "total": 0, "completed": 0, "failed": 0, "cancelled": 0, "running": 0},
        "cost": {"total_spend": 0.0, "cost_per_completed": 0.0, "avg_cost_per_session": 0.0, "by_model": []},
        "safety": {"error_count": 0, "blocked_action_count": 0},
        "behavior": {"avg_tool_calls_per_session": 0.0, "total_tool_calls": 0, "sessions_trend": []},
    }

    if not db or not hasattr(db, "fetch"):
        return result

    try:
        # ── Outcome: session counts by status ──
        rows = await db.fetch(
            "SELECT status, COUNT(*) as cnt FROM sessions "
            "WHERE created_at >= $1 GROUP BY status",
            _days_ago(30),
        )
        total = 0
        for r in rows:
            s = r["status"]
            c = r["cnt"]
            result["outcome"][s if s in ("completed", "failed", "cancelled", "running") else "failed"] = c
            total += c
        result["outcome"]["total"] = total
        completed = result["outcome"]["completed"]
        result["outcome"]["success_rate"] = round((completed / total * 100) if total > 0 else 0, 1)
    except Exception as exc:
        logger.warning("evaluate outcome query failed: %s", exc)

    try:
        # ── Cost: aggregate from token_usage ──
        cost_rows = await db.fetch(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) as total_cost, "
            "COUNT(DISTINCT session_id) as session_count "
            "FROM token_usage WHERE timestamp >= $1",
            _days_ago(30),
        )
        total_spend = float(cost_rows[0]["total_cost"] or 0)
        session_count = int(cost_rows[0]["session_count"] or 0)
        result["cost"]["total_spend"] = round(total_spend, 4)
        result["cost"]["cost_per_completed"] = round(total_spend / completed, 6) if completed > 0 else 0
        result["cost"]["avg_cost_per_session"] = round(total_spend / session_count, 6) if session_count > 0 else 0

        # Cost by model
        model_rows = await db.fetch(
            "SELECT model, COALESCE(SUM(estimated_cost_usd), 0) as cost, "
            "COUNT(*) as calls FROM token_usage "
            "WHERE timestamp >= $1 AND model != '' "
            "GROUP BY model ORDER BY cost DESC LIMIT 10",
            _days_ago(30),
        )
        result["cost"]["by_model"] = [
            {"model": r["model"], "cost": round(float(r["cost"]), 4), "calls": r["calls"]}
            for r in model_rows
        ]
    except Exception as exc:
        logger.warning("evaluate cost query failed: %s", exc)

    try:
        # ── Safety: error events from stream_events ──
        err_rows = await db.fetch(
            "SELECT COUNT(*) as cnt FROM stream_events "
            "WHERE event_type IN ('ErrorEvent', 'error', 'approval:denied', "
            "'approval:blocked') AND created_at >= $1",
            _days_ago(30),
        )
        result["safety"]["error_count"] = err_rows[0]["cnt"] if err_rows else 0

        blocked_rows = await db.fetch(
            "SELECT COUNT(*) as cnt FROM stream_events "
            "WHERE event_type IN ('approval:blocked', 'guardrail:denied', "
            "'tool:blocked') AND created_at >= $1",
            _days_ago(30),
        )
        result["safety"]["blocked_action_count"] = blocked_rows[0]["cnt"] if blocked_rows else 0
    except Exception as exc:
        logger.warning("evaluate safety query failed: %s", exc)

    try:
        # ── Behavior: tool call counts + daily trend ──
        tool_rows = await db.fetch(
            "SELECT COUNT(*) as cnt FROM stream_events "
            "WHERE event_type IN ('ToolExecutionStarted', 'tool.execution.started', "
            "'tool:start') AND created_at >= $1",
            _days_ago(30),
        )
        total_tool_calls = tool_rows[0]["cnt"] if tool_rows else 0
        result["behavior"]["total_tool_calls"] = total_tool_calls
        result["behavior"]["avg_tool_calls_per_session"] = round(
            total_tool_calls / total, 1
        ) if total > 0 else 0

        # Daily session trend (last 14 days)
        trend_rows = await db.fetch(
            "SELECT DATE(created_at) as day, COUNT(*) as cnt, "
            "COALESCE(SUM(total_cost), 0) as cost "
            "FROM sessions WHERE created_at >= $1 "
            "GROUP BY DATE(created_at) ORDER BY day ASC",
            _days_ago(14),
        )
        result["behavior"]["sessions_trend"] = [
            {"day": str(r["day"]), "count": r["cnt"], "cost": round(float(r["cost"]), 4)}
            for r in trend_rows
        ]
    except Exception as exc:
        logger.warning("evaluate behavior query failed: %s", exc)

    return result


@router.get("/agents")
async def evaluate_agents(request: Request):
    """Per-agent-role breakdown of evaluation metrics."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass
    if not db or not hasattr(db, "fetch"):
        return {"agents": []}

    try:
        rows = await db.fetch(
            "SELECT agent_role, status, COUNT(*) as cnt, "
            "COALESCE(SUM(total_tokens), 0) as tokens, "
            "COALESCE(SUM(total_cost), 0) as cost "
            "FROM sessions WHERE created_at >= $1 AND agent_role != '' "
            "GROUP BY agent_role, status ORDER BY agent_role",
            _days_ago(30),
        )
    except Exception as exc:
        logger.warning("evaluate agents query failed: %s", exc)
        return {"agents": []}

    agents: dict[str, Any] = {}
    for r in rows:
        role = r["agent_role"]
        if role not in agents:
            agents[role] = {"role": role, "total": 0, "completed": 0, "failed": 0, "tokens": 0, "cost": 0.0}
        a = agents[role]
        a["total"] += r["cnt"]
        if r["status"] == "completed":
            a["completed"] += r["cnt"]
        elif r["status"] == "failed":
            a["failed"] += r["cnt"]
        a["tokens"] += r["tokens"]
        a["cost"] += r["cost"]

    for a in agents.values():
        a["success_rate"] = round((a["completed"] / a["total"] * 100) if a["total"] > 0 else 0, 1)
        a["cost_per_task"] = round(a["cost"] / a["completed"], 6) if a["completed"] > 0 else 0

    return {"agents": list(agents.values())}
