"""Tests for C2.1: the TestPlan artifact, intent-hash cache, and store
protocol.

C2.1 makes the test plan a first-class record (was an in-conversation
artifact before). The two new conventions:

  - The cache key is `intent_hash`, a SHA-256 of the plan's
    identifying inputs (repo, sha, framework, files, invariants).
    Per Momentic: the intent is the cache key, the traceable unit,
    the user-reviewable artifact.
  - The `TestPlanStore` Protocol follows the project's "one store
    per domain" convention (per Q4).

These tests assert the data, the protocol, and the cache behavior.
The Postgres-backed adapter and the kanban-proposal-card wiring
are follow-up work outside C2.1 v1.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import fields

import pytest


# ---------------------------------------------------------------------------
# Invariant — the per-assertion unit
# ---------------------------------------------------------------------------


class TestInvariant:
    def test_id_and_description_required(self):
        from harness.test_plan import Invariant
        inv = Invariant(
            id="inv-1",
            description="the checkout rejects expired cards",
            target="src/payments/checkout.py:42",
        )
        assert inv.id == "inv-1"
        assert inv.description == "the checkout rejects expired cards"
        assert inv.target == "src/payments/checkout.py:42"
        # Defaults
        assert inv.category == "happy-path"
        assert inv.risk == "medium"

    def test_frozen_dataclass(self):
        """Invariants are frozen so the planner can't accidentally
        mutate a persisted record."""
        from harness.test_plan import Invariant
        inv = Invariant(id="i", description="d", target="t")
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            inv.id = "mutated"  # type: ignore[misc]

    def test_invalid_category_rejected(self):
        from harness.test_plan import Invariant
        with pytest.raises(ValueError, match="category"):
            Invariant(id="i", description="d", target="t", category="smoke")

    def test_invalid_risk_rejected(self):
        from harness.test_plan import Invariant
        with pytest.raises(ValueError, match="risk"):
            Invariant(id="i", description="d", target="t", risk="extreme")


# ---------------------------------------------------------------------------
# TestPlan — the artifact
# ---------------------------------------------------------------------------


class TestTestPlan:
    def _sample(self, **overrides):
        from harness.test_plan import TestPlan, Invariant
        defaults = dict(
            plan_id="plan-1",
            run_id="run-1",
            spec_id="spec-1",
            repo_url="https://github.com/acme/widgets",
            repo_sha="abc123",
            framework="pytest",
            invariants=[
                Invariant(id="i1", description="rejects expired", target="src/x.py:10", risk="high"),
                Invariant(id="i2", description="happy path", target="src/x.py:20", category="happy-path"),
            ],
            files=["src/x.py"],
            risk="medium",
            requires_browser=False,
        )
        defaults.update(overrides)
        return TestPlan(**defaults)

    def test_required_fields(self):
        plan = self._sample()
        assert plan.plan_id == "plan-1"
        assert plan.run_id == "run-1"
        assert plan.spec_id == "spec-1"
        assert plan.framework == "pytest"
        assert len(plan.invariants) == 2
        assert plan.files == ["src/x.py"]
        assert plan.risk == "medium"
        assert plan.requires_browser is False

    def test_intent_hash_auto_set(self):
        """intent_hash is computed from the plan's identifying inputs
        on construction; the caller doesn't set it."""
        plan = self._sample()
        assert plan.intent_hash != ""
        assert len(plan.intent_hash) == 64  # SHA-256 hex

    def test_intent_hash_is_deterministic(self):
        """Two plans with the same inputs hash to the same value."""
        a = self._sample()
        b = self._sample()
        assert a.intent_hash == b.intent_hash

    def test_intent_hash_changes_when_inputs_change(self):
        a = self._sample(repo_sha="sha-A")
        b = self._sample(repo_sha="sha-B")
        assert a.intent_hash != b.intent_hash

    def test_intent_hash_changes_when_framework_changes(self):
        """A different framework string → different cache key."""
        a = self._sample(framework="pytest")
        b = self._sample(framework="jest")
        assert a.intent_hash != b.intent_hash

    def test_intent_hash_stable_for_same_framework(self):
        """Two plans with the same framework string → same cache key."""
        a = self._sample(framework="jest")
        b = self._sample(framework="jest")
        assert a.intent_hash == b.intent_hash

    def test_intent_hash_changes_when_invariants_change(self):
        from harness.test_plan import TestPlan, Invariant
        base = dict(
            plan_id="plan-1", run_id="run-1", spec_id="spec-1",
            repo_url="r", repo_sha="s", framework="pytest",
            files=["src/x.py"], risk="medium", requires_browser=False,
        )
        a = TestPlan(
            **base,
            invariants=[Invariant(id="i1", description="a", target="t")],
        )
        b = TestPlan(
            **base,
            invariants=[Invariant(id="i1", description="b", target="t")],
        )
        assert a.intent_hash != b.intent_hash

    def test_intent_hash_stable_under_invariant_ordering(self):
        """Sorting the invariants differently must NOT change the hash.
        (The hash is the cache key; it must be order-stable.)"""
        from harness.test_plan import TestPlan, Invariant
        base = dict(
            plan_id="plan-1", run_id="run-1", spec_id="spec-1",
            repo_url="r", repo_sha="s", framework="pytest",
            files=["src/x.py"], risk="medium", requires_browser=False,
        )
        invs_a = [
            Invariant(id="i1", description="a", target="t1"),
            Invariant(id="i2", description="b", target="t2"),
            Invariant(id="i3", description="c", target="t3"),
        ]
        invs_b = list(reversed(invs_a))
        plan_a = TestPlan(**base, invariants=invs_a)
        plan_b = TestPlan(**base, invariants=invs_b)
        assert plan_a.intent_hash == plan_b.intent_hash

    def test_any_framework_string_accepted(self):
        """The framework string is FREE-FORM. The C2.1 v1 enum
        was wrong: the industry convention is open-ended
        (testRigor: "extendable by allowing you to support your own
        phrases"; Greptile TREX: "Any language & environment"; AWS
        universal-test-runner: adapter model). TestAI follows the
        Greptile TREX pattern: there is NO result-parsing layer. The
        agent runs the framework via `test_executor` and reads the
        result file natively."""
        # Conventional names work
        for fw in ("pytest", "jest", "vitest", "mocha", "rspec",
                   "playwright", "cypress", "go-test", "junit",
                   "xunit", "rust-test", "bun:test", "kotlin-test"):
            plan = self._sample(framework=fw)
            assert plan.framework == fw
        # Custom / unknown names are accepted too — the agent
        # passes the string through to the test runner verbatim.
        for fw in ("our-internal-test-runner-v3", "spec-from-acme",
                   "fancy-stuff-2026", "", "中文框架"):
            plan = self._sample(framework=fw)
            assert plan.framework == fw

    def test_invalid_risk_rejected(self):
        with pytest.raises(ValueError, match="risk"):
            self._sample(risk="extreme")


