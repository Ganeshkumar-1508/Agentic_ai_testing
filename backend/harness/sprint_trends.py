"""Sprint quality trends — tracks metrics over time with regression alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

SPRINT_DAYS = 14
REGRESSION_THRESHOLD = 0.1  # 10% drop triggers alert


async def get_sprint_trends(db: Any, sprints: int = 6) -> dict[str, Any]:
    """Get quality trends over the last N sprints with regression alerts."""
    now = datetime.now(timezone.utc)
    sprint_data = []
    alerts = []

    for i in range(sprints, 0, -1):
        sprint_end = now - timedelta(days=(i - 1) * SPRINT_DAYS)
        sprint_start = now - timedelta(days=i * SPRINT_DAYS)

        metrics = await _compute_sprint_metrics(db, sprint_start, sprint_end)
        sprint_data.append({
            "sprint": f"Sprint {sprints - i + 1}",
            "start_date": sprint_start.isoformat(),
            "end_date": sprint_end.isoformat(),
            **metrics,
        })

    # Detect regressions by comparing consecutive sprints
    for i in range(1, len(sprint_data)):
        prev = sprint_data[i - 1]
        curr = sprint_data[i]
        regressions = _detect_regressions(prev, curr)
        if regressions:
            alerts.append({
                "from_sprint": prev["sprint"],
                "to_sprint": curr["sprint"],
                "regressions": regressions,
            })

    return {
        "sprints": sprint_data,
        "alerts": alerts,
        "alert_count": len(alerts),
    }


async def _compute_sprint_metrics(db, start: datetime, end: datetime) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "pass_rate": 0, "total_tests": 0, "failed_tests": 0,
        "coverage": None, "flaky_rate": 0, "quality_score": 0,
        "total_runs": 0, "defect_count": 0,
    }

    # Pass rate
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) as passed "
            "FROM test_results WHERE created_at BETWEEN $1 AND $2", start, end,
        )
        if row and row["total"]:
            metrics["total_tests"] = row["total"]
            metrics["failed_tests"] = row["total"] - (row["passed"] or 0)
            metrics["pass_rate"] = round((row["passed"] / row["total"]) * 100, 1)
    except Exception:
        pass

    # Pipeline runs
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as runs FROM pipeline_runs WHERE created_at BETWEEN $1 AND $2", start, end,
        )
        if row:
            metrics["total_runs"] = row["runs"]
    except Exception:
        pass

    # Coverage (latest in sprint)
    try:
        row = await db.fetchrow(
            "SELECT line_coverage FROM coverage_reports WHERE created_at BETWEEN $1 AND $2 ORDER BY created_at DESC LIMIT 1",
            start, end,
        )
        if row:
            metrics["coverage"] = round(float(row["line_coverage"]), 1)
    except Exception:
        pass

    # Flaky rate
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as total, SUM(CASE WHEN is_quarantined=true THEN 1 ELSE 0 END) as quarantined FROM flaky_tests"
        )
        if row and row["total"]:
            metrics["flaky_rate"] = round((row["quarantined"] / row["total"]) * 100, 1)
    except Exception:
        pass

    # Quality score approximation
    pass_rate = metrics["pass_rate"]
    coverage = metrics["coverage"] or 50
    flaky = metrics["flaky_rate"]
    metrics["quality_score"] = round(pass_rate * 0.4 + coverage * 0.3 + (100 - flaky) * 0.3, 1)

    # Defect count
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as defects FROM test_results WHERE status='failed' AND created_at BETWEEN $1 AND $2",
            start, end,
        )
        if row:
            metrics["defect_count"] = row["defects"]
    except Exception:
        pass

    return metrics


def _detect_regressions(prev: dict, curr: dict) -> list[dict]:
    """Compare consecutive sprints and flag regressions."""
    regressions = []
    checks = [
        ("pass_rate", "decrease", REGRESSION_THRESHOLD),
        ("quality_score", "decrease", REGRESSION_THRESHOLD),
        ("flaky_rate", "increase", REGRESSION_THRESHOLD),
        ("defect_count", "increase", REGRESSION_THRESHOLD),
    ]

    for metric, direction, threshold in checks:
        p_val = prev.get(metric, 0) or 0
        c_val = curr.get(metric, 0) or 0

        if p_val == 0:
            continue

        if direction == "decrease":
            change = (p_val - c_val) / p_val
            if change >= threshold:
                regressions.append({
                    "metric": metric,
                    "previous": p_val,
                    "current": c_val,
                    "change_pct": round(change * 100, 1),
                    "direction": "down",
                })
        else:
            change = (c_val - p_val) / p_val
            if change >= threshold:
                regressions.append({
                    "metric": metric,
                    "previous": p_val,
                    "current": c_val,
                    "change_pct": round(change * 100, 1),
                    "direction": "up",
                })

    return regressions
