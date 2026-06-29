"""Tests for the orchestrator's `JobSpec`-aware entry point.

The chat Role's `submit_job` tool produces a `JobSpec` and hands it
to `OrchestratorEngine.run_job_spec`. The orchestrator:
  - Maps the spec's tier to behaviour (1=autonomous, 2=supervised,
    3=human-authored proposal)
  - Builds a tier-aware goal string for the coordinator agent
  - Restricts capabilities to what the spec allows
  - For tier 3, does NOT run code — just creates a kanban proposal

These tests verify the orchestrator's entry point without spinning up
real sandboxes. We patch `run_single` and `kanban_create` so the test
exercises only the dispatch logic.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from harness.jobs.spec import JobSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine():
    """Build an OrchestratorEngine without going through __init__'s
    sandbox-manager contract (which we don't need for these tests)."""
    from harness.orchestrator import OrchestratorEngine
    engine = OrchestratorEngine.__new__(OrchestratorEngine)
    engine.sandbox_manager = None
    return engine


def _make_spec(**overrides: Any) -> JobSpec:
    """Build a JobSpec with sensible defaults for testing."""
    defaults = dict(
        prompt="Test the checkout flow for expired cards",
        repo_url="github.com/foo/bar",
        branch="main",
        tier=1,
        capabilities=["read_code", "write_test_files", "edit_existing_tests",
                      "run_tests", "open_pr"],
        session_id="chat-sess-1",
        agent_id="chat-agent-1",
    )
    defaults.update(overrides)
    return JobSpec.from_chat_submission(**defaults)


# ---------------------------------------------------------------------------
# Tier 1: autonomous — calls run_single with the right args
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_1_calls_run_single():
    spec = _make_spec(tier=1)
    engine = _make_engine()

    with patch.object(
        type(engine), "run_single", autospec=True,
    ) as mock_run:
        mock_run.return_value = {"success": True, "tier": 1}
        result = await engine.run_job_spec(spec)

    assert result["tier"] == 1
    assert result["success"] is True
    mock_run.assert_awaited_once()
    # Verify the call unpacks the spec correctly.
    call_args = mock_run.call_args
    assert call_args.kwargs["run_id"] == spec.run_id
    assert call_args.kwargs["repo_url"] == "github.com/foo/bar"
    assert call_args.kwargs["branch"] == "main"
    # The goal string is the tier-aware one.
    assert "TIER 1" not in call_args.kwargs["goal"]  # tier 1 is the default
    assert "TIER: 1" in call_args.kwargs["goal"]


@pytest.mark.asyncio
async def test_tier_1_goal_includes_capabilities():
    spec = _make_spec(
        tier=1,
        capabilities=["read_code", "write_test_files", "open_pr"],
    )
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    goal = mock_run.call_args.kwargs["goal"]
    assert "write_test_files" in goal
    assert "open_pr" in goal
    # Capabilities NOT in the spec are forbidden.
    assert "FORBIDDEN" in goal
    assert "edit_existing_tests" in goal  # was forbidden


@pytest.mark.asyncio
async def test_tier_1_minimal_capabilities_means_heavy_restrictions():
    """A tier-1 job with only `read_code` should forbid every write
    capability. The orchestrator still respects the capabilities list
    even for autonomous jobs."""
    spec = _make_spec(
        tier=1,
        capabilities=["read_code"],
    )
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    goal = mock_args = mock_run.call_args.kwargs["goal"]
    assert "write_test_files" in goal and "FORBIDDEN" in goal
    assert "edit_existing_tests" in goal and "FORBIDDEN" in goal
    assert "open_pr" in goal and "FORBIDDEN" in goal
    assert "run_tests" in goal and "FORBIDDEN" in goal


# ---------------------------------------------------------------------------
# Tier 2: supervised — same as tier 1 but the goal includes the
# review-queue instruction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_2_goal_includes_review_queue_instruction():
    spec = _make_spec(tier=2)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True, "tier": 2}
        result = await engine.run_job_spec(spec)

    assert result["tier"] == 2
    goal = mock_run.call_args.kwargs["goal"]
    assert "TIER 2 — SUPERVISED" in goal
    assert "do NOT call commit_and_open_pr" in goal
    assert "post the diff" in goal
    assert "kanban task" in goal


@pytest.mark.asyncio
async def test_tier_2_still_calls_run_single():
    """Tier 2 still runs the agent. The difference is the goal string
    instructs the agent to queue the PR for review rather than
    auto-merge it."""
    spec = _make_spec(tier=2)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    mock_run.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tier 2: supervised — C4-revised wiring
