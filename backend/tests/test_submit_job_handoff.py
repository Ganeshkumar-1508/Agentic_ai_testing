"""Tests for the product-shift `submit_job` handoff.

After the shift, the chat Role is read-only. Its ONE allowed mutation
is the `submit_job` tool, which:

  1. Takes a natural-language prompt + repo + branch + tier from the LLM
  2. Builds a `JobSpec` (the chat-to-orchestrator handoff payload)
  3. Persists a Run record (status=pending, source=chat-submission)
  4. Spawns `OrchestratorEngine.run_single` as a background task
  5. Returns the `run_id` so the chat can show a tracking link

The chat Role never executes the orchestrator's work itself. The
job-runner Role does NOT have `submit_job` in its allowed_tools — the
C1-revised dispatcher gate rejects it for that role.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from harness.agent.tool_dispatch import (
    SPECIAL_TOOL_NAMES,
    ToolDispatcher,
)
from harness.delegation import DelegationContext
from harness.jobs.spec import JobSpec


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeRunStore:
    """Stand-in for `PostgresRunStore` that records every call."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.update_should_fail: bool = False
        self.create_should_fail: bool = False

    async def create_run(
        self, run_id: str, session_id: str = "", task_type: str = "",
        repo_url: str = "", branch: str = "", sha: str = "",
    ) -> Any:
        if self.create_should_fail:
            raise RuntimeError("simulated create failure")
        self.created.append({
            "run_id": run_id, "session_id": session_id,
            "task_type": task_type, "repo_url": repo_url,
            "branch": branch, "sha": sha,
        })
        return SimpleNamespace(run_id=run_id)


class _FakeStore:
    """Stand-in for `PersistentStore` — exposes a `.db` attribute that
    the submit_job handler reads through `self._deps.store.db`."""

    def __init__(self, run_store: _FakeRunStore) -> None:
        self.db = run_store
        self.run_store = run_store


class _FakePermissions:
    def resolve_level(self, name: str, args: dict) -> str:
        return "allow"

    def set_mode(self, mode: str) -> None:
        pass

    def request_approval(self, name: str, args: dict) -> str:
        return "approval-id"

    async def await_approval(self, approval_id: str, timeout: float = 120.0) -> bool:
        return True


class _RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _build_dispatcher(
    *,
    allowed_tools: list[str],
    run_store: _FakeRunStore,
    monkeypatch: pytest.MonkeyPatch | None = None,
    sandbox_manager: Any = None,
) -> ToolDispatcher:
    bus = _RecordingEventBus()
    permissions = _FakePermissions()
    deps = SimpleNamespace(
        store=_FakeStore(run_store),
        sandbox_manager=sandbox_manager,
    )
    # Patch PostgresRunStore at the source module so the dispatcher's
    # local import resolves to our fake (the chat Role's submit_job
    # handler does `from harness.store.adapters.postgres import
    # PostgresRunStore` inside the method, so we patch the source
    # module — not any bound name).
    if monkeypatch is not None:
        from harness.store import adapters
        monkeypatch.setattr(
            adapters.postgres, "PostgresRunStore", lambda _: run_store,
        )
    return ToolDispatcher(
        event_bus=bus,                                       # type: ignore[arg-type]
        permissions=permissions,                             # type: ignore[arg-type]
        mode="chat-readonly",
        session_id="chat-sess-1",
        agent_id="chat-agent-1",
        delegation=DelegationContext(),
        allowed_tools=allowed_tools,
        deps=deps,                                           # type: ignore[arg-type]
    )


def _tc(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"function": {"name": name, "arguments": json.dumps(args)}}


# ---------------------------------------------------------------------------
# Role gating (C1-revised × product shift)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_job_is_in_special_tool_names():
    """The product shift adds submit_job to the closed special-tools set."""
    assert "submit_job" in SPECIAL_TOOL_NAMES


