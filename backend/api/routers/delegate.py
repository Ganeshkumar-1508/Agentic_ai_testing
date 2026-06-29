from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from ..deps import get_db, get_agent
from .. import state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/delegate", tags=["delegate"])


class RepoSpec(BaseModel):
    url: str
    branch: str = "main"
    token: str = ""
    depends_on: list[str] = []


class DelegateRequest(BaseModel):
    prompt: str = ""
    repo_url: str = ""
    branch: str = ""
    repos: list[RepoSpec] | None = None
    tasks: list[str] | None = None
    context: str = ""
    toolsets: list[str] | None = None
    role: str = "leaf"
    run_in_background: bool = False
    model: str | None = None
    mcp_servers: list[str] | None = None

    @property
    def effective_goal(self) -> str:
        return self.prompt or (self.tasks[0] if self.tasks else "")


class SteerRequest(BaseModel):
    text: str
    mode: str = "now"  # 'now' or 'next'


class InterruptRequest(BaseModel):
    subagent_id: str = ""


class ApproveRequest(BaseModel):
    approval_id: str
    approved: bool = True
    scope: str = "once"  # "once", "session", "always"


@router.get("/{session_id}/stream")
async def stream_delegation(request: Request, session_id: str):
    """SSE stream of delegation events for the given session.
    Events: session.started, subagent.spawned, subagent.thinking,
            subagent.tool_start, subagent.complete, session.completed, etc.
    """
    async def event_generator():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                from harness.api.state import poll_stream_events
                events = await poll_stream_events(session_id, after_id=last_id)
                for event in events:
                    last_id = event["id"]
                    yield {
                        "event": event["event_type"],
                        "id": str(event["id"]),
                        "data": json.dumps(event["payload"]),
                    }
                if not events:
                    await asyncio.sleep(0.25)
            except Exception as e:
                logger.warning("SSE stream error for %s: %s", session_id, e)
                await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# POST /api/delegate/{session_id}/steer — inject instruction mid-turn (A2A Task.message)
# ---------------------------------------------------------------------------


@router.post("/{session_id}/steer")
async def steer_delegation(request: Request, session_id: str, body: SteerRequest):
    """Inject a steer instruction into a running delegation."""
    agent = get_agent(request)
    if not agent:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": "Agent not initialized"})

    steer_text = body.text
    is_now = body.mode == "now"

    # Use the agent's steer mechanism — set pending steer on the agent
    if hasattr(agent, "_pending_steer"):
        if is_now:
            agent._pending_steer = steer_text
        else:
            existing = getattr(agent, "_pending_steer", None)
            agent._pending_steer = (existing + "\n" + steer_text) if existing else steer_text
    else:
        # Fallback: inject as a new user message
        agent._add_message(role="user", content=f"[Steer - {'immediate' if is_now else 'next'}]: {steer_text}")

    from harness.api.state import emit_stream_event
    await emit_stream_event(session_id, "steer.injected", {
        "text": steer_text[:200],
        "mode": body.mode,
    })

    return {"status": "steer_injected", "mode": body.mode}


# ---------------------------------------------------------------------------
# POST /api/delegate/{session_id}/cancel — cancel entire delegation tree (A2A Task.cancel)
# ---------------------------------------------------------------------------


@router.post("/{session_id}/cancel")
async def cancel_delegation(request: Request, session_id: str):
    """Cancel an entire delegation tree. Kills all subagents and cleans up."""
    from harness.tools.delegate_task import active_subagents, set_spawn_paused

    db = get_db(request)

    set_spawn_paused(True)
    killed = 0
    for sub in active_subagents():
        sid = sub.get("id")
        if sid:
            from harness.tools.delegate_task import interrupt_subagent
            if interrupt_subagent(sid):
                killed += 1

    await db.execute(
        "UPDATE sessions SET status = 'cancelled', ended_at = NOW(), end_reason = 'cancelled' WHERE id = $1",
        session_id,
    )

    from harness.api.state import emit_stream_event
    await emit_stream_event(session_id, "session.cancelled", {
        "session_id": session_id,
        "subagents_killed": killed,
    })

    # Cancellation is scoped to the current delegation tree, not a permanent
    # global stop for all future pipeline sessions.
    set_spawn_paused(False)

    return {"status": "cancelled", "subagents_interrupted": killed}


