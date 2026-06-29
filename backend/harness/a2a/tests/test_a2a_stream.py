"""Tests for `harness.a2a.stream` — SSE bridge from EventSourceSink.

The bridge is the A2A `SendStreamingMessage` consumer; it
maps `StreamEvent` shapes into A2A `TaskStatusUpdateEvent`
and `TaskArtifactUpdateEvent` SSE frames. These tests use
a fake sink that pre-loads a queue with synthesized events
and verifies the bridge emits the correct A2A frames.

We use ``asyncio.run`` (sync wrappers) instead of
``@pytest.mark.asyncio`` so the tests don't depend on
pytest-asyncio's mode configuration. The pattern mirrors
the other async tests in the codebase (e.g.
``tests/test_pause_signal.py``).
"""
from __future__ import annotations

import asyncio
import json

from harness.a2a.stream import (
    CONNECTED_EVENT,
    _format_artifact_event,
    _format_status_event,
    _map_event_to_a2a,
    a2a_stream_from_session,
)
from harness.a2a.types import (
    Artifact,
    DataPart,
    TextPart,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSink:
    """In-memory EventSourceSink stand-in for tests.

    Mirrors the real sink's `subscribe` / `unsubscribe` /
    `subscriber_count` shape. The test pre-populates the
    subscribed queue directly (the real sink only emits to
    current subscribers, so tests must subscribe first).

    The fake is **idempotent per session_id**: repeated
    `subscribe` calls return the same queue, so a test that
    subscribes, pre-populates, and then calls the bridge
    (which subscribes again) sees the pre-populated events.

    Subscribers are tracked as a **set of queue identities**
    (not a count) so the bridge's `unsubscribe` actually
    drops the count to 0, even if the test pre-subscribed
    with the same queue.
    """

    def __init__(self) -> None:
        self.queues: dict[str, asyncio.Queue] = {}
        self.subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
        # Idempotent: same session_id returns the same queue.
        if session_id not in self.queues:
            self.queues[session_id] = asyncio.Queue()
        self.subscribers.setdefault(session_id, set()).add(
            self.queues[session_id],
        )
        return self.queues[session_id]

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        if session_id in self.subscribers:
            self.subscribers[session_id].discard(queue)

    def subscriber_count(self, session_id: str) -> int:
        return len(self.subscribers.get(session_id, set()))


async def _collect(generator, *, max_frames: int = 50) -> list[dict[str, str]]:
    """Drain an async generator up to `max_frames` or until exhausted."""
    frames: list[dict[str, str]] = []
    async for frame in generator:
        frames.append(frame)
        if len(frames) >= max_frames:
            break
    return frames


# ---------------------------------------------------------------------------
# _map_event_to_a2a
# ---------------------------------------------------------------------------


class TestMapEventToA2A:
    def test_submitted_event_becomes_submitted_status(self):
        frames = _map_event_to_a2a(
            event={"type": "job.submitted", "data": {"prompt": "x"}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert frames[0]["event"] == "task-status-update"
        assert "TASK_STATE_SUBMITTED" in frames[0]["data"]

    def test_completed_event_becomes_completed_status_final(self):
        frames = _map_event_to_a2a(
            event={"type": "run.completed", "data": {"summary": "done"}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert '"final": true' in frames[0]["data"]
        assert "TASK_STATE_COMPLETED" in frames[0]["data"]

    def test_failed_event_becomes_failed_status(self):
        frames = _map_event_to_a2a(
            event={"type": "run.failed", "data": {"error": "boom"}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert "TASK_STATE_FAILED" in frames[0]["data"]
        assert "boom" in frames[0]["data"]
        assert '"final": true' in frames[0]["data"]

    def test_cancelled_event_becomes_canceled(self):
        frames = _map_event_to_a2a(
            event={"type": "run.cancelled", "data": {}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert "TASK_STATE_CANCELED" in frames[0]["data"]

    def test_paused_event_becomes_input_required(self):
        frames = _map_event_to_a2a(
            event={"type": "job.paused", "data": {"reason": "user"}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert "TASK_STATE_INPUT_REQUIRED" in frames[0]["data"]

    def test_test_file_event_becomes_artifact(self):
        frames = _map_event_to_a2a(
            event={"type": "test_file.committed", "data": {"path": "tests/x.test.ts"}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert frames[0]["event"] == "task-artifact-update"
        assert "tests/x.test.ts" in frames[0]["data"]
        assert '"artifactId"' in frames[0]["data"]

    def test_subagent_completed_becomes_artifact(self):
        frames = _map_event_to_a2a(
            event={
                "type": "subagent.completed",
                "data": {"subagent_id": "sub-1", "output": "wrote 3 tests"},
            },
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert frames[0]["event"] == "task-artifact-update"
        assert "sub-1" in frames[0]["data"]
        assert "wrote 3 tests" in frames[0]["data"]

    def test_pr_opened_becomes_pr_artifact(self):
        frames = _map_event_to_a2a(
            event={
                "type": "pr.opened",
                "data": {"url": "https://github.com/x/y/pull/1", "branch": "test"},
            },
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert "https://github.com/x/y/pull/1" in frames[0]["data"]
        assert "test" in frames[0]["data"]

    def test_unknown_event_becomes_raw_message_passthrough(self):
        frames = _map_event_to_a2a(
            event={"type": "custom.event", "data": {"foo": "bar"}},
            task_id="t1", context_id="c1", rpc_id="r1",
        )
        assert len(frames) == 1
        assert frames[0]["event"] == "message"
        assert "foo" in frames[0]["data"]

    def test_ping_and_connected_are_skipped(self):
        for evt_type in ("ping", "connected", ""):
            frames = _map_event_to_a2a(
                event={"type": evt_type, "data": {}},
                task_id="t1", context_id="c1", rpc_id="r1",
            )
            assert frames == []


# ---------------------------------------------------------------------------
# _format_status_event / _format_artifact_event
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    def test_status_event_is_valid_json_rpc(self):
        frame = _format_status_event(
            rpc_id="r1", task_id="t1", context_id="c1",
            state="TASK_STATE_WORKING", message="running",
        )
        assert frame["event"] == "task-status-update"
        parsed = json.loads(frame["data"])
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == "r1"
        result = parsed["result"]
        assert result["taskId"] == "t1"
        assert result["contextId"] == "c1"
        assert result["status"]["state"] == "TASK_STATE_WORKING"

    def test_artifact_event_is_valid_json_rpc(self):
        art = Artifact(
            artifactId="a-1",
            name="summary",
            parts=[TextPart(text="done")],
        )
        frame = _format_artifact_event(
            rpc_id="r1", task_id="t1", context_id="c1", artifact=art,
        )
        assert frame["event"] == "task-artifact-update"
        parsed = json.loads(frame["data"])
        assert parsed["result"]["artifact"]["name"] == "summary"


# ---------------------------------------------------------------------------
# a2a_stream_from_session — full async generator
# ---------------------------------------------------------------------------


class TestStreamFromSession:
    def test_emits_connected_then_terminal_status(self):
        async def _run():
            sink = _FakeSink()
            # Subscribe first so the pre-populated event goes
            # to the same queue the bridge will drain.
            q = sink.subscribe("s1")
            await q.put({"type": "run.completed", "data": {"summary": "done"}})
            gen = a2a_stream_from_session(
                sink=sink, session_id="s1", task_id="t1", context_id="c1", rpc_id="r1",
            )
            frames = await _collect(gen, max_frames=10)
            # First frame is the connected handshake.
            assert frames[0]["event"] == CONNECTED_EVENT
            # Second frame is the terminal status update.
            terminal = frames[1]
            assert terminal["event"] == "task-status-update"
            assert "TASK_STATE_COMPLETED" in terminal["data"]
            # No subscribers left after the stream closes.
            assert sink.subscriber_count("s1") == 0
        asyncio.run(_run())

    def test_keeps_collecting_until_terminal(self):
        async def _run():
            sink = _FakeSink()
            # Subscribe first; the bridge drains from this queue.
            q = sink.subscribe("s1")
            await q.put({"type": "job.submitted", "data": {}})
            await q.put({"type": "test_file.committed", "data": {"path": "a.test.ts"}})
            await q.put({"type": "run.completed", "data": {}})

            gen = a2a_stream_from_session(
                sink=sink, session_id="s1", task_id="t1", context_id="c1", rpc_id="r1",
            )
            frames = await _collect(gen, max_frames=20)
            # 1 connected + 3 mapped events = 4 frames.
            assert len(frames) == 4
            # First non-connected is the status update.
            assert "TASK_STATE_SUBMITTED" in frames[1]["data"]
            # Second is the artifact for the test file.
            assert frames[2]["event"] == "task-artifact-update"
            assert "a.test.ts" in frames[2]["data"]
            # Third is the terminal status.
            assert "TASK_STATE_COMPLETED" in frames[3]["data"]
            assert '"final": true' in frames[3]["data"]
        asyncio.run(_run())

    def test_unsubscribes_on_exit(self):
        async def _run():
            sink = _FakeSink()
            q = sink.subscribe("s1")
            await q.put({"type": "run.completed", "data": {}})
            gen = a2a_stream_from_session(
                sink=sink, session_id="s1", task_id="t1", context_id="c1", rpc_id="r1",
            )
            # Drain fully.
            await _collect(gen, max_frames=10)
            # Subscribers should be cleaned up in the finally block.
            assert sink.subscriber_count("s1") == 0
        asyncio.run(_run())
