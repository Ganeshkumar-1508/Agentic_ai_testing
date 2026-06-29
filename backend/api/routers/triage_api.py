"""Defect triage API — aggregate failed tests for triage queue."""

from __future__ import annotations

from fastapi import APIRouter, Request
from ..deps import get_db

router = APIRouter(prefix="/api/triage", tags=["triage"])


@router.get("/queue")
async def triage_queue(request: Request, days: int = 7, severity: str = ""):
    """Get aggregate failed test results for the triage queue.

    Groups by test_name across test_results and flaky_tests.
    Returns severity, first_seen, last_seen, fail_count, status.
    """
    db = get_db(request)
    since = f"NOW() - INTERVAL '{days} days'"

    rows = await db.fetch(
        f"""SELECT
            test_name,
            COUNT(*) as fail_count,
            COUNT(DISTINCT run_id) as run_count,
            MIN(created_at) as first_seen,
            MAX(created_at) as last_seen
        FROM test_results
        WHERE status = 'failed' AND created_at >= {since}
        GROUP BY test_name
        ORDER BY fail_count DESC
        LIMIT 50"""
    )
    queue = []
    for r in rows:
        name = r["test_name"]
        fc = r["fail_count"] or 0

        # Check flaky_tests for quarantine status
        flaky = await db.fetchrow(
            "SELECT is_quarantined, flaky_score FROM flaky_tests WHERE test_name = $1",
            name,
        )
        is_quarantined = flaky["is_quarantined"] if flaky else False
        flaky_score = float(flaky["flaky_score"] or 0) if flaky else 0

        # Derive severity from failure count
        sev = "critical" if fc >= 10 else "high" if fc >= 5 else "medium" if fc >= 2 else "low"

        if severity and sev != severity and severity != "all":
            continue

        queue.append({
            "test_name": name,
            "fail_count": fc,
            "run_count": r["run_count"] or 0,
            "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
            "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            "severity": sev,
            "status": "quarantined" if is_quarantined else "open",
            "flaky_score": round(flaky_score, 1),
        })

    return {
        "queue": queue,
        "total": len(queue),
        "critical": sum(1 for d in queue if d["severity"] == "critical"),
        "high": sum(1 for d in queue if d["severity"] == "high"),
        "medium": sum(1 for d in queue if d["severity"] == "medium"),
        "low": sum(1 for d in queue if d["severity"] == "low"),
    }
