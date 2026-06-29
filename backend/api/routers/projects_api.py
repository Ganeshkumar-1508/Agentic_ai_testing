"""Projects API — list available projects and per-project summary counts."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects(request: Request):
    db = get_db(request)
    req_rows = await db.fetch(
        "SELECT project_id, COUNT(*)::int as requirement_count "
        "FROM requirements GROUP BY project_id ORDER BY project_id"
    )
    tc_rows = await db.fetch(
        "SELECT project_id, COUNT(*)::int as test_count, "
        "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END)::int as passed_count "
        "FROM test_cases GROUP BY project_id"
    )
    by_id = {r["project_id"]: dict(r) for r in req_rows}
    for r in tc_rows:
        if r["project_id"] not in by_id:
            by_id[r["project_id"]] = {
                "project_id": r["project_id"],
                "requirement_count": 0,
                "test_count": r["test_count"],
                "passed_count": r["passed_count"],
            }
        else:
            by_id[r["project_id"]]["test_count"] = r["test_count"]
            by_id[r["project_id"]]["passed_count"] = r["passed_count"]

    projects = []
    for p in by_id.values():
        req_count = p.get("requirement_count", 0) or 0
        tc_count = p.get("test_count", 0) or 0
        passed = p.get("passed_count", 0) or 0
        projects.append({
            "project_id": p["project_id"],
            "requirement_count": req_count,
            "test_count": tc_count,
            "passed_count": passed,
            "coverage_pct": round(passed / tc_count * 100, 1) if tc_count else 0.0,
            "is_default": p["project_id"] == "default",
        })
    projects.sort(key=lambda x: (not x["is_default"], x["project_id"]))
    return {"projects": projects}


@router.get("/{project_id}/summary")
async def project_summary(request: Request, project_id: str):
    db = get_db(request)
    req = await db.fetchrow("SELECT COUNT(*)::int as total FROM requirements WHERE project_id = $1", project_id)
    tc = await db.fetchrow(
        "SELECT COUNT(*)::int as total, "
        "SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END)::int as passed, "
        "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)::int as failed, "
        "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)::int as pending "
        "FROM test_cases WHERE project_id = $1",
        project_id,
    )
    defects = await db.fetchrow(
        "SELECT COUNT(*)::int as total FROM test_results tr "
        "JOIN test_cases tc ON tc.name = tr.test_name "
        "WHERE tc.project_id = $1 AND tr.defect_id IS NOT NULL",
        project_id,
    )
    gaps = await db.fetchrow(
        "SELECT COUNT(*)::int as total FROM requirements r "
        "WHERE r.project_id = $1 AND r.status = 'active' AND NOT EXISTS ("
        "SELECT 1 FROM requirement_links rl WHERE rl.requirement_id = r.id)",
        project_id,
    )
    return {
        "project_id": project_id,
        "requirements": req["total"] if req else 0,
        "tests": {
            "total": tc["total"] if tc else 0,
            "passed": tc["passed"] if tc else 0,
            "failed": tc["failed"] if tc else 0,
            "pending": tc["pending"] if tc else 0,
        },
        "defects": defects["total"] if defects else 0,
        "coverage_gaps": gaps["total"] if gaps else 0,
    }
