"""Tests for `harness.a2a.types` — Pydantic model round-trips and
JSON-RPC 2.0 envelope conformance.

C05 protocol conformance is enforced by these round-trips: if a
field serializes to the spec-required wire format and deserializes
back to the same shape, the model is spec-conformant.
"""
from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter

from harness.a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    DataPart,
    FilePart,
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
    TextPart,
    job_status_to_a2a_state,
)


#: `Part` is a smart Union (no `model_validate` of its own);
#: `TypeAdapter` is the Pydantic v2 way to validate against
#: a Union type.
_part_adapter = TypeAdapter(Part)


# ---------------------------------------------------------------------------
# Part discriminated union
# ---------------------------------------------------------------------------


class TestPartUnion:
    def test_text_part_round_trip(self):
        part = TextPart(text="hello world")
        dumped = part.model_dump()
        loaded = _part_adapter.validate_python(dumped)
        assert isinstance(loaded, TextPart)
        assert loaded.text == "hello world"

    def test_data_part_round_trip(self):
        part = DataPart(data={"x": 1, "y": [2, 3]})
        dumped = part.model_dump()
        loaded = _part_adapter.validate_python(dumped)
        assert isinstance(loaded, DataPart)
        assert loaded.data == {"x": 1, "y": [2, 3]}

    def test_file_part_url_round_trip(self):
        part = FilePart(url="https://example.com/x.png", filename="x.png")
        dumped = part.model_dump()
        loaded = _part_adapter.validate_python(dumped)
        assert isinstance(loaded, FilePart)
        assert loaded.url == "https://example.com/x.png"

    def test_smart_union_dispatches_by_field_shape(self):
        # Pydantic v2's smart union dispatches based on which
        # field is set. A `text` field → TextPart, a `data`
        # field → DataPart, a `url` field → FilePart. This
        # matches the A2A spec's `oneof` semantic.
        parts: list[Part] = [
            TextPart(text="a"),
            DataPart(data={"k": "v"}),
            FilePart(url="https://example.com"),
        ]
        dumped = [p.model_dump() for p in parts]
        reloaded = [_part_adapter.validate_python(d) for d in dumped]
        assert isinstance(reloaded[0], TextPart)
        assert isinstance(reloaded[1], DataPart)
        assert isinstance(reloaded[2], FilePart)

    def test_smart_union_accepts_spec_compliant_payload(self):
        # A2A spec payloads send `{"text": "..."}` with no
        # `kind` discriminator. The smart union should pick
        # the right variant from field shape alone.
        loaded = _part_adapter.validate_python({"text": "hello"})
        assert isinstance(loaded, TextPart)
        loaded = _part_adapter.validate_python({"data": {"x": 1}})
        assert isinstance(loaded, DataPart)
        loaded = _part_adapter.validate_python({"url": "https://x"})
        assert isinstance(loaded, FilePart)


# ---------------------------------------------------------------------------
# Message + Task
# ---------------------------------------------------------------------------


class TestMessageAndTask:
    def test_message_with_multiple_parts(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[TextPart(text="hello"), DataPart(data={"k": "v"})],
        )
        dumped = msg.model_dump(exclude_none=True)
        loaded = Message.model_validate(dumped)
        assert len(loaded.parts) == 2
        assert loaded.messageId == "m-1"

    def test_task_round_trip(self):
        task = Task(
            id="task-123",
            contextId="ctx-abc",
            status=TaskStatus(state=TaskState.WORKING, message="running"),
            artifacts=[
                Artifact(
                    artifactId="art-1",
                    name="summary",
                    parts=[TextPart(text="done")],
                )
            ],
        )
        dumped = task.model_dump(exclude_none=True)
        loaded = Task.model_validate(dumped)
        assert loaded.id == "task-123"
        assert loaded.status.state == "TASK_STATE_WORKING"
        assert len(loaded.artifacts) == 1
        assert loaded.artifacts[0].name == "summary"

    def test_task_status_update_event_serialization(self):
        evt = TaskStatusUpdateEvent(
            taskId="t1",
            contextId="c1",
            status=TaskStatus(state=TaskState.COMPLETED, message="done"),
            final=True,
        )
        dumped = evt.model_dump(exclude_none=True)
        assert dumped["taskId"] == "t1"
        assert dumped["status"]["state"] == "TASK_STATE_COMPLETED"
        assert dumped["final"] is True
        # Round-trip
        loaded = TaskStatusUpdateEvent.model_validate(dumped)
        assert loaded.final is True

    def test_task_artifact_update_event(self):
        evt = TaskArtifactUpdateEvent(
            taskId="t1",
            contextId="c1",
            artifact=Artifact(
                artifactId="a-1",
                name="test_files",
                parts=[DataPart(data={"count": 3})],
            ),
        )
        dumped = evt.model_dump(exclude_none=True)
        loaded = TaskArtifactUpdateEvent.model_validate(dumped)
        assert loaded.artifact.parts[0].data == {"count": 3}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------


