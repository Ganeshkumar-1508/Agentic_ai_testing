"""Cost tracking API endpoints — thin router, delegates to CostService."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db
from harness.services.cost_service import CostService

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("/session/{session_id}")
async def get_session_cost(request: Request, session_id: str):
    return await CostService(get_db(request)).get_session_cost(session_id)


@router.get("/global")
async def get_global_cost(request: Request):
    return await CostService(get_db(request)).get_global_cost()


@router.get("/per-model")
async def get_cost_per_model(request: Request):
    return await CostService(get_db(request)).get_per_model()


@router.get("/pricing-cache")
async def get_pricing_cache(request: Request):
    return await CostService(get_db(request)).get_pricing_cache()


@router.get("/budget")
async def get_budget_settings(request: Request):
    return {"default_session_budget_usd": 5.0, "warning_threshold_pct": 80, "global_reset_days": 30}


@router.post("/budget")
async def set_budget(request: Request, session_budget_usd: float = 5.0):
    return {"status": "updated", "budget": session_budget_usd}


@router.get("/daily-trend")
async def get_daily_cost_trend(request: Request):
    return await CostService(get_db(request)).get_daily_trend()


@router.get("/per-role")
async def get_cost_per_role(request: Request, days: int = 7):
    return await CostService(get_db(request)).get_per_role(days)


@router.get("/models/stats")
async def get_model_routing_stats(request: Request, days: int = 30):
    return await CostService(get_db(request)).get_model_stats(days)
