"""Quality Score and Release Readiness engine.

Computes a single 0-100 quality score from:
  - Test pass rate (40%)
  - Code coverage (20%)
  - Flaky test rate (20%)
  - Defect density (10%)
  - Automation coverage (10%)

Go/no-go threshold: 80+ = go, 60-79 = caution, <60 = no-go.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 14
GO_THRESHOLD = 80
CAUTION_THRESHOLD = 60

WEIGHTS = {
    "pass_rate": 0.40,
    "coverage": 0.20,
    "flaky_rate": 0.20,
    "defect_density": 0.10,
    "automation_coverage": 0.10,
}


async def compute_quality_score(db: Any, project_id: str = "", days: int = LOOKBACK_DAYS) -> dict[str, Any]:
    """Compute the quality score from all available metrics.

    Returns a dict with the overall score, component scores, and go/no-go decision.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    components: dict[str, float] = {}
    details: dict[str, Any] = {}

    # 1. Test pass rate (40%)
    pass_rate, pass_details = await _compute_pass_rate(db, since)
    if pass_rate is not None:
        components["pass_rate"] = pass_rate * WEIGHTS["pass_rate"]
        details["pass_rate"] = pass_details

    # 2. Code coverage (20%)
    coverage, cov_details = await _compute_coverage_score(db, since)
    if coverage is not None:
        components["coverage"] = coverage * WEIGHTS["coverage"]
        details["coverage"] = cov_details

    # 3. Flaky test rate (20%)
    flaky, flaky_details = await _compute_flaky_score(db, since)
    if flaky is not None:
        components["flaky_rate"] = flaky * WEIGHTS["flaky_rate"]
        details["flaky_rate"] = flaky_details

    # 4. Defect density (10%)
    defects, defect_details = await _compute_defect_score(db, since)
    if defects is not None:
        components["defect_density"] = defects * WEIGHTS["defect_density"]
        details["defect_density"] = defect_details

    # 5. Automation coverage (10%)
    automation, auto_details = await _compute_automation_score(db, since)
    if automation is not None:
        components["automation_coverage"] = automation * WEIGHTS["automation_coverage"]
        details["automation_coverage"] = auto_details

    if not components:
        return {"score": None, "verdict": "no-data", "period_days": days}

    total_score = round(sum(components.values()), 1)

    # Determine release readiness
    if total_score >= GO_THRESHOLD:
        verdict = "go"
    elif total_score >= CAUTION_THRESHOLD:
        verdict = "caution"
    else:
        verdict = "no-go"

    # Find the weakest area
    min_component = min(components, key=components.get)
    blocker = details[min_component].get("blocker", "")

    return {
        "score": total_score,
        "verdict": verdict,
        "thresholds": {"go": GO_THRESHOLD, "caution": CAUTION_THRESHOLD},
        "components": {
            name: {
                "raw": round(val / WEIGHTS[name], 2) if WEIGHTS[name] > 0 else 0,
                "weighted": round(val, 2),
                "weight": WEIGHTS[name],
                "details": details[name],
            }
            for name, val in components.items()
        },
        "weakest_area": min_component,
        "blocker": blocker,
        "period_days": days,
    }


async def _compute_pass_rate(db: Any, since: datetime) -> tuple[float, dict]:
    """Compute test pass rate as a 0-100 score."""
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed "
            "FROM test_results WHERE created_at >= $1",
            since,
        )
        total = row["total"] or 0
        passed = row["passed"] or 0
        if total == 0:
            return None, {"note": "no test data", "total": 0, "passed": 0, "blocker": ""}
        rate = (passed / total) * 100
        blocker = "" if rate >= 90 else f"Pass rate {rate:.1f}% is below 90% target"
        return min(rate, 100), {"total": total, "passed": passed, "rate": round(rate, 1), "blocker": blocker}
    except Exception as e:
        logger.warning("Pass rate query failed: %s", e)
        return 0, {"error": str(e), "blocker": "Unable to compute pass rate"}


