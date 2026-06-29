"""Dashboard overview — real-time pipeline status, flaky summary, coverage delta."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
async def dashboard_overview(request: Request):
    db = get_db(request)
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    # Pipeline runs (24h) — v1 pipeline_runs + v2 sessions
    v1_runs = await db.fetch(
        "SELECT COALESCE(status, 'unknown') as status, COUNT(*) as count FROM pipeline_runs WHERE created_at >= $1 GROUP BY status",
        since_24h,
    )
    v2_runs = await db.fetch(
        "SELECT COALESCE(status, 'unknown') as status, COUNT(*) as count FROM sessions WHERE COALESCE(created_at, started_at) >= $1 AND source IS NOT NULL GROUP BY status",
        since_24h,
    )
    run_status: dict[str, int] = {}
    for r in v1_runs:
        s = "completed" if r["status"] == "completed" else "failed" if r["status"] == "failed" else "other"
        run_status[s] = run_status.get(s, 0) + r["count"]
    for r in v2_runs:
        s = "completed" if r["status"] == "completed" else "failed" if r["status"] == "failed" else "other"
        run_status[s] = run_status.get(s, 0) + r["count"]

    # Test results (24h) — test_results + sessions with completed status
    v1_tests = await db.fetchrow(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) as passed, "
        "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed "
        "FROM test_results WHERE created_at >= $1",
        since_24h,
    )
    v2_count = await db.fetchrow(
        "SELECT COUNT(*) as total FROM sessions WHERE status = 'completed' AND COALESCE(created_at, started_at) >= $1 AND source IS NOT NULL",
        since_24h,
    )
    tests = {
        "total": (v1_tests["total"] if v1_tests else 0) + (v2_count["total"] if v2_count else 0),
        "passed": (v1_tests["passed"] or 0) if v1_tests else 0,
        "failed": (v1_tests["failed"] or 0) if v1_tests else 0,
    }

    # Flaky tests
    flaky = await db.fetch(
        "SELECT COUNT(*) as count FROM flaky_tests WHERE flaky_score > 30 AND is_quarantined = false",
    )
    quarantined = await db.fetchrow(
        "SELECT COUNT(*) as count FROM flaky_tests WHERE is_quarantined = true",
    )

    # Active subagents
    active_agents = 0
    try:
        from harness.tools.delegate_task import active_subagents
        active_agents = len(active_subagents())
    except Exception:
        pass

    # Recent failures (last 10)
    recent_failures = await db.fetch(
        "SELECT test_name, error, created_at FROM test_results "
        "WHERE status='failed' AND created_at >= $1 ORDER BY created_at DESC LIMIT 10",
        since_24h,
    )

    # Active PRs needing attention
    prs = await db.fetchrow(
        "SELECT COUNT(*) as total FROM pr_tracker WHERE status='open' AND last_test_status != 'passed'",
    )

    # ── Quality score: 5 weighted components matching the wireframe ──
    # Pass Rate (40), Coverage (20), Flaky Rate health (20),
    # Defect Density health (10), Automation Coverage (10).
    # Flaky and Defect are reported as "health" (higher = better), so we
    # invert the raw rate before applying the weight.
    flaky_count = flaky[0]["count"] if flaky else 0
    total_runs_24h = sum(run_status.values())
    pass_rate = round((tests["passed"] or 0) / max(tests["total"] or 0, 1) * 100, 1)

    coverage_pct = 0.0
    try:
        cov_row = await db.fetchrow(
            "SELECT line_coverage FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
        )
        if cov_row and cov_row["line_coverage"] is not None:
            coverage_pct = round(float(cov_row["line_coverage"]), 1)
    except Exception:
        coverage_pct = 0.0

    flaky_rate_raw = round(flaky_count / max(total_runs_24h, 1) * 100, 1)
    flaky_health = round(max(0.0, 100.0 - min(flaky_rate_raw, 100.0)), 1)

    defect_count = 0
    try:
        defect_row = await db.fetchrow(
            "SELECT COUNT(*) as c FROM test_results "
            "WHERE status='failed' AND created_at >= $1",
            since_24h,
        )
        defect_count = int(defect_row["c"] or 0) if defect_row else 0
    except Exception:
        defect_count = 0
    defect_rate_raw = round(defect_count / max(total_runs_24h, 1) * 100, 1)
    defect_health = round(max(0.0, 100.0 - min(defect_rate_raw, 100.0)), 1)

    auto_cov = 0.0
    try:
        auto_row = await db.fetchrow(
            "SELECT "
            "SUM(CASE WHEN code IS NOT NULL AND LENGTH(code) > 10 THEN 1 ELSE 0 END) as automated, "
            "COUNT(*) as total "
            "FROM test_cases"
        )
        if auto_row and auto_row["total"]:
            auto_cov = round((auto_row["automated"] or 0) / auto_row["total"] * 100, 1)
    except Exception:
        auto_cov = 0.0

    def _w(raw: float, weight: int) -> float:
        return round(raw * weight / 100, 1)

    quality_components = {
        "pass_rate": {
            "label": "Pass Rate",
            "raw": pass_rate,
            "weighted": _w(pass_rate, 40),
            "weight": 40,
        },
        "coverage": {
            "label": "Coverage",
            "raw": coverage_pct,
            "weighted": _w(coverage_pct, 20),
            "weight": 20,
        },
        "flaky_rate": {
            "label": "Flaky Rate",
            "raw": flaky_health,
            "weighted": _w(flaky_health, 20),
            "weight": 20,
        },
        "defect_density": {
            "label": "Defect Density",
            "raw": defect_health,
            "weighted": _w(defect_health, 10),
            "weight": 10,
        },
        "automation_coverage": {
            "label": "Automation Coverage",
            "raw": auto_cov,
            "weighted": _w(auto_cov, 10),
            "weight": 10,
        },
    }
    quality_score = round(sum(c["weighted"] for c in quality_components.values()), 1)

    return {
        "pipeline_runs_24h": total_runs_24h,
        "pipeline_status": run_status,
        "tests_24h": dict(tests) if tests else {"total": 0, "passed": 0, "failed": 0},
        "pass_rate_24h": pass_rate,
        "avg_duration_24h": 0,
        "flaky_tests": flaky_count,
        "quarantined_tests": quarantined["count"] if quarantined else 0,
        "quality_score": quality_score,
        "quality_components": quality_components,
        "active_agents": active_agents,
        "recent_failures": [dict(r) for r in recent_failures],
        "prs_needing_attention": prs["total"] if prs else 0,
        "timestamp": now.isoformat(),
    }


@router.get("/daily-stats")
async def daily_stats(request: Request, days: int = 30):
    """Daily aggregate stats for sparklines and trend chart. Returns array of daily buckets."""
    db = get_db(request)
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    rows = await db.fetch(
        """SELECT
            DATE(created_at) as day,
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            COALESCE(AVG(duration), 0) as avg_duration,
            COALESCE(SUM(passed_count), 0) as total_passed,
            COALESCE(SUM(test_count), 0) as total_tests
          FROM pipeline_runs
          WHERE created_at >= $1
          GROUP BY DATE(created_at)
          ORDER BY day ASC""",
        since,
    )

    # Fetch daily flaky_rate from quality_metrics
    flaky_rows = await db.fetch(
        "SELECT DATE(created_at) as day, AVG(metric_value) as rate "
        "FROM quality_metrics WHERE metric_name = 'flaky_rate' AND created_at >= $1 "
        "GROUP BY day ORDER BY day",
        since,
    )
    flaky_by_day: dict[date, float] = {}
    for r in flaky_rows:
        flaky_by_day[r["day"]] = round(float(r["rate"]) * 100, 1)

    # Return only days that have actual data
    if not rows and not flaky_by_day:
        return {"days": []}

    daily = {r["day"]: r for r in rows}
    result = []
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).date()
        ds = d.isoformat()
        r = daily.get(d)
        fr = flaky_by_day.get(ds, 0)
        if r:
            tests = r["total_tests"] or 0
            passed = r["total_passed"] or 0
            result.append({
                "date": ds,
                "runs": r["total_runs"],
                "passRate": round((passed / max(tests, 1)) * 100, 1) if tests > 0 else 0,
                "flakyRate": fr,
                "avgDuration": round(r["avg_duration"], 0),
                "failed": r["failed"],
            })
        elif fr > 0:
            result.append({
                "date": ds,
                "runs": 0,
                "passRate": 0,
                "flakyRate": fr,
                "avgDuration": 0,
                "failed": 0,
            })

    return {"days": result}


@router.get("/coverage-delta")
async def coverage_delta(request: Request, run_a: str = "", run_b: str = ""):
    """Compare coverage between two runs. Returns delta per metric."""
    db = get_db(request)
    if not run_a or not run_b:
        # Get last two coverage reports
        rows = await db.fetch(
            "SELECT id, run_id, language, line_coverage, branch_coverage, created_at "
            "FROM coverage_reports ORDER BY created_at DESC LIMIT 2",
        )
        if len(rows) < 2:
            return {"error": "Need at least 2 coverage reports to compare"}
        run_a = rows[1]["run_id"] or ""
        run_b = rows[0]["run_id"] or ""

    a = await db.fetchrow("SELECT * FROM coverage_reports WHERE run_id = $1", run_a)
    b = await db.fetchrow("SELECT * FROM coverage_reports WHERE run_id = $1", run_b)
    if not a or not b:
        return {"error": "Coverage reports not found"}

    return {
        "run_a": dict(a),
        "run_b": dict(b),
        "delta": {
            "line_coverage": round(b["line_coverage"] - a["line_coverage"], 2),
            "branch_coverage": round(b["branch_coverage"] - a["branch_coverage"], 2),
        },
        "improved": b["line_coverage"] >= a["line_coverage"],
    }


@router.post("/rerun-failed")
async def rerun_failed_tests(request: Request):
    """Re-run all failed tests from a given pipeline run."""
    db = get_db(request)
    body = await request.json()
    run_id = body.get("run_id", "")
    if not run_id:
        return {"error": "run_id required"}

    failed = await db.fetch(
        "SELECT test_name, code, code_language FROM test_results "
        "JOIN test_cases ON test_cases.name = test_results.test_name "
        "WHERE test_results.run_id = $1 AND test_results.status = 'failed' "
        "LIMIT 20",
        run_id,
    )

    if not failed:
        return {"status": "no_failures", "count": 0}

    import asyncio
    from harness.tools.docker_executor import DockerExecutorTool
    tool = DockerExecutorTool()
    results = []
    for row in failed:
        try:
            result = await tool.run(code=row["code"] or "", language=row["code_language"] or "python", timeout=120)
            results.append({"test": row["test_name"], "passed": result.success, "output": (result.output or "")[:200]})
        except Exception as e:
            results.append({"test": row["test_name"], "passed": False, "error": str(e)})

    return {"status": "completed", "rerun": len(failed), "results": results}


@router.post("/prs/bulk")
async def bulk_pr_action(request: Request):
    """Perform bulk actions on multiple PRs (run tests, auto-fix, set priority)."""
    db = get_db(request)
    body = await request.json()
    action = body.get("action", "")
    pr_ids = body.get("pr_ids", [])
    value = body.get("value")

    if not pr_ids:
        return {"error": "pr_ids required"}

    import asyncio
    tasks = []
    for pr_id in pr_ids:
        if action == "run_tests":
            from .pr_manager import _execute_pr_pipeline
            row = await db.fetchrow("SELECT * FROM pr_tracker WHERE id = $1", pr_id)
            if row:
                tasks.append(_execute_pr_pipeline(db, pr_id, str(uuid.uuid4()), row, {}))
        elif action == "set_priority" and value:
            await db.execute("UPDATE pr_tracker SET priority = $1 WHERE id = $2", value, pr_id)
        elif action == "auto_fix":
            from .pr_manager import _run_auto_fix_loop
            row = await db.fetchrow("SELECT * FROM pr_tracker WHERE id = $1", pr_id)
            if row:
                tasks.append(_run_auto_fix_loop(db, pr_id, row))

    if tasks:
        await asyncio.gather(*tasks)


@router.post("/flaky/scan")
async def trigger_flaky_scan(request: Request):
    """Trigger auto-quarantine scan. Returns newly quarantined tests."""
    db = get_db(request)
    from harness.flaky_auto_quarantine import scan_and_quarantine
    quarantined = await scan_and_quarantine(db)
    return {"status": "ok", "quarantined": quarantined, "count": len(quarantined)}

    return {"status": "ok", "affected": len(pr_ids), "action": action}
