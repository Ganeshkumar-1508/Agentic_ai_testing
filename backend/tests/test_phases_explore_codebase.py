"""Tests for ExploreCodebasePhase (C09)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.explore_codebase import ExploreCodebasePhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


@pytest.mark.asyncio
async def test_explore_attaches_findings_to_context() -> None:
    findings = "## Auth module\n- src/auth/handler.py"
    fake_explore = AsyncMock(return_value=findings)
    with patch(
        "harness.tools.orchestrator_tool._explore_codebase",
        fake_explore,
    ):
        ctx = _ctx()
        result = await ExploreCodebasePhase().execute(ctx)
    assert result.explore_findings == findings
    fake_explore.assert_awaited_once_with(ctx.goal)


@pytest.mark.asyncio
async def test_explore_empty_findings_sets_empty_string() -> None:
    fake_explore = AsyncMock(return_value="")
    with patch(
        "harness.tools.orchestrator_tool._explore_codebase",
        fake_explore,
    ):
        ctx = _ctx()
        result = await ExploreCodebasePhase().execute(ctx)
    assert result.explore_findings == ""


@pytest.mark.asyncio
async def test_explore_swallows_exception() -> None:
    fake_explore = AsyncMock(side_effect=RuntimeError("KG is down"))
    with patch(
        "harness.tools.orchestrator_tool._explore_codebase",
        fake_explore,
    ):
        ctx = _ctx()
        result = await ExploreCodebasePhase().execute(ctx)
    assert result is ctx
    assert result.explore_findings == ""


def test_explore_has_can_skip_true() -> None:
    assert ExploreCodebasePhase.can_skip is True


def test_explore_phase_name() -> None:
    assert ExploreCodebasePhase.phase_name == "explore_codebase"


def test_explore_satisfies_run_phase_protocol() -> None:
    phase: RunPhase = ExploreCodebasePhase()
    assert hasattr(phase, "phase_name")
    assert hasattr(phase, "can_skip")
    assert callable(phase.execute)
