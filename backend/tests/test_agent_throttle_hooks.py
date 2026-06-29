"""Tests for the Agent's C07 throttle-ladder hook surface
(set_hitl_gate, set_sequential_only, properties).

The Agent needs these hooks so ``BudgetTracker.observe()``
can apply the step-1 and step-2 side effects without
touching the dispatcher's internals.
"""
from __future__ import annotations

import types

from harness.permissions.manager import PermissionManager


def _fake_deps():
    return types.SimpleNamespace(permissions=PermissionManager(mode="auto"))


class _FakeAgent:
    """Mirror the Agent's __init__-time fields without spinning
    up the full LLM/permission/tool stack."""

    def __init__(self) -> None:
        self._deps = _fake_deps()
        self._hitl_gate = False
        self._sequential_only = False

    def set_hitl_gate(self, value: bool) -> None:
        self._hitl_gate = bool(value)
        try:
            self._deps.permissions.set_force_approval(bool(value))
        except Exception:
            pass

    def set_sequential_only(self, value: bool) -> None:
        self._sequential_only = bool(value)

    @property
    def hitl_gate_active(self) -> bool:
        return bool(getattr(self, "_hitl_gate", False))

    @property
    def sequential_only_active(self) -> bool:
        return bool(getattr(self, "_sequential_only", False))


class TestAgentThrottleHooks:
    def test_initial_state_off(self):
        agent = _FakeAgent()
        assert agent.hitl_gate_active is False
        assert agent.sequential_only_active is False

    def test_set_hitl_gate_true_pushes_to_permission_manager(self):
        agent = _FakeAgent()
        agent.set_hitl_gate(True)
        assert agent.hitl_gate_active is True
        assert agent._deps.permissions._force_approval is True

    def test_set_hitl_gate_false_clears_permission_manager(self):
        agent = _FakeAgent()
        agent.set_hitl_gate(True)
        agent.set_hitl_gate(False)
        assert agent.hitl_gate_active is False
        assert agent._deps.permissions._force_approval is False

    def test_set_sequential_only_toggles_flag(self):
        agent = _FakeAgent()
        agent.set_sequential_only(True)
        assert agent.sequential_only_active is True
        agent.set_sequential_only(False)
        assert agent.sequential_only_active is False

    def test_set_hitl_gate_handles_missing_permissions(self):
        agent = _FakeAgent()
        agent._deps = types.SimpleNamespace(permissions=None)
        agent.set_hitl_gate(True)
        assert agent.hitl_gate_active is True

    def test_sequential_only_does_not_touch_permissions(self):
        agent = _FakeAgent()
        before = agent._deps.permissions._force_approval
        agent.set_sequential_only(True)
        assert agent._deps.permissions._force_approval == before
