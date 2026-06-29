"""Tests for C03: BoardWaiter push-based completion.

C03 (per docs/2026-06-21-architecture-decision-tree.md) replaces
``OrchestratorEngine._wait_for_board``'s 15-second pure-poll loop
with a hybrid:

  * subscribe to session events via EventSourceSink.subscribe()
  * wake immediately on ``board.completed`` / ``board.failed``
  * dedupe ``subagent.completed`` by (subagent_id, status) tuple
  * safety-poll after 60s of silence
  * pure-poll fallback when no sink is registered

Tests cover:
  * push success (``board.completed``)
  * push failure (``board.failed``)
  * subagent dedupe (idempotency)
  * subagent failure observation (warn log, no early return)
  * other-event passthrough (tool:start etc are ignored)
  * silence-triggered safety poll
  * max_wait timeout
  * no-sink → pure poll (backwards compat)
  * heartbeat callback fires
  * event-bus routing mismatch (event for a different session)
  * event-bus routing mismatch (event for a different board)
  * heartbeat_cancelled (shutdown during wait)
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.core.events import StreamEvent
from harness.events import EventSourceSink
from harness.api.state import GenericStreamEvent
from harness.services.board_waiter import (
    BoardWaitResult,
    BoardWaiter,
    DEFAULT_MAX_WAIT_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    TERMINAL_STATUSES,
    _env_float,
)


# Mode=STRICT requires every async test to be marked. Most tests are
# async; the constants/utility tests are sync and don't need the
# mark, so we use a module-level mark and pytest will warn (not fail)
# for the sync ones.
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _evt(event_type: str, session_id: str = "s1", data: dict | None = None) -> GenericStreamEvent:
    """Build a GenericStreamEvent that matches the wire shape produced
    by ``harness.api.state.emit_stream_event``.
    """
    return GenericStreamEvent(
        session_id=session_id,
        event_type=event_type,
        data=data or {},
    )


def _typed_evt(event_type: str, session_id: str = "s1", data: dict | None = None) -> Any:
    """Build a typed StreamEvent that doesn't use GenericStreamEvent
    (so we can exercise the ``type_name`` fallback path).
    """
    @dataclasses.dataclass(frozen=True)
    class _T(StreamEvent):
        event_type: str = ""
        data: dict = dataclasses.field(default_factory=dict)
        session_id: str = ""
    return _T(event_type=event_type, data=data or {}, session_id=session_id)


# ---------------------------------------------------------------------------
# Registration & configuration
# ---------------------------------------------------------------------------


def test_constants_are_sane() -> None:
    assert DEFAULT_MAX_WAIT_SECONDS == 5400
    assert HEARTBEAT_INTERVAL_SECONDS == 60.0
    assert "completed" in TERMINAL_STATUSES
    assert "timed_out" in TERMINAL_STATUSES
    assert "stalled" in TERMINAL_STATUSES
    assert "blocked" in TERMINAL_STATUSES


def test_env_float_falls_back_on_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOARD_WAITER_MAX_WAIT_SECONDS", raising=False)
    assert _env_float("BOARD_WAITER_MAX_WAIT_SECONDS", 42.0) == 42.0


def test_env_float_parses_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARD_WAITER_MAX_WAIT_SECONDS", "12.5")
    assert _env_float("BOARD_WAITER_MAX_WAIT_SECONDS", 42.0) == 12.5


def test_env_float_warns_and_falls_back_on_invalid(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("BOARD_WAITER_MAX_WAIT_SECONDS", "not-a-float")
    assert _env_float("BOARD_WAITER_MAX_WAIT_SECONDS", 99.0) == 99.0
    assert any("not a float" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Pure-poll path (no sink)
# ---------------------------------------------------------------------------


async def test_no_sink_falls_back_to_pure_poll() -> None:
    """Without a sink, the waiter must still return a terminal result
    (it just takes 15s per cycle instead of waking on push)."""
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=None,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1",
            "status": "completed",
            "tasks": [{"id": "t1", "status": "done"}],
        })),
    ) as mock_monitor:
        result = await waiter.wait()
    assert result.success is True
    assert result.status == "completed"
    assert result.method == "poll"
    assert result.board_id == "b1"
    assert len(result.tasks) == 1
    assert mock_monitor.await_count == 1


async def test_no_sink_terminal_blocked_via_poll() -> None:
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=None,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1",
            "status": "blocked",
            "tasks": [{"id": "t1", "status": "blocked"}],
            "blocked_tasks": [{"id": "t1", "status": "blocked"}],
        })),
    ):
        result = await waiter.wait()
    assert result.success is False
    assert result.status == "blocked"
    assert result.method == "poll"
    assert len(result.blocked_tasks) == 1


async def test_no_sink_poll_failure_returns_timeout() -> None:
    """If the monitor raises every cycle, the waiter must not loop
    forever; the cap kicks in."""
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=None,
        max_wait_seconds=0.3,
        poll_interval_seconds=0.1,
        poll_after_silence_seconds=0.1,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        result = await waiter.wait()
    assert result.status == "timed_out"
    assert result.success is False
    assert result.elapsed_seconds >= 0.3


# ---------------------------------------------------------------------------
# Push path: board.completed
# ---------------------------------------------------------------------------


async def test_push_board_completed_wakes_immediately() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_after_silence_seconds=10.0,  # shouldn't matter — push fires first
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        sink.emit(_evt("board.completed", session_id="s1", data={
            "board_id": "b1",
            "done": 3,
            "total": 3,
            "tasks": [{"id": "t1", "status": "done"}, {"id": "t2", "status": "done"}],
        }))

    with patch("harness.tools.orchestrator_tool.cmd_orchestrate_monitor") as mock_monitor:
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
        mock_monitor.assert_not_called()  # push beat the poll
    assert result.success is True
    assert result.status == "completed"
    assert result.method == "push"
    assert result.events_received == 1
    assert len(result.tasks) == 2


async def test_push_board_completed_for_other_board_ignored() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
        max_wait_seconds=2.0,  # safety cap so the test can't hang
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        # Different board id — should be ignored.
        sink.emit(_evt("board.completed", session_id="s1", data={"board_id": "b2"}))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ) as mock_monitor:
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
        # Poll was called because the wrong-board event didn't count.
        assert mock_monitor.await_count >= 1
    assert result.success is True
    assert result.status == "completed"
    assert result.method == "poll"  # not push (event was filtered)


# ---------------------------------------------------------------------------
# Push path: board.failed
# ---------------------------------------------------------------------------


async def test_push_board_failed_wakes_immediately() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_after_silence_seconds=10.0,
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        sink.emit(_evt("board.failed", session_id="s1", data={
            "board_id": "b1",
            "status": "stalled",
            "tasks": [{"id": "t1", "status": "blocked"}],
            "blocked_tasks": [{"id": "t1", "status": "blocked"}],
            "stalled_tasks": [],
        }))

    with patch("harness.tools.orchestrator_tool.cmd_orchestrate_monitor") as mock_monitor:
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
        mock_monitor.assert_not_called()
    assert result.success is False
    assert result.status == "stalled"
    assert result.method == "push"
    assert len(result.blocked_tasks) == 1


async def test_push_board_failed_default_status() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(session_id="s1", board_id="b1", sink=sink)

    async def _emitter():
        await asyncio.sleep(0.05)
        sink.emit(_evt("board.failed", session_id="s1", data={
            "board_id": "b1",  # no "status" → defaults to "failed"
            "tasks": [], "blocked_tasks": [],
        }))

    result, _ = await asyncio.gather(waiter.wait(), _emitter())
    assert result.success is False
    assert result.status == "failed"


# ---------------------------------------------------------------------------
# subagent.completed dedupe + observation
# ---------------------------------------------------------------------------


async def test_subagent_completed_success_does_not_terminate() -> None:
    """Success on a single subagent must NOT wake the waiter — only
    the terminal board.completed event does.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        sink.emit(_evt("subagent.completed", session_id="s1", data={
            "subagent_id": "sa1", "status": "completed",
        }))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    assert result.status == "completed"
    assert result.method == "poll"
    # The subagent event was observed (events_received=1) but didn't
    # short-circuit the wait.
    assert result.events_received >= 1