# ---------------------------------------------------------------------------
# POST /api/delegate/{session_id}/interrupt — interrupt a specific subagent
# ---------------------------------------------------------------------------


@router.post("/{session_id}/interrupt")
async def interrupt_subagent_endpoint(request: Request, session_id: str, body: InterruptRequest):
    """Interrupt a single subagent by ID."""
    from harness.tools.delegate_task import interrupt_subagent as interrupt_sa
    ok = interrupt_sa(body.subagent_id)
    if ok:
        from harness.api.state import emit_stream_event
        await emit_stream_event(session_id, "subagent.interrupted", {
            "subagent_id": body.subagent_id,
        })
    return {"status": "interrupted" if ok else "not_found"}


# ---------------------------------------------------------------------------
# POST /api/delegate/{session_id}/pause — block new spawns, drain in-flight
# ---------------------------------------------------------------------------


@router.post("/{session_id}/pause")
async def pause_delegation(session_id: str):
    """Pause spawning of new subagents. Running agents finish naturally."""
    from harness.tools.delegate_task import set_spawn_paused
    set_spawn_paused(True)
    return {"status": "paused"}


# ---------------------------------------------------------------------------
# GET /api/delegate/{session_id} — delegation tree snapshot (A2A Task.get)
# ---------------------------------------------------------------------------


@router.get("/{session_id}")
async def get_delegation_tree(request: Request, session_id: str):
    """Get the full delegation tree for a session."""
    db = get_db(request)
    rows = await db.fetch(
        """WITH RECURSIVE tree AS (
            SELECT id, parent_session_id, goal, depth, agent_role, status,
                   started_at, ended_at, end_reason
            FROM sessions WHERE id = $1
            UNION ALL
            SELECT s.id, s.parent_session_id, s.goal, s.depth, s.agent_role, s.status,
                   s.started_at, s.ended_at, s.end_reason
            FROM sessions s JOIN tree t ON s.parent_session_id = t.id
        )
        SELECT * FROM tree ORDER BY depth, started_at""",
        session_id,
    )
    return {"session_id": session_id, "tree": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# GET /api/delegate/{session_id}/tool-calls — tool call list for a subagent
# ---------------------------------------------------------------------------


@router.get("/{session_id}/tool-calls")
async def get_subagent_tool_calls(request: Request, session_id: str, subagent_id: str = ""):
    """Get tool execution events for a specific subagent in a session."""
    db = get_db(request)
    rows = await db.fetch(
        """SELECT id, event_type, event_data, created_at
           FROM stream_events
           WHERE session_id = $1 AND subagent_id = $2
             AND event_type IN ('ToolExecutionStarted','ToolExecutionCompleted',
                                'tool.execution.started','tool.execution.completed',
                                'tool:start','tool:end')
           ORDER BY id ASC""",
        session_id, subagent_id,
    )
    return {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "tool_calls": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# Resume checkpoint — restore a session from last checkpoint
# ---------------------------------------------------------------------------


@router.post("/{session_id}/resume")
async def resume_delegation_session(request: Request, session_id: str):
    """Resume a delegation session from its last checkpoint after crash."""
    db = get_db(request)

    from harness.checkpoint import CheckpointManager
    mgr = CheckpointManager(db, session_id)
    state = await mgr.resume_state()

    if not state:
        return {"status": "no_checkpoint", "session_id": session_id}

    # Restore session status to running
    await db.execute(
        "UPDATE sessions SET status = 'running', ended_at = NULL, end_reason = NULL WHERE id = $1",
        session_id,
    )

    from harness.api.state import emit_stream_event
    await emit_stream_event(session_id, "session.resumed", {
        "session_id": session_id,
        "checkpoint_type": state.get("_checkpoint_type", "unknown"),
        "turn_count": state.get("turn_count", 0),
    })

    return {
        "status": "resumed",
        "session_id": session_id,
        "checkpoint_type": state.get("_checkpoint_type", "unknown"),
        "saved_tools": list(state.get("discovered_tools", [])),
    }


# ---------------------------------------------------------------------------
# Approval endpoints — resolve pending approvals with scope
# ---------------------------------------------------------------------------


@router.post("/approve")
async def resolve_tool_approval(request: Request, body: ApproveRequest):
    """Resolve a pending tool approval. Scope: once, session, or always."""
    agent = get_agent(request)
    if not agent:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"error": "Agent not initialized"})

    ok = agent._deps.permissions.resolve_approval(body.approval_id, body.approved, scope=body.scope)

    from harness.api.state import emit_stream_event
    await emit_stream_event("system", "approval.resolved", {
        "approval_id": body.approval_id,
        "approved": body.approved,
        "scope": body.scope,
    })

    return {"status": "resolved" if ok else "not_found", "scope": body.scope}