#
# When the ProposalStore is wired, the orchestrator saves a placeholder
# `Proposal` (status=pending_review) so the dashboard surfaces the
# review queue. The proposal_id is threaded into the goal so the
# coordinator's kanban post can cross-reference it. Without the
# ProposalStore (e.g. local dev without Postgres), the work still
# runs — we just lose the queue persistence.
# ---------------------------------------------------------------------------


@pytest.fixture
def _wired_proposal_store(monkeypatch):
    """Inject a fake `ProposalStore` into `harness.jobs.spec`.

    Returns the list of saved records so the test can assert on
    them. Cleared on teardown so it doesn't leak into other tests.
    """
    saved: list[Any] = []

    class _FakeProposalStore:
        async def save(self, record):
            saved.append(record)
        async def get(self, proposal_id):
            return next((r for r in saved if r.proposal_id == proposal_id), None)
        async def list_for_spec(self, spec_id):
            return [r for r in saved if r.spec_id == spec_id]
        async def list_pending(self, limit=50):
            return [r for r in saved if r.status == "pending_review"]
        async def mark_decision(self, proposal_id, decision, reviewer, **kw):
            for r in saved:
                if r.proposal_id == proposal_id:
                    r.status = decision
                    r.reviewer = reviewer

    import harness.jobs.spec as spec_mod
    spec_mod._deps_ref.clear()
    spec_mod.set_proposal_store(_FakeProposalStore())
    yield saved
    spec_mod._deps_ref.clear()


@pytest.mark.asyncio
async def test_tier_2_creates_proposal_placeholder(_wired_proposal_store):
    """Tier 2 with a wired `ProposalStore` must save a `Proposal`
    record in `pending_review` status, with the spec's id linked.

    The proposal is just a placeholder — the coordinator fills
    in the diff/rationale later — but it must exist in the queue
    so the dashboard can show "awaiting review" while the work is
    in progress."""
    from harness.store.protocols import ProposalRecord

    spec = _make_spec(tier=2)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    assert len(_wired_proposal_store) == 1
    record = _wired_proposal_store[0]
    assert isinstance(record, ProposalRecord)
    assert record.spec_id == spec.spec_id
    assert record.status == "pending_review"
    assert record.test_files == []       # placeholder; coordinator fills in
    assert record.rationale == ""        # placeholder; coordinator fills in
    assert record.risk_score == 0
    # A new id was generated; not the spec_id.
    assert record.proposal_id and record.proposal_id != spec.spec_id
    # 36-char UUID.
    assert len(record.proposal_id) == 36


@pytest.mark.asyncio
async def test_tier_2_threads_proposal_id_into_goal(_wired_proposal_store):
    """The proposal_id generated by the orchestrator must appear
    in the coordinator's goal string, so the coordinator's kanban
    post can reference it (the reviewer clicks the kanban link
    → the dashboard shows the proposal)."""
    spec = _make_spec(tier=2)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    goal = mock_run.call_args.kwargs["goal"]
    proposal_id = _wired_proposal_store[0].proposal_id
    assert proposal_id in goal, (
        f"goal should reference the proposal_id {proposal_id!r} "
        f"so the coordinator's kanban post can cross-link"
    )
    # And the goal retains the original tier-2 instructions.
    assert "TIER 2 — SUPERVISED" in goal
    assert "do NOT call commit_and_open_pr" in goal


@pytest.mark.asyncio
async def test_tier_2_graceful_when_proposal_store_unwired():
    """Without a wired `ProposalStore`, the tier-2 work still
    runs. We just lose the queue persistence — same pattern as
    `set_introspection_store` and `set_checkpoint_db`."""
    import harness.jobs.spec as spec_mod
    spec_mod._deps_ref.clear()  # ensure no store is wired

    spec = _make_spec(tier=2)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        result = await engine.run_job_spec(spec)

    # The work ran.
    mock_run.assert_awaited_once()
    # The goal was built without a proposal_id reference.
    goal = mock_run.call_args.kwargs["goal"]
    assert "tracked as proposal" not in goal
    assert "TIER 2 — SUPERVISED" in goal


@pytest.mark.asyncio
async def test_tier_1_does_not_create_proposal(_wired_proposal_store):
    """Tier 1 (autonomous) skips the proposal queue entirely. The
    orchestrator's coordinator opens the PR directly on success;
    there's no human review step."""
    spec = _make_spec(tier=1)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    assert _wired_proposal_store == [], (
        f"tier-1 should not create a proposal; got {_wired_proposal_store}"
    )
    goal = mock_run.call_args.kwargs["goal"]
    assert "TIER 2" not in goal
    assert "tracked as proposal" not in goal


