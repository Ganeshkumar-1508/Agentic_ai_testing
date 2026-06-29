"""Analytics service — usage + per-model aggregation queries."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from harness.memory.database import Database


class AnalyticsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_daily_usage(self, days: int = 30) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        daily: dict[str, dict] = {}
        totals = {"total_input": 0, "total_output": 0, "total_sessions": 0, "total_estimated_cost": 0.0}

        tu_rows = await self.db.fetch(
            "SELECT DATE(timestamp) as day, "
            "SUM(input_tokens) as input_tokens, "
            "SUM(output_tokens) as output_tokens, "
            "SUM(estimated_cost_usd) as estimated_cost "
            "FROM token_usage WHERE timestamp >= $1 GROUP BY day ORDER BY day",
            since,
        )
        for r in tu_rows:
            day_key = r["day"].strftime("%Y-%m-%d") if r["day"] else "unknown"
            inp = r["input_tokens"] or 0
            out = r["output_tokens"] or 0
            cost = float(r["estimated_cost"] or 0)
            daily[day_key] = {"day": day_key, "input_tokens": inp, "output_tokens": out,
                              "estimated_cost": round(cost, 6), "sessions": 0}
            totals["total_input"] += inp
            totals["total_output"] += out
            totals["total_estimated_cost"] += cost

        te_rows = await self.db.fetch(
            "SELECT DATE(created_at) as day, event_type FROM trace_events "
            "WHERE created_at >= $1 AND event_type IN ('llm:end', 'agent:start') ORDER BY created_at",
            since,
        )
        for r in te_rows:
            day_key = r["day"].strftime("%Y-%m-%d") if r["day"] else "unknown"
            daily.setdefault(day_key, {"day": day_key, "input_tokens": 0, "output_tokens": 0,
                                       "estimated_cost": 0.0, "sessions": 0})
            if r["event_type"] == "agent:start":
                daily[day_key]["sessions"] += 1
                totals["total_sessions"] += 1

        return {
            "daily": [v for k, v in sorted(daily.items()) if v["input_tokens"] > 0 or v["sessions"] > 0],
            "totals": totals,
        }

    async def get_model_breakdown(self, days: int = 30) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = await self.db.fetch(
            "SELECT model, SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens, "
            "SUM(estimated_cost_usd) as estimated_cost, COUNT(*) as api_calls "
            "FROM token_usage WHERE timestamp >= $1 GROUP BY model ORDER BY estimated_cost DESC",
            since,
        )
        models = []
        for r in rows:
            models.append({
                "model": r["model"], "input_tokens": r["input_tokens"] or 0,
                "output_tokens": r["output_tokens"] or 0,
                "estimated_cost": round(float(r["estimated_cost"] or 0), 6),
                "api_calls": r["api_calls"] or 0,
            })
        te_rows = await self.db.fetch(
            "SELECT event_data FROM trace_events WHERE created_at >= $1 AND event_type = 'llm:end'",
            since,
        )
        seen = {m["model"] for m in models}
        for r in te_rows:
            try:
                data = json.loads(r["event_data"]) if isinstance(r["event_data"], str) else r["event_data"]
                d = data.get("data", data)
                model = d.get("model", "unknown")
                if model not in seen:
                    inp = d.get("prompt_tokens", 0) or 0
                    out = d.get("completion_tokens", 0) or 0
                    models.append({
                        "model": model, "input_tokens": inp, "output_tokens": out,
                        "estimated_cost": round((inp * 0.000002) + (out * 0.00001), 6),
                        "api_calls": 1,
                    })
                    seen.add(model)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return {"models": models, "period_days": days}
