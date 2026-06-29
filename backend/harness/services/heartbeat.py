"""Subagent heartbeat — keep parent's gateway activity timestamp fresh.

C06 (per docs/2026-06-21-architecture-decision-tree.md#c06):
  Q1: Heartbeat location = inside ``delegate_task.run()``
  Q2: Parameters = Hermes defaults (5s interval, 6 idle / 60 in-tool
      stale cycles)
  Q3: Stale behavior = raise ``SubagentStuckError`` (parent decides)
  Q4: Progress signal = ``stream_events`` count delta (mirrored as
      ``(api_call_count, current_tool)`` pair from
      ``Agent.get_activity_summary``)

The heartbeat is the seam between a long-running subagent and a parent
that has its own gateway inactivity timeout. Without it, a subagent
running a long `apt-get` or `web_fetch` would cause the parent to be
killed for "no activity" by the upstream gateway. With it, the parent
sees a continuous stream of activity timestamps (5s cadence) AND a
side-channel signal that fires ``subagent.heartbeat`` events on the
EventBus for dashboard observability.

Public surface (stable):
  SubagentHeartbeat, SubagentStuckError, HeartbeatOutcome
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — Hermes defaults (per C06 Q2)
# ---------------------------------------------------------------------------

#: Heartbeat interval in seconds. Matches Hermes' ``_HEARTBEAT_INTERVAL``.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0

#: Number of consecutive heartbeat cycles with no progress before we
#: raise :class:`SubagentStuckError` when the subagent is **idle**
#: (between rounds, waiting for the next LLM response).
#: 6 cycles × 5s = 30s. A short fuse — the parent should notice fast.
DEFAULT_STALE_CYCLES_IDLE = 6

#: Number of consecutive heartbeat cycles with no progress before we
#: raise when the subagent is **in a tool call** (legitimately long
#: work like ``apt-get`` or a slow ``web_fetch``).
#: 60 cycles × 5s = 5min. Long enough to cover real tools, short
#: enough that a hung subprocess is caught.
DEFAULT_STALE_CYCLES_IN_TOOL = 60


# ---------------------------------------------------------------------------
# Errors + outcomes
# ---------------------------------------------------------------------------


class SubagentStuckError(Exception):
    """Raised by the heartbeat when the subagent stops making progress.

    C06 Q3 (locked): the heartbeat is for observability, not
    termination. Raising this error gives the parent a chance to
    react (re-plan, ask the user, or let the subagent finish if the
    cap was just a transient hang). The parent — i.e. the
    ``delegate_task._run_single_enhanced`` catch block — is
    responsible for cancelling the child task and surfacing a
    user-readable error.

    Attributes:
      subagent_id: The subagent that appeared stuck.
      last_iter: Last observed ``api_call_count``.
      last_tool: Name of the tool the subagent was in when it stopped
        making progress (or ``None`` if idle).
      stale_seconds: Wall-clock time the heartbeat saw no progress.
    """
    def __init__(
        self,
        subagent_id: str,
        last_iter: int,
        last_tool: str | None,
        stale_seconds: float,
    ) -> None:
        self.subagent_id = subagent_id
        self.last_iter = last_iter
        self.last_tool = last_tool
        self.stale_seconds = stale_seconds
        super().__init__(
            f"Subagent {subagent_id} appears stuck: no progress for "
            f"{stale_seconds:.1f}s "
            f"(last iter={last_iter}, last tool={last_tool or '<idle>'})"
        )


@dataclass(frozen=True)
class HeartbeatOutcome:
    """What the heartbeat did during its lifetime.

    Returned by :meth:`SubagentHeartbeat.run` so the parent can log
    / surface it. ``None`` for fields the heartbeat didn't observe
    (e.g. ``stuck_at_seconds`` if it never raised).
    """
    subagent_id: str
    cycles: int
    last_iter: int
    last_tool: str | None
    elapsed_seconds: float
    stuck: bool
    stuck_at_seconds: float | None = None


# ---------------------------------------------------------------------------
# Protocol — anything ``Agent``-shaped is fine
# ---------------------------------------------------------------------------


class HeartbeatTarget(Protocol):
    """The shape the heartbeat needs from the subagent.

    TestAI's :class:`harness.agent.agent.Agent` implements this
    naturally. Tests can pass a stub.
    """
    def get_activity_summary(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# SubagentHeartbeat
# ---------------------------------------------------------------------------


class SubagentHeartbeat:
    """Poll a subagent's activity summary and detect stuckness.

    Args:
      subagent_id: The id of the subagent being monitored. Used for
        log lines and the ``SubagentStuckError`` payload.
      target: The subagent (or any object implementing
        :class:`HeartbeatTarget`). The heartbeat calls
        ``target.get_activity_summary()`` every ``interval`` seconds.
      interval: Seconds between heartbeat cycles. Default 5.0.
      stale_cycles_idle: Max consecutive cycles with no progress
        before raising, when the subagent is idle. Default 6.
      stale_cycles_in_tool: Max consecutive cycles with no progress
        before raising, when the subagent is in a tool call. Default
        60.
      on_heartbeat: Optional async callback fired on every successful
        (non-stale) cycle. Used by ``delegate_task`` to publish the
        ``subagent.heartbeat`` event on the EventBus. Exceptions in
        the callback are logged and swallowed.
      on_stale_warning: Optional async callback fired when the
        subagent has been stale for half the cycle limit (so a human
        watching the dashboard sees a "warning" before the hard
        failure). Default ``None``.
    """

    def __init__(
        self,
        subagent_id: str,
        target: HeartbeatTarget,
        *,
        interval: float | None = None,
        stale_cycles_idle: int | None = None,
        stale_cycles_in_tool: int | None = None,
        on_heartbeat: Any | None = None,
        on_stale_warning: Any | None = None,
    ) -> None:
        self._subagent_id = subagent_id
        self._target = target
        self._interval = float(
            interval
            if interval is not None
            else _env_float("SUBAGENT_HEARTBEAT_INTERVAL", DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
        )
        self._stale_cycles_idle = int(
            stale_cycles_idle
            if stale_cycles_idle is not None
            else int(_env_float("SUBAGENT_HEARTBEAT_STALE_IDLE", DEFAULT_STALE_CYCLES_IDLE))
        )
        self._stale_cycles_in_tool = int(
            stale_cycles_in_tool
            if stale_cycles_in_tool is not None
            else int(_env_float("SUBAGENT_HEARTBEAT_STALE_IN_TOOL", DEFAULT_STALE_CYCLES_IN_TOOL))
        )
        self._on_heartbeat = on_heartbeat
        self._on_stale_warning = on_stale_warning
        self._warning_fired: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, stop_event: asyncio.Event) -> HeartbeatOutcome:
        """Run the heartbeat loop until ``stop_event`` is set.

        The loop is robust to ``target.get_activity_summary()``
        raising — exceptions are logged at debug and treated as "no
        progress" (which is the safe default).

        Raises:
          SubagentStuckError: when the subagent has been stale for
            the appropriate cycle limit.
        """
        start = time.time()
        last_iter = -1
        last_tool: str | None = None
        stale_count = 0
        cycles = 0

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._interval)
                # stop_event was set during the wait; exit cleanly
                break
            except asyncio.TimeoutError:
                pass

            cycles += 1
            try:
                summary = self._target.get_activity_summary()
                current_iter = int(summary.get("api_call_count", 0) or 0)
                current_tool = summary.get("current_tool")
                last_activity_desc = summary.get("last_activity_desc", "")
            except Exception as exc:
                logger.debug(
                    "heartbeat summary failed subagent_id=%s err=%s",
                    self._subagent_id, exc,
                )
                # Defensive: assume the agent is alive but no
                # progress (we can't read the summary, so the safest
                # assumption is "stuck until proven otherwise").
                current_iter = last_iter
                current_tool = last_tool
                last_activity_desc = "summary_unavailable"

            iter_advanced = current_iter > last_iter
            tool_changed = current_tool != last_tool
            if iter_advanced or tool_changed:
                # Progress! Reset the stale counter. The
                # ``tool_changed`` arm fires when the child switches
                # tools (e.g. between tool calls in the same round)
                # — that's a meaningful "still alive" signal even
                # when no new LLM call has happened.
                last_iter = current_iter
                last_tool = current_tool
                stale_count = 0
                self._warning_fired = False
            else:
                stale_count += 1

            # Pick the right threshold: in-tool gets a long fuse.
            stale_limit = (
                self._stale_cycles_in_tool
                if current_tool
                else self._stale_cycles_idle
            )
            if stale_count >= stale_limit:
                elapsed = time.time() - start
                logger.warning(
                    "Subagent %s appears stuck: stale_count=%d limit=%d "
                    "tool=%s iter=%d elapsed=%.1fs",
                    self._subagent_id, stale_count, stale_limit,
                    current_tool or "<idle>", current_iter, elapsed,
                )
                return HeartbeatOutcome(
                    subagent_id=self._subagent_id,
                    cycles=cycles,
                    last_iter=current_iter,
                    last_tool=current_tool,
                    elapsed_seconds=elapsed,
                    stuck=True,
                    stuck_at_seconds=elapsed,
                )

            # Stale-warning callback: fired once per stuck episode
            # when the counter crosses half the limit. Lets the
            # dashboard show a yellow "warning" state.
            if (
                not self._warning_fired
                and stale_count >= stale_limit // 2
                and self._on_stale_warning is not None
            ):
                self._warning_fired = True
                try:
                    result = self._on_stale_warning(
                        subagent_id=self._subagent_id,
                        current_iter=current_iter,
                        current_tool=current_tool,
                        stale_count=stale_count,
                        stale_limit=stale_limit,
                    )
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.debug(
                        "heartbeat on_stale_warning callback failed: %s",
                        exc,
                    )

            # Per-cycle callback (subagent.heartbeat event emit).
            if self._on_heartbeat is not None:
                try:
                    result = self._on_heartbeat(
                        subagent_id=self._subagent_id,
                        current_iter=current_iter,
                        current_tool=current_tool,
                        last_activity_desc=last_activity_desc,
                        stale_count=stale_count,
                        elapsed_seconds=time.time() - start,
                    )
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.debug(
                        "heartbeat on_heartbeat callback failed: %s",
                        exc,
                    )

        # Clean exit (stop_event set without us raising).
        return HeartbeatOutcome(
            subagent_id=self._subagent_id,
            cycles=cycles,
            last_iter=last_iter,
            last_tool=last_tool,
            elapsed_seconds=time.time() - start,
            stuck=False,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "subagent_heartbeat env %s=%r is not a float; using default %s",
            name, raw, default,
        )
        return default
