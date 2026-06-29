"""Quality Score API — release readiness gate + metric time-series."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/score")
async def get_quality_score(request: Request, days: int = 14):
    """Compute the current quality score and release readiness."""
    db = get_db(request)
    from harness.quality_score import compute_quality_score
    result = await compute_quality_score(db, days=days)
    return result


@router.get("/trend")
async def get_quality_trend(request: Request, days: int = 90):
    """Get quality score snapshots over time for trend charting."""
    db = get_db(request)
    from harness.quality_score import compute_quality_score

    now = datetime.now(timezone.utc)
    trend = []
    for i in range(days // 7, 0, -1):
        period_days = i * 7
        try:
            score = await compute_quality_score(db, days=period_days)
            if score.get("score") is not None:
                trend.append({
                    "date": (now - timedelta(days=period_days)).isoformat(),
                    "score": score["score"],
                    "verdict": score["verdict"],
                })
        except Exception:
            pass

    return {"trend": trend}


@router.get("/metrics")
async def get_quality_metrics(request: Request, period: str = "30d"):
    """Get time-series metrics from the quality_metrics table.

    Period: 7d, 30d, 90d
    Returns bucketed metric values (pass_rate, flaky_rate, coverage_line, etc.)
    """
    db = get_db(request)
    days = 30
    if period == "7d":
        days = 7
    elif period == "90d":
        days = 90

    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = await db.fetch(
        "SELECT metric_name, metric_value, created_at FROM quality_metrics "
        "WHERE created_at >= $1 ORDER BY created_at ASC",
        since,
    )

    series: dict[str, list[dict]] = {}
    for r in rows:
        m = r["metric_name"]
        if m not in series:
            series[m] = []
        series[m].append({
            "value": float(r["metric_value"]),
            "date": r["created_at"].isoformat() if r["created_at"] else "",
        })

    return {
        "period": period,
        "metrics": series,
        "available": list(series.keys()),
    }
