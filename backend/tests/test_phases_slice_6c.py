"""Compact tests for the migrated RunPhase classes (C09; slice 6c).

Each phase gets a minimal smoke test: build a ``RunContext``,
patch the external dependencies, run the phase, assert the
shape of the returned context. These are not exhaustive &mdash;
the per-phase contract is small and the orchestrator's
integration tests cover the rest.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.phases import RunContext, RunPhase
from harness.phases.clone_repo import CloneRepoPhase
from harness.phases.bootstrap_deps import BootstrapDepsPhase
from harness.phases.worktree_create import WorktreeCreatePhase
from harness.phases.clone_context_repos import CloneContextReposPhase
from harness.phases.inject_credentials import InjectCredentialsPhase
from harness.phases.orchestrate_board import OrchestrateBoardPhase
from harness.phases.coordinator_spawn import CoordinatorSpawnPhase
from harness.phases.post_run_kg_sync import PostRunKGSyncPhase
from harness.phases.l2_reflection import L2ReflectionPhase


def _ctx(**overrides: Any) -> RunContext:
    base = dict(
        run_id="run-1", session_id="sess-1", spec_id="spec-1",
        repo_url="https://github.com/foo/bar", branch="main",
        goal="Add unit tests for the auth flow",
    )
    base.update(overrides)
    return RunContext(**base)


def _orchestrator_with_sandbox(sandbox: Any = None) -> MagicMock:
    sm = MagicMock()
    sm.get_or_create = AsyncMock(return_value=sandbox or MagicMock())
    orch = MagicMock()
    orch.sandbox_manager = sm
    return orch


# ---------------------------------------------------------------------------
# CloneRepoPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_repo_requires_sandbox_and_orchestrator() -> None:
    with pytest.raises(RuntimeError):
        await CloneRepoPhase().execute(_ctx())
    with pytest.raises(RuntimeError):
        await CloneRepoPhase().execute(
            _ctx(orchestrator=_orchestrator_with_sandbox(), sandbox=None),
        )


@pytest.mark.asyncio
async def test_clone_repo_git_clone_success() -> None:
    sandbox = MagicMock()
    sandbox.run = AsyncMock(
        return_value=MagicMock(returncode=0, stdout="cloned\n", stderr=""),
    )
    ctx = _ctx(orchestrator=_orchestrator_with_sandbox(), sandbox=sandbox)
    result = await CloneRepoPhase().execute(ctx)
    assert result is ctx
    sandbox.run.assert_called()


@pytest.mark.asyncio
async def test_clone_repo_git_clone_failure_raises() -> None:
    """On clone failure, the phase raises RuntimeError.
    The pipeline propagates it (can_skip=False) and the
    orchestrator's error path handles it."""
    sandbox = MagicMock()
    sandbox.run = AsyncMock(
        return_value=MagicMock(returncode=128, stdout="", stderr="fatal"),
    )
    ctx = _ctx(orchestrator=_orchestrator_with_sandbox(), sandbox=sandbox)
    with pytest.raises(RuntimeError, match="Clone failed"):
        await CloneRepoPhase().execute(ctx)


def test_clone_repo_phase_meta() -> None:
    assert CloneRepoPhase.phase_name == "clone_repo"
    assert CloneRepoPhase.can_skip is False


# ---------------------------------------------------------------------------
# BootstrapDepsPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_deps_skips_without_sandbox() -> None:
    ctx = _ctx()
    result = await BootstrapDepsPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_bootstrap_deps_swallows_exception() -> None:
    with patch(
        "harness.services.sandbox_bootstrap.SandboxBootstrap.bootstrap",
        AsyncMock(side_effect=RuntimeError("npm install failed")),
    ):
        sandbox = MagicMock()
        ctx = _ctx(sandbox=sandbox)
        result = await BootstrapDepsPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_bootstrap_deps_calls_sandbox_bootstrap() -> None:
    with patch(
        "harness.services.sandbox_bootstrap.SandboxBootstrap.bootstrap",
        AsyncMock(),
    ) as mock_bootstrap:
        sandbox = MagicMock()
        ctx = _ctx(sandbox=sandbox)
        await BootstrapDepsPhase().execute(ctx)
    mock_bootstrap.assert_awaited_once_with(sandbox, "/workspace/repo")


