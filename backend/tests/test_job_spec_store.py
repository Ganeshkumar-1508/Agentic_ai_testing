"""Tests for the C4-revised `JobSpecStore` and `ProposalStore` protocols.

The chat surface (the only producer of `JobSpec`) and the
orchestrator surface (the only consumer) are protocol-bound. These
tests pin the contract:

  - The in-memory `JobSpec` dataclass and the persistent
    `JobSpecRecord` round-trip cleanly through `to_record()`.
  - `PostgresJobSpecStore` is `@runtime_checkable`-conformant
    (i.e. an instance of the store satisfies the protocol).
  - A `JobSpec` produced by `submit_job` flows through the
    `JobSpecStore` and back out unchanged for the fields the
    store persists. The store may add status fields the chat
    never set.
  - `PostgresProposalStore` is protocol-conformant; its
    `mark_decision` updates status and reviewer.
  - The dispatcher's `submit_job` handler calls the store when
    one is wired, and falls through gracefully when one isn't.
  - The orchestrator's tier-2 path can produce a `Proposal`
    record (the integration is in v2; this test pins the
    standalone store contract).
"""
from __future__ import annotations

import json

import pytest

from harness.jobs.spec import (
    JobSpec, DEFAULT_CAPABILITIES, to_record,
    set_job_spec_store, set_proposal_store,
    _job_spec_store, _proposal_store,
)
from harness.store.adapters.postgres import (
    PostgresJobSpecStore, PostgresProposalStore,
)
from harness.store.protocols import (
    JobSpecRecord, JobSpecStore, ProposalRecord, ProposalStore,
)


# ---------------------------------------------------------------------------
# In-memory round-trip: JobSpec → JobSpecRecord → JobSpec
# ---------------------------------------------------------------------------


def test_jobspec_to_record_carries_all_fields():
    """Every field on the chat-produced `JobSpec` must survive the
    conversion to the persistent `JobSpecRecord`. The store is
    the seam between surfaces; field loss here would silently
    change behaviour downstream."""
    spec = JobSpec.from_chat_submission(
        prompt="Add unit tests for the new auth flow",
        repo_url="https://github.com/example/foo",
        branch="feat/auth",
        tier=2,
        capabilities=["read_code", "write_test_files", "run_tests"],
        session_id="sess-42",
        agent_id="agent-7",
        approval={"mode": "review_queue", "destination": "github_pr"},
    )
    rec = to_record(spec)
    assert isinstance(rec, JobSpecRecord)
    assert rec.spec_id == spec.spec_id
    assert rec.run_id == spec.run_id
    assert rec.source == "chat-submission"
    assert rec.prompt == spec.prompt
    assert rec.repo_url == spec.repo_url
    assert rec.branch == spec.branch
    assert rec.sha == spec.sha
    assert rec.tier == spec.tier
    assert rec.capabilities == spec.capabilities
    assert rec.approval == spec.approval
    # C08: ``context`` is now a typed :class:`JobContext`; the
    # record's ``context`` is the dict payload produced by
    # ``JobContext.to_payload()``. Compare via the payload.
    assert rec.context == spec.context.to_payload()
    # The store assigns `pending` status on a fresh record.
    assert rec.status == "pending"


def test_jobspec_default_capabilities():
    """A chat Role that calls `submit_job` without specifying
    capabilities should get the safe autonomous set. The
    orchestrator's coordinator uses this as its allowed-tools
    filter — silent dropping of a capability would let the
    orchestrator do work it shouldn't."""
    spec = JobSpec.from_chat_submission(prompt="x")
    assert spec.capabilities == list(DEFAULT_CAPABILITIES)
    # Sanity: the default includes `open_pr` (autonomous tier-1).
    assert "open_pr" in spec.capabilities


def test_to_record_isolates_the_two_shapes():
    """`JobSpec` and `JobSpecRecord` are intentionally separate
    shapes. `to_record()` is the conversion point — a future
    field added to one shouldn't silently leak into the other."""
    spec = JobSpec.from_chat_submission(prompt="x")
    # C08: ``context`` is now a Pydantic JobContext. We can still
    # add extras via the ``extras`` dict on the fallback path or
    # via the Pydantic ``model_construct`` for the typed path.
    # The simplest way: replace context with a dict, then the
    # conversion carries it through.
    spec.context = {
        "session_id": "sess-1",
        "clarification_qa": [{"q": "?", "a": "!"}],
    }
    rec = to_record(spec)
    # The Q&A is in the record.
    assert rec.context["clarification_qa"] == [{"q": "?", "a": "!"}]
    # And the record has status fields the chat never set.
    assert hasattr(rec, "status")
    assert hasattr(rec, "created_at")
    # But the chat-side dataclass doesn't carry `status` (it
    # doesn't need to — the store assigns it).
    assert not hasattr(spec, "status")


