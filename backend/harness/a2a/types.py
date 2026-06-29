"""A2A Protocol v1.0 — wire types.

Pure Pydantic models. No I/O, no FastAPI imports. Used by the
server router and the mapping layer.

Reference: https://a2a-protocol.org/latest/specification/
"""
from __future__ import annotations

import json
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Task lifecycle (A2A v1.0 §task-states)
# ---------------------------------------------------------------------------


class TaskState:
    """A2A v1.0 `TaskState` enum values.

    The A2A spec uses string constants like ``"TASK_STATE_WORKING"``;
    we expose them as plain class attributes so call sites can
    reference them like ``TaskState.WORKING`` without pulling in
    an enum (avoids the "str enum" gymnastics in Pydantic v2).
    """

    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"
    COMPLETED = "TASK_STATE_COMPLETED"
    CANCELED = "TASK_STATE_CANCELED"  # spec: 1 L
    FAILED = "TASK_STATE_FAILED"
    REJECTED = "TASK_STATE_REJECTED"
    # Hybrid-agent-only:
    WORKING_COMPLETED = "TASK_STATE_WORKING_COMPLETED"


#: TestAI `JobStatus` → A2A `TaskState`. The "paused → input-required"
#: mapping is the only lossy one — TestAI has no concept of
#: input-required, but `paused` is operationally identical
#: (the agent is waiting on the user). See
#: `docs/2026-06-21-c05-design.md` for rationale.
JOB_STATUS_TO_A2A_STATE: dict[str, str] = {
    "pending":   TaskState.SUBMITTED,
    "queued":    TaskState.SUBMITTED,
    "submitted": TaskState.SUBMITTED,
    "running":   TaskState.WORKING,
    "completed": TaskState.COMPLETED,
    "failed":    TaskState.FAILED,
    "cancelled": TaskState.CANCELED,
    "paused":    TaskState.INPUT_REQUIRED,
}


def job_status_to_a2a_state(status: str) -> str:
    """Map a TestAI `JobStatus` string to an A2A `TaskState` constant.

    Unknown statuses default to ``TASK_STATE_SUBMITTED`` (the
    safest "not yet complete" assumption).
    """
    return JOB_STATUS_TO_A2A_STATE.get(status, TaskState.SUBMITTED)


# ---------------------------------------------------------------------------
# Part — flexible content container (A2A v1.0 §parts)
# ---------------------------------------------------------------------------


# The A2A spec uses a Protobuf-style `oneof` for Parts: exactly
# one of `text` / `raw` / `url` / `data` is set. Pydantic v2's
# discriminated union requires a `kind` discriminator in the
# input — but real A2A clients follow the spec and send
# `{"text": "..."}` with no discriminator. We use a smart union
# (Pydantic v2's default for Union[BaseModel, ...]) so the
# dispatcher infers the variant from which field is set.
#
# `kind` is included on each variant as an optional field so
# the serialized form is unambiguous (some clients do send a
# discriminator). The field is ignored on input by the smart
# union — it relies on the content field instead.


class TextPart(BaseModel):
    """A2A `TextPart` — a plain text payload."""
    model_config = ConfigDict(extra="ignore")

    kind: Literal["text"] | None = "text"
    text: str
    mediaType: str = "text/plain"
    metadata: dict[str, Any] | None = None


class DataPart(BaseModel):
    """A2A `DataPart` — a structured JSON value."""
    model_config = ConfigDict(extra="ignore")

    kind: Literal["data"] | None = "data"
    data: dict[str, Any]
    mediaType: str = "application/json"
    metadata: dict[str, Any] | None = None


class FilePart(BaseModel):
    """A2A `FilePart` — a file reference (URL or inline bytes).

    C05 only supports ``url`` — inline ``raw`` bytes return an
    error from the server (no file ingestion path). See
    `docs/2026-06-21-c05-design.md` §what-c05-is-not.
    """
    model_config = ConfigDict(extra="ignore")

    kind: Literal["file"] | None = "file"
    url: str | None = None
    raw: str | None = None  # base64-encoded bytes (C05: ignored)
    mediaType: str = "application/octet-stream"
    filename: str | None = None
    metadata: dict[str, Any] | None = None


# Smart union — Pydantic v2 dispatches based on which field is
# set (`text` → TextPart, `data` → DataPart, `url` or `raw` →
# FilePart). This matches the A2A spec's `oneof` semantic
# exactly and is forgiving of clients that do/don't include
# the `kind` discriminator.
Part = Union[TextPart, DataPart, FilePart]


# ---------------------------------------------------------------------------
# Message — a single turn of communication (A2A v1.0 §messages)
# ---------------------------------------------------------------------------


Role = Literal["user", "agent"]


class Message(BaseModel):
    """A2A `Message` — a single turn of communication.

    A `Message` has a `role` (the speaker), a `messageId`, optional
    `contextId` / `referenceTaskIds` for multi-turn context, and
    one or more `Part` objects carrying the actual content.
    """
    model_config = ConfigDict(extra="forbid")

    role: Role
    messageId: str
    parts: list[Part] = Field(default_factory=list)
    contextId: str | None = None
    referenceTaskIds: list[str] | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Task / Status / Artifact (A2A v1.0 §task)
