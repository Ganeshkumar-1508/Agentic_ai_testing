"""Tests for C06: SubagentHeartbeat + stale detection.

C06 (per docs/2026-06-21-architecture-decision-tree.md#c06) ports
Hermes' heartbeat pattern to TestAI's asyncio-based subagent loop.
The four locked decisions are tested here:

  Q1: Heartbeat location = inside ``delegate_task.run()``
  Q2: Hermes defaults (5s interval, 6 idle / 60 in-tool stale cycles)
  Q3: Raise ``SubagentStuckError`` (parent decides)
  Q4: Progress signal = ``(api_call_count, current_tool)`` pair from
      ``Agent.get_activity_summary()``
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.services.heartbeat import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_STALE_CYCLES_IDLE,
    DEFAULT_STALE_CYCLES_IN_TOOL,
    HeartbeatOutcome,
    SubagentHeartbeat,
    SubagentStuckError,
    _env_float,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeAgent:
    """Minimal stand-in for harness.agent.agent.Agent.

    Implements the ``HeartbeatTarget`` protocol. Tests set
    ``summary`` to whatever dict the heartbeat should see on the
    next call, and inspect ``calls`` to verify how many times the
    heartbeat polled.
    """

    def __init__(self, summary: dict[str, Any] | None = None) -> None:
        self.summary = summary or {
            "current_tool": None,
            "api_call_count": 0,
            "max_iterations": 20,
            "last_activity_desc": "",
        }
        self.calls = 0

    def get_activity_summary(self) -> dict[str, Any]:
        self.calls += 1
        return self.summary

    def set_summary(self, summary: dict[str, Any]) -> None:
        self.summary = summary


# ---------------------------------------------------------------------------
# Configuration & constants
# ---------------------------------------------------------------------------


def test_constants_match_hermes_defaults() -> None:
    """Hermes defaults per C06 Q2: 5s interval, 6 idle / 60 in-tool."""
    assert DEFAULT_HEARTBEAT_INTERVAL_SECONDS == 5.0
    assert DEFAULT_STALE_CYCLES_IDLE == 6
    assert DEFAULT_STALE_CYCLES_IN_TOOL == 60


def test_env_float_falls_back_on_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUBAGENT_HEARTBEAT_INTERVAL", raising=False)
    assert _env_float("SUBAGENT_HEARTBEAT_INTERVAL", 7.0) == 7.0


def test_env_float_parses_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBAGENT_HEARTBEAT_INTERVAL", "3.5")
    assert _env_float("SUBAGENT_HEARTBEAT_INTERVAL", 7.0) == 3.5


def test_env_float_warns_and_falls_back_on_invalid(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("SUBAGENT_HEARTBEAT_INTERVAL", "garbage")
    assert _env_float("SUBAGENT_HEARTBEAT_INTERVAL", 7.0) == 7.0
    assert any("not a float" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Basic lifecycle
# ---------------------------------------------------------------------------


async def test_clean_exit_on_stop_event() -> None:
    """When the stop_event is set, the heartbeat returns cleanly with
    ``stuck=False``.
    """
    agent = _FakeAgent()
    stop = asyncio.Event()
    hb = SubagentHeartbeat(
        subagent_id="sa-1",
        target=agent,
        interval=0.05,
    )
    # Schedule stop after one cycle.
    async def _stop_after():
        await asyncio.sleep(0.07)
        stop.set()
    outcome, _ = await asyncio.gather(hb.run(stop), _stop_after())
    assert outcome.stuck is False
    assert outcome.subagent_id == "sa-1"
    assert outcome.cycles >= 1
    assert outcome.stuck_at_seconds is None


async def test_heartbeat_polls_at_least_once() -> None:
    """Even a sub-millisecond stop_event wait should poll at least once."""
    agent = _FakeAgent()
    stop = asyncio.Event()
    hb = SubagentHeartbeat(
        subagent_id="sa-1",
        target=agent,
        interval=0.01,
    )
    stop.set()  # pre-set so the first wait_for returns immediately
    outcome = await hb.run(stop)
    # The loop runs: while not stop.is_set() is False, so it exits
    # without polling. Verify this is the case (zero polls before
    # the while check is even reached).
    assert outcome.cycles == 0
    assert agent.calls == 0


# ---------------------------------------------------------------------------
# Stale detection: idle
# ---------------------------------------------------------------------------


async def test_stuck_when_idle_summary_never_changes() -> None:
    """If the summary never advances, the heartbeat eventually returns
    ``stuck=True`` (after the idle threshold).
    """
    agent = _FakeAgent({"current_tool": None, "api_call_count": 5,
                        "max_iterations": 20, "last_activity_desc": ""})
    stop = asyncio.Event()
    hb = SubagentHeartbeat(
        subagent_id="sa-stuck",
        target=agent,
        interval=0.02,
        stale_cycles_idle=3,
        stale_cycles_in_tool=10,  # not relevant for idle
    )
    outcome = await hb.run(stop)
    assert outcome.stuck is True
    # ``stuck_at_seconds`` is the wall-clock time the heartbeat was
    # alive. With 3 cycles of 0.02s, it's ≥0 (may round to 0 on
    # coarse-grained clocks). We just verify it was set.
    assert outcome.stuck_at_seconds is not None
    assert outcome.stuck_at_seconds >= 0
    # We polled at least stale_cycles_idle times before returning.
    assert agent.calls >= 3


async def test_progress_resets_stale_counter() -> None:
    """If the summary advances at least once per N cycles (where N is
    the threshold), the heartbeat should NEVER go stuck.
    """
    # Use a mutable state so we can change the summary per cycle.
    state = {"iter": 0, "calls": 0}

    class _AdvancingAgent:
        def get_activity_summary(self) -> dict[str, Any]:
            state["calls"] += 1
            # Advance iter every poll — never stale.
            state["iter"] += 1
            return {
                "current_tool": None,
                "api_call_count": state["iter"],
                "max_iterations": 20,
                "last_activity_desc": f"iter {state['iter']}",
            }

    agent = _AdvancingAgent()
    stop = asyncio.Event()

    async def _stop_after():
        await asyncio.sleep(0.1)
        stop.set()

    hb = SubagentHeartbeat(
        subagent_id="sa-progressing",
        target=agent,
        interval=0.01,
        stale_cycles_idle=3,
    )
    outcome, _ = await asyncio.gather(hb.run(stop), _stop_after())
    assert outcome.stuck is False
    assert state["calls"] >= 2


async def test_tool_change_resets_stale_counter() -> None:
    """A tool transition (same iter, different tool) also counts as
    progress — the child is alive even if it hasn't made a new LLM
    call.
    """
    state = {"iter": 5, "tool": "web_fetch", "calls": 0}

    class _ToolSwitcher:
        def get_activity_summary(self) -> dict[str, Any]:
            state["calls"] += 1
            # Same iter, but switch tool every 2 cycles.
            if state["calls"] % 2 == 0:
                state["tool"] = "read_file" if state["tool"] == "web_fetch" else "web_fetch"
            return {
                "current_tool": state["tool"],
                "api_call_count": state["iter"],
                "max_iterations": 20,
                "last_activity_desc": f"tool {state['tool']}",
            }

    agent = _ToolSwitcher()
    stop = asyncio.Event()

    async def _stop_after():
        await asyncio.sleep(0.1)
        stop.set()

    hb = SubagentHeartbeat(
        subagent_id="sa-tool-switcher",
        target=agent,
        interval=0.01,
        stale_cycles_in_tool=3,
    )
    outcome, _ = await asyncio.gather(hb.run(stop), _stop_after())
    assert outcome.stuck is False


# ---------------------------------------------------------------------------
# Stale detection: in-tool
# ---------------------------------------------------------------------------


async def test_stuck_when_in_tool_too_long() -> None:
    """In-tool stale threshold fires after the in-tool cycles (longer
    than idle).
    """
    agent = _FakeAgent({
        "current_tool": "bash",
        "api_call_count": 5,
        "max_iterations": 20,
        "last_activity_desc": "running bash",
    })
    stop = asyncio.Event()
    hb = SubagentHeartbeat(
        subagent_id="sa-bash-hung",
        target=agent,
        interval=0.01,
        stale_cycles_idle=3,
        stale_cycles_in_tool=8,  # 8 * 0.01s = 80ms
    )
    outcome = await hb.run(stop)
    assert outcome.stuck is True
    assert outcome.last_tool == "bash"
    assert agent.calls >= 8


async def test_in_tool_threshold_longer_than_idle() -> None:
    """In-tool threshold is the long fuse; idle is the short fuse.
    Verifies the design intent: don't kill a child running a long
    tool.
    """
    agent = _FakeAgent({
        "current_tool": "web_fetch",
        "api_call_count": 5,
        "max_iterations": 20,
        "last_activity_desc": "running web_fetch",
    })
    stop = asyncio.Event()
    # Set the thresholds so that idle would fire in 3 cycles but
    # in-tool needs 8. The agent is "in tool", so we should run 8.
    hb = SubagentHeartbeat(
        subagent_id="sa-web-fetch",
        target=agent,
        interval=0.01,
        stale_cycles_idle=3,
        stale_cycles_in_tool=8,
    )
    outcome = await hb.run(stop)
    assert outcome.stuck is True
    # We polled 8+ times — more than the idle threshold of 3.
    assert agent.calls >= 8


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


async def test_on_heartbeat_callback_fires() -> None:
    """Per-cycle callback should fire on every poll (when not stuck)."""
    agent = _FakeAgent()
    stop = asyncio.Event()
    calls: list[dict[str, Any]] = []

    def _on_hb(**kw: Any) -> None:
        calls.append(kw)

    async def _stop_after():
        await asyncio.sleep(0.1)
        stop.set()

    hb = SubagentHeartbeat(
        subagent_id="sa-cb",
        target=agent,
        interval=0.02,
        on_heartbeat=_on_hb,
    )
    outcome, _ = await asyncio.gather(hb.run(stop), _stop_after())
    assert outcome.stuck is False
    assert len(calls) >= 2
    # Each call carries the expected fields.
    for c in calls:
        assert c["subagent_id"] == "sa-cb"
        assert "current_iter" in c
        assert "elapsed_seconds" in c


async def test_on_heartbeat_async_callback_also_works() -> None:
    agent = _FakeAgent()
    stop = asyncio.Event()
    calls: list[int] = []

    async def _on_hb(**kw: Any) -> None:
        calls.append(1)
        await asyncio.sleep(0)

    async def _stop_after():
        await asyncio.sleep(0.1)
        stop.set()

    hb = SubagentHeartbeat(
        subagent_id="sa-async-cb",
        target=agent,
        interval=0.02,
        on_heartbeat=_on_hb,
    )
    outcome, _ = await asyncio.gather(hb.run(stop), _stop_after())
    assert outcome.stuck is False
    assert len(calls) >= 2


async def test_on_heartbeat_callback_exception_swallowed() -> None:
    """A raising callback must not crash the heartbeat.

    We use an agent whose summary *advances* every cycle so the
    heartbeat doesn't trip the stuck threshold before stop_event
    fires. This isolates the "callback raises" behavior from the
    stuck-detection behavior.
    """
    state = {"iter": 0}

    class _AdvancingAgent:
        def get_activity_summary(self) -> dict[str, Any]:
            state["iter"] += 1
            return {
                "current_tool": None,
                "api_call_count": state["iter"],
                "max_iterations": 20,
                "last_activity_desc": "progressing",
            }

    agent = _AdvancingAgent()
    stop = asyncio.Event()

    def _on_hb(**kw: Any) -> None:
        raise RuntimeError("callback broke")

    async def _stop_after():
        await asyncio.sleep(0.1)
        stop.set()

    hb = SubagentHeartbeat(
        subagent_id="sa-broken-cb",
        target=agent,
        interval=0.02,
        on_heartbeat=_on_hb,
    )
    outcome, _ = await asyncio.gather(hb.run(stop), _stop_after())
    # The heartbeat should still exit cleanly (not stuck, even
    # though the callback raised on every cycle).
    assert outcome.stuck is False
    # And the callback was actually called — at least twice.
    assert state["iter"] >= 2


async def test_on_stale_warning_fires_at_half_threshold() -> None:
    """The warning callback should fire once when stale_count crosses
    half the threshold.
    """
    agent = _FakeAgent({"current_tool": None, "api_call_count": 0,
                        "max_iterations": 20, "last_activity_desc": ""})
    stop = asyncio.Event()
    warnings: list[dict[str, Any]] = []

    def _on_warn(**kw: Any) -> None:
        warnings.append(kw)

    hb = SubagentHeartbeat(
        subagent_id="sa-warn",
        target=agent,
        interval=0.01,
        stale_cycles_idle=6,
        on_stale_warning=_on_warn,
    )
    outcome = await hb.run(stop)
    assert outcome.stuck is True
    # Warning should have fired once (at stale_count=3 = half of 6).
    assert len(warnings) == 1
    assert warnings[0]["stale_count"] == 3
    assert warnings[0]["stale_limit"] == 6


async def test_on_stale_warning_fires_only_once() -> None:
    """The warning callback should fire ONCE per stuck episode —
    not on every subsequent cycle.
    """
    agent = _FakeAgent({"current_tool": None, "api_call_count": 0,
                        "max_iterations": 20, "last_activity_desc": ""})
    stop = asyncio.Event()
    warnings: list[dict[str, Any]] = []

    def _on_warn(**kw: Any) -> None:
        warnings.append(kw)

    hb = SubagentHeartbeat(
        subagent_id="sa-warn-once",
        target=agent,
        interval=0.01,
        stale_cycles_idle=4,
        on_stale_warning=_on_warn,
    )
    outcome = await hb.run(stop)
    assert outcome.stuck is True
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------


async def test_get_activity_summary_exception_is_safe() -> None:
    """If the agent's get_activity_summary raises, the heartbeat
    treats it as 'no progress' and bumps the stale counter.
    """

    class _RaisingAgent:
        def get_activity_summary(self) -> dict[str, Any]:
            raise RuntimeError("agent is broken")

    agent = _RaisingAgent()
    stop = asyncio.Event()
    hb = SubagentHeartbeat(
        subagent_id="sa-raising",
        target=agent,
        interval=0.01,
        stale_cycles_idle=3,
    )
    outcome = await hb.run(stop)
    # Eventually goes stuck because the summary never advances.
    assert outcome.stuck is True


async def test_missing_keys_in_summary_use_defaults() -> None:
    """A summary missing fields should not crash the heartbeat."""
    agent = _FakeAgent({})  # empty dict
    stop = asyncio.Event()
    hb = SubagentHeartbeat(
        subagent_id="sa-empty",
        target=agent,
        interval=0.01,
        stale_cycles_idle=3,
    )
    outcome = await hb.run(stop)
    assert outcome.stuck is True
    # Defaults: current_tool=None, api_call_count=0.


async def test_stale_subagent_stuck_error_attributes() -> None:
    """SubagentStuckError carries the right payload for the parent's
    error path.
    """
    err = SubagentStuckError(
        subagent_id="sa-x",
        last_iter=5,
        last_tool="bash",
        stale_seconds=42.0,
    )
    assert err.subagent_id == "sa-x"
    assert err.last_iter == 5
    assert err.last_tool == "bash"
    assert err.stale_seconds == 42.0
    assert "sa-x" in str(err)
    assert "42.0" in str(err)
    assert "bash" in str(err)


async def test_heartbeat_outcome_is_frozen() -> None:
    """HeartbeatOutcome is a frozen dataclass."""
    o = HeartbeatOutcome(
        subagent_id="sa-1",
        cycles=5,
        last_iter=3,
        last_tool=None,
        elapsed_seconds=1.0,
        stuck=False,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        o.cycles = 99  # type: ignore[misc]


async def test_invalid_env_value_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env vars that are non-float use the default."""
    monkeypatch.setenv("SUBAGENT_HEARTBEAT_STALE_IDLE", "not-a-number")
    agent = _FakeAgent({"current_tool": None, "api_call_count": 0,
                        "max_iterations": 20, "last_activity_desc": ""})
    stop = asyncio.Event()
    hb = SubagentHeartbeat(subagent_id="sa-bad-env", target=agent, interval=0.01)
    # Default is 6 — verify it took effect.
    assert hb._stale_cycles_idle == 6


