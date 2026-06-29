"""Tests for SandboxPreparePhase (C09)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.sandbox_prepare import SandboxPreparePhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


def _orchestrator_with_sandbox(sandbox: Any) -> MagicMock:
    sm = MagicMock()
    sm.get_or_create = AsyncMock(return_value=sandbox)
    orch = MagicMock()
    orch.sandbox_manager = sm
    return orch


@pytest.mark.asyncio
async def test_sandbox_prepare_gets_or_creates_sandbox() -> None:
    sandbox = MagicMock(name="sandbox-env")
    orch = _orchestrator_with_sandbox(sandbox)
    ctx = _ctx()
    ctx = replace(ctx, orchestrator=orch)
    result = await SandboxPreparePhase().execute(ctx)
    assert result.sandbox is sandbox
    orch.sandbox_manager.get_or_create.assert_awaited_once_with(
        "sess-1", volume_key="https://github.com/foo/bar",
    )


@pytest.mark.asyncio
async def test_sandbox_prepare_extracts_url_from_goal_when_empty() -> None:
    """If repo_url is empty, the phase tries to extract one from
    the goal via URLAutoExtractor."""
    sandbox = MagicMock(name="sandbox-env")
    orch = _orchestrator_with_sandbox(sandbox)
    ctx = _ctx(
        repo_url="",
        goal="Fix https://github.com/acme/widget the login bug",
    )
    ctx = replace(ctx, orchestrator=orch)
    result = await SandboxPreparePhase().execute(ctx)
    assert result.repo_url == "https://github.com/acme/widget"
    orch.sandbox_manager.get_or_create.assert_awaited_once_with(
        "sess-1", volume_key="https://github.com/acme/widget",
    )


@pytest.mark.asyncio
async def test_sandbox_prepare_uses_default_volume_key_when_no_url() -> None:
    """No repo_url (not in goal either) — volume_key is 'default'."""
    sandbox = MagicMock(name="sandbox-env")
    orch = _orchestrator_with_sandbox(sandbox)
    ctx = _ctx(repo_url="", goal="do the thing")
    ctx = replace(ctx, orchestrator=orch)
    result = await SandboxPreparePhase().execute(ctx)
    assert result.repo_url == ""  # nothing extracted
    orch.sandbox_manager.get_or_create.assert_awaited_once_with(
        "sess-1", volume_key="default",
    )


@pytest.mark.asyncio
async def test_sandbox_prepare_runs_dns_check() -> None:
    """Phase runs a DNS check on the sandbox before returning."""
    sandbox = MagicMock(name="sandbox-env")
    sandbox.run = AsyncMock(
        return_value=MagicMock(returncode=0, stdout="140.82.121.4 github.com\n"),
    )
    orch = _orchestrator_with_sandbox(sandbox)
    ctx = _ctx()
    ctx = replace(ctx, orchestrator=orch)
    await SandboxPreparePhase().execute(ctx)
    assert sandbox.run.await_count == 1
    call = sandbox.run.await_args
    assert "getent hosts github.com" in call.args[0]


@pytest.mark.asyncio
async def test_sandbox_prepare_continues_when_dns_check_fails() -> None:
    """DNS check raised — phase swallows, ctx still has sandbox."""
    sandbox = MagicMock(name="sandbox-env")
    sandbox.run = AsyncMock(side_effect=RuntimeError("sandbox down"))
    orch = _orchestrator_with_sandbox(sandbox)
    ctx = _ctx()
    ctx = replace(ctx, orchestrator=orch)
    result = await SandboxPreparePhase().execute(ctx)
    assert result.sandbox is sandbox


@pytest.mark.asyncio
async def test_sandbox_prepare_raises_when_no_orchestrator() -> None:
    """Forgetting to wire ctx.orchestrator is a programmer bug."""
    ctx = _ctx()
    with pytest.raises(RuntimeError, match="ctx.orchestrator"):
        await SandboxPreparePhase().execute(ctx)


def test_sandbox_prepare_has_can_skip_false() -> None:
    assert SandboxPreparePhase.can_skip is False


def test_sandbox_prepare_phase_name() -> None:
    assert SandboxPreparePhase.phase_name == "sandbox_prepare"


def test_run_context_has_orchestrator_field() -> None:
    import dataclasses
    fields = {f.name for f in dataclasses.fields(RunContext)}
    assert "orchestrator" in fields