# ---------------------------------------------------------------------------
# compute_intent_hash — the cache-key function
# ---------------------------------------------------------------------------


class TestComputeIntentHash:
    def test_same_plan_twice_yields_same_hash(self):
        from harness.test_plan import TestPlan, Invariant, compute_intent_hash
        plan = TestPlan(
            plan_id="p", run_id="r", spec_id="s",
            repo_url="u", repo_sha="abc", framework="pytest",
            invariants=[Invariant(id="i1", description="d", target="t")],
        )
        h1 = compute_intent_hash(plan)
        h2 = compute_intent_hash(plan)
        assert h1 == h2

    def test_hash_format(self):
        """The hash is a 64-char hex string (SHA-256)."""
        from harness.test_plan import TestPlan, compute_intent_hash
        plan = TestPlan(
            plan_id="p", run_id="r", spec_id="s",
            repo_url="u", repo_sha="abc", framework="pytest",
        )
        h = compute_intent_hash(plan)
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_files_order_does_not_affect_hash(self):
        from harness.test_plan import TestPlan, compute_intent_hash
        a = TestPlan(
            plan_id="p", run_id="r", spec_id="s",
            repo_url="u", repo_sha="abc", framework="pytest",
            files=["a.py", "b.py", "c.py"],
        )
        b = TestPlan(
            plan_id="p", run_id="r", spec_id="s",
            repo_url="u", repo_sha="abc", framework="pytest",
            files=["c.py", "a.py", "b.py"],
        )
        assert compute_intent_hash(a) == compute_intent_hash(b)


# ---------------------------------------------------------------------------
# InMemoryTestPlanStore — the test-friendly adapter
# ---------------------------------------------------------------------------