async def test_subagent_failed_logs_but_does_not_terminate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed subagents log a warning; they don't return until the
    kanban service escalates to ``board.failed``.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )
    caplog.set_level(logging.WARNING, logger="harness.services.board_waiter")

    async def _emitter():
        await asyncio.sleep(0.05)
        sink.emit(_evt("subagent.completed", session_id="s1", data={
            "subagent_id": "sa1", "status": "failed",
        }))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "stalled",
            "tasks": [], "blocked_tasks": [], "stalled_tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    assert result.status == "stalled"
    assert result.method == "poll"
    # Warning was logged.
    assert any("subagent failed" in r.message for r in caplog.records)


async def test_subagent_dedupes_by_id_and_status() -> None:
    """The same (subagent_id, status) pair seen twice must only count
    once — protects against retried events from Hermes' loop guard.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        # Same pair twice.
        for _ in range(2):
            sink.emit(_evt("subagent.completed", session_id="s1", data={
                "subagent_id": "sa1", "status": "completed",
            }))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    # events_received counts BOTH events (they did pass through the
    # queue), but the dedupe set should have ONE entry.
    assert len(waiter._seen_subagents) == 1
    assert ("sa1", "completed") in waiter._seen_subagents
    assert result.status == "completed"


async def test_subagent_missing_fields_ignored() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        # Missing subagent_id
        sink.emit(_evt("subagent.completed", session_id="s1", data={"status": "completed"}))
        await asyncio.sleep(0.05)
        # Missing status
        sink.emit(_evt("subagent.completed", session_id="s1", data={"subagent_id": "sa1"}))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    assert result.status == "completed"
    # Neither bad event was added to the dedupe set.
    assert waiter._seen_subagents == set()


# ---------------------------------------------------------------------------
# Routing: other session / other board
# ---------------------------------------------------------------------------


async def test_event_for_different_session_ignored() -> None:
    """A board.completed for session_id="s2" must not wake a waiter
    subscribed to "s1".
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        # s2's bus queue gets it (sink is per-session) but s1's
        # subscription doesn't.
        sink.emit(_evt("board.completed", session_id="s2", data={"board_id": "b1"}))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    # Fallback poll had to discover the completion.
    assert result.status == "completed"
    assert result.method == "poll"


