"""Analytics endpoints — thin router, delegates to AnalyticsService."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db
from harness.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/usage")
async def get_usage_analytics(request: Request, days: int = 30):
    svc = AnalyticsService(get_db(request))
    return await svc.get_daily_usage(days)


@router.get("/analytics/models")
async def get_model_analytics(request: Request, days: int = 30):
    svc = AnalyticsService(get_db(request))
    return await svc.get_model_breakdown(days)
