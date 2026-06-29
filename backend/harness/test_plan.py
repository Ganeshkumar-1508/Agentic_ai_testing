"""TestPlan artifact — first-class record of what tests we will write
and why, produced before any code is written.

Per the C2.1 deepening of the architecture review, a TestPlan is the
durable handoff between the explore phase and the test-generation
phase. It is the cache key, the traceable unit, and the
user-reviewable artifact (the Momentic convention). The plan is
consumed by `test_generator`; if a plan with the same `intent_hash`
already exists, we skip generation and go straight to execution.

This module is the data + protocol layer. The actual subagent that
*produces* a TestPlan lives in `.testai/prompts/agents/test-planner.txt`
(declarative role, loaded on demand by `load_agent_prompt`); the
orchestrator wiring that calls it is a follow-up.

Scope (C2.1 v1):
  - `TestPlan` dataclass
  - `Invariant` dataclass
  - `compute_intent_hash()` — deterministic hash for cache lookup
  - `TestPlanStore` Protocol
  - `InMemoryTestPlanStore` — test-friendly implementation
  - `get_cached_plan()` / `save_plan()` helpers
  - `get_test_planner_prompt()` — loads the role body

Out of scope (follow-up):
  - Postgres-backed `TestPlanStore` adapter
  - Kanban "TestPlanProposal" card
  - `test_generator.py` consumer integration
  - Orchestrator invocation of the planner subagent
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

# Risk enum. The store round-trips this as a TEXT column.
RISKS: tuple[str, ...] = ("low", "medium", "high")

# Invariant category enum.
INVARIANT_CATEGORIES: tuple[str, ...] = (
    "happy-path", "edge-case", "regression", "security", "performance",
)

# Framework is a free-form string. The C2.1 v1 enum ("playwright" |
# "pytest" | "vitest" | "go-test") was wrong: the industry convention
# is open-ended (testRigor: "extendable by allowing you to support
# your own phrases"; Greptile TREX: "Any language & environment";
# AWS universal-test-runner: "delegates to the appropriate adapter in
# order to execute tests for a specific framework"). TestAI follows
# the Greptile TREX pattern: there is NO result-parsing layer. The
# agent runs the framework via `test_executor` (or `bash`), the
# framework emits whatever output it natively emits (JUnit XML for
# pytest/jest/vitest/playwright/mocha/go-test, Playwright JSON for
# Playwright, Allure for the Allure crowd), and the agent reads the
# result file natively via `read_file`. No parser in the middle.
# The C2.1 planner picks the framework string from the prompt,
# from `tech_stack_detector`, or from `repo_analyzer`'s manifest-
# based detection; the string is whatever the runtime invocation
# will use downstream.


@dataclass(frozen=True, slots=True)
class Invariant:
    """A single property the tests will assert.

    Invariants are the durable, user-reviewable units of the plan.
    A failure on a test links back to the `Invariant.id` it was
    written for, so the user can see "we asserted that the checkout
    rejects expired cards" without re-reading the test.
    """
    id: str
    description: str
    target: str                            # file:line of the code being tested
    category: str = "happy-path"          # one of INVARIANT_CATEGORIES
    risk: str = "medium"                  # one of RISKS

    def __post_init__(self) -> None:
        if self.category not in INVARIANT_CATEGORIES:
            raise ValueError(
                f"Invariant category {self.category!r} must be one of "
                f"{INVARIANT_CATEGORIES}"
            )
        if self.risk not in RISKS:
            raise ValueError(
                f"Invariant risk {self.risk!r} must be one of {RISKS}"
            )


@dataclass
class TestPlan:
    """A first-class record of what tests we will write and why.

    The plan is produced before any test code is written. The
    `intent_hash` is the cache key: when a new run targets the
    same `(repo_url, repo_sha, framework, invariants)`, the planner
    can short-circuit and reuse this plan.

    `framework` is a free-form string ("pytest", "jest", "mocha",
    "rspec", "playwright", whatever the user mentioned in the
    prompt or `tech_stack_detector` reported). It is NOT validated
    against an enum. There is no result-parsing layer in TestAI
    (the Greptile TREX pattern): the agent runs the framework via
    `test_executor` and reads the result file natively. The
    framework string is whatever the runtime invocation will use
    downstream.
    """
    plan_id: str
    run_id: str
    spec_id: str
    repo_url: str
    repo_sha: str                          # pins plan to repo state
    framework: str                         # free-form; no enum
    invariants: list[Invariant] = field(default_factory=list)
    files: list[str] = field(default_factory=list)   # target files
    risk: str = "medium"                  # one of RISKS — overall plan risk
    requires_browser: bool = False
    intent_hash: str = ""                 # set by compute_intent_hash; cache key
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.risk not in RISKS:
            raise ValueError(
                f"TestPlan risk {self.risk!r} must be one of {RISKS}"
            )
        if not self.intent_hash:
            object.__setattr__(self, "intent_hash", compute_intent_hash(self))


# ---------------------------------------------------------------------------
# Intent hash — deterministic cache key
# ---------------------------------------------------------------------------

def _normalize_invariants(invariants: list[Invariant]) -> list[dict[str, str]]:
    """Project invariants to a canonical, order-stable shape for hashing.

    Sorts by id (UUIDs are stable identifiers, not hashes themselves)
    so the hash is invariant to ordering.
    """
    return [
        {
            "id": inv.id,
            "description": inv.description,
            "target": inv.target,
            "category": inv.category,
            "risk": inv.risk,
        }
        for inv in sorted(invariants, key=lambda i: i.id)
    ]


def compute_intent_hash(plan: TestPlan) -> str:
    """Deterministic SHA-256 of the plan's identifying inputs.

    Two plans with the same `(repo_url, repo_sha, framework, files,
    invariants, requires_browser)` hash to the same intent. The hash
    is the cache key used by `get_cached_plan()` to short-circuit
    regeneration on a re-run with the same intent.
    """
    payload = {
        "repo_url": plan.repo_url,
        "repo_sha": plan.repo_sha,
        "framework": plan.framework,
        "requires_browser": plan.requires_browser,
        "files": sorted(plan.files),
        "invariants": _normalize_invariants(plan.invariants),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def new_plan_id() -> str:
    """Generate a fresh plan_id. Used by callers that don't have one
    yet (e.g. the planner subagent)."""
    return str(uuid.uuid4())


def new_invariant_id() -> str:
    """Generate a fresh invariant id. The C2.1 Verifier cross-checks
    that the test file actually exercises this invariant."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Store Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class TestPlanStore(Protocol):
    """The persistence contract for `TestPlan`.

    Two production adapters will exist eventually:
      - `PostgresTestPlanStore` (per Q4's "one store per domain"
        convention; see `harness/store/adapters/postgres.py` for the
        existing Postgres adapters)
      - `InMemoryTestPlanStore` (tests; this module)
    """

    async def save(self, plan: TestPlan) -> None:
        """Insert or update a plan. Idempotent on `plan_id`."""

    async def get_by_id(self, plan_id: str) -> TestPlan | None:
        """Lookup by primary key."""

    async def get_by_intent_hash(self, intent_hash: str) -> TestPlan | None:
        """Cache lookup. Returns the plan whose `intent_hash` matches,
        or None if no plan exists for this intent. The planner
        uses this to short-circuit regeneration."""

    async def list_for_spec(self, spec_id: str) -> list[TestPlan]:
        """All plans attached to a given JobSpec, newest first."""


