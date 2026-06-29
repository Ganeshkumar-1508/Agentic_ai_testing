"""Sprint quality trends API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import get_db

router = APIRouter(prefix="/api/sprint", tags=["sprint"])


@router.get("/trends")
async def get_sprint_trends(request: Request, sprints: int = 6):
    """Get quality trends over the last N sprints with regression alerts."""
    db = get_db(request)
    from harness.sprint_trends import get_sprint_trends
    return await get_sprint_trends(db, sprints=sprints)
