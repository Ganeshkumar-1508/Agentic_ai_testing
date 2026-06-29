"""API endpoints for visual testing, load testing, and self-healing logs."""

from __future__ import annotations

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse

from ..deps import get_db

router = APIRouter(prefix="/api/testing", tags=["testing"])


# ── Visual Testing ──


@router.get("/visual/baselines")
async def list_baselines(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM visual_baselines ORDER BY created_at DESC LIMIT 50")
    return {"baselines": [dict(r) for r in rows]}


@router.post("/visual/capture")
async def capture_screenshot(request: Request):
    body = await request.json()
    url = body.get("url", "")
    test_name = body.get("test_name", "unnamed")
    viewport = body.get("viewport", "1280x720")
    from harness.visual_testing import capture_screenshot, compute_hash
    path = await capture_screenshot(url, f"{test_name.replace('/', '_')}.png", viewport)
    if not path:
        return JSONResponse(status_code=502, content={"error": "Screenshot capture failed"})
    image_hash = compute_hash(path)
    return {"path": path, "hash": image_hash}


@router.post("/visual/compare")
async def compare_screenshots(request: Request):
    body = await request.json()
    baseline = body.get("baseline_path", "")
    actual = body.get("actual_path", "")
    from harness.visual_testing import compare_screenshots
    result = compare_screenshots(baseline, actual)
    return result


# ── Load Testing ──


@router.post("/load/run")
async def run_load_test(request: Request):
    body = await request.json()
    spec = body.get("openapi_spec", {})
    test_type = body.get("test_type", "stress")
    vu_count = body.get("vu_count", 10)
    duration_sec = body.get("duration_sec", 60)
    if not spec:
        return JSONResponse(status_code=400, content={"error": "openapi_spec required"})
    from harness.load_tester import run_load_test
    result = await run_load_test(spec, test_type, vu_count, duration_sec)
    return result


@router.get("/load/runs")
async def list_load_runs(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM load_test_runs ORDER BY created_at DESC LIMIT 20")
    return {"runs": [dict(r) for r in rows]}


# ── Screenshot Serving ──


@router.get("/screenshot")
async def get_screenshot(request: Request, path: str = ""):
    """Serve a captured screenshot file."""
    if not path or not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Screenshot not found"})
    if not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return JSONResponse(status_code=400, content={"error": "Invalid file type"})
    return FileResponse(path, media_type="image/png")


# ── Healing Logs ──


@router.get("/healing/logs")
async def list_healing_logs(request: Request, limit: int = 50):
    db = get_db(request)
    rows = await db.fetch(
        "SELECT * FROM healing_log ORDER BY created_at DESC LIMIT $1", limit,
    )
    return {"logs": [dict(r) for r in rows]}
