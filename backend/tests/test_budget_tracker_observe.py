"""Tests for `harness.budget_tracker.observe()` — the C07 4-step
auto-throttle ladder.

The observe() method is the single glue between the budget
tracker and the agent/llm_router/event_bus. These tests cover
each step's side effect, event emission, and idempotency.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.budget_tracker import BudgetConfig, BudgetTracker
from harness.core.events import BudgetThrottled


class _FakeAgent:
    def __init__(self) -> None:
        self._hitl_gate = False
        self._sequential_only = False
        self.interrupt_count = 0
        self.set_hitl_calls = 0
        self.set_sequential_calls = 0

    def set_hitl_gate(self, value: bool) -> None:
        self._hitl_gate = bool(value)
        self.set_hitl_calls += 1

    def set_sequential_only(self, value: bool) -> None:
        self._sequential_only = bool(value)
        self.set_sequential_calls += 1

    def interrupt(self) -> None:
        self.interrupt_count += 1


class _FakeRouter:
    def __init__(self) -> None:
        self.tier: str | None = None
        self.set_tier_calls = 0

    def set_tier(self, tier: str | None) -> None:
        self.tier = tier
        self.set_tier_calls += 1


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _make_tracker() -> BudgetTracker:
    return BudgetTracker(
        run_id="run-1",
        session_id="sess-1",
        spec_id="spec-1",
        config=BudgetConfig(
            run_soft_cap_usd=1.5,
            run_hard_cap_usd=5.0,
            hitl_threshold_usd=1.0,
            sequential_threshold_usd=2.0,
            cheaper_model_threshold_usd=3.0,
            pause_threshold_usd=4.0,
        ),
    )


def _run(coro):
    return asyncio.run(coro)


class TestObserveBaseline:
    def test_under_all_thresholds_is_noop(self):
        tracker = _make_tracker()
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        snap = _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert snap.throttle_step == 0
        assert agent._hitl_gate is False
        assert agent._sequential_only is False
        assert router.tier is None
        assert agent.interrupt_count == 0
        assert bus.events == []
        assert agent.set_hitl_calls == 0

    def test_no_agents_routers_or_bus_is_safe(self):
        tracker = _make_tracker()
        tracker._spent = 4.5
        snap = _run(tracker.observe())
        assert snap.throttle_step == 4


class TestStepClimbs:
    def test_step_1_sets_hitl_gate(self):
        tracker = _make_tracker()
        tracker._spent = 1.5
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert agent._hitl_gate is True
        assert agent._sequential_only is False
        assert router.tier is None
        assert agent.interrupt_count == 0
        assert len(bus.events) == 1
        evt = bus.events[0]
        assert isinstance(evt, BudgetThrottled)
        assert evt.new_step == 1
        assert evt.prev_step == 0

    def test_step_2_sets_sequential_only(self):
        tracker = _make_tracker()
        tracker._spent = 2.5
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert agent._hitl_gate is True
        assert agent._sequential_only is True
        assert router.tier is None
        assert agent.interrupt_count == 0
        assert bus.events[-1].new_step == 2

    def test_step_3_calls_set_tier_small(self):
        tracker = _make_tracker()
        tracker._spent = 3.5
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert agent._hitl_gate is True
        assert agent._sequential_only is True
        assert router.tier == "small"
        assert agent.interrupt_count == 0
        assert bus.events[-1].new_step == 3

    def test_step_4_calls_interrupt(self):
        tracker = _make_tracker()
        tracker._spent = 4.5
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert agent._hitl_gate is True
        assert agent._sequential_only is True
        assert router.tier == "small"
        assert agent.interrupt_count == 1
        assert bus.events[-1].new_step == 4


class TestIdempotency:
    def test_repeated_observe_at_same_step_does_not_reapply(self):
        tracker = _make_tracker()
        tracker._spent = 1.5
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert agent.set_hitl_calls == 1
        assert len(bus.events) == 1

    def test_climb_0_to_3_emits_one_event_with_prev_zero(self):
        tracker = _make_tracker()
        tracker._spent = 3.5
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert len(bus.events) == 1
        assert bus.events[0].prev_step == 0
        assert bus.events[0].new_step == 3

    def test_climb_0_to_1_to_3_emits_two_events(self):
        tracker = _make_tracker()
        agent = _FakeAgent()
        router = _FakeRouter()
        bus = _FakeBus()
        tracker._spent = 1.2
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        tracker._spent = 3.2
        _run(tracker.observe(agent=agent, llm_router=router, event_bus=bus))
        assert len(bus.events) == 2
        assert bus.events[0].new_step == 1
        assert bus.events[1].new_step == 3
        assert router.set_tier_calls == 1

    def test_event_payload_carries_spec_id_and_run_id(self):
        tracker = _make_tracker()
        tracker._spent = 1.5
        bus = _FakeBus()
        _run(tracker.observe(event_bus=bus))
        evt = bus.events[0]
        assert evt.spec_id == "spec-1"
        assert evt.run_id == "run-1"
        assert evt.session_id == "sess-1"
        assert evt.spent_usd > 0
        assert evt.soft_cap_usd == 1.5


class TestFailureModes:
    def test_agent_set_hitl_gate_failure_does_not_break_observe(self):
        tracker = _make_tracker()
        tracker._spent = 1.5

        class _BadAgent:
            def set_hitl_gate(self, value):
                raise RuntimeError("boom")

            def set_sequential_only(self, value):
                pass

            def interrupt(self):
                pass

        bus = _FakeBus()
        snap = _run(tracker.observe(agent=_BadAgent(), event_bus=bus))
        assert snap.throttle_step == 1
        assert len(bus.events) == 1

    def test_event_emit_failure_does_not_break_observe(self):
        tracker = _make_tracker()
        tracker._spent = 1.5

        class _BadBus:
            async def emit(self, event):
                raise RuntimeError("boom")

        agent = _FakeAgent()
        snap = _run(tracker.observe(agent=agent, event_bus=_BadBus()))
        assert snap.throttle_step == 1
        assert agent._hitl_gate is True


class TestHardCap:
    def test_hard_cap_exceeded_at_five(self):
        tracker = _make_tracker()
        tracker._spent = 5.5
        assert tracker.hard_cap_exceeded() is True
        tracker._spent = 4.99
        assert tracker.hard_cap_exceeded() is False