@pytest.mark.asyncio
async def test_chat_role_with_submit_job_proceeds(monkeypatch):
    """Chat Role has `submit_job` in allowed_tools → proceeds normally."""
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job", "list_runs", "get_run", "question"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    out = await dispatcher.execute(_tc("submit_job", {
        "prompt": "Test the checkout flow for expired cards",
        "repo_url": "github.com/foo/bar",
        "branch": "main",
        "tier": 1,
    }))

    assert "Job submitted" in out
    assert "run_id=" in out
    assert "github.com/foo/bar" in out
    assert "Track progress at: /runs/" in out
    # A Run record was created.
    assert len(run_store.created) == 1
    row = run_store.created[0]
    assert row["task_type"] == "chat-job-tier1"
    assert row["repo_url"] == "github.com/foo/bar"
    assert row["branch"] == "main"


@pytest.mark.asyncio
async def test_job_runner_role_rejects_submit_job():
    """Job-runner Role does NOT have `submit_job` → rejected with a clear
    error and a `ToolExecutionCompleted(success=False)` audit event.
    Job-runners don't submit jobs; they ARE the jobs."""
    run_store = _FakeRunStore()
    bus = _RecordingEventBus()
    permissions = _FakePermissions()
    deps = SimpleNamespace(store=_FakeStore(run_store), sandbox_manager=None)
    dispatcher = ToolDispatcher(
        event_bus=bus,                                       # type: ignore[arg-type]
        permissions=permissions,                             # type: ignore[arg-type]
        mode="auto",
        session_id="job-sess-1",
        agent_id="job-agent-1",
        delegation=DelegationContext(),
        deps=deps,                                           # type: ignore[arg-type]
        allowed_tools=["bash", "write_file", "delegate_task", "tool_search"],
    )

    out = await dispatcher.execute(_tc("submit_job", {
        "prompt": "do something",
    }))

    assert "not available in this role" in out
    assert "submit_job" in out
    # No Run record was created.
    assert run_store.created == []
    # Audit event recorded.
    completed = [e for e in bus.events if e.__class__.__name__ == "ToolExecutionCompleted"]
    assert any(e.success is False for e in completed)


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_job_requires_prompt(monkeypatch):
    """A blank prompt is rejected at the handler, not at the role gate."""
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    out = await dispatcher.execute(_tc("submit_job", {"prompt": ""}))

    assert "prompt" in out.lower()
    assert "required" in out.lower()
    assert run_store.created == []


@pytest.mark.asyncio
async def test_submit_job_defaults_branch_to_main(monkeypatch):
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    await dispatcher.execute(_tc("submit_job", {
        "prompt": "test the login",
        "repo_url": "github.com/foo/bar",
    }))

    assert run_store.created[0]["branch"] == "main"


@pytest.mark.asyncio
async def test_submit_job_default_tier_is_1(monkeypatch):
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    await dispatcher.execute(_tc("submit_job", {
        "prompt": "x",
        "tier": "not-a-number",  # type-coerced; defaults to 1
    }))

    # Tier was coerced to 1.
    assert run_store.created[0]["task_type"] == "chat-job-tier1"


@pytest.mark.asyncio
async def test_submit_job_higher_tier_produces_different_task_type(monkeypatch):
    """Tier 2 (supervised) and tier 3 (human-authored) produce distinct
    task types in the Run record so the dashboard can filter by them."""
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    await dispatcher.execute(_tc("submit_job", {"prompt": "x", "tier": 2}))
    await dispatcher.execute(_tc("submit_job", {"prompt": "y", "tier": 3}))

    assert run_store.created[0]["task_type"] == "chat-job-tier2"
    assert run_store.created[1]["task_type"] == "chat-job-tier3"


@pytest.mark.asyncio
async def test_submit_job_does_not_crash_when_run_store_fails(monkeypatch):
    """If the Run record can't be persisted, the chat still gets a
    useful response. The recorder failure is logged, not propagated."""
    run_store = _FakeRunStore()
    run_store.create_should_fail = True
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store,
    )

    out = await dispatcher.execute(_tc("submit_job", {"prompt": "x"}))

    assert "Job submitted" in out
    assert "run_id=" in out


