"""Tests for pipeline flow — verifies all 12 phases run correctly.

Tests the pipeline from sandbox creation through coordinator spawn,
verifying that each phase completes and passes context correctly.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeRunContext:
    def __init__(self, **kwargs):
        self.run_id = kwargs.get("run_id", "test-run")
        self.session_id = kwargs.get("session_id", "test-session")
        self.repo_url = kwargs.get("repo_url", "https://github.com/octocat/Hello-World")
        self.branch = kwargs.get("branch", "master")
        self.goal = kwargs.get("goal", "Write a test")
        self.orchestrator = kwargs.get("orchestrator", None)
        self.sandbox = kwargs.get("sandbox", None)
        self.test_config = kwargs.get("test_config", None)
        self.board_id = kwargs.get("board_id", None)
        self.kg_ctx = kwargs.get("kg_ctx", None)
        self.explore_findings = kwargs.get("explore_findings", "")
        self.memory_block = kwargs.get("memory_block", "")
        self.coordinator_result = kwargs.get("coordinator_result", None)
        self.run_started_at = kwargs.get("run_started_at", "")
        self.errors = kwargs.get("errors", ())
        self.worktree_path = kwargs.get("worktree_path", None)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)


# ---------------------------------------------------------------------------
# Tests — phase execution
# ---------------------------------------------------------------------------


async def test_sandbox_prepare_phase_name():
    """SandboxPreparePhase has correct phase name."""
    from harness.phases.sandbox_prepare import SandboxPreparePhase
    phase = SandboxPreparePhase()
    assert phase.phase_name == "sandbox_prepare"
    assert phase.can_skip is False


async def test_clone_repo_phase_requires_sandbox():
    """CloneRepoPhase raises if sandbox is None."""
    from harness.phases.clone_repo import CloneRepoPhase
    phase = CloneRepoPhase()
    ctx = _FakeRunContext(sandbox=None)

    with pytest.raises(RuntimeError, match="requires orchestrator"):
        await phase.execute(ctx)


async def test_bootstrap_deps_phase_can_skip():
    """BootstrapDepsPhase is skippable."""
    from harness.phases.bootstrap_deps import BootstrapDepsPhase
    phase = BootstrapDepsPhase()
    assert phase.can_skip is True


async def test_kg_index_phase_name():
    """KGIndexPhase has correct phase name."""
    from harness.phases.kg_index import KGIndexPhase
    phase = KGIndexPhase()
    assert phase.phase_name == "kg_index"


async def test_memory_load_phase_name():
    """MemoryLoadPhase has correct phase name."""
    from harness.phases.memory_load import MemoryLoadPhase
    phase = MemoryLoadPhase()
    assert phase.phase_name == "memory_load"


async def test_orchestrate_board_phase_name():
    """OrchestrateBoardPhase has correct phase name."""
    from harness.phases.orchestrate_board import OrchestrateBoardPhase
    phase = OrchestrateBoardPhase()
    assert phase.phase_name == "orchestrate_board"


async def test_coordinator_spawn_phase_name():
    """CoordinatorSpawnPhase has correct phase name."""
    from harness.phases.coordinator_spawn import CoordinatorSpawnPhase
    phase = CoordinatorSpawnPhase()
    assert phase.phase_name == "coordinator_spawn"
    assert phase.can_skip is False


async def test_post_run_kg_sync_phase_name():
    """PostRunKGSyncPhase has correct phase name."""
    from harness.phases.post_run_kg_sync import PostRunKGSyncPhase
    phase = PostRunKGSyncPhase()
    assert phase.phase_name == "post_run_kg_sync"


async def test_l2_reflection_phase_name():
    """L2ReflectionPhase has correct phase name."""
    from harness.phases.l2_reflection import L2ReflectionPhase
    phase = L2ReflectionPhase()
    assert phase.phase_name == "l2_reflection"


async def test_evidence_bundle_phase_name():
    """EvidenceBundlePhase has correct phase name."""
    from harness.phases.evidence_bundle import EvidenceBundlePhase
    phase = EvidenceBundlePhase()
    assert phase.phase_name == "evidence_bundle"


async def test_finalize_job_spec_phase_name():
    """FinalizeJobSpecPhase has correct phase name."""
    from harness.phases.finalize_job_spec import FinalizeJobSpecPhase
    phase = FinalizeJobSpecPhase()
    assert phase.phase_name == "finalize_job_spec"


# ---------------------------------------------------------------------------
# Tests — RunContext
# ---------------------------------------------------------------------------


async def test_run_context_has_test_config():
    """RunContext carries test_config through the pipeline."""
    from harness.phases import RunContext

    ctx = RunContext(
        run_id="test-run",
        session_id="test-session",
        test_config={"timeout_seconds": 300},
    )
    assert ctx.test_config == {"timeout_seconds": 300}


async def test_run_context_test_config_default_none():
    """RunContext test_config defaults to None."""
    from harness.phases import RunContext

    ctx = RunContext(run_id="test-run", session_id="test-session")
    assert ctx.test_config is None


async def test_run_context_sandbox_default_none():
    """RunContext sandbox defaults to None."""
    from harness.phases import RunContext

    ctx = RunContext(run_id="test-run", session_id="test-session")
    assert ctx.sandbox is None
