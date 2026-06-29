"""Coverage analyzer — parses lcov reports and surfaces uncovered lines.

The lcov format is the de-facto standard coverage output for Python
(coverage.py), JavaScript (c8, nyc), Rust (grcov, llvm-cov), C/C++
(gcov, lcov itself), and Go (go test -cover). Format:

    SF:/path/to/file.py
    DA:12,1           # line 12 was hit
    DA:13,0           # line 13 was NOT hit
    ...
    LF:100            # total lines found
    LH:80             # lines hit
    end_of_record

This tool reads an lcov file and returns a markdown report of
uncovered lines per file. The orchestrator's coordinator uses this
to decide what to add tests for.

Fallback: if the file doesn't exist or is empty, return a clear
"no coverage data" message rather than crashing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry


# Lcov record parser. We split the file into records, then extract
# per-file hit/miss lines.
_RECORD_END = "end_of_record"
_DA_LINE = re.compile(r"^DA:(\d+),(\d+)$")  # DA:<line>,<hit-count>


def _parse_lcov(text: str) -> list[dict[str, Any]]:
    """Parse lcov text into a list of per-file records."""
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("SF:"):
            current = {"file": line[3:], "lines": {}}
        elif line == _RECORD_END:
            if current is not None:
                records.append(current)
            current = None
        elif current is not None:
            m = _DA_LINE.match(line)
            if m:
                current["lines"][int(m.group(1))] = int(m.group(2))
    return records


class CoverageAnalyzerTool(BaseTool):
    name = "coverage_analyzer"
    default_level = "allow"
    description = (
        "Analyse an lcov-format coverage report. Returns per-file "
        "coverage percentage and a list of uncovered line numbers. "
        "Used by the orchestrator's coordinator to triage test gaps."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "report_path": {"type": "string",
                                    "description": "Path to lcov file (e.g. coverage/lcov.info)"},
                },
                "required": ["report_path"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        report_path = Path(kwargs.get("report_path", ""))
        if not report_path:
            return ToolResult(success=False, output="`report_path` is required", error="missing_arg")
        if not report_path.exists():
            return ToolResult(
                success=False,
                output=(
                    f"Coverage report not found at {report_path}. "
                    f"Run tests with coverage first (e.g. `pytest --cov` "
                    f"for Python, `c8` for Node)."
                ),
                error="not_found",
            )

        try:
            text = report_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return ToolResult(success=False, output=f"Read failed: {exc}", error="io_error")

        records = _parse_lcov(text)
        if not records:
            return ToolResult(
                success=True,
                output=f"No records parsed from {report_path}. Is it lcov format?",
                data={"files": []},
            )

        out: list[dict[str, Any]] = []
        lines: list[str] = [f"## Coverage report: {report_path}\n"]
        lines.append("| File | Lines | Hit | Coverage | Uncovered |")
        lines.append("|---|---:|---:|---:|---|")

        for rec in records:
            line_data = rec["lines"]
            if not line_data:
                continue
            total = len(line_data)
            hit = sum(1 for h in line_data.values() if h > 0)
            uncovered = sorted(ln for ln, h in line_data.items() if h == 0)
            pct = (100.0 * hit / total) if total else 0.0
            out.append({
                "file": rec["file"], "total_lines": total, "hit_lines": hit,
                "coverage_pct": round(pct, 2), "uncovered": uncovered,
            })
            # Cap the uncovered list per file for readability.
            uncovered_str = ", ".join(str(x) for x in uncovered[:20])
            if len(uncovered) > 20:
                uncovered_str += f" ... (+{len(uncovered) - 20} more)"
            lines.append(
                f"| {rec['file']} | {total} | {hit} | {pct:.1f}% | {uncovered_str} |"
            )

        if len(out) > 1:
            total_lines = sum(r["total_lines"] for r in out)
            total_hit = sum(r["hit_lines"] for r in out)
            overall = (100.0 * total_hit / total_lines) if total_lines else 0.0
            lines.append(
                f"\n**Overall: {total_hit}/{total_lines} = {overall:.1f}%** "
                f"across {len(out)} file(s)."
            )
        return ToolResult(success=True, output="\n".join(lines), data={"files": out})


registry.register(CoverageAnalyzerTool(), toolset="read")