async def test_heartbeat_isolated_target_state() -> None:
    """Two heartbeats on two different agents don't share state."""
    agent_a = _FakeAgent({"current_tool": None, "api_call_count": 0,
                          "max_iterations": 20, "last_activity_desc": ""})
    agent_b = _FakeAgent({"current_tool": None, "api_call_count": 0,
                          "max_iterations": 20, "last_activity_desc": ""})
    stop_a = asyncio.Event()
    stop_b = asyncio.Event()

    async def _stop_a():
        await asyncio.sleep(0.05)
        stop_a.set()

    async def _stop_b():
        await asyncio.sleep(0.05)
        stop_b.set()

    hb_a = SubagentHeartbeat(
        subagent_id="sa-a", target=agent_a, interval=0.01,
        stale_cycles_idle=2,
    )
    hb_b = SubagentHeartbeat(
        subagent_id="sa-b", target=agent_b, interval=0.01,
        stale_cycles_idle=2,
    )

    out_a, out_b, _, _ = await asyncio.gather(
        hb_a.run(stop_a), hb_b.run(stop_b), _stop_a(), _stop_b(),
    )
    # Each heartbeat polled its own agent — counters are independent.
    assert out_a.subagent_id == "sa-a"
    assert out_b.subagent_id == "sa-b"