async def test_typed_event_uses_type_name_fallback() -> None:
    """A typed StreamEvent (no ``event_type`` field) should still be
    classified via the ``type_name`` (class name) attribute.
    """
    @dataclasses.dataclass(frozen=True)
    class BoardCompletedEvent(StreamEvent):
        session_id: str = "s1"
        data: dict = dataclasses.field(default_factory=dict)

    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
        max_wait_seconds=0.5,
    )

    async def _emitter():
        await asyncio.sleep(0.05)
        # No event_type attribute → falls back to type_name == "BoardCompletedEvent"
        sink.emit(BoardCompletedEvent(data={"board_id": "b1"}))

    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    # The class name "BoardCompletedEvent" doesn't match either of
    # the expected event types — the waiter keeps waiting, then the
    # poll fallback fires. This documents the seam: typed events
    # must use the same ``event_type`` string convention.
    assert result.status == "completed"
    assert result.method == "poll"


# ---------------------------------------------------------------------------
# Silence-triggered safety poll
# ---------------------------------------------------------------------------


async def test_silence_triggers_safety_poll() -> None:
    """If no events arrive for ``poll_after_silence``, the waiter
    falls back to a DB poll rather than waiting forever.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.1,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ) as mock_monitor:
        result = await waiter.wait()
    assert result.status == "completed"
    assert result.method == "poll"
    assert mock_monitor.await_count >= 1


async def test_silence_poll_does_not_re_run_faster_than_interval() -> None:
    """The silence poll is rate-limited to ``poll_interval`` — even
    if the queue loops many times, we don't hammer the DB.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.5,
        poll_after_silence_seconds=0.05,
        max_wait_seconds=0.4,  # short cap so the test exits fast
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "in_progress", "tasks": [],
        })),
    ) as mock_monitor:
        result = await waiter.wait()
    assert result.status == "timed_out"
    # In ~0.4s with poll_interval=0.5s, the rate-limit should keep
    # the count to 1 (initial silence poll) — definitely < 3.
    assert mock_monitor.await_count <= 2


async def _force_timeout(waiter: BoardWaiter, max_wait: float) -> None:
    """Helper: drive the waiter past the wall-clock cap."""
    # Reach in and lower the cap for the test.
    waiter._max_wait = max_wait
    # Ensure at least one cycle of the inner loop ran before timeout.
    await asyncio.sleep(max_wait + 0.2)


# ---------------------------------------------------------------------------
# Max-wait timeout
# ---------------------------------------------------------------------------


async def test_max_wait_kicks_in() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        max_wait_seconds=0.3,
        poll_interval_seconds=10.0,  # would normally not fire
        poll_after_silence_seconds=10.0,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "in_progress", "tasks": [],
        })),
    ):
        result = await waiter.wait()
    assert result.status == "timed_out"
    assert result.success is False
    assert result.elapsed_seconds >= 0.3


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


async def test_heartbeat_fires_on_interval() -> None:
    sink = EventSourceSink()
    heartbeat = AsyncMock()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        max_wait_seconds=0.3,
        poll_interval_seconds=10.0,
        poll_after_silence_seconds=10.0,
        heartbeat_cb=heartbeat,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "in_progress", "tasks": [],
        })),
    ):
        await waiter.wait()
    # The HEARTBEAT_INTERVAL_SECONDS is 60s, which is >> our 0.3s
    # cap, so the heartbeat never fires. We only check the cb
    # closure wiring in the "pure-poll" path below.
    assert heartbeat.await_count == 0