async def _compute_coverage_score(db: Any, since: datetime) -> tuple[float, dict]:
    """Compute coverage as a 0-100 score."""
    try:
        row = await db.fetchrow(
            "SELECT line_coverage, total_lines, covered_lines FROM coverage_reports "
            "WHERE created_at >= $1 ORDER BY created_at DESC LIMIT 1",
            since,
        )
        if not row:
            return None, {"note": "no coverage data", "blocker": ""}
        coverage = float(row["line_coverage"] or 0)
        blocker = "" if coverage >= 80 else f"Coverage {coverage:.1f}% is below 80% target"
        return min(coverage, 100), {
            "coverage": round(coverage, 1),
            "total_lines": row["total_lines"],
            "covered_lines": row["covered_lines"],
            "blocker": blocker,
        }
    except Exception as e:
        logger.warning("Coverage query failed: %s", e)
        return 0, {"error": str(e), "blocker": "Unable to compute coverage"}


async def _compute_flaky_score(db: Any, since: datetime) -> tuple[float, dict]:
    """Compute flaky score — inverse of flaky rate. 0 flaky = 100 score."""
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN is_quarantined = true THEN 1 ELSE 0 END) as quarantined, "
            "COALESCE(AVG(flaky_score), 0) as avg_flaky "
            "FROM flaky_tests"
        )
        total = row["total"] or 0
        quarantined = row["quarantined"] or 0
        avg_flaky = float(row["avg_flaky"] or 0)

        if total == 0:
            return None, {"note": "no flaky data", "total": 0}

        # Score = 100 - (quarantined_ratio * 50 + avg_flaky * 50)
        quarantined_ratio = quarantined / total if total > 0 else 0
        score = 100 - (quarantined_ratio * 50 + avg_flaky * 50)
        score = max(0, min(100, score))

        blocker = "" if score >= 80 else f"{quarantined} quarantined tests, avg flaky score {avg_flaky:.2f}"
        return score, {
            "total": total,
            "quarantined": quarantined,
            "avg_flaky_score": round(avg_flaky, 3),
            "score": round(score, 1),
            "blocker": blocker,
        }
    except Exception as e:
        logger.warning("Flaky query failed: %s", e)
        return 100, {"note": "fallback", "blocker": ""}


async def _compute_defect_score(db: Any, since: datetime) -> tuple[float, dict]:
    """Compute defect density score. Lower defect density = higher score."""
    try:
        # Count failed test results as defects
        row = await db.fetchrow(
            "SELECT COUNT(*) as failed, COUNT(DISTINCT test_name) as unique_failed "
            "FROM test_results WHERE status = 'failed' AND created_at >= $1",
            since,
        )
        failed = row["failed"] or 0
        unique_failed = row["unique_failed"] or 0

        total_row = await db.fetchrow(
            "SELECT COUNT(*) as total FROM test_results WHERE created_at >= $1",
            since,
        )
        total = total_row["total"] or 0

        if total == 0:
            return None, {"note": "no test data", "total": 0}

        # Defect density = failed / total. Score = 100 - (density * 100)
        density = failed / total if total > 0 else 0
        score = max(0, 100 - (density * 100))

        blocker = "" if score >= 80 else f"{failed} failures ({unique_failed} unique tests)"
        return score, {
            "failed": failed,
            "unique_failed": unique_failed,
            "total": total,
            "density": round(density, 3),
            "score": round(score, 1),
            "blocker": blocker,
        }
    except Exception as e:
        logger.warning("Defect query failed: %s", e)
        return 100, {"note": "fallback", "blocker": ""}


async def _compute_automation_score(db: Any, since: datetime) -> tuple[float, dict]:
    """Compute automation coverage score based on pipeline runs vs manual."""
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as total_runs FROM pipeline_runs WHERE created_at >= $1",
            since,
        )
        total_runs = row["total_runs"] or 0

        if total_runs == 0:
            return None, {"note": "no pipeline data", "total_runs": 0}

        # If we have pipeline runs, automation coverage is implied
        # Score based on test count per run
        test_row = await db.fetchrow(
            "SELECT AVG(test_count) as avg_tests FROM pipeline_runs "
            "WHERE created_at >= $1 AND test_count > 0",
            since,
        )
        avg_tests = float(test_row["avg_tests"] or 0) if test_row else 0

        # More automated tests = higher score, capped at 100
        score = min(100, avg_tests * 5 + 50) if avg_tests > 0 else 50
        return score, {
            "total_runs": total_runs,
            "avg_tests_per_run": round(avg_tests, 1),
            "score": round(score, 1),
            "blocker": "",
        }
    except Exception as e:
        logger.warning("Automation query failed: %s", e)
        return 50, {"note": "fallback", "blocker": ""}
