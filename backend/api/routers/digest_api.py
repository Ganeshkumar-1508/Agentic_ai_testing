"""Daily digest configuration API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps import get_db

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("/configs")
async def list_digest_configs(request: Request):
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM digest_configs ORDER BY created_at DESC")
    return {"configs": [dict(r) for r in rows]}


@router.post("/configs")
async def save_digest_config(request: Request):
    db = get_db(request)
    body = await request.json()
    platform = body.get("platform", "")
    channel_id = body.get("channel_id", "")
    schedule = body.get("schedule", "0 8 * * 1-5")
    if not platform or not channel_id:
        return JSONResponse(status_code=400, content={"error": "platform and channel_id required"})
    await db.execute(
        "INSERT INTO digest_configs (platform, channel_id, schedule) VALUES ($1, $2, $3)",
        platform, channel_id, schedule,
    )
    return {"status": "ok"}


@router.delete("/configs/{config_id}")
async def delete_digest_config(request: Request, config_id: str):
    db = get_db(request)
    await db.execute("DELETE FROM digest_configs WHERE id = $1", config_id)
    return {"status": "deleted"}


@router.post("/run")
async def run_digest_now(request: Request):
    """Manually trigger a digest run for testing."""
    from harness.daily_digest import run_digest_for_configs
    db = get_db(request)
    router = getattr(request.app.state, "delivery_router", None)
    if not router:
        return JSONResponse(status_code=503, content={"error": "Delivery router not initialized"})
    await run_digest_for_configs(db, router)
    return {"status": "digest_sent"}