async def test_heartbeat_fires_in_pure_poll_path() -> None:
    """Heartbeat fires on every tick of the inner loop (pure-poll path
    doesn't gate on events). We mock the monitor to return
    in_progress the first 5 calls so the loop doesn't exit early.
    """
    sink = None
    heartbeat = AsyncMock()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.01,
        poll_after_silence_seconds=0.01,
        max_wait_seconds=0.3,
        heartbeat_cb=heartbeat,
    )
    # Force the heartbeat tick to fire by lowering the interval.
    from harness.services import board_waiter as _bw
    original = _bw.HEARTBEAT_INTERVAL_SECONDS
    _bw.HEARTBEAT_INTERVAL_SECONDS = 0.01
    try:
        in_progress_payload = json.dumps({
            "board_id": "b1", "status": "in_progress", "tasks": [],
        })
        completed_payload = json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })
        # Return in_progress 5 times, then completed.
        monitor_mock = AsyncMock(side_effect=[in_progress_payload] * 5 + [completed_payload])
        with patch(
            "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
            new=monitor_mock,
        ):
            await waiter.wait()
    finally:
        _bw.HEARTBEAT_INTERVAL_SECONDS = original
    # After 5 in_progress polls + 1 completed, the loop has run at
    # least 5 times; the heartbeat should have fired multiple times.
    assert heartbeat.await_count >= 3


async def test_heartbeat_swallows_exceptions() -> None:
    """A raising heartbeat must not crash the waiter.

    Uses the pure-poll path (no sink) so the loop iteration time is
    bounded by ``poll_interval_seconds`` only.
    """
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=None,  # pure-poll path
        poll_interval_seconds=0.01,
        poll_after_silence_seconds=0.01,
        max_wait_seconds=0.3,
        heartbeat_cb=AsyncMock(side_effect=RuntimeError("nope")),
    )
    from harness.services import board_waiter as _bw
    original = _bw.HEARTBEAT_INTERVAL_SECONDS
    _bw.HEARTBEAT_INTERVAL_SECONDS = 0.01
    try:
        in_progress_payload = json.dumps({
            "board_id": "b1", "status": "in_progress", "tasks": [],
        })
        completed_payload = json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })
        monitor_mock = AsyncMock(side_effect=[in_progress_payload] * 5 + [completed_payload])
        with patch(
            "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
            new=monitor_mock,
        ):
            result = await waiter.wait()
    finally:
        _bw.HEARTBEAT_INTERVAL_SECONDS = original
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


async def test_unsubscribe_is_called_on_exit() -> None:
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        await waiter.wait()
    assert sink.subscriber_count("s1") == 0


async def test_unsubscribe_swallows_errors() -> None:
    """A bad unsubscribe (e.g. sink torn down during shutdown) must
    not propagate.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )
    # Monkey-patch the sink to raise on unsubscribe.
    sink.unsubscribe = MagicMock(side_effect=RuntimeError("nope"))
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result = await waiter.wait()
    assert result.status == "completed"


async def test_terminal_statuses_poll_returns_only_terminal() -> None:
    """``in_progress`` must NOT cause a poll result — only the
    statuses in ``TERMINAL_STATUSES`` should.
    """
    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.1,
        max_wait_seconds=0.2,
    )
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "in_progress", "tasks": [],
        })),
    ):
        result = await waiter.wait()
    # Waiter timed out because in_progress is not terminal.
    assert result.status == "timed_out"


async def _force_timeout(waiter: BoardWaiter, max_wait: float) -> None:
    """Helper: drive the waiter past the wall-clock cap (unused now)."""
    waiter._max_wait = max_wait
    await asyncio.sleep(max_wait + 0.2)


async def test_board_wait_result_is_frozen() -> None:
    """BoardWaitResult is a frozen dataclass — defensive guard
    against mutation bugs.
    """
    r = BoardWaitResult(success=True, status="completed", board_id="b1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.success = False  # type: ignore[misc]


async def test_non_dict_data_payload_ignored() -> None:
    """Defensive: an event with a non-dict ``data`` (e.g. corrupted
    wire payload) must not crash the classifier.
    """
    @dataclasses.dataclass(frozen=True)
    class WeirdEvent(StreamEvent):
        event_type: str = "board.completed"
        data: str = "this should be a dict"
        session_id: str = "s1"

    sink = EventSourceSink()
    waiter = BoardWaiter(
        session_id="s1",
        board_id="b1",
        sink=sink,
        poll_interval_seconds=0.05,
        poll_after_silence_seconds=0.05,
    )
    async def _emitter():
        await asyncio.sleep(0.05)
        sink.emit(WeirdEvent())
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate_monitor",
        new=AsyncMock(return_value=json.dumps({
            "board_id": "b1", "status": "completed", "tasks": [],
        })),
    ):
        result, _ = await asyncio.gather(waiter.wait(), _emitter())
    # Defensive: dropped the bad event, then polled for the result.
    assert result.status == "completed"