@pytest.mark.asyncio
async def test_submit_job_returns_a_run_id_in_response(monkeypatch):
    """The run_id in the response must be a UUID-shaped string and must
    match what the Run record got."""
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    out = await dispatcher.execute(_tc("submit_job", {
        "prompt": "test the checkout flow",
        "repo_url": "github.com/foo/bar",
    }))

    # Extract run_id from the response.
    import re
    match = re.search(r"run_id=([a-f0-9-]{36})", out)
    assert match is not None
    response_run_id = match.group(1)
    # Same id in the Run record.
    assert run_store.created[0]["run_id"] == response_run_id


@pytest.mark.asyncio
async def test_submit_job_emits_completion_event(monkeypatch):
    """Audit trail: a successful submit_job emits a
    `ToolExecutionCompleted(success=True)` event with the run_id in
    the preview."""
    run_store = _FakeRunStore()
    bus = _RecordingEventBus()
    permissions = _FakePermissions()
    deps = SimpleNamespace(store=_FakeStore(run_store), sandbox_manager=None)
    dispatcher = ToolDispatcher(
        event_bus=bus,                                       # type: ignore[arg-type]
        permissions=permissions,                             # type: ignore[arg-type]
        mode="chat-readonly",
        session_id="chat-sess-1",
        agent_id="chat-agent-1",
        delegation=DelegationContext(),
        allowed_tools=["submit_job"],
        deps=deps,                                           # type: ignore[arg-type]
    )

    await dispatcher.execute(_tc("submit_job", {"prompt": "x"}))

    started = [e for e in bus.events if e.__class__.__name__ == "ToolExecutionStarted"]
    completed = [e for e in bus.events if e.__class__.__name__ == "ToolExecutionCompleted"]
    assert len(started) == 1
    assert started[0].tool_name == "submit_job"
    assert len(completed) == 1
    assert completed[0].tool_name == "submit_job"
    assert completed[0].success is True
    assert "Job submitted" in completed[0].output_preview


# ---------------------------------------------------------------------------
# JobSpec contract
# ---------------------------------------------------------------------------


def test_job_spec_from_chat_submission_defaults():
    """The chat-submission factory applies safe defaults: source,
    capabilities, approval routing, context carrying session_id/agent_id.
    A chat call without explicit values still produces a valid spec."""
    spec = JobSpec.from_chat_submission(
        prompt="test the login",
        session_id="sess-1",
        agent_id="agent-1",
    )
    assert spec.source == "chat-submission"
    assert spec.tier == 1
    assert spec.branch == "main"
    assert "write_test_files" in spec.capabilities
    assert spec.approval["mode"] == "review_queue"
    # C08: context is now a typed JobContext (Pydantic with
    # extra='allow'). Use attribute access; for dict-style access,
    # call to_dict() first.
    assert spec.context.session_id == "sess-1"
    assert spec.context.agent_id == "agent-1"
    # UUIDs were generated.
    assert len(spec.spec_id) == 36
    assert len(spec.run_id) == 36


def test_job_spec_round_trip_via_dict():
    """Serializing and re-parsing a JobSpec produces the same shape."""
    original = JobSpec.from_chat_submission(
        prompt="test X",
        repo_url="github.com/foo/bar",
        branch="develop",
        tier=2,
        capabilities=["write_test_files"],
        session_id="sess-1",
        agent_id="agent-1",
    )
    data = original.to_dict()
    restored = JobSpec.from_dict(data)
    assert restored.prompt == original.prompt
    assert restored.repo_url == original.repo_url
    assert restored.branch == original.branch
    assert restored.tier == original.tier
    assert restored.capabilities == original.capabilities
    assert restored.context == original.context
    assert restored.source == original.source
    assert restored.spec_id == original.spec_id
    assert restored.run_id == original.run_id


def test_job_spec_attach_run_id_mutates_in_place():
    """The orchestrator calls this to swap the spec's placeholder
    run_id for the real one. The chat endpoint reads this to confirm
    the handoff succeeded."""
    spec = JobSpec.from_chat_submission(prompt="x")
    assert spec.run_id != "real-run-id"
    spec.attach_run_id("real-run-id")
    assert spec.run_id == "real-run-id"