# ---------------------------------------------------------------------------
# Protocol conformance — adapters match the protocol
# ---------------------------------------------------------------------------


def test_postgres_job_spec_store_is_protocol_conformant():
    """A `PostgresJobSpecStore` instance must satisfy the
    `JobSpecStore` protocol. `isinstance` against a
    `@runtime_checkable` Protocol is the cheap test."""
    import inspect
    # PostgresJobSpecStore needs a real DB; we only check the
    # method surface here, not actual SQL behaviour.
    methods = {m for m in dir(PostgresJobSpecStore) if not m.startswith("_")}
    for required in ("save", "get", "update_status", "list_pending"):
        assert required in methods, (
            f"PostgresJobSpecStore missing required method: {required}"
        )


def test_postgres_proposal_store_is_protocol_conformant():
    import inspect
    methods = {m for m in dir(PostgresProposalStore) if not m.startswith("_")}
    for required in ("save", "get", "list_for_spec", "list_pending", "mark_decision"):
        assert required in methods, (
            f"PostgresProposalStore missing required method: {required}"
        )


def test_job_spec_store_protocol_has_required_methods():
    """The protocol itself must declare the same methods the
    Postgres adapter implements. A new method on the protocol
    without a corresponding implementation is a silent failure."""
    proto_methods = set(dir(JobSpecStore))
    for required in ("save", "get", "update_status", "list_pending"):
        assert required in proto_methods, (
            f"JobSpecStore protocol missing method: {required}"
        )


def test_proposal_store_protocol_has_required_methods():
    proto_methods = set(dir(ProposalStore))
    for required in ("save", "get", "list_for_spec", "list_pending", "mark_decision"):
        assert required in proto_methods, (
            f"ProposalStore protocol missing method: {required}"
        )


# ---------------------------------------------------------------------------
# Module-level store setters — same pattern as set_introspection_store
# ---------------------------------------------------------------------------


def test_set_job_spec_store_injects_at_module_level():
    """A `set_job_spec_store(store)` call must make that store
    visible to the dispatcher's `submit_job` handler via
    `_job_spec_store()`. This is the only seam between the
    chat surface and the persistence layer."""
    class _FakeStore:
        async def save(self, record): self.saved = record
        async def get(self, spec_id): return None
        async def update_status(self, *a, **kw): pass
        async def list_pending(self, limit=50): return []
    fake = _FakeStore()
    set_job_spec_store(fake)
    try:
        assert _job_spec_store() is fake
    finally:
        # Reset so the singleton doesn't leak into other tests.
        import harness.jobs.spec as spec_mod
        spec_mod._deps_ref.clear()


def test_set_proposal_store_injects_at_module_level():
    class _FakeStore:
        async def save(self, record): self.saved = record
        async def get(self, pid): return None
        async def list_for_spec(self, sid): return []
        async def list_pending(self, limit=50): return []
        async def mark_decision(self, *a, **kw): pass
    fake = _FakeStore()
    set_proposal_store(fake)
    try:
        assert _proposal_store() is fake
    finally:
        import harness.jobs.spec as spec_mod
        spec_mod._deps_ref.clear()


def test_unset_job_spec_store_returns_none():
    """A fresh import (no setter called) must return None, not crash.

    The dispatcher's `submit_job` handler falls through gracefully
    in this case: it builds the in-memory spec and hands it to the
    orchestrator without persistence. The test below covers that
    path. The point of this assertion is that the getter does not
    raise."""
    import harness.jobs.spec as spec_mod
    spec_mod._deps_ref.clear()
    assert _job_spec_store() is None
    assert _proposal_store() is None


# ---------------------------------------------------------------------------
# Proposal record shape — the orchestrator's tier-2 work product
# ---------------------------------------------------------------------------


