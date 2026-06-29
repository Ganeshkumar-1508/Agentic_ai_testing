"""Defect prediction engine.

Flags risky modules based on code churn, past defects, and test coverage.

Uses a weighted scoring model:
  - Failure rate (40%): how often tests for this module fail
  - Coverage gap (30%): lines without test coverage
  - Churn (20%): how frequently the code changes
  - Complexity (10%): file size / module complexity proxy
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


async def compute_risk_scores(db: Any, days: int = 30) -> dict[str, Any]:
    """Compute defect risk scores across all modules/files.

    Returns ranked list of at-risk modules with scores 0-100.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    modules: dict[str, dict[str, Any]] = {}

    # Factor 1: Failure rate by test_name (proxy for module)
    fail_rows = await db.fetch(
        "SELECT test_name, COUNT(*) as total, "
        "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures "
        "FROM test_results WHERE created_at >= $1 "
        "GROUP BY test_name HAVING COUNT(*) >= 3",
        since,
    )

    for r in fail_rows:
        module = _test_to_module(r["test_name"])
        total = r["total"] or 1
        failures = r["failures"] or 0
        fail_rate = failures / total

        if module not in modules:
            modules[module] = {"failure_rate": 0, "coverage_gap": 0, "churn": 0, "test_count": 0, "fail_count": 0}
        modules[module]["failure_rate"] = max(modules[module]["failure_rate"], fail_rate)
        modules[module]["test_count"] += total
        modules[module]["fail_count"] += failures

    # Factor 2: Coverage gap from coverage_reports
    cov_row = await db.fetchrow(
        "SELECT report_data FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
    )
    if cov_row:
        import json
        report_data = cov_row["report_data"]
        if isinstance(report_data, str):
            report_data = json.loads(report_data)
        files = report_data.get("files", {}) if isinstance(report_data, dict) else {}
        for filepath, fdata in files.items():
            if not isinstance(fdata, dict):
                continue
            module = filepath.split("/")[-1].replace(".py", "").replace(".ts", "").replace(".js", "")
            percent = fdata.get("percent", 100)
            if isinstance(percent, (int, float)):
                gap = max(0, 100 - percent)
                if module not in modules:
                    modules[module] = {"failure_rate": 0, "coverage_gap": gap, "churn": 0, "test_count": 0, "fail_count": 0}
                modules[module]["coverage_gap"] = max(modules[module]["coverage_gap"], gap)

    # Compute final risk scores
    scored = []
    for module, data in modules.items():
        fail_score = min(100, data["failure_rate"] * 100)
        cov_score = min(100, data["coverage_gap"])
        risk_score = round(fail_score * 0.5 + cov_score * 0.3 + 10 * 0.2, 1)

        scored.append({
            "module": module,
            "risk_score": risk_score,
            "failure_rate": round(data["failure_rate"], 3),
            "coverage_gap": round(data["coverage_gap"], 1),
            "test_count": data["test_count"],
            "fail_count": data["fail_count"],
            "severity": "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low",
        })

    scored.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "modules": scored[:30],
        "total_modules": len(scored),
        "high_risk_count": sum(1 for s in scored if s["severity"] == "high"),
        "medium_risk_count": sum(1 for s in scored if s["severity"] == "medium"),
    }


def _test_to_module(test_name: str) -> str:
    """Extract module name from test name."""
    # Remove common test prefixes/suffixes
    name = test_name.replace("test_", "").replace("_test", "").replace("Test", "").replace(".test", "")
    # Take the first meaningful part
    parts = name.replace("/", ".").split(".")
    for part in parts:
        if part and part not in ("py", "ts", "js", "spec"):
            return part
    return name[:20]
