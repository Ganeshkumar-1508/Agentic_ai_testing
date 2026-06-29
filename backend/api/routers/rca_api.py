"""Root Cause Analysis API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/rca", tags=["rca"])


@router.get("/summary")
async def get_rca_summary(request: Request, days: int = 30, run_id: str = ""):
    """Get RCA summary: total failures, defect vs flake breakdown, top clusters."""
    db = get_db(request)
    from harness.rca import analyze_failures, get_rca_summary

    if run_id:
        result = await analyze_failures(db, run_id=run_id)
    else:
        result = await get_rca_summary(db, days=days)

    return result


@router.get("/failures")
async def get_failure_clusters(request: Request, days: int = 30):
    """Get all failure clusters with verdicts."""
    db = get_db(request)
    from harness.rca import analyze_failures

    result = await analyze_failures(db, days=days)
    return {
        "clusters": result.get("clusters", [])[:20],
        "total": result["total_failures"],
        "total_clusters": result.get("total_clusters", 0),
        "defect_count": result.get("defect_count", 0),
        "flake_count": result.get("flake_count", 0),
    }


@router.post("/re-run")
async def rerun_failure_cluster(request: Request, tests: str = ""):
    """Re-run all failed tests from a cluster. Accepts pipe-delimited test names."""
    db = get_db(request)
    if not tests:
        return {"error": "tests parameter required"}

    test_names = [t.strip() for t in tests.split("|") if t.strip()]
    if not test_names:
        return {"error": "no valid test names"}

    # Find failed test results and re-run via Docker executor
    rows = await db.fetch(
        "SELECT test_name, code, code_language FROM test_results "
        "JOIN test_cases ON test_cases.name = test_results.test_name "
        "WHERE test_results.status = 'failed' AND test_results.test_name = ANY($1) "
        "LIMIT 20",
        test_names,
    )

    if not rows:
        return {"status": "no_failures", "count": 0}

    from harness.tools.docker_executor import DockerExecutorTool
    tool = DockerExecutorTool()
    results = []
    for row in rows:
        try:
            result = await tool.run(code=row["code"] or "", language=row["code_language"] or "python", timeout=120)
            results.append({
                "test": row["test_name"],
                "passed": result.success,
                "output": (result.output or "")[:200],
            })
        except Exception as e:
            results.append({"test": row["test_name"], "passed": False, "error": str(e)})

    return {"status": "completed", "rerun": len(rows), "results": results}
