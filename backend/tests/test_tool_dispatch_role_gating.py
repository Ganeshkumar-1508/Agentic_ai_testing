"""Tests for the role-gated `ToolDispatcher`.

The dispatcher is always role-gated. The Agent's `allowed_tools` is
required and is the sole authority for which special tools the LLM
can call. There is no unfiltered path — the dispatcher rejects any
special tool not in the role's `allowed_tools`, even for tools like
`bash` that exist in the regular registry.

The closed set of special tools is
`{delegate_task, tool_search, submit_job}`. Adding `set_mode` is not
a path we support (the chat Role doesn't need it; the orchestrator
Role doesn't need it; the agent shouldn't switch its own mode).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from harness.agent.tool_dispatch import (
    SPECIAL_TOOL_NAMES,
    ToolDispatcher,
)
from harness.delegation import DelegationContext


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakePermissions:
    """Stand-in for `PermissionManager` that always allows."""

    def resolve_level(self, name: str, args: dict) -> str:
        return "allow"

    def request_approval(self, name: str, args: dict) -> str:
        return "approval-id"

    async def await_approval(self, approval_id: str, timeout: float = 120.0) -> bool:
        return True


class _RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _build_dispatcher(*, allowed_tools: list[str]) -> tuple[ToolDispatcher, _RecordingEventBus]:
    bus = _RecordingEventBus()
    permissions = _FakePermissions()
    dispatcher = ToolDispatcher(
        event_bus=bus,                                       # type: ignore[arg-type]
        permissions=permissions,                             # type: ignore[arg-type]
        mode="auto",
        session_id="sess-1",
        agent_id="agent-1",
        delegation=DelegationContext(),
        allowed_tools=allowed_tools,
    )
    return dispatcher, bus


def _tc(name: str, args: dict | None = None) -> dict[str, Any]:
    return {
        "function": {
            "name": name,
            "arguments": "{}" if args is None else _json_dumps(args),
        }
    }


def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# Closed set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_special_tool_names_constant_is_closed_set():
    """The set of special tools is exactly the two
    in-process-bridging tools: ``delegate_task`` and
    ``tool_search``. The seven chat-side job-control tools
    (``submit_job`` / ``cancel_job`` / ``pause_job`` /
    ``resume_job`` / ``list_jobs`` / ``get_job_status`` /
    ``comment_on_job``) were moved to ``JobControlDispatcher``
    in C09 and are gated via ``_JOB_CONTROL_ACTION_BY_NAME``
    + the ``_role_allowed_tools`` check inside ``execute()``.
    """
    assert SPECIAL_TOOL_NAMES == frozenset({
        "delegate_task", "tool_search",
    })
    from harness.agent.tool_dispatch import _JOB_CONTROL_ACTION_BY_NAME
    assert set(_JOB_CONTROL_ACTION_BY_NAME) == {
        "submit_job", "cancel_job", "pause_job", "resume_job",
        "list_jobs", "get_job_status", "comment_on_job",
    }


# ---------------------------------------------------------------------------
# Role gating — each closed-set tool gets rejected when not in allowed_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_role_without_set_mode_is_unchanged():
    """`set_mode` is no longer special-cased. A role that happens to
    include it in its allowed_tools (legacy configs) routes through the
    regular registry path — the tool's `run()` returns a no-op result."""
    dispatcher, bus = _build_dispatcher(allowed_tools=["bash", "read_file"])

    called = []

    async def fake_handle_regular(name, args, trace_id, llm_response_id=""):
        called.append(name)
        return "regular:ok"

    async def fake_handle_delegate(*a, **kw):
        called.append("delegate_task")
        return "ok"

    async def fake_handle_search(*a, **kw):
        called.append("tool_search")
        return "ok"

    dispatcher._handle_regular_tool = fake_handle_regular
    dispatcher._handle_delegate_task = fake_handle_delegate_task = fake_handle_delegate
    dispatcher._handle_tool_search = fake_handle_tool_search = fake_handle_search

    out = await dispatcher.execute(_tc("set_mode", {"mode": "auto"}))
    assert out == "regular:ok"
    assert called == ["set_mode"]