def test_bootstrap_deps_phase_meta() -> None:
    assert BootstrapDepsPhase.phase_name == "bootstrap_deps"
    assert BootstrapDepsPhase.can_skip is True


# ---------------------------------------------------------------------------
# WorktreeCreatePhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worktree_skips_without_sandbox() -> None:
    ctx = _ctx()
    result = await WorktreeCreatePhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_worktree_creates_and_sets_worktree_path() -> None:
    fake_info = MagicMock()
    fake_info.path = "/workspace/.worktrees/sess-1"
    fake_info.slug = "sess-1"
    fake_info.branch = "session/sess-1"
    with patch(
        "harness.services.worktree_manager.WorktreeManager.create_worktree",
        AsyncMock(return_value=fake_info),
    ):
        ctx = _ctx()
        ctx = replace(ctx, sandbox=MagicMock())
        result = await WorktreeCreatePhase().execute(ctx)
    assert result.worktree_path == "/workspace/.worktrees/sess-1"


@pytest.mark.asyncio
async def test_worktree_swallows_exception() -> None:
    with patch(
        "harness.services.worktree_manager.WorktreeManager.create_worktree",
        AsyncMock(side_effect=RuntimeError("not a git repo")),
    ):
        ctx = _ctx()
        ctx = replace(ctx, sandbox=MagicMock())
        result = await WorktreeCreatePhase().execute(ctx)
    assert result is ctx
    assert result.worktree_path is None


def test_worktree_phase_meta() -> None:
    assert WorktreeCreatePhase.phase_name == "worktree_create"
    assert WorktreeCreatePhase.can_skip is True


# ---------------------------------------------------------------------------
# CloneContextReposPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_repos_skips_when_none() -> None:
    ctx = _ctx()
    result = await CloneContextReposPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_context_repos_clones_each_one() -> None:
    orch = _orchestrator_with_sandbox()
    orch._context_repos = [
        {"url": "https://github.com/acme/lib", "branch": "main"},
        {"url": "https://github.com/acme/util", "branch": ""},
    ]
    sandbox = MagicMock()
    sandbox.run = AsyncMock(return_value=MagicMock(returncode=0))
    ctx = _ctx(orchestrator=orch, sandbox=sandbox)
    result = await CloneContextReposPhase().execute(ctx)
    assert "context_paths" in result.coordinator_result
    paths = result.coordinator_result["context_paths"]
    assert "lib" in paths
    assert "util" in paths


def test_context_repos_phase_meta() -> None:
    assert CloneContextReposPhase.phase_name == "clone_context_repos"
    assert CloneContextReposPhase.can_skip is True


# ---------------------------------------------------------------------------
# InjectCredentialsPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_credentials_skips_without_sandbox() -> None:
    ctx = _ctx()
    result = await InjectCredentialsPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_credentials_skips_when_no_db() -> None:
    with patch("harness.memory.db_context.get_db", return_value=None):
        sandbox = MagicMock()
        ctx = _ctx(sandbox=sandbox)
        result = await InjectCredentialsPhase().execute(ctx)
    sandbox.run.assert_not_called()


@pytest.mark.asyncio
async def test_credentials_injects_gh_token() -> None:
    fake_db = MagicMock()
    fake_db.fetchrow = AsyncMock(
        return_value={"config": {"token": "ghp_abc123"}},
    )
    with patch("harness.memory.db_context.get_db", return_value=fake_db):
        sandbox = MagicMock()
        sandbox.run = AsyncMock()
        orch = MagicMock()
        orch._shq = lambda s: s  # identity — avoids double-quoting
        ctx = _ctx(orchestrator=orch, sandbox=sandbox)
        await InjectCredentialsPhase().execute(ctx)
    sandbox.run.assert_called_once()
    cmd = sandbox.run.await_args.args[0]
    assert "GH_TOKEN=ghp_abc123" in cmd


def test_credentials_phase_meta() -> None:
    assert InjectCredentialsPhase.phase_name == "inject_credentials"
    assert InjectCredentialsPhase.can_skip is True