# ---------------------------------------------------------------------------
# C1.1: user-tier override contextvar
#
# The chat UI's 3-segment tier selector (auto / supervised / authored)
# plumbs the user's choice into `ChatRequest.tier`. The chat router
# sets `_USER_TIER_OVERRIDE` for the duration of the call so the
# dispatcher's `_handle_submit_job` uses the USER's choice
# (authoritative) over the LLM's pick (hint). These tests assert
# that contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_tier_override_2_overrides_llm_tier_1(monkeypatch):
    """User picked Tier 2 in the UI; LLM picked Tier 1. The
    JobSpec must use Tier 2 (the user's choice is authoritative)."""
    from harness.agent.tool_dispatch import (
        reset_user_tier_override, set_user_tier_override,
    )
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    token = set_user_tier_override(2)
    try:
        await dispatcher.execute(_tc("submit_job", {
            "prompt": "test the login",
            "tier": 1,  # LLM's pick
        }))
    finally:
        reset_user_tier_override(token)

    assert run_store.created[0]["task_type"] == "chat-job-tier2"


@pytest.mark.asyncio
async def test_user_tier_override_3_overrides_llm_tier_2(monkeypatch):
    """User picked Tier 3 (human-authored); LLM picked Tier 2.
    JobSpec uses Tier 3."""
    from harness.agent.tool_dispatch import (
        reset_user_tier_override, set_user_tier_override,
    )
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    token = set_user_tier_override(3)
    try:
        await dispatcher.execute(_tc("submit_job", {
            "prompt": "test",
            "tier": 2,  # LLM's pick (supervised)
        }))
    finally:
        reset_user_tier_override(token)

    assert run_store.created[0]["task_type"] == "chat-job-tier3"


@pytest.mark.asyncio
async def test_no_user_tier_override_uses_llm_choice(monkeypatch):
    """If the chat router never sets the override (e.g. a
    programmatic caller that bypasses the chat UI), the LLM's
    `tier` arg is used. Backward-compatible with pre-C1.1."""
    from harness.agent.tool_dispatch import (
        reset_user_tier_override, set_user_tier_override,
    )
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    # Explicitly clear any inherited override.
    token = set_user_tier_override(None)
    try:
        await dispatcher.execute(_tc("submit_job", {
            "prompt": "test",
            "tier": 2,
        }))
    finally:
        reset_user_tier_override(token)

    assert run_store.created[0]["task_type"] == "chat-job-tier2"


@pytest.mark.asyncio
async def test_invalid_user_tier_override_falls_back_to_llm(monkeypatch):
    """A defensive guard: if the override is set to a non-int
    (defensive against a programming error in the chat router),
    fall back to the LLM's pick rather than crashing the
    handoff."""
    from harness.agent.tool_dispatch import (
        reset_user_tier_override, set_user_tier_override,
    )
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    token = set_user_tier_override("oops")  # type: ignore[arg-type]
    try:
        await dispatcher.execute(_tc("submit_job", {
            "prompt": "test",
            "tier": 1,
        }))
    finally:
        reset_user_tier_override(token)

    # Fell back to LLM's tier=1.
    assert run_store.created[0]["task_type"] == "chat-job-tier1"


@pytest.mark.asyncio
async def test_user_tier_override_does_not_leak_between_calls(monkeypatch):
    """If the override is set, used, and reset, the NEXT call (with
    no override) must NOT inherit the previous value. Critical
    because the dispatcher (and its contextvars) is long-lived
    across many requests."""
    from harness.agent.tool_dispatch import (
        reset_user_tier_override, set_user_tier_override,
    )
    run_store = _FakeRunStore()
    dispatcher = _build_dispatcher(
        allowed_tools=["submit_job"],
        run_store=run_store, monkeypatch=monkeypatch,
    )

    # First call: user picked tier 3.
    token = set_user_tier_override(3)
    try:
        await dispatcher.execute(_tc("submit_job", {"prompt": "a"}))
    finally:
        reset_user_tier_override(token)
    assert run_store.created[0]["task_type"] == "chat-job-tier3"

    # Second call: NO override. The LLM picks tier 1; we must NOT
    # inherit the stale tier-3 from the previous request.
    await dispatcher.execute(_tc("submit_job", {"prompt": "b", "tier": 1}))
    assert run_store.created[1]["task_type"] == "chat-job-tier1"
