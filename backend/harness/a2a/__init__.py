"""A2A Protocol v1.0 — TestAI's A2A Server.

Exposes the TestAI orchestrator over the A2A (Agent2Agent) wire protocol
so any A2A-compatible client can submit jobs, stream events, poll
status, and cancel runs without knowing TestAI's HTTP API.

Layout:
  - `types`     — Pydantic models for the A2A v1.0 wire format
  - `mapping`   — pure functions: JobSpecRecord ↔ Message, JobOutput → Artifact
  - `stream`    — SSE bridge: EventSourceSink → A2A `SendStreamingMessage` events
  - `server`    — FastAPI router (Agent Card + JSON-RPC methods)

Spec: https://a2a-protocol.org/latest/
Design: `docs/2026-06-21-c05-design.md`.

C05 is a **thin shim** over the C08 surface (`POST /api/jobs` +
`/api/jobs/{id}` + `/api/jobs/{id}/cancel` + `EventSourceSink.subscribe`).
No new persistence, no new orchestrator paths — the same `submit_job_to_orchestrator`
seam the chat uses is the seam the A2A server uses.
"""
from .types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Artifact,
    JSONRPCError,
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    job_status_to_a2a_state,
)
from .mapping import (
    artifact_from_output,
    job_record_to_task,
    message_to_job_spec,
    request_to_message,
)
from .stream import a2a_stream_from_session

__all__ = [
    # types
    "AgentCard",
    "AgentCapabilities",
    "AgentSkill",
    "Artifact",
    "JSONRPCError",
    "JSONRPCErrorCode",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "Message",
    "Part",
    "Task",
    "TaskArtifactUpdateEvent",
    "TaskState",
    "TaskStatus",
    "TaskStatusUpdateEvent",
    "job_status_to_a2a_state",
    # mapping
    "artifact_from_output",
    "job_record_to_task",
    "message_to_job_spec",
    "request_to_message",
    # stream
    "a2a_stream_from_session",
]
