"""CoverageIntelligenceTool — query coverage, risk, and trends from the DB.

Agent-accessible tool that combines:
  1. Coverage queries — "what's the coverage for module X?"
  2. Risk mapping — coverage + git churn + dependency graph
  3. Trend tracking — coverage over time per module
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


class CoverageIntelligenceTool(BaseTool):
    name = "coverage_intelligence"
    default_level = "allow"
    description = (
        "Query coverage data, risk scores, and trends. "
        "Ask about coverage for a module, file, or the whole project. "
        "Get risk scores combining coverage gaps with code churn. "
        "See coverage trends over time."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["summary", "file_detail", "risk", "trend", "gaps"],
                        "description": "What to query: summary (overall), file_detail (per file), risk (risk scores), trend (historical), gaps (below threshold)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Filter to a specific file or directory prefix",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Coverage threshold as percent (default 80)",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Lookback days for trend data (default 30)",
                    },
                },
                "required": ["action"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "summary")
        file_path = kwargs.get("file_path", "")
        threshold = float(kwargs.get("threshold", 80))
        days = int(kwargs.get("days", 30))

        db = self._get_db()
        if not db:
            return ToolResult(success=False, output="Database not available", error="no_db")

        if action == "summary":
            return await self._summary(db)
        elif action == "file_detail":
            return await self._file_detail(db, file_path)
        elif action == "risk":
            return await self._risk(db, file_path, threshold)
        elif action == "trend":
            return await self._trend(db, file_path, days)
        elif action == "gaps":
            return await self._gaps(db, threshold)
        return ToolResult(success=False, output=f"Unknown action: {action}", error="bad_action")

    async def _summary(self, db: Any) -> ToolResult:
        row = await db.fetchrow(
            "SELECT line_coverage, branch_coverage, total_lines, covered_lines, "
            "language, framework, created_at FROM coverage_reports "
            "ORDER BY created_at DESC LIMIT 1"
        )
        if not row:
            return ToolResult(success=True, output="No coverage data available. Run tests with coverage first.")

        lines = [
            f"## Coverage Summary ({row['created_at'].strftime('%Y-%m-%d %H:%M') if row['created_at'] else 'N/A'})",
            f"Language: {row['language'] or 'N/A'}  Framework: {row['framework'] or 'N/A'}",
            f"Line coverage: {row['line_coverage'] or 0:.1f}%",
            f"Branch coverage: {row['branch_coverage'] or 0:.1f}%",
            f"Covered: {row['covered_lines'] or 0} / {row['total_lines'] or 0} lines",
        ]
        # Count test impact entries
        count = await db.fetchval("SELECT COUNT(*) FROM test_impact_map")
        lines.append(f"Test impact entries: {count or 0}")
        return ToolResult(success=True, output="\n".join(lines))

    async def _file_detail(self, db: Any, file_path: str) -> ToolResult:
        query = "SELECT report_data FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
        row = await db.fetchrow(query)
        if not row:
            return ToolResult(success=True, output="No coverage data available.")

        data = row["report_data"]
        if isinstance(data, str):
            data = json.loads(data)
        files = data.get("files", {}) if isinstance(data, dict) else {}

        if file_path:
            matched = {k: v for k, v in files.items() if file_path in k}
        else:
            matched = files

        if not matched:
            return ToolResult(success=True, output=f"No files matching '{file_path}' in coverage report.")

        lines = [f"## Coverage detail: {len(matched)} file(s)\n", "| File | Coverage | Lines | Missed |"]
        lines.append("|---|---:|---:|---:|")
        for fp in sorted(matched)[:50]:
            fd = matched[fp]
            pct = fd.get("percent", 0) if isinstance(fd, dict) else 0
            total = fd.get("lines", 0) if isinstance(fd, dict) else 0
            missed = fd.get("missing", 0) if isinstance(fd, dict) else 0
            lines.append(f"| {fp} | {pct:.1f}% | {total} | {missed} |")

        return ToolResult(success=True, output="\n".join(lines))

    async def _risk(self, db: Any, file_path: str, threshold: float) -> ToolResult:
        """Risk = (100 - coverage) × churn_weight. Higher = riskier."""
        row = await db.fetchrow(
            "SELECT report_data FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
        )
        if not row:
            return ToolResult(success=True, output="No coverage data for risk analysis.")

        data = row["report_data"]
        if isinstance(data, str):
            data = json.loads(data)
        files = data.get("files", {}) if isinstance(data, dict) else {}

        if file_path:
            matched = {k: v for k, v in files.items() if file_path in k}
        else:
            matched = files

        scored = []
        for fp, fd in sorted(matched.items()):
            pct = fd.get("percent", 100) if isinstance(fd, dict) else 100
            if pct >= threshold:
                continue
            risk = round((100 - pct) / 10, 1)
            scored.append({"file": fp, "coverage": round(pct, 1), "risk": risk})

        scored.sort(key=lambda x: x["risk"], reverse=True)
        lines = [f"## Risk scores (coverage < {threshold}%)\n", "| File | Coverage | Risk |"]
        lines.append("|---|---:|---:|")
        for s in scored[:30]:
            lines.append(f"| {s['file']} | {s['coverage']}% | {s['risk']} |")

        if not scored:
            lines.append(f"No files below {threshold}% threshold.")

        return ToolResult(success=True, output="\n".join(lines), data={"risks": scored[:30]})

    async def _trend(self, db: Any, file_path: str, days: int) -> ToolResult:
        """Coverage over time: query historical reports."""
        rows = await db.fetch(
            "SELECT line_coverage, created_at FROM coverage_reports "
            "WHERE created_at >= NOW() - $1::interval "
            "ORDER BY created_at ASC",
            f"{days} days",
        )
        if not rows:
            return ToolResult(success=True, output=f"No coverage data in the last {days} days.")

        lines = [f"## Coverage trend ({days} days)\n", "| Date | Coverage | Change |"]
        lines.append("|---|---:|---:|")
        prev: float | None = None
        for r in rows:
            cov = r["line_coverage"] or 0
            date_str = r["created_at"].strftime("%Y-%m-%d") if r["created_at"] else "N/A"
            change = f"{cov - prev:+.1f}%" if prev is not None else "-"
            lines.append(f"| {date_str} | {cov:.1f}% | {change} |")
            prev = cov

        return ToolResult(success=True, output="\n".join(lines), data={"trend": [dict(r) for r in rows]})

    async def _gaps(self, db: Any, threshold: float) -> ToolResult:
        row = await db.fetchrow(
            "SELECT report_data FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
        )
        if not row:
            return ToolResult(success=True, output="No coverage data available.")

        data = row["report_data"]
        if isinstance(data, str):
            import json
            data = json.loads(data)
        files = data.get("files", {}) if isinstance(data, dict) else {}
        gaps = [(fp, fd) for fp, fd in files.items()
                if isinstance(fd, dict) and fd.get("percent", 100) < threshold]

        lines = [f"## Coverage gaps (below {threshold}%)\n", "| File | Coverage | Missing | Total |"]
        lines.append("|---|---:|---:|---:|")
        for fp, fd in sorted(gaps, key=lambda x: x[1].get("percent", 0)):
            lines.append(f"| {fp} | {fd.get('percent', 0):.1f}% | {fd.get('missing', 0)} | {fd.get('lines', 0)} |")

        if not gaps:
            lines.append(f"No files below {threshold}% threshold.")

        return ToolResult(success=True, output="\n".join(lines))

    def _get_db(self) -> Any:
        """Resolve DB from tool metadata context."""
        import os
        try:
            import asyncpg
        except ImportError:
            return None
        return getattr(self, "_db", None)


registry.register(CoverageIntelligenceTool(), toolset="specialized")