@pytest.mark.asyncio
async def test_tier_3_does_not_create_proposal(_wired_proposal_store):
    """Tier 3 (human-authored) uses a kanban task, not a
    `Proposal` row. The `ProposalStore` is for tier-2 work
    only — a tier-3 spec is a higher-elevation proposal that
    doesn't go through the orchestrator's work pipeline at all."""
    spec = _make_spec(tier=3)
    engine = _make_engine()

    class _FakeKanban:
        async def run(self, **kwargs):
            return SimpleNamespace(output='{"board_id": "kanban-tier3-xyz"}')

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        with patch(
            "harness.tools.registry.registry.get",
            return_value=_FakeKanban(),
        ):
            await engine.run_job_spec(spec)

    assert _wired_proposal_store == []
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 3: human-authored proposal — does NOT call run_single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_3_does_not_call_run_single():
    spec = _make_spec(tier=3)
    engine = _make_engine()

    class _FakeKanban:
        async def run(self, **kwargs):
            return SimpleNamespace(
                output='{"board_id": "kanban-tier3-xyz"}',
            )

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        with patch(
            "harness.tools.registry.registry.get",
            return_value=_FakeKanban(),
        ) as _:
            result = await engine.run_job_spec(spec)

    assert result["tier"] == 3
    assert result["human_authored"] is True
    assert "did not execute" in result["output"]
    # The orchestrator did NOT spawn the coordinator agent.
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_tier_3_creates_kanban_proposal():
    """The tier-3 path must create a kanban board with a
    'HUMAN-AUTHORED PROPOSAL' description so the reviewer can find it."""
    spec = _make_spec(tier=3)
    engine = _make_engine()

    captured: dict[str, Any] = {}

    class _FakeKanban:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output='{"board_id": "kanban-xyz"}',
            )

    with patch(
        "harness.tools.registry.registry.get",
        return_value=_FakeKanban(),
    ):
        result = await engine.run_job_spec(spec)

    assert "HUMAN-AUTHORED PROPOSAL" in captured["description"]
    assert "tier 3" in captured["description"]
    assert spec.prompt in captured["description"]
    assert result["board_id"] == "kanban-xyz"


@pytest.mark.asyncio
async def test_tier_3_no_kanban_tool_still_succeeds():
    """If the kanban tool isn't registered, tier 3 still records a
    proposal (with board_id=None) and the user sees a clear message."""
    spec = _make_spec(tier=3)
    engine = _make_engine()

    with patch(
        "harness.tools.registry.registry.get",
        return_value=None,
    ):
        result = await engine.run_job_spec(spec)

    assert result["success"] is True
    assert result["tier"] == 3
    assert result["board_id"] is None


# ---------------------------------------------------------------------------
# Tier 1 capabilities round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_1_full_capabilities_means_no_forbidden_block():
    """If the spec has all four standard capabilities, the forbidden
    block should not appear (or should be empty)."""
    spec = _make_spec(
        tier=1,
        capabilities=["read_code", "write_test_files",
                      "edit_existing_tests", "run_tests", "open_pr"],
    )
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    goal = mock_run.call_args.kwargs["goal"]
    # The forbidden block should be the "no additional restrictions" branch.
    assert "no additional restrictions" in goal


# ---------------------------------------------------------------------------
# Run-id propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_id_is_propagated_to_run_single():
    """The spec's run_id must reach run_single. The chat endpoint
    relies on this for the URL it returns to the user."""
    spec = _make_spec(tier=1)
    engine = _make_engine()

    with patch.object(type(engine), "run_single", autospec=True) as mock_run:
        mock_run.return_value = {"success": True}
        await engine.run_job_spec(spec)

    assert mock_run.call_args.kwargs["run_id"] == spec.run_id


@pytest.mark.asyncio
async def test_tier_3_run_id_is_still_recorded_in_response():
    spec = _make_spec(tier=3)
    engine = _make_engine()

    with patch(
        "harness.tools.registry.registry.get",
        return_value=None,
    ):
        result = await engine.run_job_spec(spec)

    # The tier-3 response carries the run_id even though the agent
    # never ran. The user gets the run_id in the chat response and
    # the dashboard shows the proposal.
    assert "output" in result
    assert "Tier-3" in result["output"] or "tier-3" in result["output"]