@pytest.mark.asyncio
async def test_role_excluding_delegate_task_rejects_it(monkeypatch):
    dispatcher, bus = _build_dispatcher(
        allowed_tools=["set_mode", "tool_search", "bash", "submit_job"],
    )
    called = []

    async def fake_handler(*args, **kwargs):
        called.append(True)
        return "ok"

    monkeypatch.setattr(dispatcher, "_handle_delegate_task", fake_handler)

    out = await dispatcher.execute(_tc("delegate_task", {"goal": "x"}))

    assert "not available in this role" in out
    assert "delegate_task" in out
    assert called == []


@pytest.mark.asyncio
async def test_role_excluding_tool_search_rejects_it(monkeypatch):
    dispatcher, bus = _build_dispatcher(
        allowed_tools=["set_mode", "delegate_task", "bash", "submit_job"],
    )
    called = []

    async def fake_handler(*args, **kwargs):
        called.append(True)
        return "ok"

    monkeypatch.setattr(dispatcher, "_handle_tool_search", fake_handler)

    out = await dispatcher.execute(_tc("tool_search", {"query": "x"}))

    assert "not available in this role" in out
    assert "tool_search" in out
    assert called == []


@pytest.mark.asyncio
async def test_role_excluding_submit_job_rejects_it():
    """The job-runner Role never has submit_job. The chat Role is the
    only one. Verify the gate."""
    dispatcher, bus = _build_dispatcher(
        allowed_tools=["bash", "write_file", "delegate_task", "tool_search"],
    )

    out = await dispatcher.execute(_tc("submit_job", {
        "prompt": "test the checkout flow",
        "repo_url": "github.com/foo/bar",
    }))

    assert "not available in this role" in out
    assert "submit_job" in out


# ---------------------------------------------------------------------------
# Non-special tools are not gated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_special_tool_unaffected_by_role_gating(monkeypatch):
    """Bash, write_file, read_file — not in SPECIAL_TOOL_NAMES — must NOT
    be rejected by the role gate. The role's allowed_tools still
    constrains which tools the LLM sees, but the dispatcher gate only
    fires for special tools."""
    dispatcher, bus = _build_dispatcher(allowed_tools=["bash"])

    called = []

    async def fake_handle_regular(name, args, trace_id, llm_response_id=""):
        called.append(name)
        return "regular:ok"

    monkeypatch.setattr(dispatcher, "_handle_regular_tool", fake_handle_regular)

    out = await dispatcher.execute(_tc("bash", {"command": "ls"}))

    assert out == "regular:ok"
    assert called == ["bash"]


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejection_still_emits_started_event():
    """The dispatcher emits `ToolExecutionStarted` BEFORE the gate check.
    The audit log must show the agent *attempted* the call, not just the
    rejection — useful for investigating misconfigured roles."""
    dispatcher, bus = _build_dispatcher(
        allowed_tools=["bash"],
    )

    await dispatcher.execute(_tc("submit_job", {"prompt": "x"}))

    started = [e for e in bus.events if e.__class__.__name__ == "ToolExecutionStarted"]
    completed = [e for e in bus.events if e.__class__.__name__ == "ToolExecutionCompleted"]
    assert len(started) == 1
    assert started[0].tool_name == "submit_job"
    assert len(completed) == 1
    assert completed[0].tool_name == "submit_job"
    assert completed[0].success is False


# ---------------------------------------------------------------------------
# Empty / explicit allowed_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_allowed_tools_rejects_every_special_tool(monkeypatch):
    """An empty `allowed_tools` list is a valid (if extreme) role
    config: no tools are allowed. All three special tools must be
    rejected."""
    dispatcher, bus = _build_dispatcher(allowed_tools=[])

    for name in ("submit_job", "delegate_task", "tool_search"):
        out = await dispatcher.execute(_tc(name, {}))
        assert "not available in this role" in out
        assert name in out


