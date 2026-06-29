"""Stakeholder views API — role-filtered dashboards."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/stakeholder", tags=["stakeholder"])

ROLE_CONFIG = {
    "qa-engineer": {
        "label": "QA Engineer",
        "sections": ["test_execution", "flaky_tests", "coverage_gaps", "self_healing", "rca"],
    },
    "qa-manager": {
        "label": "QA Manager",
        "sections": ["quality_score", "defect_trends", "automation_coverage", "team_metrics", "sprint_progress"],
    },
    "executive": {
        "label": "Executive",
        "sections": ["quality_score", "release_readiness", "cost_trends", "pass_rates"],
    },
    "dev-team": {
        "label": "Dev Team",
        "sections": ["build_stability", "test_impact", "defect_prediction", "coverage_gaps"],
    },
}


@router.get("/{role}")
async def get_stakeholder_view(role: str, request: Request):
    """Get filtered dashboard data for a specific role."""
    db = get_db(request)

    config = ROLE_CONFIG.get(role)
    if not config:
        return {"error": f"Unknown role: {role}", "valid_roles": list(ROLE_CONFIG.keys())}

    data = {"role": role, "label": config["label"], "sections": {}}

    for section in config["sections"]:
        if section == "quality_score":
            from harness.quality_score import compute_quality_score
            data["sections"]["quality_score"] = await compute_quality_score(db)
        elif section == "flaky_tests":
            from harness.flaky_detector import get_flaky_summary
            data["sections"]["flaky_tests"] = await get_flaky_summary(db)
        elif section == "coverage_gaps":
            from harness.coverage_gaps import get_coverage_summary
            data["sections"]["coverage_gaps"] = await get_coverage_summary(db)
        elif section == "rca":
            from harness.rca import get_rca_summary
            data["sections"]["rca"] = await get_rca_summary(db)
        elif section == "self_healing":
            from harness.self_healing import get_healing_stats
            data["sections"]["self_healing"] = await get_healing_stats(db)
        elif section == "defect_prediction":
            from harness.defect_prediction import compute_risk_scores
            data["sections"]["defect_prediction"] = await compute_risk_scores(db)
        elif section in ("test_execution", "build_stability", "pass_rates"):
            data["sections"][section] = await _get_test_execution_summary(db)
        elif section == "automation_coverage":
            data["sections"][section] = await _get_automation_summary(db)
        elif section in ("defect_trends", "sprint_progress"):
            data["sections"][section] = await _get_defect_trends(db)
        elif section == "release_readiness":
            qs = await _get_test_execution_summary(db)
            qs["release_readiness"] = "on-track" if qs.get("pass_rate", 0) >= 90 else "needs-attention"
            data["sections"]["release_readiness"] = qs
        elif section == "cost_trends":
            from harness.cost_tracker import GlobalBudgetTracker
            tracker = GlobalBudgetTracker(db)
            data["sections"]["cost_trends"] = await tracker.get_global_cost()
        elif section == "test_impact":
            data["sections"]["test_impact"] = {"note": "Run POST /api/impact/analyze with changed_files"}
        elif section == "team_metrics":
            data["sections"]["team_metrics"] = await _get_team_metrics(db)

    return {"role": role, "label": config["label"], "data": data}


@router.get("/roles")
async def list_roles():
    """List available stakeholder roles and their sections."""
    return {
        "roles": {
            role: {"label": cfg["label"], "sections": cfg["sections"]}
            for role, cfg in ROLE_CONFIG.items()
        }
    }


async def _get_test_execution_summary(db) -> dict:
    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed, "
            "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed "
            "FROM test_results WHERE created_at >= NOW() - INTERVAL '14 days'"
        )
        total = row["total"] or 1
        passed = row["passed"] or 0
        failed = row["failed"] or 0
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round((passed / total) * 100, 1) if total > 0 else 0,
            "period_days": 14,
        }
    except Exception:
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0}


async def _get_automation_summary(db) -> dict:
    try:
        row = await db.fetchrow("SELECT COUNT(*) as runs FROM pipeline_runs WHERE created_at >= NOW() - INTERVAL '30 days'")
        return {"pipeline_runs": row["runs"] if row else 0, "period_days": 30}
    except Exception:
        return {"pipeline_runs": 0}


async def _get_defect_trends(db) -> dict:
    try:
        rows = await db.fetch(
            "SELECT DATE(created_at) as day, COUNT(*) as failures "
            "FROM test_results WHERE status = 'failed' "
            "AND created_at >= NOW() - INTERVAL '30 days' "
            "GROUP BY day ORDER BY day"
        )
        return {"trend": [{"date": r["day"].isoformat(), "failures": r["failures"]} for r in rows]}
    except Exception:
        return {"trend": []}


async def _get_team_metrics(db) -> dict:
    try:
        runs = await db.fetchrow("SELECT COUNT(*) as total, COUNT(DISTINCT run_id) as unique_runs FROM test_results")
        return {
            "total_results": runs["total"] if runs else 0,
            "unique_runs": runs["unique_runs"] if runs else 0,
        }
    except Exception:
        return {"total_results": 0, "unique_runs": 0}
