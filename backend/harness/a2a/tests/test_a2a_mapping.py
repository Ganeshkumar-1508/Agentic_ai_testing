"""Tests for `harness.a2a.mapping` — JobSpec ↔ Message, JobOutput → Artifact."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from harness.a2a.mapping import (
    artifact_from_output,
    job_record_to_task,
    message_to_job_spec,
    request_to_message,
)
from harness.a2a.types import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    TaskState,
    TextPart,
)


# ---------------------------------------------------------------------------
# message_to_job_spec
# ---------------------------------------------------------------------------


class TestMessageToJobSpec:
    def test_text_only_message(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[TextPart(text="Write tests for the auth module")],
        )
        spec = message_to_job_spec(msg)
        assert spec["prompt"] == "Write tests for the auth module"
        assert spec["repo_url"] == ""
        assert spec["source"] == "a2a"
        assert spec["tier"] == 1
        # Default capabilities include test-runner operations.
        assert "write_test_files" in spec["capabilities"]

    def test_multiple_text_parts_concatenated(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[
                TextPart(text="Add Jest tests for "),
                TextPart(text="the auth module."),
            ],
        )
        spec = message_to_job_spec(msg)
        # Two text parts joined with a blank line.
        assert "Add Jest tests" in spec["prompt"]
        assert "the auth module." in spec["prompt"]
        assert "\n\n" in spec["prompt"]

    def test_url_part_becomes_repo_url(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[
                TextPart(text="Add tests for "),
                FilePart(url="https://github.com/acme/api"),
            ],
        )
        spec = message_to_job_spec(msg)
        assert spec["repo_url"] == "https://github.com/acme/api"

    def test_data_part_becomes_context(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[
                TextPart(text="Run tests"),
                DataPart(data={"browser": "chrome", "os": "linux"}),
            ],
        )
        spec = message_to_job_spec(msg)
        assert spec["context"]["browser"] == "chrome"
        assert spec["context"]["os"] == "linux"

    def test_data_part_with_metadata_title_nests(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[
                TextPart(text="Run"),
                DataPart(
                    data={"pre_commands": ["npm install"]},
                    metadata={"title": "test_config"},
                ),
            ],
        )
        spec = message_to_job_spec(msg)
        # Title-prefixed: the part nests under context[title].
        assert spec["context"]["test_config"] == {"pre_commands": ["npm install"]}

    def test_raw_file_part_raises(self):
        # C05 doesn't support inline file bytes — the design
        # doc explicitly defers file ingestion.
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[FilePart(raw="base64data", filename="x.png")],
        )
        with pytest.raises(ValueError, match="raw"):
            message_to_job_spec(msg)

    def test_message_metadata_overrides_tier(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[TextPart(text="supervised review")],
            metadata={"tier": 2, "capabilities": ["read_code", "run_tests"]},
        )
        spec = message_to_job_spec(msg)
        assert spec["tier"] == 2
        assert spec["capabilities"] == ["read_code", "run_tests"]

    def test_context_id_becomes_session_id(self):
        msg = Message(
            role="user",
            messageId="m-1",
            parts=[TextPart(text="do work")],
            contextId="ctx-abc",
        )
        spec = message_to_job_spec(msg)
        assert spec["context"]["session_id"] == "ctx-abc"


# ---------------------------------------------------------------------------
# job_record_to_task
# ---------------------------------------------------------------------------


def _make_record(**overrides) -> dict:
    """Build a minimal JobSpecRecord dict for tests."""
    base = {
        "spec_id": "spec-123",
        "run_id": "run-456",
        "source": "a2a",
        "prompt": "Add tests",
        "repo_url": "https://github.com/acme/api",
        "branch": "main",
        "sha": "",
        "tier": 1,
        "capabilities": [],
        "approval": {},
        "context": {"session_id": "ctx-abc"},
        "status": "running",
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


class TestJobRecordToTask:
    def test_basic_conversion(self):
        rec = _make_record(status="running")
        task = job_record_to_task(rec)
        assert task.id == "spec-123"
        assert task.contextId == "ctx-abc"
        assert task.status.state == "TASK_STATE_WORKING"

    def test_completed_status(self):
        rec = _make_record(status="completed")
        task = job_record_to_task(rec)
        assert task.status.state == "TASK_STATE_COMPLETED"

    def test_paused_status_maps_to_input_required(self):
        rec = _make_record(status="paused")
        task = job_record_to_task(rec)
        assert task.status.state == TaskState.INPUT_REQUIRED

    def test_with_artifacts_attached(self):
        rec = _make_record(status="completed")
        arts = [
            Artifact(
                artifactId="a-1",
                name="summary",
                parts=[TextPart(text="done")],
            )
        ]
        task = job_record_to_task(rec, artifacts=arts)
        assert len(task.artifacts) == 1
        assert task.artifacts[0].name == "summary"

    def test_context_id_falls_back_to_spec_id(self):
        rec = _make_record(context={})
        task = job_record_to_task(rec)
        assert task.contextId == "spec-123"

    def test_metadata_carries_run_id_and_tier(self):
        rec = _make_record(tier=2)
        task = job_record_to_task(rec)
        assert task.metadata["run_id"] == "run-456"
        assert task.metadata["tier"] == 2


# ---------------------------------------------------------------------------
# artifact_from_output
# ---------------------------------------------------------------------------


class TestArtifactFromOutput:
    def test_empty_output_no_artifacts(self):
        assert artifact_from_output(None) == []

    def test_summary_only(self):
        out = {"spec_id": "s1", "summary": "Wrote 3 tests", "artifacts": []}
        arts = artifact_from_output(out)
        assert len(arts) == 1
        assert arts[0].name == "summary"
        assert arts[0].parts[0].text == "Wrote 3 tests"

    def test_pr_only(self):
        out = {
            "spec_id": "s1",
            "summary": "Opened a PR",
            "pr_url": "https://github.com/acme/api/pull/42",
            "artifacts": [],
        }
        arts = artifact_from_output(out)
        # summary + pr = 2 artifacts
        assert len(arts) == 2
        names = {a.name for a in arts}
        assert "pull_request" in names
        assert "summary" in names

    def test_test_files_artifact(self):
        out = {
            "spec_id": "s1",
            "summary": "done",
            "artifacts": [
                {"path": "tests/auth.test.ts"},
                {"path": "tests/jwt.test.ts"},
            ],
        }
        arts = artifact_from_output(out)
        names = {a.name for a in arts}
        assert "test_files" in names
        # Find the test_files artifact and verify parts.
        test_art = next(a for a in arts if a.name == "test_files")
        # One text part (the path list) + one data part (count+paths).
        assert len(test_art.parts) == 2
        assert "tests/auth.test.ts" in test_art.parts[0].text

    def test_all_three_kinds(self):
        out = {
            "spec_id": "s1",
            "summary": "Wrote 3 tests and opened a PR",
            "pr_url": "https://github.com/x/y/pull/1",
            "artifacts": [{"path": "tests/x.test.ts"}],
        }
        arts = artifact_from_output(out)
        names = {a.name for a in arts}
        assert {"test_files", "pull_request", "summary"} <= names

    def test_other_artifacts_artifact(self):
        # Non-path artifacts (no `path` key) are grouped into
        # `other_artifacts`.
        out = {
            "spec_id": "s1",
            "summary": "done",
            "artifacts": [{"kind": "metric", "value": 42}],
        }
        arts = artifact_from_output(out)
        names = {a.name for a in arts}
        assert "other_artifacts" in names


# ---------------------------------------------------------------------------
# request_to_message
# ---------------------------------------------------------------------------


class TestRequestToMessage:
    def test_valid_request(self):
        req = {
            "params": {
                "message": {
                    "role": "user",
                    "messageId": "m-1",
                    "parts": [{"text": "hello"}],
                }
            }
        }
        msg = request_to_message(req)
        assert msg.messageId == "m-1"
        assert msg.parts[0].text == "hello"

    def test_missing_message_raises(self):
        with pytest.raises(ValueError, match="params.message"):
            request_to_message({"params": {}})
        with pytest.raises(ValueError, match="params.message"):
            request_to_message({})
