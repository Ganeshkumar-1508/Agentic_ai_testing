"""Auto-quarantine flaky tests based on historical run data.

Scans test_results for inconsistent outcomes (same test, same branch,
different results across recent runs). When a test exceeds the flaky
threshold, it's auto-quarantined and a quality_metric is recorded.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

FLAKY_THRESHOLD = 0.3  # 30%+ inconsistent → flaky
QUARANTINE_AFTER_RUNS = 5  # min runs before we can judge


async def scan_and_quarantine(db: Any) -> list[dict[str, Any]]:
    """Scan test_results for flaky tests and auto-quarantine.

    Returns list of newly quarantined tests.
    """
    rows = await db.fetch(
        "SELECT test_name, branch, "
        "COUNT(*) as total_runs, "
        "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passes, "
        "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures "
        "FROM test_results "
        "WHERE created_at > NOW() - INTERVAL '7 days' "
        "GROUP BY test_name, branch"
    )

    newly_quarantined = []
    for r in rows:
        total = r["total_runs"]
        if total < QUARANTINE_AFTER_RUNS:
            continue

        failures = r["failures"] or 0
        flaky_score = round(failures / total, 2)

        await db.execute(
            "INSERT INTO flaky_tests (test_name, run_id, branch, total_runs, pass_count, fail_count, flaky_score) "
            "VALUES ($1, 'auto', $2, $3, $4, $5, $6) "
            "ON CONFLICT (test_name, branch) "
            "DO UPDATE SET total_runs = EXCLUDED.total_runs, pass_count = EXCLUDED.pass_count, "
            "fail_count = EXCLUDED.fail_count, flaky_score = EXCLUDED.flaky_score, updated_at = NOW()",
            r["test_name"], r["branch"], total, r["passes"] or 0, failures, flaky_score,
        )

        if flaky_score >= FLAKY_THRESHOLD:
            existing = await db.fetchrow(
                "SELECT is_quarantined FROM flaky_tests WHERE test_name = $1 AND branch = $2",
                r["test_name"], r["branch"],
            )
            if existing and not existing["is_quarantined"]:
                await db.execute(
                    "UPDATE flaky_tests SET is_quarantined = true WHERE test_name = $1 AND branch = $2",
                    r["test_name"], r["branch"],
                )
                newly_quarantined.append({
                    "test_name": r["test_name"],
                    "branch": r["branch"],
                    "flaky_score": flaky_score,
                })
                logger.info("Auto-quarantined flaky test: %s (score: %.2f)", r["test_name"], flaky_score)
                try:
                    from harness.notifications import dispatch
                    await dispatch("flaky.quarantine", {
                        "test": r["test_name"],
                        "branch": r["branch"],
                        "score": flaky_score,
                        "runs": total,
                        "failures": failures,
                    }, db)
                except Exception:
                    pass

    return newly_quarantined