class TestJSONRPCEnvelope:
    def test_request_round_trip(self):
        req = JSONRPCRequest(
            id="req-1",
            method="SendMessage",
            params={"message": {"role": "user", "messageId": "m", "parts": []}},
        )
        loaded = JSONRPCRequest.model_validate(req.model_dump())
        assert loaded.id == "req-1"
        assert loaded.method == "SendMessage"
        assert loaded.params["message"]["role"] == "user"

    def test_response_with_result(self):
        resp = JSONRPCResponse(id="req-1", result={"task": {"id": "t-1"}})
        sse = resp.to_sse_data()
        parsed = json.loads(sse)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "req-1"
        assert parsed["result"] == {"task": {"id": "t-1"}}
        assert "error" not in parsed

    def test_response_with_error(self):
        resp = JSONRPCResponse(
            id="req-1",
            error=JSONRPCError(
                code=JSONRPCErrorCode.METHOD_NOT_FOUND,
                message="Method 'X' not found",
            ),
        )
        sse = resp.to_sse_data()
        parsed = json.loads(sse)
        assert parsed["error"]["code"] == -32601
        assert "result" not in parsed

    def test_standard_error_codes(self):
        # Sanity check the JSON-RPC spec's reserved codes.
        assert JSONRPCErrorCode.PARSE_ERROR == -32700
        assert JSONRPCErrorCode.INVALID_REQUEST == -32600
        assert JSONRPCErrorCode.METHOD_NOT_FOUND == -32601
        assert JSONRPCErrorCode.INVALID_PARAMS == -32602
        assert JSONRPCErrorCode.INTERNAL_ERROR == -32603


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


class TestAgentCard:
    def test_agent_card_round_trip(self):
        card = AgentCard(
            name="TestAI",
            description="Test agent",
            url="https://example.com/a2a/jsonrpc",
            version="1.0.0",
            capabilities=AgentCapabilities(streaming=True),
            skills=[
                AgentSkill(
                    id="test-gen",
                    name="Generate tests",
                    description="Generates tests",
                    examples=["write tests for X"],
                )
            ],
        )
        loaded = AgentCard.model_validate(card.model_dump(exclude_none=True))
        assert loaded.name == "TestAI"
        assert loaded.capabilities.streaming is True
        assert loaded.skills[0].id == "test-gen"


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


class TestStatusMapping:
    @pytest.mark.parametrize(
        "job_status,expected_a2a",
        [
            ("pending", "TASK_STATE_SUBMITTED"),
            ("queued", "TASK_STATE_SUBMITTED"),
            ("submitted", "TASK_STATE_SUBMITTED"),
            ("running", "TASK_STATE_WORKING"),
            ("completed", "TASK_STATE_COMPLETED"),
            ("failed", "TASK_STATE_FAILED"),
            ("cancelled", "TASK_STATE_CANCELED"),
            ("paused", "TASK_STATE_INPUT_REQUIRED"),
        ],
    )
    def test_job_status_to_a2a_state(self, job_status, expected_a2a):
        assert job_status_to_a2a_state(job_status) == expected_a2a

    def test_unknown_status_defaults_to_submitted(self):
        # Unknown statuses default to SUBMITTED (the safe
        # "not yet complete" assumption per the design doc).
        assert job_status_to_a2a_state("weird") == TaskState.SUBMITTED
