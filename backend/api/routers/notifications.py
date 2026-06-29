"""Notification API — in-app notification history, unread count, and delivery log.

Backed by the `notifications` table which records every notification sent
by the system (run completion, run failure, budget warnings, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(request: Request, limit: int = 50):
    """List recent notifications with delivery status."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    if not db or not hasattr(db, "fetch"):
        return {"notifications": [], "unread": 0}

    try:
        rows = await db.fetch(
            "SELECT id, channel, recipient, subject, body, status, error, "
            "source, run_id, created_at, delivered_at "
            "FROM notifications ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        unread_row = await db.fetchrow(
            "SELECT COUNT(*) as cnt FROM notifications WHERE status = 'pending'",
        )
        unread = unread_row["cnt"] if unread_row else 0
    except Exception as exc:
        logger.warning("list_notifications query failed: %s", exc)
        return {"notifications": [], "unread": 0}

    return {
        "notifications": [dict(r) for r in rows],
        "unread": unread,
    }


@router.get("/unread")
async def unread_count(request: Request):
    """Get unread notification count (for bell badge)."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    if not db or not hasattr(db, "fetchrow"):
        return {"count": 0}

    try:
        row = await db.fetchrow(
            "SELECT COUNT(*) as cnt FROM notifications WHERE status = 'pending'",
        )
        return {"count": row["cnt"] if row else 0}
    except Exception:
        return {"count": 0}


@router.post("/{notification_id}/read")
async def mark_read(request: Request, notification_id: str):
    """Mark a single notification as delivered (read)."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    if db and hasattr(db, "execute"):
        await db.execute(
            "UPDATE notifications SET status = 'delivered', delivered_at = NOW() "
            "WHERE id = $1",
            notification_id,
        )
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read(request: Request):
    """Mark all pending notifications as read."""
    db = None
    try:
        from ..deps import get_db
        db = get_db(request)
    except Exception:
        pass

    if db and hasattr(db, "execute"):
        await db.execute(
            "UPDATE notifications SET status = 'delivered', delivered_at = NOW() "
            "WHERE status = 'pending'",
        )
    return {"status": "ok"}
