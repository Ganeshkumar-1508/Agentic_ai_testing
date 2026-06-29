"""Logs API — thin router, delegates to LogsService."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..deps import get_db
from harness.services.logs_service import LogsService

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs/sessions")
async def list_log_sessions(
    request: Request,
    status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
):
    svc = LogsService(get_db(request))
    return await svc.list_sessions(status, search, limit, cursor)


@router.get("/logs/sessions/{session_id}")
async def get_log_session(request: Request, session_id: str):
    svc = LogsService(get_db(request))
    result = await svc.get_session(session_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return result


@router.get("/logs/sessions/{session_id}/events")
async def list_log_events(
    request: Request,
    session_id: str,
    type: str | None = Query(None, alias="type"),
    search: str | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    cursor: str | None = Query(None),
):
    svc = LogsService(get_db(request))
    result = await svc.list_events(session_id, type, search, since, until, limit, cursor)
    if isinstance(result, dict) and result.get("error") == "not_found":
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return result

