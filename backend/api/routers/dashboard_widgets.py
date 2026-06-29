"""Dashboard widget endpoints — thin delegates to DashboardWidgetService.

Each endpoint is read-only and falls back to safe defaults (empty lists,
zeros) when underlying tables are empty. Never returns mock/synthetic
data — if the table is empty, the response is empty.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request

from ..deps import get_db
from harness.services.dashboard_service import DashboardWidgetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard/widgets", tags=["dashboard-widgets"])


def _svc(request: Request) -> DashboardWidgetService:
    return DashboardWidgetService(get_db(request))


@router.get("/self-healing")
async def self_healing_widget(request: Request, limit: int = Query(8, ge=1, le=50)):
    return await _svc(request).get_self_healing(limit=limit)


@router.get("/logs")
async def logs_widget(
    request: Request,
    type: str = Query("console", description="console | network | errors"),
    limit: int = Query(20, ge=1, le=200),
):
    return await _svc(request).get_logs(type=type, limit=limit)


@router.get("/provider-failover")
async def provider_failover_widget(request: Request, days: int = Query(7, ge=1, le=90)):
    return await _svc(request).get_provider_failover(days=days)


@router.get("/defect-prediction")
async def defect_prediction_widget(request: Request, limit: int = Query(8, ge=1, le=30)):
    return await _svc(request).get_defect_prediction(limit=limit)


@router.get("/rca-clusters")
async def rca_clusters_widget(request: Request, days: int = Query(30, ge=1, le=90)):
    return await _svc(request).get_rca_clusters(days=days)


@router.get("/traceability")
async def traceability_widget(request: Request):
    return await _svc(request).get_traceability()


@router.get("/cost-by-model")
async def cost_by_model_widget(request: Request, days: int = Query(30, ge=1, le=90)):
    return await _svc(request).get_cost_by_model(days=days)


@router.get("/token-heatmap")
async def token_heatmap_widget(request: Request, days: int = Query(7, ge=1, le=30)):
    return await _svc(request).get_token_heatmap(days=days)


@router.get("/coverage-gaps")
async def coverage_gaps_widget(request: Request, threshold: float = Query(80.0, ge=0, le=100)):
    return await _svc(request).get_coverage_gaps(threshold=threshold)


@router.get("/analytics-30d")
async def analytics_30d_widget(request: Request, days: int = Query(30, ge=1, le=90)):
    return await _svc(request).get_analytics_30d(days=days)


@router.get("/quick-actions")
async def quick_actions_widget(request: Request):
    return await _svc(request).get_quick_actions()


@router.get("/coverage")
async def coverage_widget(request: Request, days: int = Query(30, ge=1, le=90)):
    return await _svc(request).get_coverage(days=days)


@router.get("/sprint-trends")
async def sprint_trends_widget(request: Request, sprints: int = Query(5, ge=1, le=12)):
    return await _svc(request).get_sprint_trends(sprints=sprints)


@router.get("/notifications")
async def notifications_widget(request: Request, limit: int = Query(8, ge=1, le=50)):
    return await _svc(request).get_notifications(limit=limit)


@router.get("/system-health")
async def system_health_widget(request: Request):
    return await _svc(request).get_system_health()