@router.get("/approvals/pending")
async def list_pending_approvals(request: Request):
    """List all pending tool approvals waiting for human response."""
    agent = get_agent(request)
    if not agent:
        return {"approvals": []}
    return {"approvals": agent._deps.permissions.pending_approvals()}




@router.post("/{session_id}/fork")
async def fork_delegation_session(request: Request, session_id: str, body: dict | None = None):
    """Fork a delegation session: copy the source's context, allow a new
    goal, spawn as a brand-new session_id that points to the source as
    its parent. Useful when the user wants to keep the prior run's
    memory and explored context but redirect the work.

    Body (optional):
      {
        "new_goal": "<override prompt>",
        "repo_url": "<optional override>",
        "branch":   "<optional override>",
        "tier":     1|2|3  # optional, default = source's tier
      }

    Returns:
      202 { "status": "forked", "source_session_id": "...",
            "new_session_id": "...", "new_goal": "..." }
    """
    import asyncio
    import uuid
    from harness.jobs.spec import JobSpec
    from harness.orchestrator import OrchestratorEngine

    body = body or {}
    new_goal = (body.get("new_goal") or "").strip()
    if not new_goal:
        raise HTTPException(status_code=400, detail="new_goal is required for fork")

    db = get_db(request)

    # Look up the source session to inherit repo/branch/tier.
    src = await db.fetchrow(
        "SELECT id, agent_role, model, parent_session_id, source, backend_type FROM sessions WHERE id = $1",
        session_id,
    )
    if not src:
        raise HTTPException(status_code=404, detail=f"source session not found: {session_id}")

    repo_url = body.get("repo_url") or ""
    branch = body.get("branch") or "main"
    try:
        tier = int(body.get("tier", 2))
    except (TypeError, ValueError):
        tier = 2

    new_session_id = str(uuid.uuid4())
    # Register the new session row, parented to the source.
    try:
        await db.execute(
            """INSERT INTO sessions
               (id, source, status, depth, agent_role, goal, model, parent_session_id, started_at, backend_type)
               VALUES ($1, $2, 'running', 0, 'orchestrator', $3, $4, $5, NOW(), $6)""",
            new_session_id, "fork", new_goal[:500], src["model"] or "", session_id,
            src.get("backend_type") or "local",
        )
    except Exception as exc:
        logger.warning("fork: session row insert failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"session create failed: {exc}")

    # Submit the new run via the orchestrator (background task).
    spec = JobSpec.from_chat_submission(
        prompt=new_goal,
        repo_url=repo_url,
        branch=branch,
        tier=tier,
        capabilities=["read", "write", "test", "run_tests"],
        session_id=new_session_id,
        agent_id="fork-from-" + session_id[:8],
    )
    engine = OrchestratorEngine()
    new_run_id = spec.run_id

    async def _run_fork():
        try:
            await engine.run_job_spec(spec)
        except Exception as exc:
            logger.warning(
                "fork: orchestrator run_job_spec failed new_run=%s: %s",
                new_run_id, exc,
            )

    try:
        asyncio.create_task(_run_fork())
    except RuntimeError:
        pass

    # Emit a stream event on the SOURCE session so the dashboard
    # surfaces "forked from this session" in the source's timeline.
    try:
        from harness.api.state import emit_stream_event
        await emit_stream_event(session_id, "session.forked", {
            "source_session_id": session_id,
            "new_session_id": new_session_id,
            "new_run_id": new_run_id,
            "new_goal": new_goal[:200],
        })
    except Exception:
        pass

    return {
        "status": "forked",
        "source_session_id": session_id,
        "new_session_id": new_session_id,
        "new_run_id": new_run_id,
        "new_goal": new_goal,
    }


@router.get("/{session_id}/shadow/stream")
async def shadow_stream(request: Request, session_id: str):
    """Q11-C: live shadow / watch-mode SSE stream for a running session.

    Streams the session's stream_events rows in near-real-time so
    a human can watch the agent's tool calls, LLM reasoning, kanban
    updates, and cost ticks as they happen. Read-only; the operator
    cannot intervene through this stream (use /steer for that).

    Events emitted:
      - token (LLM deltas)
      - reasoning
      - tool_calls (assistant tool-call batch)
      - tool_result (per tool result)
      - kanban.updated (any kanban event for boards this session touches)
      - budget.tick (per-round budget snapshot)
      - cost.tick (per-LLM-call cost)
      - session.forked
      - session.failed
      - session.completed

    Implementation: polls the stream_events table every 500ms for
    new rows since the last cursor. Yields each row as an SSE event.
    Stops on client disconnect (the generator's natural close).
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    db = get_db(request)

    # Confirm the session exists
    row = await db.fetchrow("SELECT id FROM sessions WHERE id = $1", session_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    last_id = 0
    start_time = asyncio.get_event_loop().time()

    async def event_generator():
        nonlocal last_id
        # Initial cursor: pick up from the LATEST event so we don't
        # replay the whole history. The first poll returns "no new
        # events" if the session has already produced events before
        # the watcher started.
        try:
            cur = await db.fetchrow(
                "SELECT COALESCE(MAX(id), 0) AS max_id FROM stream_events WHERE session_id = $1",
                session_id,
            )
            last_id = int(cur["max_id"] or 0)
        except Exception:
            last_id = 0

        # Send a hello event so the client knows the stream is live
        yield _sse_pack("shadow.ready", {
            "session_id": session_id,
            "cursor": last_id,
        })

        while True:
            try:
                # Hard cap: 6 hours of shadowing per request (matches
                # the orchestrator's max-run budget). After that, the
                # dashboard should reconnect.
                if (asyncio.get_event_loop().time() - start_time) > 6 * 3600:
                    yield _sse_pack("shadow.ended", {"reason": "max_duration"})
                    return
                rows = await db.fetch(
                    "SELECT id, event_type, event_data, created_at FROM stream_events "
                    "WHERE session_id = $1 AND id > $2 "
                    "ORDER BY id ASC LIMIT 50",
                    session_id, last_id,
                )
                if rows:
                    for r in rows:
                        last_id = max(last_id, int(r["id"]))
                        ed = r["event_data"]
                        if isinstance(ed, str):
                            try:
                                ed = json.loads(ed)
                            except (json.JSONDecodeError, TypeError):
                                ed = {}
                        yield _sse_pack(r["event_type"], {
                            "id": r["id"],
                            "ts": r["created_at"].isoformat() if r.get("created_at") else None,
                            "data": ed or {},
                        })
                else:
                    # Heartbeat: tell the client we're alive, even
                    # if no new events. SSE comment lines keep the
                    # connection warm.
                    yield ": hb\n\n"
            except asyncio.CancelledError:
                return
            except Exception as exc:
                yield _sse_pack("shadow.error", {"error": str(exc)[:200]})
                # Don't tight-loop on persistent errors
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse_pack(event_type: str, data: dict) -> str:
    """Format one SSE event. Standard format: `event: <type>\\ndata: <json>\\n\\n`."""
    import json as _json
    return f"event: {event_type}\ndata: {_json.dumps(data, default=str)}\n\n"
