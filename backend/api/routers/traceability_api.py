from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps import get_db

router = APIRouter(prefix="/api/traceability", tags=["traceability"])


@router.get("/requirements")
async def list_requirements(request: Request, project_id: str = "default"):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT * FROM requirements WHERE project_id = $1 ORDER BY updated_at DESC", project_id
    )
    return {"requirements": [dict(r) for r in rows]}


@router.get("/coverage-gaps")
async def coverage_gaps(request: Request, project_id: str = "default"):
    db = get_db(request)
    all_reqs = await db.fetch(
        "SELECT id, title FROM requirements WHERE status = 'active' AND project_id = $1", project_id
    )
    gaps = []
    for r in all_reqs:
        link_row = await db.fetchrow(
            "SELECT COUNT(*) as total FROM requirement_links WHERE requirement_id = $1",
            r["id"],
        )
        total = link_row["total"] if link_row else 0
        passed_row = await db.fetchrow(
            "SELECT COUNT(*) as passed FROM requirement_links rl "
            "JOIN test_cases tc ON tc.id = rl.test_case_id "
            "WHERE rl.requirement_id = $1 AND tc.status = 'passed'",
            r["id"],
        )
        passed = passed_row["passed"] if passed_row else 0
        gaps.append({
            "requirement_id": r["id"],
            "title": r["title"],
            "test_count": total,
            "passed_count": passed,
            "has_gap": total == 0 or passed < total,
            "gap_type": "no_tests" if total == 0 else "failing_tests" if passed < total else "none",
        })
    return {"gaps": gaps}


@router.get("/matrix")
async def traceability_matrix(request: Request, project_id: str = "default"):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT r.id as req_id, r.title as req_title, r.priority as req_priority, "
        "tc.id as test_id, tc.name as test_name, tc.status as test_status, "
        "tc.test_type, rl.created_at as linked_at "
        "FROM requirements r "
        "LEFT JOIN requirement_links rl ON rl.requirement_id = r.id "
        "LEFT JOIN test_cases tc ON tc.id = rl.test_case_id "
        "WHERE r.project_id = $1 "
        "ORDER BY r.created_at DESC, rl.created_at DESC",
        project_id,
    )
    matrix: dict[str, dict[str, Any]] = {}
    for r in rows:
        rid = r["req_id"]
        if rid not in matrix:
            matrix[rid] = {
                "requirement_id": rid,
                "title": r["req_title"],
                "priority": r["req_priority"],
                "tests": [],
                "test_count": 0,
                "passed_count": 0,
            }
        if r["test_id"]:
            matrix[rid]["tests"].append({
                "id": r["test_id"],
                "name": r["test_name"],
                "status": r["test_status"],
                "test_type": r["test_type"],
                "linked_at": r["linked_at"].isoformat() if r["linked_at"] else None,
            })
            matrix[rid]["test_count"] += 1
            if r["test_status"] == "passed":
                matrix[rid]["passed_count"] += 1
    return {"matrix": list(matrix.values())}


@router.get("/matrix/{requirement_id}")
async def requirement_detail(request: Request, requirement_id: str):
    db = get_db(request)
    req = await db.fetchrow("SELECT * FROM requirements WHERE id = $1", requirement_id)
    if not req:
        return JSONResponse(status_code=404, content={"error": "Requirement not found"})
    tests = await db.fetch(
        "SELECT tc.*, rl.created_at as linked_at FROM requirement_links rl "
        "JOIN test_cases tc ON tc.id = rl.test_case_id "
        "WHERE rl.requirement_id = $1 ORDER BY rl.created_at DESC",
        requirement_id,
    )
    return {"requirement": dict(req), "tests": [dict(t) for t in tests]}


