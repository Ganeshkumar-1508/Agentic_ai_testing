"""Blueprint catalog API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from harness.cron.blueprint_catalog import (
    CATALOG,
    get_blueprint,
    blueprint_form_schema,
    fill_blueprint,
    BlueprintFillError,
)
from ..deps import get_db

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/blueprints")
async def list_blueprints():
    """List all available automation blueprints with their form schemas."""
    result = []
    for bp in CATALOG:
        entry = {
            "key": bp.key,
            "title": bp.title,
            "description": bp.description,
            "category": bp.category,
            "tags": list(bp.tags),
            "form_schema": blueprint_form_schema(bp),
        }
        result.append(entry)
    return {"blueprints": result}


@router.get("/blueprints/{key}")
async def get_blueprint_endpoint(key: str):
    """Get a single blueprint with its form schema."""
    bp = get_blueprint(key)
    if bp is None:
        return {"status": "error", "error": f"Blueprint '{key}' not found"}
    return {
        "blueprint": {
            "key": bp.key,
            "title": bp.title,
            "description": bp.description,
            "category": bp.category,
            "tags": list(bp.tags),
            "form_schema": blueprint_form_schema(bp),
        }
    }


@router.post("/blueprints/{key}/schedule")
async def schedule_blueprint(request: Request, key: str, body: dict[str, Any]):
    """Fill a blueprint and create a cron job."""
    bp = get_blueprint(key)
    if bp is None:
        return {"status": "error", "error": f"Blueprint '{key}' not found"}

    values = body.get("values", {})

    try:
        job_config = fill_blueprint(bp, values)
    except BlueprintFillError as e:
        return {"status": "error", "error": str(e)}

    # Persist to cron_jobs table
    db = get_db(request)
    try:
        from harness.scheduler.store import create_table, create_job
        await create_table(db)
        job = await create_job(db, job_config)
        return {"status": "ok", "job": job}
    except Exception as e:
        return {"status": "error", "error": str(e)}
