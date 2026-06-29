"""Cost tracking and budget enforcement per session and global.

Tracks token usage per session/subagent/model/tool. Persists to token_usage table.
Enforces budget caps with SSE alerts when thresholds are crossed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .pricing_cache import PricingCache

logger = logging.getLogger(__name__)

# Global pricing cache instance (initialized with DB on startup)
_pricing: PricingCache | None = None


def init_pricing_cache(db: Any) -> PricingCache:
    """Initialize the global pricing cache. Called on backend startup."""
    global _pricing
    _pricing = PricingCache(db)
    return _pricing


def get_pricing_cache() -> PricingCache:
    """Get the global pricing cache instance."""
    global _pricing
    if _pricing is None:
        _pricing = PricingCache()
    return _pricing

# Model rates cache — populated from PricePerToken MCP on first use
# Falls back to these built-in estimates if MCP is unavailable
_FALLBACK_RATES: dict[str, dict[str, float]] = {
    "default": {"input": 0.002, "output": 0.008, "cache_read": 0.001},
}

_model_rates_cache: dict[str, dict[str, float]] = dict(_FALLBACK_RATES)
_cache_loaded = False

DEFAULT_BUDGET_PER_SESSION_USD = 5.0
BUDGET_WARNING_THRESHOLD = 0.8  # 80% of budget triggers a warning alert
GLOBAL_BUDGET_RESET_DAYS = 30


class CostTracker:
    """Per-session cost tracking with budget enforcement."""

    def __init__(self, db: Any, session_id: str):
        self.db = db
        self.session_id = session_id
        self._session_budget = DEFAULT_BUDGET_PER_SESSION_USD
        self._running_cost: float = 0.0

    async def set_budget(self, budget_usd: float) -> None:
        self._session_budget = budget_usd

    async def record_usage(
        self,
        model: str,
        provider: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Record token usage and calculate cost. Persists to DB.

        Returns usage summary dict with cost breakdown and budget status.
        """
        cache = get_pricing_cache()
        rates = await cache.get_rate(model)
        cost_input = (input_tokens / 1000) * rates["input"]
        cost_output = (output_tokens / 1000) * rates["output"]
        cost_cache = (cache_read_tokens / 1000) * rates.get("cache_read", rates["input"] * 0.5)
        total_cost = cost_input + cost_output + cost_cache

        self._running_cost += total_cost

        try:
            await self.db.execute(
                """INSERT INTO token_usage
                   (session_id, task_id, model, provider,
                    input_tokens, output_tokens, cache_read_tokens,
                    cache_write_tokens, reasoning_tokens,
                    estimated_cost_usd)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                self.session_id, task_id, model, provider or "",
                input_tokens, output_tokens, cache_read_tokens,
                cache_write_tokens, reasoning_tokens, total_cost,
            )
        except Exception as e:
            logger.warning("Failed to persist token_usage: %s", e)

        usage_pct = (self._running_cost / self._session_budget) * 100 if self._session_budget > 0 else 0

        result = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "total_tokens": input_tokens + output_tokens + cache_read_tokens,
            "cost_input": round(cost_input, 6),
            "cost_output": round(cost_output, 6),
            "cost_cache": round(cost_cache, 6),
            "total_cost": round(total_cost, 6),
            "running_cost": round(self._running_cost, 6),
            "session_budget": self._session_budget,
            "budget_used_pct": round(usage_pct, 1),
            "budget_exceeded": self._running_cost >= self._session_budget,
            "budget_warning": usage_pct >= (BUDGET_WARNING_THRESHOLD * 100),
        }

        # Emit budget event if budget exceeded or warning threshold crossed
        if result["budget_exceeded"] or result["budget_warning"]:
            await self._emit_budget_event(result)

        return result

    async def _emit_budget_event(self, usage: dict[str, Any]) -> None:
        try:
            import json
            from harness.core.events import StatusEvent
            from harness.api.state import _shared_bus
            bus = _shared_bus
            if bus is not None:
                await bus.emit(StatusEvent(
                    message=f"budget.alert: {json.dumps(usage, default=str)[:500]}",
                ))
        except Exception:
            pass

    async def get_session_cost(self) -> dict[str, Any]:
        """Get aggregated cost for the current session across all subagents."""
        try:
            row = await self.db.fetchrow(
                "SELECT model, SUM(input_tokens) as input_tokens, "
                "SUM(output_tokens) as output_tokens, "
                "SUM(cache_read_tokens) as cache_read_tokens, "
                "SUM(estimated_cost_usd) as total_cost "
                "FROM token_usage WHERE session_id = $1 "
                "GROUP BY model ORDER BY total_cost DESC",
                self.session_id,
            )
            if row:
                return dict(row)
        except Exception:
            pass
        return {}


class GlobalBudgetTracker:
    """Tracks total spend across all sessions with rolling window."""

    def __init__(self, db: Any):
        self.db = db

    async def get_global_cost(self, days: int = GLOBAL_BUDGET_RESET_DAYS) -> dict[str, Any]:
        try:
            row = await self.db.fetchrow(
                "SELECT COUNT(DISTINCT session_id) as session_count, "
                "SUM(input_tokens) as total_input_tokens, "
                "SUM(output_tokens) as total_output_tokens, "
                "SUM(estimated_cost_usd) as total_cost "
                "FROM token_usage "
                "WHERE timestamp >= NOW() - INTERVAL '1 day' * $1",
                days,
            )
            if row:
                return dict(row)
        except Exception:
            pass
        return {"session_count": 0, "total_cost": 0}
