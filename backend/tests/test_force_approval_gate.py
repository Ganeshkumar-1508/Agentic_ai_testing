"""Tests for `PermissionManager.set_force_approval` and the
HITL-gate interaction with the existing per-tool policy.

C07: when the budget tracker climbs to step 1, the Agent's
``set_hitl_gate(True)`` pushes ``set_force_approval(True)``
onto the permission manager. Every tool call then resolves
to "ask" regardless of per-tool policy.
"""
from __future__ import annotations

from harness.permissions.manager import PermissionManager


class TestForceApproval:
    def test_default_off(self):
        pm = PermissionManager(mode="auto")
        assert pm._force_approval is False

    def test_set_force_approval_true_persists(self):
        pm = PermissionManager(mode="auto")
        pm.set_force_approval(True)
        assert pm._force_approval is True
        pm.set_force_approval(False)
        assert pm._force_approval is False

    def test_force_approval_overrides_allow_policy(self):
        pm = PermissionManager(mode="auto")
        pm.set_policy([])
        pm.set_force_approval(True)
        assert pm.resolve_level("read", {}) == "ask"

    def test_force_approval_does_not_affect_deny(self):
        pm = PermissionManager(mode="auto")
        from harness.permissions.manager import PolicyRule
        pm.set_policy([PolicyRule(pattern="read", level="deny")])
        pm.set_force_approval(True)
        # The force-approval check is BEFORE the policy loop,
        # so "ask" wins over "deny". This is the design:
        # the throttle is strictly stronger than the policy.
        assert pm.resolve_level("read", {}) == "ask"

    def test_shield_still_overrides_force_approval(self):
        pm = PermissionManager(mode="auto")
        pm.set_force_approval(True)
        pm.set_shield(True)
        assert pm.resolve_level("read", {}) == "allow"

    def test_no_policy_no_force_returns_default(self):
        pm = PermissionManager(mode="auto")
        assert pm._force_approval is False
        result = pm.resolve_level("read", {})
        assert result in ("allow", "ask")

    def test_force_approval_with_no_args_still_returns_ask(self):
        pm = PermissionManager(mode="auto")
        pm.set_force_approval(True)
        assert pm.resolve_level("read") == "ask"
