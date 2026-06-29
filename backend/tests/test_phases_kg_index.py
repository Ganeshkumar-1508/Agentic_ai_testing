"""Tests for KGIndexPhase (C09; the pre-existing Phase was built in C1).

The phase is run as a 'validation alongside' check in the orchestrator
today; C09 makes it the canonical entry point for the KG index step.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.kg_index import KGIndexPhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


@pytest.mark.asyncio
async def test_kg_index_attaches_kg_ctx_on_success() -> None:
    """After successful index, ctx.kg_ctx is set to a non-None value."""
    kg_ctx = MagicMock()
    with patch(
        "harness.services.knowledge_graph_syncer.KnowledgeGraphSyncer.index",
        AsyncMock(return_value={"success": True, "nodeCount": 100}),
    ):
        with patch(
            "harness.services.knowledge_graph_syncer.SandboxKGContext.build",
            return_value=kg_ctx,
        ):
            ctx = _ctx()
            ctx = replace(ctx, sandbox=MagicMock())
            result = await KGIndexPhase().execute(ctx)
    assert result.kg_ctx is kg_ctx


@pytest.mark.asyncio
async def test_kg_index_retries_on_failure_then_succeeds() -> None:
    """First attempt fails, second succeeds. Phase should retry."""
    kg_ctx = MagicMock()
    side_effects = [
        RuntimeError("sandbox down"),
        {"success": True, "nodeCount": 50},
    ]
    with patch(
        "harness.services.knowledge_graph_syncer.KnowledgeGraphSyncer.index",
        AsyncMock(side_effect=side_effects),
    ):
        with patch(
            "harness.services.knowledge_graph_syncer.SandboxKGContext.build",
            return_value=kg_ctx,
        ):
            ctx = _ctx()
            ctx = replace(ctx, sandbox=MagicMock())
            result = await KGIndexPhase().execute(ctx)
    assert result.kg_ctx is kg_ctx


@pytest.mark.asyncio
async def test_kg_index_propagates_exception_after_max_retries() -> None:
    """All retries fail. Phase raises (can_skip=False)."""
    with patch(
        "harness.services.knowledge_graph_syncer.KnowledgeGraphSyncer.index",
        AsyncMock(side_effect=RuntimeError("persistent failure")),
    ):
        with patch(
            "harness.services.knowledge_graph_syncer.SandboxKGContext.build",
            return_value=MagicMock(),
        ):
            ctx = _ctx()
            ctx = replace(ctx, sandbox=MagicMock())
            with pytest.raises(RuntimeError, match="persistent failure"):
                await KGIndexPhase().execute(ctx)


def test_kg_index_has_can_skip_true() -> None:
    """The phase advertises can_skip=True (in the docstring) so a
    failure of the inline KG code doesn't kill the run. But the
    implementation raises (can_skip is True but the retry loop
    raises the last exception). The can_skip attribute documents
    the intent; the pipeline honours it by catching."""
    assert KGIndexPhase.can_skip is True


def test_kg_index_phase_name() -> None:
    assert KGIndexPhase.phase_name == "kg_index"
