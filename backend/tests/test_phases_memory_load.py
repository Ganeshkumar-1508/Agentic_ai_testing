"""Tests for MemoryLoadPhase (C09)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import patch

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.memory_load import MemoryLoadPhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


@pytest.mark.asyncio
async def test_memory_load_attaches_snapshot_to_context() -> None:
    snapshot = "## Past runs\n- 2026-06-15: fixed login race condition"
    with patch(
        "harness.tools.memory_tool.get_memory_snapshot",
        return_value=snapshot,
    ):
        ctx = _ctx()
        result = await MemoryLoadPhase().execute(ctx)
    assert result.memory_block == snapshot
    assert result is not ctx  # new RunContext instance


@pytest.mark.asyncio
async def test_memory_load_empty_snapshot_sets_empty_string() -> None:
    """get_memory_snapshot returns '' (not None) when no memory exists."""
    with patch(
        "harness.tools.memory_tool.get_memory_snapshot",
        return_value="",
    ):
        ctx = _ctx()
        result = await MemoryLoadPhase().execute(ctx)
    assert result.memory_block == ""


@pytest.mark.asyncio
async def test_memory_load_skips_when_no_repo_url() -> None:
    """No repo_url — phase skips, ctx unchanged."""
    ctx = _ctx(repo_url="")
    result = await MemoryLoadPhase().execute(ctx)
    assert result is ctx
    assert result.memory_block == ""


@pytest.mark.asyncio
async def test_memory_load_swallows_exception() -> None:
    """The memory tool raised — phase swallows (can_skip=True)."""
    with patch(
        "harness.tools.memory_tool.get_memory_snapshot",
        side_effect=RuntimeError("memory store is down"),
    ):
        ctx = _ctx()
        result = await MemoryLoadPhase().execute(ctx)
    assert result is ctx
    assert result.memory_block == ""


def test_memory_load_has_can_skip_true() -> None:
    assert MemoryLoadPhase.can_skip is True


def test_memory_load_phase_name() -> None:
    assert MemoryLoadPhase.phase_name == "memory_load"


def test_memory_load_satisfies_run_phase_protocol() -> None:
    phase: RunPhase = MemoryLoadPhase()
    assert hasattr(phase, "phase_name")
    assert hasattr(phase, "can_skip")
    assert callable(phase.execute)


def test_run_context_has_memory_block_field() -> None:
    """The RunContext schema must include the new memory_block field
    so phases can write to it."""
    fields = {f.name for f in __import__("dataclasses").fields(RunContext)}
    assert "memory_block" in fields
