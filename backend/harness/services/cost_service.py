"""Cost service — session/global/per-model cost aggregation queries."""

from __future__ import annotations

import logging
from typing import Any

from harness.memory.database import Database

logger = logging.getLogger(__name__)


class CostService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_session_cost(self, session_id: str) -> dict[str, Any]:
        try:
            rows = await self.db.fetch(
                "SELECT model, provider, SUM(input_tokens) as input_tokens, "
                "SUM(output_tokens) as output_tokens, "
                "SUM(cache_read_tokens) as cache_read_tokens, "
                "SUM(estimated_cost_usd) as estimated_cost "
                "FROM token_usage WHERE session_id = $1 "
                "GROUP BY model, provider ORDER BY estimated_cost DESC",
                session_id,
            )
            total = sum(r["estimated_cost"] for r in rows)
            return {"session_id": session_id, "models": [dict(r) for r in rows],
                    "total_cost": round(total, 6), "currency": "USD"}
        except Exception as e:
            return {"error": str(e)}

    async def get_global_cost(self) -> dict[str, Any]:
        from harness.cost_tracker import GlobalBudgetTracker
        return await GlobalBudgetTracker(self.db).get_global_cost()

    async def get_per_model(self) -> dict[str, Any]:
        try:
            rows = await self.db.fetch(
                "SELECT model, COUNT(DISTINCT session_id) as session_count, "
                "SUM(input_tokens) as total_input, SUM(output_tokens) as total_output, "
                "SUM(estimated_cost_usd) as total_cost FROM token_usage "
                "WHERE timestamp >= NOW() - INTERVAL '30 days' "
                "GROUP BY model ORDER BY total_cost DESC"
            )
            return {"models": [dict(r) for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    async def get_pricing_cache(self) -> dict[str, Any]:
        from harness.cost_tracker import get_pricing_cache
        cache = get_pricing_cache()
        usage_counts: dict[str, int] = {}
        try:
            rows = await self.db.fetch("SELECT model, COUNT(*) as cnt FROM token_usage GROUP BY model")
            for r in rows:
                usage_counts[r["model"].lower().strip()] = r["cnt"]
        except Exception:
            pass
        models = []
        for slug, rates in cache._in_memory.items():
            usage = 0
            slug_key = slug.lower().strip()
            for model_name, cnt in usage_counts.items():
                if slug_key in model_name or model_name in slug_key:
                    usage += cnt
                    break
            models.append({
                "slug": slug,
                "input_per_1k": round(rates.get("input", 0) * 1000, 6),
                "output_per_1k": round(rates.get("output", 0) * 1000, 6),
                "input_per_1m": round(rates.get("input", 0) * 1_000_000, 6),
                "output_per_1m": round(rates.get("output", 0) * 1_000_000, 6),
                "cache_read_per_1k": round(rates.get("cache_read", 0) * 1000, 6),
                "context_length": rates.get("context_length"),
                "supports_vision": rates.get("supports_vision", False),
                "supports_reasoning": rates.get("supports_reasoning", False),
                "supports_tool_calls": rates.get("supports_tool_calls", False),
                "usage_count": usage,
            })
        models.sort(key=lambda m: (-m["usage_count"], m["slug"]))
        return {"models": models, "count": len(models), "cached_at": getattr(cache, "_last_refresh", 0)}

    async def get_daily_trend(self) -> dict[str, Any]:
        try:
            rows = await self.db.fetch(
                "SELECT DATE(timestamp) as day, SUM(estimated_cost_usd) as cost, "
                "SUM(input_tokens + output_tokens) as total_tokens "
                "FROM token_usage WHERE timestamp >= NOW() - INTERVAL '30 days' "
                "GROUP BY day ORDER BY day"
            )
            return {"days": [dict(r) for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    async def get_per_role(self, days: int = 7) -> dict[str, Any]:
        try:
            rows = await self.db.fetch(
                "SELECT agent_role, COUNT(*) as total_calls, "
                "SUM(input_tokens) as total_input, SUM(output_tokens) as total_output, "
                "SUM(estimated_cost_usd) as total_cost, SUM(duration_ms) as total_duration_ms "
                "FROM agent_delegations WHERE created_at >= NOW() - ($1 || ' days')::interval "
                "GROUP BY agent_role ORDER BY total_cost DESC",
                str(days),
            )
            total = sum(r["total_cost"] for r in rows)
            return {"roles": [dict(r) for r in rows], "total_cost": round(total, 6), "days": days}
        except Exception as e:
            return {"error": str(e)}

    async def get_model_stats(self, days: int = 30) -> dict[str, Any]:
        try:
            rows = await self.db.fetch(
                "SELECT model, provider, COUNT(*) as total_calls, "
                "SUM(input_tokens) as total_input, SUM(output_tokens) as total_output, "
                "SUM(estimated_cost_usd) as total_cost FROM token_usage "
                "WHERE timestamp >= NOW() - ($1 || ' days')::interval "
                "GROUP BY model, provider ORDER BY total_cost DESC",
                str(days),
            )
            return {"models": [dict(r) for r in rows], "total_days": days}
        except Exception as e:
            return {"error": str(e)}
