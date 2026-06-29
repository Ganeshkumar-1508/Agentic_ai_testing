"""Coverage gap analysis API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/coverage", tags=["coverage"])


@router.get("/summary")
async def coverage_summary(request: Request, days: int = 30, run_id: str = ""):
    """Get coverage summary with gap analysis and trend."""
    db = get_db(request)
    from harness.coverage_gaps import get_coverage_summary
    result = await get_coverage_summary(db, run_id=run_id or None, days=days)
    return result


@router.get("/gaps")
async def coverage_gaps(request: Request, threshold: float = 80.0, limit: int = 50):
    """Get files with coverage below threshold, sorted by coverage ascending."""
    db = get_db(request)
    try:
        row = await db.fetchrow(
            "SELECT report_data FROM coverage_reports ORDER BY created_at DESC LIMIT 1"
        )
        if not row:
            return {"gaps": [], "count": 0}

        report_data = row["report_data"]
        if isinstance(report_data, str):
            import json
            report_data = json.loads(report_data)

        files = report_data.get("files", {}) if isinstance(report_data, dict) else {}
        gaps = [
            {
                "path": fp,
                "percent": round(fd.get("percent", 0), 2) if isinstance(fd, dict) else 0,
                "missing": fd.get("missing", 0) if isinstance(fd, dict) else 0,
                "total": fd.get("lines", 0) if isinstance(fd, dict) else 0,
            }
            for fp, fd in sorted(files.items(), key=lambda x: x[1].get("percent", 100) if isinstance(x[1], dict) else 100)
            if isinstance(fd, dict) and fd.get("percent", 100) < threshold
        ]

        return {"gaps": gaps[:limit], "count": len(gaps), "threshold": threshold}
    except Exception as e:
        return {"error": str(e), "gaps": [], "count": 0}