class InMemoryTestPlanStore:
    """Thread-unsafe in-memory `TestPlanStore` for tests.

    The C2.1 planner subagent will use the Postgres-backed store in
    production; this in-memory impl exists so unit tests can exercise
    the cache-hit / cache-miss flow without a database.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, TestPlan] = {}
        self._by_intent: dict[str, str] = {}  # intent_hash -> plan_id

    async def save(self, plan: TestPlan) -> None:
        self._by_id[plan.plan_id] = plan
        self._by_intent[plan.intent_hash] = plan.plan_id

    async def get_by_id(self, plan_id: str) -> TestPlan | None:
        return self._by_id.get(plan_id)

    async def get_by_intent_hash(self, intent_hash: str) -> TestPlan | None:
        plan_id = self._by_intent.get(intent_hash)
        if plan_id is None:
            return None
        return self._by_id.get(plan_id)

    async def list_for_spec(self, spec_id: str) -> list[TestPlan]:
        matches = [p for p in self._by_id.values() if p.spec_id == spec_id]
        matches.sort(key=lambda p: p.created_at, reverse=True)
        return matches

    def __len__(self) -> int:
        return len(self._by_id)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

async def get_cached_plan(
    store: TestPlanStore,
    intent_hash: str,
) -> TestPlan | None:
    """Cache lookup by intent. Returns None on miss.

    Equivalent to `store.get_by_intent_hash(intent_hash)`; exists as
    a named helper so callers (planner, test_generator) can read
    intent at the call site without re-importing the store protocol.
    """
    return await store.get_by_intent_hash(intent_hash)


async def save_plan(store: TestPlanStore, plan: TestPlan) -> None:
    """Persist a plan. The store indexes by `plan_id` and
    `intent_hash` so subsequent `get_cached_plan` calls can find it."""
    await store.save(plan)


# ---------------------------------------------------------------------------
# Role loader
# ---------------------------------------------------------------------------

def get_test_planner_prompt() -> str:
    """Load the test-planner role body from
    ``.testai/prompts/agents/test-planner.txt``.

    The C2.1 planner is a read-only subagent. The role body
    describes the planner's contract: produce a `TestPlan` (a list
    of `Invariant`s over the target files) without writing any
    code. The orchestrator wires the actual subagent invocation
    in a follow-up; this helper just gives the orchestrator a
    stable load path that matches the convention used by
    `planner.txt` (loaded by `prompt_builder.py:229`).
    """
    from harness.prompt_builder import load_agent_prompt
    return load_agent_prompt("test-planner") or ""


__all__ = [
    "Invariant",
    "TestPlan",
    "TestPlanStore",
    "InMemoryTestPlanStore",
    "RISKS",
    "INVARIANT_CATEGORIES",
    "compute_intent_hash",
    "new_plan_id",
    "new_invariant_id",
    "get_cached_plan",
    "save_plan",
    "get_test_planner_prompt",
]
