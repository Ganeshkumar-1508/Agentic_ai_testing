"""Coverage gap analysis engine.

Parses coverage reports, identifies uncovered files/lines,
maps gaps to source changes, and persists to coverage_reports table.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def ingest_coverage_report(
    db: Any,
    run_id: str,
    language: str,
    framework: str,
    raw_report: str,
) -> dict[str, Any]:
    """Parse and store a coverage report from test execution.

    Supports coverage.py JSON and istanbul JSON summary formats.
    """
    try:
        data = json.loads(raw_report) if isinstance(raw_report, str) else raw_report
    except json.JSONDecodeError:
        logger.warning("Coverage report is not valid JSON")
        return {"error": "invalid_json", "files": 0}

    files: dict[str, Any] = {}
    total_lines = 0
    covered_lines = 0

    # coverage.py format: {"meta": {...}, "files": {"path.py": {"summary": {...}, "lines": {...}}}}
    if "files" in data and isinstance(data["files"], dict):
        for filepath, fdata in data["files"].items():
            summary = fdata.get("summary", {})
            if not summary:
                continue
            flines = summary.get("num_statements", 0) or 0
            fcovered = summary.get("covered_lines", 0) or 0
            fmissing = summary.get("missing_lines", 0) or 0
            fpercent = summary.get("percent_covered", 100.0) or 100.0
            missing_lines = fdata.get("missing_lines", []) or []
            files[filepath] = {
                "path": filepath,
                "lines": flines,
                "covered": fcovered,
                "missing": fmissing,
                "percent": round(fpercent, 2),
                "missing_lines": missing_lines,
            }
            total_lines += flines
            covered_lines += fcovered

    # istanbul format: {"total": {...}, "files": {...}}
    elif "total" in data and isinstance(data.get("files"), dict):
        for filepath, fdata in data["files"].items():
            if not isinstance(fdata, dict):
                continue
            lines_total = fdata.get("lines", {}).get("total", 0)
            lines_covered = fdata.get("lines", {}).get("covered", 0)
            lines_pct = fdata.get("lines", {}).get("pct", 100)
            files[filepath] = {
                "path": filepath,
                "lines": lines_total,
                "covered": lines_covered,
                "missing": lines_total - lines_covered,
                "percent": round(lines_pct, 2),
                "missing_lines": [],
            }
            total_lines += lines_total
            covered_lines += lines_covered

    if not files:
        return {"error": "no_files_parsed", "files": 0}

    # Persist to coverage_reports table
    try:
        report_data = json.dumps({"files": files, "language": language, "framework": framework})
        await db.execute(
            """INSERT INTO coverage_reports
               (id, run_id, language, framework, line_coverage, branch_coverage,
                total_lines, covered_lines, report_data)
               VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6, $7, $8)""",
            run_id, language, framework,
            round(covered_lines / total_lines * 100, 2) if total_lines > 0 else 0,
            0, total_lines, covered_lines, report_data,
        )
    except Exception as e:
        logger.warning("Failed to persist coverage report: %s", e)

    # Find files with low coverage (gaps)
    gaps = [
        {"path": fp, "percent": fd["percent"], "missing": fd["missing"], "missing_lines": fd["missing_lines"][:20]}
        for fp, fd in sorted(files.items(), key=lambda x: x[1]["percent"])
        if fd["percent"] < 80
    ]

    return {
        "files": len(files),
        "total_lines": total_lines,
        "covered_lines": covered_lines,
        "line_coverage": round(covered_lines / total_lines * 100, 2) if total_lines > 0 else 0,
        "gaps": gaps,
        "gap_count": len(gaps),
    }


async def get_coverage_summary(db: Any, run_id: str | None = None, days: int = 30) -> dict[str, Any]:
    """Get coverage summary for a specific run or averaged over recent runs."""
    try:
        if run_id:
            rows = await db.fetch(
                "SELECT * FROM coverage_reports WHERE run_id = $1 ORDER BY created_at DESC LIMIT 1",
                run_id,
            )
        else:
            rows = await db.fetch(
                "SELECT * FROM coverage_reports WHERE created_at >= NOW() - INTERVAL '1 day' * $1 ORDER BY created_at DESC",
                days,
            )

        if not rows:
            return {"coverage": None, "trend": [], "gaps": []}

        latest = rows[0]
        total_coverage = float(latest["line_coverage"]) if latest["line_coverage"] else 0

        # Parse stored report_data
        report_data = latest.get("report_data", "{}")
        if isinstance(report_data, str):
            report_data = json.loads(report_data)
        files = report_data.get("files", {}) if isinstance(report_data, dict) else {}

        gaps = [
            {"path": fp, "percent": fd["percent"], "missing_lines": fd.get("missing_lines", [])[:10]}
            for fp, fd in sorted(files.items(), key=lambda x: x[1]["percent"])
            if isinstance(fd, dict) and fd.get("percent", 100) < 80
        ]

        # Coverage trend over recent reports
        trend_rows = await db.fetch(
            "SELECT created_at, line_coverage FROM coverage_reports "
            "WHERE created_at >= NOW() - INTERVAL '1 day' * $1 ORDER BY created_at ASC",
            days,
        )
        trend = [
            {"date": r["created_at"].isoformat() if r["created_at"] else "", "coverage": round(float(r["line_coverage"]), 2)}
            for r in trend_rows
        ]

        return {
            "coverage": {
                "line_coverage": round(total_coverage, 2),
                "total_lines": latest["total_lines"],
                "covered_lines": latest["covered_lines"],
                "language": latest["language"],
                "framework": latest["framework"],
                "run_id": latest["run_id"],
            },
            "gaps": gaps[:20],
            "gap_count": len(gaps),
            "trend": trend,
        }

    except Exception as e:
        logger.warning("Coverage summary failed: %s", e)
        return {"coverage": None, "trend": [], "gaps": []}
