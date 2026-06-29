"""Flaky test detection engine.

After each test run, computes flaky scores based on pass/fail history.
Auto-quarantines tests above a configurable threshold.

Flaky score: 0.0 (stable) to 1.0 (extremely flaky)
  - Based on recent pass/fail ratio weighted by recency
  - Tests that alternate pass/fail get higher scores
  - Tests that consistently pass or fail get lower scores
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

FLAKY_THRESHOLD = 0.4  # Auto-quarantine above this score
HEAL_THRESHOLD = 0.15   # Auto-unquarantine below this score (test healed)
LOOKBACK_RUNS = 20      # Number of recent runs to analyze


async def update_flaky_score(db: Any, test_name: str, branch: str = "") -> dict[str, Any]:
    """Recompute flaky score for a single test after a new run.

    Called after every test execution to keep flaky scores up to date.
    """
    try:
        rows = await db.fetch(
            "SELECT status, duration_ms, created_at FROM test_results "
            "WHERE test_name = $1 AND branch = $2 "
            "ORDER BY created_at DESC LIMIT $3",
            test_name, branch, LOOKBACK_RUNS,
        )

        if not rows:
            return {"test_name": test_name, "flaky_score": 0.0, "quarantined": False}

        total = len(rows)
        pass_count = sum(1 for r in rows if r["status"] == "passed")
        fail_count = total - pass_count

        # Weighted flaky score: recent failures count more
        score = 0.0
        for i, r in enumerate(rows):
            weight = 1.0 - (i / total) * 0.5  # Most recent gets weight 1.0, oldest gets 0.5
            if r["status"] != "passed":
                score += weight

        # Normalize to 0.0 - 1.0
        max_possible = sum(1.0 - (i / total) * 0.5 for i in range(total))
        flaky_score = round(score / max_possible, 4) if max_possible > 0 else 0.0

        # Determine if quarantined
        was_quarantined = rows[0].get("is_quarantined", False) if len(rows) > 0 else False
        is_quarantined = was_quarantined

        if flaky_score >= FLAKY_THRESHOLD and not was_quarantined:
            is_quarantined = True
        elif flaky_score <= HEAL_THRESHOLD and was_quarantined:
            is_quarantined = False

        # Update flaky_tests table
        await db.execute(
            """INSERT INTO flaky_tests (test_name, branch, total_runs, pass_count, fail_count,
               flaky_score, is_quarantined, last_healed, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
               ON CONFLICT (test_name, branch) DO UPDATE SET
               total_runs = $3, pass_count = $4, fail_count = $5,
               flaky_score = $6, is_quarantined = $7,
               last_healed = CASE WHEN $7 = false AND flaky_tests.is_quarantined = true THEN true ELSE flaky_tests.last_healed END,
               updated_at = NOW()""",
            test_name, branch, total, pass_count, fail_count,
            flaky_score, is_quarantined, is_quarantined == was_quarantined,
        )

        if is_quarantined and not was_quarantined:
            logger.info("Test '%s' auto-quarantined (flaky score: %.2f)", test_name, flaky_score)
            try:
                from harness.notifications import dispatch
                await dispatch("flaky.quarantine", {
                    "test": test_name,
                    "branch": branch,
                    "score": flaky_score,
                    "runs": total,
                    "failures": fail_count,
                }, db)
            except Exception:
                pass

        return {
            "test_name": test_name,
            "flaky_score": flaky_score,
            "quarantined": is_quarantined,
            "total_runs": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
        }

    except Exception as e:
        logger.warning("Failed to update flaky score for '%s': %s", test_name, e)
        return {"test_name": test_name, "flaky_score": 0.0, "quarantined": False}


async def get_flaky_summary(db: Any, days: int = 30) -> dict[str, Any]:
    """Get aggregate flaky test statistics for the dashboard."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        total = await db.fetchval("SELECT COUNT(*) FROM flaky_tests")
        quarantined = await db.fetchval("SELECT COUNT(*) FROM flaky_tests WHERE is_quarantined = true")
        avg_score = await db.fetchval("SELECT COALESCE(AVG(flaky_score), 0) FROM flaky_tests")
        healed = await db.fetchval("SELECT COUNT(*) FROM flaky_tests WHERE last_healed = true")

        # Daily trend
        trend_rows = await db.fetch(
            "SELECT DATE(updated_at) as day, AVG(flaky_score) as avg_score "
            "FROM flaky_tests WHERE updated_at >= $1 GROUP BY day ORDER BY day",
            since,
        )

        return {
            "total": total or 0,
            "quarantined": quarantined or 0,
            "avg_score": round(float(avg_score or 0), 3),
            "healed": healed or 0,
            "trend": [
                {"date": r["day"].isoformat(), "score": round(float(r["avg_score"]), 3)}
                for r in trend_rows
            ],
        }
    except Exception as e:
        logger.warning("Flaky summary failed: %s", e)
        return {"total": 0, "quarantined": 0, "avg_score": 0, "healed": 0, "trend": []}