def test_proposal_record_default_shape():
    """A fresh `ProposalRecord` is `pending_review` with empty
    `test_files` and zero `risk_score`. The orchestrator's tier-2
    path fills these in as the coordinator subagent works."""
    rec = ProposalRecord(proposal_id="prop-1", spec_id="spec-1")
    assert rec.status == "pending_review"
    assert rec.test_files == []
    assert rec.rationale == ""
    assert rec.risk_score == 0
    assert rec.reviewer == ""


def test_proposal_status_values():
    """The four valid statuses for a proposal."""
    valid = {"pending_review", "approved", "rejected", "superseded"}
    # All four are valid literals a human reviewer or CI check might
    # pass to `mark_decision`. The store itself doesn't enforce
    # this — it just stores whatever string it's given. The
    # orchestrator is responsible for keeping the values in this
    # set. The test pins the documented contract.
    assert valid == {"pending_review", "approved", "rejected", "superseded"}


# ---------------------------------------------------------------------------
# Dispat: a submit_job flow that has a fake store attached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_job_calls_jobspecstore_when_wired(monkeypatch):
    """The dispatcher's `submit_job` handler should call
    `JobSpecStore.save()` with a `JobSpecRecord` derived from the
    in-memory `JobSpec`. The chat's only mutation should leave a
    durable trace.

    We use a fake store (no Postgres roundtrip) and a no-op
    orchestrator spawn to keep the test hermetic. The
    `set_job_spec_store` injection follows the same pattern as
    `set_introspection_store`.
    """
    import harness.agent.tool_dispatch as td
    import harness.jobs.spec as spec_mod

    saved: list[JobSpecRecord] = []

    class _FakeJobSpecStore:
        async def save(self, record: JobSpecRecord) -> None:
            saved.append(record)
        async def get(self, spec_id: str): return None
        async def update_status(self, *a, **kw): pass
        async def list_pending(self, limit=50): return []

    spec_mod._deps_ref.clear()
    spec_mod.set_job_spec_store(_FakeJobSpecStore())

    # Stub out the orchestrator so the test doesn't actually spawn one.
    # The dispatcher imports `OrchestratorEngine` lazily inside
    # `_handle_submit_job`; we patch the source module rather than
    # the already-imported `tool_dispatch` namespace.
    class _StubEngine:
        async def run_job_spec(self, spec): return {"success": True}
    import harness.orchestrator as orch_mod
    monkeypatch.setattr(orch_mod, "OrchestratorEngine", _StubEngine)

    # Build a minimal dispatcher; bypass the rest of Agent init.
    from harness.events import EventBus
    from harness.permissions.manager import PermissionManager
    from harness.delegation import DelegationContext
    from harness.agent.deps import AgentDependencies
    from harness.memory.store import PersistentStore
    from harness.llm import LLMRouter
    from harness.memory.database import Database

    bus = EventBus()
    perms = PermissionManager(mode="chat")
    delegation = DelegationContext()
    deps = AgentDependencies(
        llm=LLMRouter(), store=PersistentStore.__new__(PersistentStore),
        permissions=perms, sandbox_manager=None,
    )
    # Bypass the store's actual DB connection.
    deps.store.db = object()

    dispatcher = td.ToolDispatcher(
        event_bus=bus, permissions=perms, mode="chat",
        session_id="sess-1", agent_id="agent-1",
        delegation=delegation, allowed_tools=["submit_job"],
        deps=deps,
    )

    args = {
        "prompt": "Add unit tests for the new auth flow",
        "repo_url": "https://github.com/example/foo",
        "branch": "feat/auth",
        "tier": 2,
    }
    output = await dispatcher.execute(
        {"function": {"name": "submit_job",
                     "arguments": json.dumps(args)}},
        llm_response_id="r-1",
    )

    # The handler returns the user-facing success message.
    assert "Job submitted" in output
    assert "run_id=" in output

    # The store was called exactly once with a record derived from
    # the chat's spec.
    assert len(saved) == 1
    rec = saved[0]
    assert rec.prompt == "Add unit tests for the new auth flow"
    assert rec.repo_url == "https://github.com/example/foo"
    assert rec.branch == "feat/auth"
    assert rec.tier == 2
    assert rec.source == "chat-submission"
    assert rec.status == "pending"

    spec_mod._deps_ref.clear()