class TestInMemoryTestPlanStore:
    def _plan(self, **overrides):
        from harness.test_plan import TestPlan
        defaults = dict(
            plan_id="p1", run_id="r1", spec_id="s1",
            repo_url="u", repo_sha="abc", framework="pytest",
        )
        defaults.update(overrides)
        return TestPlan(**defaults)

    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self):
        from harness.test_plan import InMemoryTestPlanStore
        store = InMemoryTestPlanStore()
        plan = self._plan()
        await store.save(plan)
        got = await store.get_by_id(plan.plan_id)
        assert got is plan

    @pytest.mark.asyncio
    async def test_get_by_id_miss(self):
        from harness.test_plan import InMemoryTestPlanStore
        store = InMemoryTestPlanStore()
        assert await store.get_by_id("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_by_intent_hash_hit(self):
        """Cache hit: a plan with the same intent_hash is found."""
        from harness.test_plan import InMemoryTestPlanStore
        store = InMemoryTestPlanStore()
        a = self._plan(plan_id="p1")
        b = self._plan(plan_id="p2")
        assert a.intent_hash == b.intent_hash  # same inputs -> same hash
        await store.save(a)
        got = await store.get_by_intent_hash(b.intent_hash)
        assert got is a

    @pytest.mark.asyncio
    async def test_get_by_intent_hash_miss(self):
        from harness.test_plan import InMemoryTestPlanStore
        store = InMemoryTestPlanStore()
        # Save plan with sha="abc"
        await store.save(self._plan(repo_sha="abc"))
        # Lookup with sha="def" — no cache hit
        got = await store.get_by_intent_hash(
            "0" * 64,  # any unknown hash
        )
        assert got is None

    @pytest.mark.asyncio
    async def test_list_for_spec(self):
        from harness.test_plan import InMemoryTestPlanStore
        store = InMemoryTestPlanStore()
        await store.save(self._plan(plan_id="a", spec_id="spec-A"))
        await store.save(self._plan(plan_id="b", spec_id="spec-A"))
        await store.save(self._plan(plan_id="c", spec_id="spec-B"))
        a_plans = await store.list_for_spec("spec-A")
        assert len(a_plans) == 2
        assert {p.plan_id for p in a_plans} == {"a", "b"}
        b_plans = await store.list_for_spec("spec-B")
        assert len(b_plans) == 1
        assert b_plans[0].plan_id == "c"
        assert await store.list_for_spec("spec-C") == []

    @pytest.mark.asyncio
    async def test_save_overwrites_on_same_id(self):
        from harness.test_plan import InMemoryTestPlanStore
        store = InMemoryTestPlanStore()
        a = self._plan(plan_id="p1", repo_sha="abc")
        await store.save(a)
        b = self._plan(plan_id="p1", repo_sha="def")
        await store.save(b)
        got = await store.get_by_id("p1")
        assert got is b

    def test_implements_protocol(self):
        """The in-memory adapter MUST be a runtime-checkable instance
        of `TestPlanStore`. The Postgres adapter will need the same."""
        from harness.test_plan import InMemoryTestPlanStore, TestPlanStore
        store = InMemoryTestPlanStore()
        assert isinstance(store, TestPlanStore)

    def test_protocol_has_expected_methods(self):
        """Guard against drift: the protocol defines 4 methods, no
        more, no less."""
        from harness.test_plan import TestPlanStore
        methods = [m for m in dir(TestPlanStore) if not m.startswith("_")]
        assert set(methods) == {"save", "get_by_id", "get_by_intent_hash", "list_for_spec"}


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


class TestConvenienceHelpers:
    def _plan(self, **overrides):
        from harness.test_plan import TestPlan
        defaults = dict(
            plan_id="p1", run_id="r1", spec_id="s1",
            repo_url="u", repo_sha="abc", framework="pytest",
        )
        defaults.update(overrides)
        return TestPlan(**defaults)

    @pytest.mark.asyncio
    async def test_get_cached_plan_delegates_to_store(self):
        from harness.test_plan import InMemoryTestPlanStore, get_cached_plan
        store = InMemoryTestPlanStore()
        plan = self._plan()
        await store.save(plan)
        got = await get_cached_plan(store, plan.intent_hash)
        assert got is plan

    @pytest.mark.asyncio
    async def test_save_plan_delegates_to_store(self):
        from harness.test_plan import InMemoryTestPlanStore, save_plan, get_cached_plan
        store = InMemoryTestPlanStore()
        plan = self._plan()
        await save_plan(store, plan)
        got = await get_cached_plan(store, plan.intent_hash)
        assert got is plan


# ---------------------------------------------------------------------------
# ID generators
# ---------------------------------------------------------------------------


class TestIdGenerators:
    def test_new_plan_id_is_uuid(self):
        from harness.test_plan import new_plan_id
        pid = new_plan_id()
        assert isinstance(pid, str)
        # UUID v4 format
        import uuid
        uuid.UUID(pid)  # raises if not a valid UUID

    def test_new_plan_id_unique(self):
        from harness.test_plan import new_plan_id
        ids = {new_plan_id() for _ in range(100)}
        assert len(ids) == 100

    def test_new_invariant_id_unique(self):
        from harness.test_plan import new_invariant_id
        ids = {new_invariant_id() for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# Role loader
# ---------------------------------------------------------------------------


class TestTestPlannerRole:
    def test_role_file_exists(self):
        """The test-planner role file is at
        ``.testai/prompts/agents/test-planner.txt`` (matches the
        convention used by `planner.txt`, `coordinator.txt`, etc.)."""
        from pathlib import Path
        role = (
            Path(__file__).resolve().parents[2]
            / ".testai" / "prompts" / "agents" / "test-planner.txt"
        )
        assert role.is_file(), f"role file missing: {role}"

    def test_role_body_loads(self):
        from harness.test_plan import get_test_planner_prompt
        body = get_test_planner_prompt()
        assert body, "test-planner role body is empty"
        # The role body must tell the planner it is read-only
        assert "read-only" in body.lower()
        # The role body must tell the planner NOT to write code
        assert "do not" in body.lower() and "code" in body.lower()
        # The role body must define the output JSON schema
        assert "framework" in body
        assert "invariants" in body

    def test_role_body_tells_planner_to_use_tech_stack_detector(self):
        """The planner must use the existing auto-detection tool, not
        pick from a hardcoded list."""
        from harness.test_plan import get_test_planner_prompt
        body = get_test_planner_prompt()
        # The role must tell the planner to use tech_stack_detector
        # (already in the orchestrator's toolset).
        assert "tech_stack_detector" in body
        # The role must NOT pin a fixed list of frameworks.
        for pinned in ("\"playwright\" | \"pytest\" | \"vitest\" | \"go-test\"",
                       "MUST be one of the four values"):
            assert pinned not in body, (
                f"role body still pins a fixed list: {pinned!r}"
            )
        # The role must explain that the framework string is
        # free-form and that there is no result-parsing layer
        # (the Greptile TREX pattern: the agent reads results
        # natively).
        assert "free-form" in body.lower()
        assert "no result" in body.lower() or "no parsing" in body.lower() or "Greptile" in body


# ---------------------------------------------------------------------------
# Convention guard: the 4 framework values are the official ones
# ---------------------------------------------------------------------------


class TestFrameworkAndRiskEnums:
    def test_frameworks_constant_no_longer_exists(self):
        """The C2.1 v1 `FRAMEWORKS` enum was wrong (industry
        convention is open ended). It has been removed in favor of
        a free-form framework string."""
        from harness import test_plan
        assert not hasattr(test_plan, "FRAMEWORKS"), (
            "FRAMEWORKS enum was reintroduced — drop it; framework is "
            "a free-form string passed verbatim to the test runner"
        )

    def test_risks_exact_set(self):
        """Risk is a small fixed enum (low/medium/high is a common
        QA convention; not as contentious as frameworks)."""
        from harness.test_plan import RISKS
        assert RISKS == ("low", "medium", "high")

    def test_invariant_categories_set(self):
        from harness.test_plan import INVARIANT_CATEGORIES
        assert INVARIANT_CATEGORIES == (
            "happy-path", "edge-case", "regression", "security", "performance",
        )

    def test_intent_hash_distinguishes_unrecognised_frameworks(self):
        """Even an unknown framework string is part of the cache key
        (so re-plans with the same unknown framework hit cache, but
        a different unknown framework misses — which is the
        correct behavior: the user might have switched runtimes)."""
        from harness.test_plan import TestPlan, compute_intent_hash
        base = dict(plan_id="p", run_id="r", spec_id="s",
                    repo_url="u", repo_sha="abc")
        a = TestPlan(**base, framework="our-internal-runner-v3")
        b = TestPlan(**base, framework="our-internal-runner-v4")
        assert compute_intent_hash(a) != compute_intent_hash(b)