@pytest.mark.asyncio
async def test_chat_role_full_ladder(monkeypatch):
    """The chat Role's toolset includes all three special tools. The
    full ladder fires for each one."""
    dispatcher, bus = _build_dispatcher(
        allowed_tools=["submit_job", "delegate_task", "tool_search"],
    )

    calls: list[str] = []

    async def fake_delegate(*a, **kw):
        calls.append("delegate_task")
        return "ok"

    async def fake_search(*a, **kw):
        calls.append("tool_search")
        return "ok"

    async def fake_dispatch_job_control(self, action, args, trace_id, llm_response_id=""):
        calls.append(action.value)
        return "ok"

    monkeypatch.setattr(dispatcher, "_handle_delegate_task", fake_delegate)
    monkeypatch.setattr(dispatcher, "_handle_tool_search", fake_search)
    monkeypatch.setattr(type(dispatcher), "_dispatch_job_control", fake_dispatch_job_control)

    await dispatcher.execute(_tc("submit_job", {"prompt": "x"}))
    await dispatcher.execute(_tc("delegate_task", {"goal": "x"}))
    await dispatcher.execute(_tc("tool_search", {"query": "x"}))

    assert set(calls) == {"submit_job", "delegate_task", "tool_search"}


@pytest.mark.asyncio
async def test_job_runner_role_lacks_submit_job(monkeypatch):
    """The job-runner Role (orchestrator) has delegate_task and
    tool_search but NOT submit_job. Verifying the chat→orchestrator
    boundary."""
    dispatcher, bus = _build_dispatcher(
        allowed_tools=["bash", "write_file", "delegate_task", "tool_search"],
    )

    submit_called = []

    async def fake_dispatch_job_control(self, action, args, trace_id, llm_response_id=""):
        submit_called.append(action.value)
        return "ok"

    monkeypatch.setattr(type(dispatcher), "_dispatch_job_control", fake_dispatch_job_control)

    out = await dispatcher.execute(_tc("submit_job", {"prompt": "x"}))
    assert "not available in this role" in out
    assert submit_called == []


# ---------------------------------------------------------------------------
# Agent wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_passes_allowed_tools_to_dispatcher():
    """The Agent must pass its `self._allowed_tools` to the dispatcher it
    creates. This is the wiring that connects the role concept to the
    dispatcher's gate."""
    from harness.agent.agent import Agent

    deps = SimpleNamespace(
        llm=SimpleNamespace(chat_stream=lambda *a, **kw: None),
        store=None,
        permissions=_FakePermissions(),
        mcp=None,
        sandbox_manager=None,
        event_bus=_RecordingEventBus(),
        store_registry=None,
    )
    agent = Agent(
        deps=deps,                                         # type: ignore[arg-type]
        mode="auto",
        allowed_tools=["submit_job", "delegate_task", "tool_search", "bash"],
    )

    dispatcher = agent._make_dispatcher()
    assert "submit_job" in dispatcher._role_allowed_tools
    assert "bash" in dispatcher._role_allowed_tools
    assert "set_mode" not in dispatcher._role_allowed_tools


@pytest.mark.asyncio
async def test_agent_create_subagent_requires_explicit_allowed_tools():
    """The Agent's `create_subagent` requires an explicit `allowed_tools`
    list. There is no unfiltered default — every subagent is a Role."""
    from harness.agent.agent import Agent

    deps = SimpleNamespace(
        llm=SimpleNamespace(chat_stream=lambda *a, **kw: None),
        store=None,
        permissions=_FakePermissions(),
        mcp=None,
        sandbox_manager=None,
        event_bus=_RecordingEventBus(),
        store_registry=None,
    )
    parent = Agent(
        deps=deps,                                         # type: ignore[arg-type]
        mode="auto",
        allowed_tools=["submit_job", "bash"],
    )

    sub = parent.create_subagent(allowed_tools=["bash", "write_file"])
    assert "bash" in sub._allowed_tools
    assert "write_file" in sub._allowed_tools
    assert "submit_job" not in sub._allowed_tools
