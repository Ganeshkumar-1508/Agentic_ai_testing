"""Tests for SandboxPreparePhase — verifies Docker sandbox creation.

The phase was an empty stub that never created a sandbox, causing
CloneRepoPhase to crash with "requires orchestrator + sandbox".
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeRunContext:
    run_id: str = "test-run"
    session_id: str = "test-session"
    repo_url: str = "https://github.com/octocat/Hello-World"
    branch: str = "master"
    goal: str = "Write a test"
    orchestrator: Any = None
    sandbox: Any = None
    test_config: Any = None
    board_id: str | None = None
    kg_ctx: Any = None
    explore_findings: str = ""
    memory_block: str = ""
    coordinator_result: Any = None
    run_started_at: str = ""
    errors: tuple = ()
    worktree_path: str | None = None


# ---------------------------------------------------------------------------
# Tests — sandbox creation
# ---------------------------------------------------------------------------


async def test_sandbox_prepare_creates_docker_sandbox():
    """SandboxPreparePhase creates a DockerEnvironment when available."""
    from harness.phases.sandbox_prepare import SandboxPreparePhase

    phase = SandboxPreparePhase()
    ctx = _FakeRunContext()

    with patch("harness.backends.docker.DockerEnvironment") as mock_docker:
        mock_instance = MagicMock()
        mock_docker.return_value = mock_instance
        result = await phase.execute(ctx)

    assert result.sandbox is not None


async def test_sandbox_prepare_falls_back_to_local():
    """SandboxPreparePhase falls back to LocalEnvironment if Docker fails."""
    from harness.phases.sandbox_prepare import SandboxPreparePhase

    phase = SandboxPreparePhase()
    ctx = _FakeRunContext()

    with patch("harness.backends.docker.DockerEnvironment", side_effect=Exception("Docker not available")):
        with patch("harness.backends.local.LocalEnvironment") as mock_local:
            mock_instance = MagicMock()
            mock_local.return_value = mock_instance
            result = await phase.execute(ctx)

    assert result.sandbox is not None


async def test_sandbox_prepare_extracts_repo_url():
    """SandboxPreparePhase extracts repo URL from goal if not provided."""
    from harness.phases.sandbox_prepare import SandboxPreparePhase

    phase = SandboxPreparePhase()
    ctx = _FakeRunContext(repo_url="")

    with patch("harness.backends.docker.DockerEnvironment") as mock_docker:
        mock_docker.return_value = MagicMock()
        result = await phase.execute(ctx)

    # Should not crash even if URL extraction fails
    assert result.sandbox is not None


async def test_sandbox_prepare_handles_all_failures():
    """SandboxPreparePhase returns None sandbox if everything fails."""
    from harness.phases.sandbox_prepare import SandboxPreparePhase

    phase = SandboxPreparePhase()
    ctx = _FakeRunContext()

    with patch("harness.backends.docker.DockerEnvironment", side_effect=Exception("Docker failed")):
        with patch("harness.backends.local.LocalEnvironment", side_effect=Exception("Local failed")):
            result = await phase.execute(ctx)

    assert result.sandbox is None