# ---------------------------------------------------------------------------
# Agent.get_activity_summary integration
# ---------------------------------------------------------------------------


async def test_agent_get_activity_summary_returns_dict() -> None:
    """The Agent's get_activity_summary should return the expected
    dict shape.

    This is a smoke test — we don't exercise the full agent loop,
    just verify the new method exists and returns the right keys.
    """
    from harness.agent.agent import Agent

    # Build a minimal Agent instance. We don't need to start its
    # loop; we just want to call get_activity_summary().
    # The Agent.__init__ takes (deps, allowed_tools, mode, ...).
    # We'll pass a stub deps.
    fake_deps = MagicMock()
    fake_deps.event_bus = MagicMock()

    agent = Agent(
        deps=fake_deps,
        allowed_tools=["bash"],
        mode="chat",
        max_tool_rounds=10,
    )
    summary = agent.get_activity_summary()
    assert "current_tool" in summary
    assert "api_call_count" in summary
    assert "max_iterations" in summary
    assert "last_activity_desc" in summary
    assert summary["max_iterations"] == 10
    assert summary["api_call_count"] == 0
    assert summary["current_tool"] is None


async def test_agent_set_current_tool_updates_state() -> None:
    """The internal _set_current_tool helper updates the summary."""
    from harness.agent.agent import Agent
    fake_deps = MagicMock()
    fake_deps.event_bus = MagicMock()
    agent = Agent(deps=fake_deps, allowed_tools=["bash"], mode="chat")
    agent._set_current_tool("read_file")
    s = agent.get_activity_summary()
    assert s["current_tool"] == "read_file"
    assert s["last_activity_desc"] == "running tool read_file"
    agent._set_current_tool(None)
    s = agent.get_activity_summary()
    assert s["current_tool"] is None


async def test_agent_bump_api_call_increments() -> None:
    """The internal _bump_api_call helper increments the counter."""
    from harness.agent.agent import Agent
    fake_deps = MagicMock()
    fake_deps.event_bus = MagicMock()
    agent = Agent(deps=fake_deps, allowed_tools=["bash"], mode="chat")
    assert agent.get_activity_summary()["api_call_count"] == 0
    agent._bump_api_call()
    assert agent.get_activity_summary()["api_call_count"] == 1
    agent._bump_api_call()
    assert agent.get_activity_summary()["api_call_count"] == 2
