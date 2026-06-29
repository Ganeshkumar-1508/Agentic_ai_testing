"""Kanban board API — multi-agent task coordination.

Thin router: validates input → calls KanbanService → formats response.
All DB queries and background logic live in harness/services/kanban_service.py.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Any
from sse_starlette.sse import EventSourceResponse

from ..deps import get_db
from harness.services.kanban_service import KanbanService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kanban", tags=["kanban"])


class BoardCreate(BaseModel):
    name: str
    description: str = ""
    columns: list[str] = ["triage", "backlog", "ready", "in_progress", "review", "done", "flaky_heat"]
    wip_limits: dict = {"in_progress": 3}
    config: dict = {}


class TaskCreate(BaseModel):
    board_id: str = ""
    title: str
    description: str = ""
    column_name: str = "backlog"
    priority: str = "p2"
    tags: str = ""
    assigned_to: str = ""
    agent_type: str = "general-purpose"
    coverage_file: str = ""
    flaky_test_name: str = ""
    timebox_seconds: int = 0
    estimate_minutes: int = 0
    deadline: str = ""
    pipeline_run_id: str = ""
    parent_task_id: str = ""
    needs_review: bool = False

    def to_task_body(self) -> dict[str, Any]:
        body = self.model_dump()
        if not self.board_id:
            body.pop("board_id", None)
        return body


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    column_name: str | None = None
    priority: str | None = None
    tags: str | None = None
    assigned_to: str | None = None
    coverage_file: str | None = None
    result_summary: str | None = None
    needs_review: bool | None = None
    review_status: str | None = None
    deadline: str | None = None
    estimate_minutes: int | None = None
    timebox_seconds: int | None = None


class ReviewBody(BaseModel):
    action: str
    reviewer: str
    notes: str = ""


class TriageBody(BaseModel):
    mode: str = "auto"
    instructions: str = ""


class CommentBody(BaseModel):
    author: str = "user"
    body: str


# ── Boards ─────────────────────────────────────────────────────────


def _scoped_board_id(request: Request, board_id: str = "") -> str:
    """If the request has a board-scope header, the path's board_id
    must match it. Returns the effective board_id to query.

    For ``/boards`` (list, no path board_id): filters the list to
    the scoped board only. For ``/boards/{board_id}/...``: rejects
    any request whose path board_id doesn't match the scope.

    Human operators (no scope header) are unaffected.
    """
    scope = request.headers.get("X-TestAI-Board-Id", "").strip()
    if not scope:
        return board_id
    if board_id and board_id != scope:
        # Mismatch — return a sentinel that the caller treats as
        # "no results". We don't raise 403 because the caller is
        # likely an agent that doesn't know the scope; raising
        # would surface the scope to the LLM, which is the leak
        # we're trying to prevent.
        return ""
    return scope


@router.get("/boards")
async def list_boards(request: Request):
    svc = KanbanService(get_db(request))
    board_id = _scoped_board_id(request)
    return {"boards": await svc.list_boards(board_id=board_id) if board_id else await svc.list_boards()}


@router.post("/boards")
async def create_board(request: Request, body: BoardCreate):
    svc = KanbanService(get_db(request))
    board_id = await svc.create_board(body.name, body.description, body.columns, body.wip_limits, body.config)
    return {"id": board_id, "status": "ok"}


@router.patch("/boards/{board_id}")
async def update_board(request: Request, board_id: str, body: BoardCreate):
    effective = _scoped_board_id(request, board_id)
    if not effective:
        return {"status": "ok"}  # scope mismatch — silently no-op
    svc = KanbanService(get_db(request))
    await svc.update_board(effective, body.name, body.description, body.columns, body.wip_limits, body.config)
    return {"status": "ok"}


@router.delete("/boards/{board_id}")
async def delete_board(request: Request, board_id: str):
    svc = KanbanService(get_db(request))
    await svc.delete_board(board_id)
    return {"status": "ok"}


# ── Tasks ──────────────────────────────────────────────────────────


@router.get("/boards/{board_id}/tasks")
async def list_tasks(request: Request, board_id: str, sprint: str = ""):
    svc = KanbanService(get_db(request))
    return {"tasks": await svc.list_tasks(board_id, sprint)}


@router.get("/boards/{board_id}/sprints")
async def list_sprints(request: Request, board_id: str):
    svc = KanbanService(get_db(request))
    return {"sprints": await svc.list_sprints(board_id)}


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    task = await svc.get_task(task_id)
    if not task:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return {"task": task}


@router.post("/boards/{board_id}/tasks")
async def create_task(request: Request, board_id: str, body: TaskCreate):
    svc = KanbanService(get_db(request))
    task_id = await svc.create_task(board_id, body.to_task_body())
    return {"id": task_id, "status": "ok"}


@router.patch("/tasks/{task_id}")
async def update_task(request: Request, task_id: str, body: TaskUpdate):
    import datetime as _dt
    svc = KanbanService(get_db(request))
    updates = body.model_dump(exclude_none=True)
    col = updates.get("column_name", "")
    if col == "in_progress":
        updates["started_at"] = _dt.datetime.now(_dt.timezone.utc)
    elif col == "done":
        updates["completed_at"] = _dt.datetime.now(_dt.timezone.utc)
    await svc.update_task(task_id, updates)
    return {"status": "ok"}


@router.post("/tasks/{task_id}/claim")
async def claim_task(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    return await svc.claim_task(task_id)


@router.post("/tasks/{task_id}/complete")
async def complete_task(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    result = await svc.complete_task(task_id)
    if result["status"] == "not_found":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return result


@router.post("/tasks/{task_id}/heartbeat")
async def heartbeat_task(request: Request, task_id: str, body: dict | None = None):
    svc = KanbanService(get_db(request))
    note = (body or {}).get("note", "") if body else ""
    return await svc.heartbeat_task(task_id, note)


@router.post("/tasks/{task_id}/review")
async def review_task(request: Request, task_id: str, body: ReviewBody):
    svc = KanbanService(get_db(request))
    result = await svc.review_task(task_id, body.action, body.reviewer, body.notes)
    if result is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    if "error" in result:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content=result)
    return result


@router.post("/tasks/{task_id}/block")
async def block_task(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    await svc.block_task(task_id)
    return {"status": "ok"}


@router.post("/tasks/{task_id}/unblock")
async def unblock_task(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    await svc.unblock_task(task_id)
    return {"status": "ok"}


@router.post("/tasks/{task_id}/comment")
async def comment_task(request: Request, task_id: str, body: CommentBody):
    svc = KanbanService(get_db(request))
    result = await svc.add_comment(task_id, body.author, body.body)
    if result.get("status") == "not_found":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return result


@router.post("/tasks/{task_id}/triage")
async def triage_task(request: Request, task_id: str, body: TriageBody):
    svc = KanbanService(get_db(request))
    result = await svc.triage_task(task_id, body.mode, body.instructions)
    if result.get("status") == "not_found":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Task not found"})
    return result


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    await svc.delete_task(task_id)
    return {"status": "ok"}


# ── Dependencies ────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/dependencies")
async def list_dependencies(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    return {"dependencies": await svc.list_dependencies(task_id)}


@router.post("/tasks/{task_id}/dependencies")
async def add_dependency(request: Request, task_id: str, body: dict):
    depends_on = body.get("depends_on_task_id", "")
    if not depends_on:
        return {"error": "depends_on_task_id required"}
    svc = KanbanService(get_db(request))
    status = await svc.add_dependency(task_id, depends_on)
    return {"status": status}


@router.delete("/tasks/{task_id}/dependencies/{dep_id}")
async def remove_dependency(request: Request, task_id: str, dep_id: str):
    svc = KanbanService(get_db(request))
    await svc.remove_dependency(task_id, dep_id)
    return {"status": "ok"}


# ── Agent Log ───────────────────────────────────────────────────────


@router.post("/tasks/{task_id}/log")
async def log_agent_action(request: Request, task_id: str, body: dict):
    svc = KanbanService(get_db(request))
    await svc.log_agent_action(task_id, body.get("agent_id", "unknown"), body.get("action", ""), body.get("detail", ""))
    return {"status": "ok"}


@router.get("/tasks/{task_id}/log")
async def get_agent_log(request: Request, task_id: str):
    svc = KanbanService(get_db(request))
    return {"log": await svc.get_agent_log(task_id)}


# ── Events / Stats ──────────────────────────────────────────────────


@router.get("/boards/{board_id}/events")
async def get_board_events(request: Request, board_id: str, after: int = 0, limit: int = 50):
    svc = KanbanService(get_db(request))
    return {"events": await svc.get_events(board_id, after, limit)}


@router.get("/boards/{board_id}/stats")
async def get_board_stats(request: Request, board_id: str):
    svc = KanbanService(get_db(request))
    return await svc.get_stats(board_id)


@router.get("/events/stream")
async def stream_kanban_events(request: Request, board_id: str = "", since: int = 0):
    """SSE endpoint for real-time kanban events.

    Polls ``kanban_events`` for new rows and pushes them as SSE events.
    Clients reconnect automatically via the browser ``EventSource`` API.

    Query params:
        board_id:  Filter to a specific board (empty = all boards).
        since:     Last known event ID (0 = all recent events).
    """
    db = get_db(request)
    _POLL_SECONDS = 2
    _KEEPALIVE_SECONDS = 25
    _BATCH_LIMIT = 100

    async def event_generator():
        cursor = since
        last_keepalive = asyncio.get_event_loop().time()
        while True:
            if await request.is_disconnected():
                break
            try:
                if board_id:
                    rows = await db.fetch(
                        "SELECT id, board_id, task_id, event_type, payload, created_at "
                        "FROM kanban_events WHERE board_id = $1 AND id > $2 "
                        "ORDER BY id ASC LIMIT $3",
                        board_id, cursor, _BATCH_LIMIT,
                    )
                else:
                    rows = await db.fetch(
                        "SELECT id, board_id, task_id, event_type, payload, created_at "
                        "FROM kanban_events WHERE id > $1 "
                        "ORDER BY id ASC LIMIT $2",
                        cursor, _BATCH_LIMIT,
                    )
                for r in rows:
                    cursor = r["id"]
                    payload = r["payload"]
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except (json.JSONDecodeError, TypeError):
                            payload = {}
                    yield {
                        "event": r["event_type"],
                        "id": str(r["id"]),
                        "data": json.dumps({
                            "id": r["id"],
                            "board_id": r["board_id"],
                            "task_id": r["task_id"],
                            "event_type": r["event_type"],
                            "payload": payload,
                            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                        }),
                    }
            except Exception as exc:
                logger.debug("kanban SSE poll failed: %s", exc)

            now = asyncio.get_event_loop().time()
            if now - last_keepalive >= _KEEPALIVE_SECONDS:
                yield {"event": "ping", "data": "{}"}
                last_keepalive = now

            await asyncio.sleep(_POLL_SECONDS)

    return EventSourceResponse(event_generator())


@router.post("/from-pipeline")
async def create_task_from_pipeline(request: Request, body: dict):
    svc = KanbanService(get_db(request))
    result = await svc.create_task_from_pipeline(
        body.get("run_id", ""), body.get("title", ""), body.get("status", "completed"),
    )
    return result