@router.post("/link")
async def link_test_to_requirement(request: Request):
    db = get_db(request)
    body = await request.json()
    req_id = body.get("requirement_id", "")
    test_id = body.get("test_case_id", "")
    if not req_id or not test_id:
        return JSONResponse(status_code=400, content={"error": "requirement_id and test_case_id required"})
    try:
        await db.execute(
            "INSERT INTO requirement_links (requirement_id, test_case_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            req_id, test_id,
        )
        return {"status": "linked"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.delete("/unlink")
async def unlink_test_from_requirement(request: Request):
    db = get_db(request)
    body = await request.json()
    await db.execute(
        "DELETE FROM requirement_links WHERE requirement_id = $1 AND test_case_id = $2",
        body.get("requirement_id", ""), body.get("test_case_id", ""),
    )
    return {"status": "unlinked"}


@router.post("/generate")
async def generate_tests_for_requirements(request: Request):
    """AI-generate tests from requirements and link them."""
    db = get_db(request)
    body = await request.json()
    req_ids: list[str] = body.get("requirement_ids", [])
    llm = getattr(request.app.state, "llm", None)
    if not llm:
        return JSONResponse(status_code=503, content={"error": "LLM not initialized"})
    if not req_ids:
        return JSONResponse(status_code=400, content={"error": "requirement_ids required"})

    from harness.test_generator import generate_test_cases, save_test_cases

    all_tests = []
    for req_id in req_ids:
        req = await db.fetchrow("SELECT id, title, description FROM requirements WHERE id = $1", req_id)
        if not req:
            continue
        input_text = f"{req['title']}\n{req.get('description', '')}"
        if not input_text.strip():
            continue
        tcs = await generate_test_cases(input_text, llm, count=5)
        if tcs:
            saved = await save_test_cases(db, "default-project", req_id, tcs)
            for tc in tcs:
                all_tests.append({"requirement_id": req_id, "title": tc.get("title", tc.get("name", "")), "saved": True})
            for tc_saved in tcs[:saved]:
                test_row = await db.fetchrow(
                    "SELECT id FROM test_cases WHERE requirement_id = $1 ORDER BY created_at DESC LIMIT 1",
                    req_id,
                )
                if test_row:
                    await db.execute(
                        "INSERT INTO requirement_links (requirement_id, test_case_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        req_id, test_row["id"],
                    )

    return {"generated": len(all_tests), "tests": all_tests}


@router.get("/impact")
async def impact_analysis(request: Request, requirement_id: str = ""):
    db = get_db(request)
    if not requirement_id:
        return {"error": "requirement_id is required"}
    tests = await db.fetch(
        "SELECT tc.id, tc.name, tc.status, tc.code_language "
        "FROM requirement_links rl JOIN test_cases tc ON tc.id = rl.test_case_id "
        "WHERE rl.requirement_id = $1",
        requirement_id,
    )
    return {"requirement_id": requirement_id, "tests": [dict(t) for t in tests]}


@router.get("/risk-score")
async def risk_scores(request: Request, project_id: str = "default"):
    db = get_db(request)
    all_reqs = await db.fetch(
        "SELECT id, title, priority FROM requirements WHERE status = 'active' AND project_id = $1", project_id
    )
    scores = []
    for r in all_reqs:
        tc = await db.fetchrow(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed "
            "FROM test_cases WHERE requirement_id = $1",
            r["id"],
        )
        total = tc["total"] if tc else 0
        passed = tc["passed"] if tc else 0
        coverage_pct = (passed / total * 100) if total > 0 else 0
        priority_weight = {"high": 3, "medium": 2, "low": 1}.get(r["priority"], 2)
        risk = round((100 - coverage_pct) * priority_weight / 3, 1) if total > 0 else 100
        scores.append({
            "requirement_id": r["id"],
            "title": r["title"],
            "priority": r["priority"],
            "coverage_pct": round(coverage_pct, 1),
            "risk_score": risk,
        })
    return {"scores": scores}


@router.get("/heatmap")
async def coverage_heatmap(request: Request):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT test_type, status, COUNT(*) as count FROM test_cases GROUP BY test_type, status ORDER BY test_type",
    )
    heatmap: dict[str, dict[str, int]] = {}
    for r in rows:
        ttype = r["test_type"] or "unknown"
        if ttype not in heatmap:
            heatmap[ttype] = {"total": 0, "passed": 0, "failed": 0, "pending": 0}
        heatmap[ttype]["total"] += r["count"]
        status = r["status"]
        if status in heatmap[ttype]:
            heatmap[ttype][status] += r["count"]
    return {"heatmap": heatmap}


@router.post("/requirements")
async def create_requirement(request: Request):
    db = get_db(request)
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"error": "title is required"})
    desc = body.get("description", "")
    priority = body.get("priority", "medium")
    project_id = body.get("project_id") or "default"
    row = await db.fetchrow(
        "INSERT INTO requirements (title, description, priority, source, project_id) "
        "VALUES ($1, $2, $3, 'manual', $4) RETURNING *",
        title, desc, priority, project_id,
    )
    return {"requirement": dict(row)}


@router.put("/requirements")
async def update_requirement(request: Request):
    db = get_db(request)
    body = await request.json()
    req_id = body.get("id", "")
    title = body.get("title")
    status = body.get("status")
    if not req_id:
        return JSONResponse(status_code=400, content={"error": "id is required"})
    sets = []
    vals: list[Any] = []
    i = 1
    if title is not None:
        sets.append(f"title = ${i}"); vals.append(title); i += 1
    if status is not None:
        sets.append(f"status = ${i}"); vals.append(status); i += 1
    sets.append("updated_at = NOW()")
    if not sets:
        return JSONResponse(status_code=400, content={"error": "no fields"})
    vals.append(req_id)
    await db.execute(f"UPDATE requirements SET {', '.join(sets)} WHERE id = ${i}", *vals)
    return {"status": "ok"}


@router.delete("/requirements")
async def delete_requirement(request: Request):
    db = get_db(request)
    body = await request.json()
    req_id = body.get("id", "")
    await db.execute("DELETE FROM requirements WHERE id = $1", req_id)
    return {"status": "deleted"}


@router.post("/requirements/delete")
async def delete_requirement_post(request: Request):
    db = get_db(request)
    body = await request.json()
    req_id = body.get("id", "")
    await db.execute("DELETE FROM requirements WHERE id = $1", req_id)
    return {"status": "deleted"}


@router.get("/defects")
async def list_defects(request: Request, project_id: str = "default"):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT tcr.defect_id, tcr.defect_url, tc.name as test_name, tc.requirement_id, tc.status "
        "FROM test_results tcr JOIN test_cases tc ON tc.id = tcr.test_name "
        "WHERE tcr.defect_id IS NOT NULL AND tc.project_id = $1 "
        "ORDER BY tcr.created_at DESC LIMIT 100",
        project_id,
    )
    return {"defects": [dict(r) for r in rows]}