# ---------------------------------------------------------------------------
# OrchestrateBoardPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrate_calls_cmd_orchestrate_and_sets_board_id() -> None:
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate",
        AsyncMock(return_value='{"board_id": "board-42", "task_count": 5}'),
    ):
        ctx = _ctx()
        result = await OrchestrateBoardPhase().execute(ctx)
    assert result.board_id == "board-42"


@pytest.mark.asyncio
async def test_orchestrate_falls_back_to_direct_kanban() -> None:
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate",
        AsyncMock(side_effect=RuntimeError("LLM is down")),
    ):
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock(status_code=201, json=MagicMock(
                return_value={"id": "fallback-board"},
            ))
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp,
            )
            ctx = _ctx()
            result = await OrchestrateBoardPhase().execute(ctx)
    assert result.board_id == "fallback-board"


@pytest.mark.asyncio
async def test_orchestrate_no_board_when_both_fail() -> None:
    with patch(
        "harness.tools.orchestrator_tool.cmd_orchestrate",
        AsyncMock(side_effect=RuntimeError("LLM is down")),
    ):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=RuntimeError("http also down"),
            )
            ctx = _ctx()
            result = await OrchestrateBoardPhase().execute(ctx)
    assert result.board_id is None


def test_orchestrate_phase_meta() -> None:
    assert OrchestrateBoardPhase.phase_name == "orchestrate_board"
    assert OrchestrateBoardPhase.can_skip is True


# ---------------------------------------------------------------------------
# CoordinatorSpawnPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_spawn_requires_orchestrator() -> None:
    with pytest.raises(RuntimeError):
        await CoordinatorSpawnPhase().execute(_ctx())


def test_coordinator_phase_meta() -> None:
    assert CoordinatorSpawnPhase.phase_name == "coordinator_spawn"
    assert CoordinatorSpawnPhase.can_skip is False


# ---------------------------------------------------------------------------
# PostRunKGSyncPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_run_kg_sync_skips_without_sandbox() -> None:
    ctx = _ctx()
    result = await PostRunKGSyncPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_post_run_kg_sync_runs_knowledge_graph_syncer() -> None:
    with patch(
        "harness.services.knowledge_graph_syncer.KnowledgeGraphSyncer.sync",
        AsyncMock(return_value={"nodeCount": 100, "edgeCount": 50}),
    ):
        ctx = _ctx()
        ctx = replace(
            ctx, sandbox=MagicMock(), kg_ctx=MagicMock(),
        )
        result = await PostRunKGSyncPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_post_run_kg_sync_swallows_exception() -> None:
    with patch(
        "harness.services.knowledge_graph_syncer.KnowledgeGraphSyncer.sync",
        AsyncMock(side_effect=RuntimeError("KG is down")),
    ):
        ctx = _ctx()
        ctx = replace(ctx, sandbox=MagicMock(), kg_ctx=MagicMock())
        result = await PostRunKGSyncPhase().execute(ctx)
    assert result is ctx


def test_post_run_kg_sync_phase_meta() -> None:
    assert PostRunKGSyncPhase.phase_name == "post_run_kg_sync"
    assert PostRunKGSyncPhase.can_skip is True


# ---------------------------------------------------------------------------
# L2ReflectionPhase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l2_reflection_skips_without_repo_url() -> None:
    ctx = _ctx(repo_url="")
    result = await L2ReflectionPhase().execute(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_l2_reflection_calls_schedule() -> None:
    with patch(
        "harness.l2_reflection.schedule_l2_reflection",
    ) as mock_schedule:
        ctx = _ctx()
        ctx = replace(
            ctx,
            coordinator_result={"raw_result": "the coordinator output"},
        )
        await L2ReflectionPhase().execute(ctx)
    mock_schedule.assert_called_once()
    kwargs = mock_schedule.call_args.kwargs
    assert kwargs["repo_url"] == ctx.repo_url
    assert kwargs["run_id"] == ctx.run_id


def test_l2_reflection_phase_meta() -> None:
    assert L2ReflectionPhase.phase_name == "l2_reflection"
    assert L2ReflectionPhase.can_skip is True