# ---------------------------------------------------------------------------


class TaskStatus(BaseModel):
    """A2A `TaskStatus` — the current state of a Task."""
    model_config = ConfigDict(extra="forbid")

    state: str
    message: str | None = None
    # The spec allows a server-defined timestamp; we use ISO 8601.
    timestamp: str | None = None


class Artifact(BaseModel):
    """A2A `Artifact` — tangible output produced by a Task.

    Has a unique `artifactId`, a human-readable `name`, optional
    `description`, and one or more `Part` objects.
    """
    model_config = ConfigDict(extra="forbid")

    artifactId: str
    name: str
    description: str | None = None
    parts: list[Part] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class Task(BaseModel):
    """A2A `Task` — a stateful unit of work.

    Has a unique `id`, a `contextId` (groups related tasks),
    the current `status`, the `history` of messages exchanged
    (we don't keep history in C05 — the SSE stream is the
    history), and any `artifacts` produced.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    contextId: str
    status: TaskStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    history: list[Message] | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Streaming-event envelopes (A2A v1.0 §streaming)
# ---------------------------------------------------------------------------


class TaskStatusUpdateEvent(BaseModel):
    """A2A `TaskStatusUpdateEvent` — emitted on the SSE stream when
    a Task's state changes."""
    model_config = ConfigDict(extra="forbid")

    taskId: str
    contextId: str
    status: TaskStatus
    final: bool = False
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(BaseModel):
    """A2A `TaskArtifactUpdateEvent` — emitted on the SSE stream when
    an Artifact is appended or updated."""
    model_config = ConfigDict(extra="forbid")

    taskId: str
    contextId: str
    artifact: Artifact
    final: bool = False
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope (A2A v1.0 §transport)
# ---------------------------------------------------------------------------


class JSONRPCError(BaseModel):
    """A2A / JSON-RPC 2.0 error payload."""
    model_config = ConfigDict(extra="forbid")

    code: int
    message: str
    data: Any | None = None


class JSONRPCErrorCode:
    """JSON-RPC 2.0 standard error codes + A2A-specific extensions.

    See: https://www.jsonrpc.org/specification#error_object
    A2A-specific codes are in the -32000 to -32099 range.
    """
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # A2A-specific (server-defined, in -32000 to -32099)
    TASK_NOT_FOUND = -32001
    TASK_NOT_CANCELABLE = -32002
    UNSUPPORTED_OPERATION = -32003


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request envelope."""
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response envelope.

    Either `result` is present (success) or `error` is present
    (failure) — never both. The A2A spec wraps the
    `SendStreamingMessage` result inside the standard JSON-RPC
    `result` field, even for SSE frames.
    """
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JSONRPCError | None = None

    def to_sse_data(self) -> str:
        """Render the response as an SSE `data:` line value.

        Excludes the `None` fields so the on-wire JSON is clean.
        """
        payload: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            payload["error"] = self.error.model_dump(exclude_none=True)
        else:
            payload["result"] = self.result
        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Agent Card (A2A v1.0 §agent-card)
# ---------------------------------------------------------------------------


class AgentCapabilities(BaseModel):
    """A2A `AgentCapabilities` — what optional features the server supports."""
    model_config = ConfigDict(extra="forbid")

    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentSkill(BaseModel):
    """A2A `AgentSkill` — a single named capability the agent offers."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    inputModes: list[str] = Field(default_factory=lambda: ["text"])
    outputModes: list[str] = Field(default_factory=lambda: ["text"])
    examples: list[str] | None = None
    tags: list[str] | None = None


class AgentAuthentication(BaseModel):
    """A2A `AgentAuthentication` — auth schemes the agent requires.

    The A2A spec defers to standard web security; we use bearer JWT.
    """
    model_config = ConfigDict(extra="forbid")

    schemes: list[str]
    # Optional: credentials field for non-bearer schemes. We omit
    # (bearer is implicit from the schemes list).
    credentials: str | None = None


class AgentCard(BaseModel):
    """A2A `AgentCard` — the server's self-description.

    Served at `GET /.well-known/agent.json`. A2A clients fetch
    this to discover the server's URL, version, skills, and
    required authentication.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    url: str
    version: str
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    defaultInputModes: list[str] = Field(default_factory=lambda: ["text"])
    defaultOutputModes: list[str] = Field(default_factory=lambda: ["text"])
    skills: list[AgentSkill] = Field(default_factory=list)
    authentication: AgentAuthentication | None = None
    # The A2A spec also allows provider, documentationUrl, iconUrl,
    # etc. We omit them — they're optional and the Agent Card stays
    # focused on what a client needs to call us.
    metadata: dict[str, Any] | None = None


__all__ = [
    "AgentCapabilities",
    "AgentCard",
    "AgentSkill",
    "AgentAuthentication",
    "Artifact",
    "DataPart",
    "FilePart",
    "JOB_STATUS_TO_A2A_STATE",
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
    "TextPart",
    "job_status_to_a2a_state",
]
