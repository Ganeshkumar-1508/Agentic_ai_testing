"""Notification configuration API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/api/notify", tags=["notify"])


class WebhookConfig(BaseModel):
    url: str
    name: str = ""
    events: list[str] = []
    enabled: bool = True


@router.get("/channels")
async def get_channels(request: Request):
    """List configured notification channels."""
    db = get_db(request)
    try:
        rows = await db.fetch(
            "SELECT id, name, url, type, events, enabled FROM webhook_configs ORDER BY created_at DESC"
        )
        return {"channels": [dict(r) for r in rows]}
    except Exception as e:
        return {"channels": [], "error": str(e)}


@router.post("/channels")
async def add_channel(request: Request, body: WebhookConfig):
    """Add a notification channel."""
    import uuid, json
    db = get_db(request)
    channel_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO webhook_configs (id, name, url, type, events, enabled) VALUES ($1, $2, $3, 'webhook', $4, $5)",
        channel_id, body.name or body.url[:30], body.url,
        json.dumps(body.events), body.enabled,
    )
    return {"status": "created", "id": channel_id}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str, request: Request):
    """Remove a notification channel."""
    db = get_db(request)
    await db.execute("DELETE FROM webhook_configs WHERE id = $1", channel_id)
    return {"status": "deleted"}


@router.post("/test")
async def test_notification(request: Request):
    """Send a test notification to all configured channels."""
    db = get_db(request)
    from harness.notifications import dispatch
    await dispatch("session.completed", {"test": True, "message": "Test notification from TestAI"}, db)
    return {"status": "sent"}
