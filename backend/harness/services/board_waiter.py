"""BoardWaiter — push-based completion with poll fallback.

C03 architecture decision (locked):
  Q1: Subscribed events = board.completed + board.failed + subagent.completed
  Q2: Subscription mechanism = asyncio.Event via existing EventSourceSink
  Q3: Idempotency key = (subagent_id, status) set
  Q4: Fallback timeout = poll cmd_orchestrate_monitor every 15s after 60s of silence

This replaces ``OrchestratorEngine._wait_for_board``'s 15-second pure-poll
loop with a hybrid:

  ┌─────────────────────────────────────────────────────────────┐
  │ subscribe to session events via EventSourceSink.subscribe()  │
  │ loop:                                                       │
  │   wait for event (1s timeout so heartbeat + poll can run)   │
  │   classify event → board.completed / board.failed           │
  │   on hit: return immediately (push)                         │
  │   on timeout: if (now - last_event) > 60s → poll DB once    │
  │   poll returns terminal → return (poll)                     │
  │   on heartbeat tick (60s) → call heartbeat_cb()             │
  └─────────────────────────────────────────────────────────────┘

Why hybrid: the EventBus is in-process and per-session; if the subagent
that emitted the event happened to be running in a different worker
process, the SSE queue won't see it. The 60s silence-then-poll
fallback bounds latency in that case to 60s worst-case.

Idempotency: the same subagent can report completion more than once if
it's retried (Hermes' loop-guard pattern). The waiter dedupes by
``(subagent_id, status)`` tuple.

Worst case: 5400s (90min) cap, same as the previous pure-poll loop.

Public surface (stable):
  BoardWaiter, BoardWaitResult, TERMINAL_STATUSES
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from harness.core.events import StreamEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: How long the waiter is willing to wait total. Matches the previous
#: ``_wait_for_board`` cap.
DEFAULT_MAX_WAIT_SECONDS = 5400

#: How long the waiter waits on the event queue before falling through
#: to the heartbeat / poll branch. Short enough that the heartbeat
#: fires on time, long enough to avoid spin-looping the queue.
QUEUE_GET_TIMEOUT_SECONDS = 1.0

#: How often the heartbeat callback fires (seconds). Matches the
#: previous _wait_for_board cadence.
HEARTBEAT_INTERVAL_SECONDS = 60.0

#: After this many seconds of no events, the waiter does a poll to
#: guard against lost events (cross-process, dropped, etc).
DEFAULT_POLL_AFTER_SILENCE_SECONDS = 60.0

#: The cadence of the safety poll once silence is detected.
DEFAULT_POLL_INTERVAL_SECONDS = 15.0


#: Statuses that are considered terminal for a board. Mirrors the
#: values ``cmd_orchestrate_monitor`` returns.
TERMINAL_STATUSES = frozenset({
    "completed", "stalled", "blocked", "failed", "timed_out",
})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


Method = Literal["push", "poll", "timeout"]


@dataclass(frozen=True)
class BoardWaitResult:
    """The terminal state of a board wait.

    Attributes:
      success: True iff the board completed cleanly.
      status: ``completed`` | ``stalled`` | ``blocked`` | ``failed`` | ``timed_out``.
      board_id: The kanban board id.
      tasks: Final task list (caller can render in dashboard).
      stalled_tasks: Tasks with failure_count > threshold (subset of tasks).
      blocked_tasks: Tasks in the ``blocked`` column (subset of tasks).
      elapsed_seconds: Wall-clock time spent in ``wait()``.
      method: How we learned about the result.
        * ``push`` — a ``board.completed`` or ``board.failed`` event arrived.
        * ``poll`` — a safety poll against the DB discovered the terminal state.
        * ``timeout`` — neither push nor poll fired in time.
      events_received: Number of session events seen (for observability).
      last_event_at: Timestamp of the last event seen; 0.0 if none.
    """
    success: bool
    status: str
    board_id: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    stalled_tasks: list[dict[str, Any]] = field(default_factory=list)
    blocked_tasks: list[dict[str, Any]] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    method: Method = "timeout"
    events_received: int = 0
    last_event_at: float = 0.0


# ---------------------------------------------------------------------------
# BoardWaiter
# ---------------------------------------------------------------------------


HeartbeatCb = Callable[[], Awaitable[None]]
EventSourceSinkProtocol = Any  # typing-only; see ``subscribe`` docstring


class BoardWaiter:
    """Wait for a kanban board to reach a terminal state via push events.

    Args:
      session_id: The orchestrator's session id; the bus's
        EventSourceSink routes per-session events to per-session queues.
      board_id: The kanban board id to watch.
      sink: The shared ``harness.events.EventSourceSink`` instance
        (duck-typed: needs ``subscribe`` / ``unsubscribe``). Pass
        ``None`` to force the pure-poll path (backwards-compat).
      max_wait_seconds: Total wall-clock budget (default 5400s = 90min).
      poll_after_silence_seconds: How long the queue can be idle
        before we do a safety poll. Lower bound is
        ``HEARTBEAT_INTERVAL_SECONDS`` to keep heartbeats running.
      poll_interval_seconds: How often the safety poll fires once
        silence is detected.
      heartbeat_cb: Optional async callback fired every
        ``HEARTBEAT_INTERVAL_SECONDS`` while waiting. Used by the
        orchestrator to refresh ``sessions.heartbeat_at`` so the
        auto-resume reclaim path doesn't pick the run up again.
    """

    def __init__(
        self,
        session_id: str,
        board_id: str,
        sink: EventSourceSinkProtocol | None = None,
        max_wait_seconds: float | None = None,
        poll_after_silence_seconds: float | None = None,
        poll_interval_seconds: float | None = None,
        heartbeat_cb: HeartbeatCb | None = None,
    ) -> None:
        self._session_id = session_id
        self._board_id = board_id
        self._sink = sink
        self._max_wait = float(
            max_wait_seconds
            if max_wait_seconds is not None
            else _env_float("BOARD_WAITER_MAX_WAIT_SECONDS", DEFAULT_MAX_WAIT_SECONDS)
        )
        # The caller is responsible for picking sane values — there's
        # no automatic clamp to HEARTBEAT_INTERVAL_SECONDS because that
        # made the default 60s unoverridable in tests. The heartbeat
        # tick and the silence poll are independent code paths inside
        # the loop; both fire on their own clocks.
        self._poll_after_silence = float(
            poll_after_silence_seconds
            if poll_after_silence_seconds is not None
            else _env_float("BOARD_WAITER_POLL_AFTER_SILENCE", DEFAULT_POLL_AFTER_SILENCE_SECONDS)
        )
        self._poll_interval = float(
            poll_interval_seconds
            if poll_interval_seconds is not None
            else _env_float("BOARD_WAITER_POLL_INTERVAL", DEFAULT_POLL_INTERVAL_SECONDS)
        )
        self._heartbeat_cb = heartbeat_cb

        # Idempotency: dedupe (subagent_id, status) pairs.
        self._seen_subagents: set[tuple[str, str]] = set()
        # Last poll result, cached so we don't re-call cmd_orchestrate_monitor
        # every iteration. The DB read is the dominant cost.
        self._last_poll_at: float = 0.0
        self._last_poll_result: BoardWaitResult | None = None

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def wait(self) -> BoardWaitResult:
        """Block until the board is terminal or the budget is exhausted.

        Returns a :class:`BoardWaitResult`. Never raises (terminal
        errors are folded into ``status`` and ``success=False``).
        """
        # If no sink is available, fall back to pure polling — matches
        # the pre-C03 behavior for callers that haven't been wired up
        # to the EventBus yet.
        if self._sink is None:
            return await self._wait_pure_poll()

        queue = self._sink.subscribe(self._session_id)
        try:
            return await self._wait_with_push(queue)
        finally:
            try:
                self._sink.unsubscribe(self._session_id, queue)
            except Exception:
                logger.debug("board_waiter unsubscribe failed", exc_info=True)

    # ------------------------------------------------------------------
    # Pure-poll path (no EventBus)
    # ------------------------------------------------------------------

    async def _wait_pure_poll(self) -> BoardWaitResult:
        """The previous polling behavior, preserved verbatim.

        Kept so unit tests and any caller without an EventBus can use
        the same waiter interface.
        """
        start = time.time()
        last_hb = start
        last_event_at = start
        events_received = 0

        while (time.time() - start) < self._max_wait:
            if self._heartbeat_cb and (time.time() - last_hb) > HEARTBEAT_INTERVAL_SECONDS:
                try:
                    await self._heartbeat_cb()
                except Exception:
                    logger.debug("board_waiter heartbeat failed", exc_info=True)
                last_hb = time.time()

            result = await self._poll_once()
            if result is not None:
                return _finalize(result, start, events_received, last_event_at, "poll")

            await asyncio.sleep(self._poll_interval)
            # In pure-poll mode, every iteration counts as an "event"
            # for the silence heuristic (otherwise the silence
            # trigger would never fire).
            last_event_at = time.time()
            events_received += 1

        return BoardWaitResult(
            success=False,
            status="timed_out",
            board_id=self._board_id,
            elapsed_seconds=time.time() - start,
            method="timeout",
            events_received=events_received,
            last_event_at=last_event_at,
        )

    # ------------------------------------------------------------------
    # Push-with-poll-fallback path
    # ------------------------------------------------------------------

    async def _wait_with_push(self, queue) -> BoardWaitResult:
        start = time.time()
        last_hb = start
        last_event_at = start
        last_poll_at = start
        events_received = 0

        while (time.time() - start) < self._max_wait:
            # Heartbeat tick.
            if self._heartbeat_cb and (time.time() - last_hb) > HEARTBEAT_INTERVAL_SECONDS:
                try:
                    await self._heartbeat_cb()
                except Exception:
                    logger.debug("board_waiter heartbeat failed", exc_info=True)
                last_hb = time.time()

            # Wait for an event (with a short timeout so we re-check
            # the silence / heartbeat conditions promptly).
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=QUEUE_GET_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                event = None

            if event is not None:
                events_received += 1
                last_event_at = time.time()

                classified = self._classify_event(event)
                if classified is not None:
                    return _finalize(classified, start, events_received, last_event_at, "push")

            # Silence-triggered safety poll.
            now = time.time()
            silence = now - last_event_at
            if silence > self._poll_after_silence and (now - last_poll_at) > self._poll_interval:
                last_poll_at = now
                polled = await self._poll_once()
                if polled is not None:
                    return _finalize(polled, start, events_received, last_event_at, "poll")

        return BoardWaitResult(
            success=False,
            status="timed_out",
            board_id=self._board_id,
            elapsed_seconds=time.time() - start,
            method="timeout",
            events_received=events_received,
            last_event_at=last_event_at,
        )

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------

    def _classify_event(self, event: StreamEvent) -> BoardWaitResult | None:
        """Map a StreamEvent to a terminal BoardWaitResult, or None.

        Returns None for non-terminal events (e.g. subagent progress
        pings). The caller keeps waiting.
        """
        # ``GenericStreamEvent`` carries the original event_type string
        # in the ``event_type`` field; typed StreamEvent subtypes use
        # ``type_name`` (the class name).
        event_type = getattr(event, "event_type", None) or getattr(event, "type_name", None)
        if not event_type:
            return None

        data = getattr(event, "data", None)
        if not isinstance(data, dict):
            return None

        # ── board.completed — push success ───────────────────────────
        if event_type == "board.completed":
            if data.get("board_id") != self._board_id:
                return None
            return BoardWaitResult(
                success=True,
                status="completed",
                board_id=self._board_id,
                tasks=_as_task_list(data.get("tasks")),
                elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
                method="push",
            )

        # ── board.failed — push failure ─────────────────────────────
        if event_type == "board.failed":
            if data.get("board_id") != self._board_id:
                return None
            return BoardWaitResult(
                success=False,
                status=str(data.get("status", "failed")),
                board_id=self._board_id,
                tasks=_as_task_list(data.get("tasks")),
                blocked_tasks=_as_task_list(data.get("blocked_tasks")),
                stalled_tasks=_as_task_list(data.get("stalled_tasks")),
                method="push",
            )

        # ── subagent.completed — dedupe + observe ────────────────────
        if event_type == "subagent.completed":
            subagent_id = data.get("subagent_id")
            status = data.get("status")
            if not subagent_id or not status:
                return None
            key = (str(subagent_id), str(status))
            if key in self._seen_subagents:
                return None
            self._seen_subagents.add(key)
            # We do NOT terminate on individual subagent failures —
            # the board.failed event will arrive when the orchestrator
            # / kanban service has confirmed the cascading failure.
            # Surface the observation for logs / metrics.
            if str(status) in ("failed", "error"):
                logger.warning(
                    "board_waiter subagent failed board_id=%s subagent_id=%s status=%s",
                    self._board_id, subagent_id, status,
                )
            return None

        # Everything else (tool:start, llm:call, etc) is ignored.
        return None

    # ------------------------------------------------------------------
    # Safety poll — wraps cmd_orchestrate_monitor
    # ------------------------------------------------------------------

    async def _poll_once(self) -> BoardWaitResult | None:
        """One safety poll against the kanban DB.

        Returns a BoardWaitResult if the board is in a terminal state
        (per ``TERMINAL_STATUSES``), else None.
        """
        # Avoid re-querying faster than the configured cadence.
        now = time.time()
        if (now - self._last_poll_at) < self._poll_interval and self._last_poll_result is not None:
            return self._last_poll_result
        self._last_poll_at = now

        try:
            from harness.tools.orchestrator_tool import cmd_orchestrate_monitor
            raw = await cmd_orchestrate_monitor(self._board_id, max_wait_seconds=0)
        except Exception as exc:
            logger.debug("board_waiter poll failed board_id=%s err=%s", self._board_id, exc)
            self._last_poll_result = None
            return None

        try:
            status = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            status = {}

        s = status.get("status")
        if s not in TERMINAL_STATUSES:
            self._last_poll_result = None
            return None

        result = BoardWaitResult(
            success=(s == "completed"),
            status=str(s),
            board_id=self._board_id,
            tasks=_as_task_list(status.get("tasks")),
            blocked_tasks=_as_task_list(status.get("blocked_tasks")),
            stalled_tasks=_as_task_list(status.get("stalled_tasks")),
            method="poll",
        )
        self._last_poll_result = result
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_task_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [t for t in value if isinstance(t, dict)]


def _finalize(
    result: BoardWaitResult,
    start: float,
    events_received: int,
    last_event_at: float,
    method: Method,
) -> BoardWaitResult:
    """Stamp the observability fields and return."""
    return BoardWaitResult(
        success=result.success,
        status=result.status,
        board_id=result.board_id,
        tasks=result.tasks,
        blocked_tasks=result.blocked_tasks,
        stalled_tasks=result.stalled_tasks,
        elapsed_seconds=(time.time() - start),
        method=method,
        events_received=events_received,
        last_event_at=last_event_at if last_event_at else result.last_event_at,
    )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("board_waiter env %s=%r is not a float; using default %s", name, raw, default)
        return default
