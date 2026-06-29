"""Admin API — hooks, plugins, and cron job management."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Hooks ──────────────────────────────────────────────

@router.get("/hooks")
async def list_hooks(request: Request):
    """List all registered hooks and their event types."""
    try:
        from harness._hook_system import get_hook_registry
        reg = get_hook_registry()
        events = {}
        if hasattr(reg, '_hooks'):
            events = {k: len(v) for k, v in reg._hooks.items()}
        return {"hooks": events}
    except Exception as e:
        return {"hooks": {}, "error": str(e)}


@router.get("/hooks/events")
async def list_hook_events():
    """List available hook event types."""
    return {"events": [
        "session_start", "session_end",
        "pre_llm_call", "post_llm_call",
        "pre_tool_call", "post_tool_call",
        "pre_compact", "post_compact",
        "user_prompt_submit", "notification",
        "stop", "subagent_stop",
    ]}


# ── Plugins ────────────────────────────────────────────

@router.get("/plugins")
async def list_plugins():
    """List discovered plugins."""
    try:
        from harness.plugins import discover_plugins
        plugins = discover_plugins()
        return {"plugins": [{"name": p, "enabled": True} for p in plugins]}
    except Exception as e:
        return {"plugins": [], "error": str(e)}


# ── Cron Jobs ──────────────────────────────────────────

class CronJobRequest(BaseModel):
    name: str
    prompt: str
    schedule_type: str = "interval"
    schedule_expr: str = "every 1h"
    skill: str = ""
    script: str = ""
    max_repeats: int = 0


@router.get("/cron")
async def list_cron_jobs(request: Request):
    db = get_db(request)
    from harness.scheduler.store import list_jobs
    jobs = await list_jobs(db)
    return {"jobs": jobs}


@router.post("/cron")
async def create_cron_job(request: Request, body: CronJobRequest):
    db = get_db(request)
    from harness.scheduler.store import create_job
    job = await create_job(db, body.model_dump())
    return {"status": "created", "job": job}


@router.delete("/cron/{job_id}")
async def delete_cron_job(request: Request, job_id: str):
    db = get_db(request)
    from harness.scheduler.store import delete_job
    ok = await delete_job(db, job_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return {"status": "deleted"}


@router.post("/cron/{job_id}/toggle")
async def toggle_cron_job(request: Request, job_id: str):
    db = get_db(request)
    from harness.scheduler.store import get_job, update_job
    job = await get_job(db, job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    await update_job(db, job_id, {"enabled": not job["enabled"]})
    return {"status": "toggled", "enabled": not job["enabled"]}
