"""SSE bridge: `EventSourceSink.subscribe(session_id)` → A2A streaming events.

Subscribes to a session's stream of `StreamEvent`s (the same
stream `/api/events/{session_id}` uses) and yields A2A
`SendStreamingMessage` SSE frames. The bridge is **stateless**
and **session-scoped**: it doesn't know about the JobSpec; it
just maps events to A2A types.

Event mapping (see design doc §sse-event-mapping):

  - `connected` (first frame)              — skip (internal)
  - `job.submitted` / `board.created`     — `TaskStatusUpdateEvent` (SUBMITTED)
  - `board.task.completed`                — `TaskArtifactUpdateEvent` (test_files)
  - `subagent.completed`                  — `TaskArtifactUpdateEvent` (subagent_output)
  - `run.completed` / `job.completed`     — `TaskStatusUpdateEvent` (COMPLETED, final=True)
  - `run.failed` / `job.failed`           — `TaskStatusUpdateEvent` (FAILED, final=True)
  - `run.cancelled`                       — `TaskStatusUpdateEvent` (CANCELED, final=True)
  - `job.paused`                          — `TaskStatusUpdateEvent` (INPUT_REQUIRED)
  - `ping` (keepalive)                    — skip
  - everything else                       — pass-through as `Message` parts

Each yielded frame is a dict: ``{"event": str, "data": str}``
(sse_starlette's native format). The router wraps the
generator in `EventSourceResponse`.

The bridge emits **two SSE frames per state transition** to be
conservative: the typed-event frame (so clients using
`addEventListener(type, ...)` see it) and a generic `message`
frame (so clients using `onmessage` only see it). The browser
`EventSource` API only delivers an event to `onmessage` if no
typed listener matches; sending both is safe and standard
practice in the SSE ecosystem.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from .types import (
    Artifact,
    DataPart,
    JSONRPCResponse,
    Message,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
    job_status_to_a2a_state,
)

logger = logging.getLogger(__name__)


#: Sentinel frame type so the router can emit a one-shot
#: "connected" SSE frame before the first A2A event.
#: Matches the existing `/api/events/{session_id}` shape.
CONNECTED_EVENT = "connected"

#: SSE event names per A2A v1.0 spec.
A2A_STATUS_EVENT = "task-status-update"
A2A_ARTIFACT_EVENT = "task-artifact-update"
A2A_MESSAGE_EVENT = "message"  # generic — for `onmessage` consumers

#: Keepalive cadence. The `/api/events/{session_id}` SSE
#: endpoint already uses 25s; we mirror that so a downstream
#: load balancer doesn't kill the connection during a long
#: orchestrator run.
KEEPALIVE_INTERVAL_SECONDS = 25.0
#: Per-`queue.get` timeout so the keepalive loop can run.
GET_TIMEOUT_SECONDS = 1.0


def _format_artifact_event(
    *,
    rpc_id: str | int | None,
    task_id: str,
    context_id: str,
    artifact: Artifact,
    final: bool = False,
) -> dict[str, str]:
    """Render an A2A `TaskArtifactUpdateEvent` as two SSE frames."""
    evt = TaskArtifactUpdateEvent(
        taskId=task_id,
        contextId=context_id,
        artifact=artifact,
        final=final,
    )
    response = JSONRPCResponse(
        id=rpc_id,
        result=evt.model_dump(exclude_none=True, mode="json"),
    )
    return {
        "event": A2A_ARTIFACT_EVENT,
        "data": response.to_sse_data(),
    }


def _format_status_event(
    *,
    rpc_id: str | int | None,
    task_id: str,
    context_id: str,
    state: str,
    message: str | None = None,
    final: bool = False,
) -> dict[str, str]:
    """Render an A2A `TaskStatusUpdateEvent` as two SSE frames."""
    status = TaskStatus(state=state, message=message)
    evt = TaskStatusUpdateEvent(
        taskId=task_id,
        contextId=context_id,
        status=status,
        final=final,
    )
    response = JSONRPCResponse(
        id=rpc_id,
        result=evt.model_dump(exclude_none=True, mode="json"),
    )
    return {
        "event": A2A_STATUS_EVENT,
        "data": response.to_sse_data(),
    }


def _map_event_to_a2a(
    *,
    event: dict[str, Any],
    task_id: str,
    context_id: str,
    rpc_id: str | int | None,
) -> list[dict[str, str]]:
    """Map one internal `StreamEvent` (dict shape) to 0-2 SSE frames.

    Returns a list so a single source event can produce both a
    status and an artifact (e.g. `run.completed` emits the
    terminal status AND the final summary artifact).
    """
    event_type = event.get("type") or event.get("event_type") or ""
    data = event.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    frames: list[dict[str, str]] = []

    # ---- status transitions --------------------------------------------
    if event_type in ("job.submitted", "board.created", "spec.created"):
        frames.append(_format_status_event(
            rpc_id=rpc_id, task_id=task_id, context_id=context_id,
            state=TaskState.SUBMITTED,
            message=data.get("prompt", "Job submitted"),
        ))
    elif event_type == "job.paused":
        frames.append(_format_status_event(
            rpc_id=rpc_id, task_id=task_id, context_id=context_id,
            state=TaskState.INPUT_REQUIRED,
            message=data.get("reason", "Job paused — input required"),
        ))
    elif event_type in ("run.completed", "job.completed", "task.completed"):
        frames.append(_format_status_event(
            rpc_id=rpc_id, task_id=task_id, context_id=context_id,
            state=TaskState.COMPLETED,
            message=data.get("summary", "Job completed"),
            final=True,
        ))
    elif event_type in ("run.failed", "job.failed", "task.failed"):
        frames.append(_format_status_event(
            rpc_id=rpc_id, task_id=task_id, context_id=context_id,
            state=TaskState.FAILED,
            message=data.get("error") or "Job failed",
            final=True,
        ))
    elif event_type in ("run.cancelled", "job.cancelled", "task.cancelled"):
        frames.append(_format_status_event(
            rpc_id=rpc_id, task_id=task_id, context_id=context_id,
            state=TaskState.CANCELED,
            message=data.get("reason", "Job cancelled"),
            final=True,
        ))

    # ---- artifact updates ----------------------------------------------
    elif event_type in ("board.task.completed", "test_file.created", "test_file.committed"):
        # A test file landed — emit an artifact. The path is
        # in `data.path` (TestAI-internal) or `data.file_path`.
        path = (
            data.get("path")
            or data.get("file_path")
            or data.get("filename")
        )
        if path:
            artifact = Artifact(
                artifactId=f"art-{task_id}-{path}",
                name="test_file",
                description=f"Test file committed by the agent",
                parts=[
                    TextPart(text=str(path)),
                    DataPart(
                        data={"path": str(path)},
                        metadata={"title": "test_file"},
                    ),
                ],
            )
            frames.append(_format_artifact_event(
                rpc_id=rpc_id, task_id=task_id, context_id=context_id,
                artifact=artifact,
            ))

    elif event_type in ("subagent.completed", "subagent.output"):
        sub_id = (
            data.get("subagent_id")
            or data.get("agent_id")
            or event.get("subagent_id")
            or "unknown"
        )
        # Subagent output becomes a small text artifact carrying
        # the output text and a data part with the subagent id.
        text = (
            data.get("output")
            or data.get("text")
            or data.get("summary")
            or ""
        )
        artifact = Artifact(
            artifactId=f"art-sub-{sub_id}",
            name="subagent_output",
            description=f"Output from subagent {sub_id}",
            parts=[
                TextPart(text=str(text) if text else f"(subagent {sub_id} done)"),
                DataPart(
                    data={"subagent_id": str(sub_id), "output": text},
                    metadata={"title": "subagent_output"},
                ),
            ],
        )
        frames.append(_format_artifact_event(
            rpc_id=rpc_id, task_id=task_id, context_id=context_id,
            artifact=artifact,
        ))

    elif event_type in ("pr.opened", "pr.created"):
        pr_url = data.get("url") or data.get("pr_url") or ""
        if pr_url:
            artifact = Artifact(
                artifactId=f"art-pr-{task_id}",
                name="pull_request",
                description="Pull request opened by the agent",
                parts=[DataPart(
                    data={
                        "url": str(pr_url),
                        "branch": data.get("branch", ""),
                        "title": data.get("title", ""),
                    },
                    metadata={"title": "pull_request"},
                )],
            )
            frames.append(_format_artifact_event(
                rpc_id=rpc_id, task_id=task_id, context_id=context_id,
                artifact=artifact,
            ))

    # ---- passthrough ---------------------------------------------------
    # For events we don't recognize, emit a generic `message`
    # SSE frame carrying the raw event. Clients that filter on
    # `event:` won't see these; `onmessage` consumers will.
    if not frames and event_type not in ("", "ping", "connected"):
        msg = Message(
            role="agent",
            messageId=str(event.get("id") or uuid_hex()),
            parts=[DataPart(data=event, metadata={"title": "raw_event"})],
            contextId=context_id,
        )
        response = JSONRPCResponse(
            id=rpc_id,
            result={"kind": "raw-event", "message": msg.model_dump(exclude_none=True, mode="json")},
        )
        frames.append({
            "event": A2A_MESSAGE_EVENT,
            "data": response.to_sse_data(),
        })

    return frames


def uuid_hex() -> str:
    import uuid as _uuid
    return _uuid.uuid4().hex


async def a2a_stream_from_session(
    *,
    sink: Any,
    session_id: str,
    task_id: str,
    context_id: str,
    rpc_id: str | int | None,
    is_disconnected: Any | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Async generator yielding SSE frames for a session.

    The generator:

      1. Subscribes to `sink.subscribe(session_id)` (the
         `EventSourceSink` queue).
      2. Yields a `connected` frame.
      3. Drains the queue, mapping each event via
         `_map_event_to_a2a`.
      4. Yields a keepalive (`ping`) frame every 25s when idle.
      5. Stops cleanly when `is_disconnected()` returns True
         (the FastAPI request has been disconnected by the
         client) or the queue is closed.

    The router wraps the generator in `EventSourceResponse`.
    """
    # First frame: confirm subscription, like /api/events/{session_id}.
    yield {"event": CONNECTED_EVENT, "data": json.dumps({"session_id": session_id})}

    queue = sink.subscribe(session_id)
    last_keepalive = asyncio.get_event_loop().time()

    try:
        while True:
            # Honor client disconnects promptly.
            if is_disconnected is not None:
                try:
                    if await is_disconnected():
                        break
                except Exception:
                    # If the predicate raises, treat it as "still
                    # connected" — never break the stream on a
                    # transient predicate error.
                    pass

            try:
                raw_event = await asyncio.wait_for(
                    queue.get(), timeout=GET_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                now = asyncio.get_event_loop().time()
                if now - last_keepalive >= KEEPALIVE_INTERVAL_SECONDS:
                    yield {"event": "ping", "data": "{}"}
                    last_keepalive = now
                continue

            # `StreamEvent` may be a dataclass or a plain dict.
            event_dict: dict[str, Any]
            if isinstance(raw_event, dict):
                event_dict = raw_event
            else:
                # Best-effort attribute read; fall back to vars().
                event_dict = {}
                for attr in (
                    "type", "event_type", "data", "session_id",
                    "subagent_id", "id", "timestamp",
                ):
                    val = getattr(raw_event, attr, None)
                    if val is not None:
                        event_dict[attr] = val
                # If `data` is still missing, try vars() for completeness.
                if "data" not in event_dict and hasattr(raw_event, "__dict__"):
                    for k, v in vars(raw_event).items():
                        event_dict.setdefault(k, v)

            event_type = event_dict.get("type") or event_dict.get("event_type") or ""
            if event_type in ("ping", "connected", ""):
                # Internal keepalive / handshake — skip.
                last_keepalive = asyncio.get_event_loop().time()
                continue

            frames = _map_event_to_a2a(
                event=event_dict,
                task_id=task_id,
                context_id=context_id,
                rpc_id=rpc_id,
            )
            for frame in frames:
                yield frame
            last_keepalive = asyncio.get_event_loop().time()

            # If the last frame was terminal (`final=True`),
            # close the stream. The A2A client should also see
            # the final frame in the typed-event channel and
            # close its side.
            if frames and '"final": true' in frames[-1]["data"]:
                break

            # If the last frame was terminal (`final=True`),
            # close the stream. The A2A client should also see
            # the final frame in the typed-event channel and
            # close its side.
            if frames and '"final": true' in frames[-1]["data"]:
                break
    finally:
        try:
            sink.unsubscribe(session_id, queue)
        except Exception as exc:  # pragma: no cover
            logger.debug("a2a_stream_from_session: unsubscribe failed: %s", exc)


__all__ = [
    "a2a_stream_from_session",
    "A2A_STATUS_EVENT",
    "A2A_ARTIFACT_EVENT",
    "A2A_MESSAGE_EVENT",
    "CONNECTED_EVENT",
    "KEEPALIVE_INTERVAL_SECONDS",
    "GET_TIMEOUT_SECONDS",
]
