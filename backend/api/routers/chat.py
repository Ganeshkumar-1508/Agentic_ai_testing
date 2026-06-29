"""Chat API — REST + SSE surface for the chat UI."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from harness.chat import (
    ChatMessage,
    ChatThread,
    archive_thread,
    create_thread,
    get_messages,
    get_thread,
    list_threads,
    stream_chat_response,
)
from harness.chat.threads import THREAD_SOURCES, get_thread_by_run_id
from harness.chat.sse import DEFAULT_MAX_RUN_SECONDS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class CreateThreadRequest(BaseModel):
    title: str | None = None
    source: str = Field(default="api", description=f"One of {THREAD_SOURCES}")
    run_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)
    max_run_seconds: float | None = Field(default=None, ge=1, le=3600)


class ThreadListResponse(BaseModel):
    threads: list[ChatThread]
    total: int
    limit: int
    offset: int


class MessageListResponse(BaseModel):
    thread_id: str
    messages: list[ChatMessage]
    total: int
    limit: int
    offset: int


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads_endpoint(
    request: Request,
    run_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ThreadListResponse:
    db = request.app.state.db
    threads = await list_threads(
        run_id=run_id,
        session_id=session_id,
        include_archived=archived,
        limit=limit,
        offset=offset,
        db=db,
    )
    from harness.chat.threads import count_threads as _count_threads
    total = await _count_threads(
        run_id=run_id,
        session_id=session_id,
        include_archived=archived,
        db=db,
    )
    return ThreadListResponse(
        threads=threads,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/threads", response_model=ChatThread)
async def create_thread_endpoint(
    request: Request, body: CreateThreadRequest
) -> ChatThread:
    if body.source not in THREAD_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"source must be one of {sorted(THREAD_SOURCES)}",
        )
    db = request.app.state.db
    if body.run_id:
        existing = await get_thread_by_run_id(body.run_id, db=db)
        if existing is not None:
            return existing
    thread = await create_thread(
        title=body.title,
        source=body.source,
        run_id=body.run_id,
        session_id=body.session_id,
        db=db,
    )
    return thread


@router.get("/threads/{thread_id}", response_model=ChatThread)
async def get_thread_endpoint(request: Request, thread_id: str) -> ChatThread:
    db = request.app.state.db
    thread = await get_thread(thread_id, db=db)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return thread


@router.delete("/threads/{thread_id}")
async def archive_thread_endpoint(request: Request, thread_id: str) -> JSONResponse:
    db = request.app.state.db
    ok = await archive_thread(thread_id, db=db)
    if not ok:
        raise HTTPException(status_code=404, detail="thread not found")
    return JSONResponse({"status": "ok", "thread_id": thread_id, "archived": True})


@router.get(
    "/threads/{thread_id}/messages", response_model=MessageListResponse,
)
async def list_messages_endpoint(
    request: Request,
    thread_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    include_tool_results: bool = Query(default=True),
) -> MessageListResponse:
    db = request.app.state.db
    thread = await get_thread(thread_id, db=db)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    messages = await get_messages(
        thread_id,
        limit=limit,
        offset=offset,
        include_tool_results=include_tool_results,
        db=db,
    )
    return MessageListResponse(
        thread_id=thread_id,
        messages=messages,
        total=thread.message_count,
        limit=limit,
        offset=offset,
    )


@router.post("/threads/{thread_id}/messages")
async def post_message_endpoint(
    request: Request, thread_id: str, body: PostMessageRequest
):
    from sse_starlette.sse import EventSourceResponse

    db = request.app.state.db
    thread = await get_thread(thread_id, db=db)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if thread.archived:
        raise HTTPException(status_code=410, detail="thread is archived")
    agent = request.app.state.agent
    max_run = body.max_run_seconds or DEFAULT_MAX_RUN_SECONDS
    return EventSourceResponse(
        stream_chat_response(
            thread_id=thread_id,
            user_content=body.content,
            agent=agent,
            is_disconnected=request.is_disconnected,
            db=db,
            max_run_seconds=max_run,
        ),
        ping=15,
    )


@router.get("/threads/{thread_id}/stream")
async def stream_thread_endpoint(request: Request, thread_id: str):
    """Stream chat.* SSE frames for events on the thread's run.

    EventSource-friendly (GET). Subscribes to the orchestrator's
    EventSourceSink for the thread's ``run_id`` and yields
    translated chat.* frames as the orchestrator emits events.

    The page opens this stream right after ``POST /api/jobs``
    returns a ``thread_id``. The stream is also useful for
    resuming observation of an in-flight run from any surface.
    """
    from sse_starlette.sse import EventSourceResponse

    from harness.chat.sse import stream_thread_events

    db = request.app.state.db
    thread = await get_thread(thread_id, db=db)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if not thread.run_id:
        raise HTTPException(
            status_code=409,
            detail="thread has no run_id; orchestrator not started",
        )
    event_sink = getattr(request.app.state, "event_source_sink", None)
    if event_sink is None:
        raise HTTPException(
            status_code=503,
            detail="event_source_sink not configured on app state",
        )
    return EventSourceResponse(
        stream_thread_events(
            thread_id=thread_id,
            event_sink=event_sink,
            is_disconnected=request.is_disconnected,
            db=db,
        ),
        ping=15,
    )
