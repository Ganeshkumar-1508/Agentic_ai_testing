"""Risk scoring for PRs, requirements, and pipeline runs.

Computes a composite risk score (0-100) based on:
  - Change scope (files changed, lines added/deleted)
  - Test coverage gaps
  - Historical flakiness of affected tests
  - Priority/severity of the feature area
  - LOGAF score from auto-fix cycles
"""

from __future__ import annotations

from typing import Any

RISK_WEIGHTS = {
    "files_changed": 0.15,
    "lines_changed": 0.10,
    "coverage_gap": 0.25,
    "flakiness": 0.15,
    "priority": 0.20,
    "logaf": 0.15,
}


def compute_pr_risk_score(
    files_changed: int = 0,
    additions: int = 0,
    deletions: int = 0,
    coverage_pct: float = 100.0,
    flaky_tests_count: int = 0,
    total_tests: int = 1,
    priority: str = "medium",
    logaf_score: float = 100.0,
) -> float:
    """Compute a composite risk score (0-100) for a PR.

    Higher score = higher risk.
    """
    files_score = min(files_changed / 20 * 100, 100)
    lines_score = min((additions + deletions) / 500 * 100, 100)
    coverage_score = max(0, 100 - coverage_pct)
    flaky_score = min(flaky_tests_count / max(total_tests, 1) * 100, 100)
    priority_map = {"low": 20, "medium": 50, "high": 80, "critical": 100}
    priority_score = priority_map.get(priority, 50)
    logaf_risk = max(0, 100 - logaf_score)

    score = (
        files_score * RISK_WEIGHTS["files_changed"]
        + lines_score * RISK_WEIGHTS["lines_changed"]
        + coverage_score * RISK_WEIGHTS["coverage_gap"]
        + flaky_score * RISK_WEIGHTS["flakiness"]
        + priority_score * RISK_WEIGHTS["priority"]
        + logaf_risk * RISK_WEIGHTS["logaf"]
    )
    return round(min(score, 100), 1)


def risk_tier(score: float) -> str:
    """Classify a risk score into a tier."""
    if score >= 70:
        return "critical"
    if score >= 40:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


async def update_pr_risk_score(db: Any, pr_id: str) -> None:
    """Recompute and persist risk score for a PR."""
    row = await db.fetchrow(
        "SELECT files_changed, additions, deletions, priority, last_logaf_score "
        "FROM pr_tracker WHERE id = $1",
        pr_id,
    )
    if not row:
        return

    flaky_row = await db.fetchrow(
        "SELECT COUNT(*) as flaky FROM flaky_tests WHERE flaky_score > 30 AND is_quarantined = false"
    )
    flaky_count = flaky_row["flaky"] if flaky_row else 0

    total_row = await db.fetchrow("SELECT COUNT(*) as total FROM test_cases")
    total = total_row["total"] if total_row else 1

    score = compute_pr_risk_score(
        files_changed=row["files_changed"] or 0,
        additions=row["additions"] or 0,
        deletions=row["deletions"] or 0,
        coverage_pct=50.0,
        flaky_tests_count=flaky_count,
        total_tests=total,
        priority=row["priority"] or "medium",
        logaf_score=row["last_logaf_score"] or 100.0,
    )
    await db.execute(
        "UPDATE pr_tracker SET risk_score = $1, updated_at = NOW() WHERE id = $2",
        score, pr_id,
    )
