"""Pipeline integration test (C09 slice 9).

Verifies the *structure* of the full pipeline (15 phases, in
order, correct names). Doesn't run the phases end-to-end
because the phases call out to real sandbox / KG / LLM services
that would need extensive mocking. The per-phase unit tests
cover behaviour; this test is the integration contract.
"""
from __future__ import annotations

from harness.phases.pipeline import RunPipeline
from harness.phases.sandbox_prepare import SandboxPreparePhase
from harness.phases.clone_repo import CloneRepoPhase
from harness.phases.bootstrap_deps import BootstrapDepsPhase
from harness.phases.worktree_create import WorktreeCreatePhase
from harness.phases.clone_context_repos import CloneContextReposPhase
from harness.phases.inject_credentials import InjectCredentialsPhase
from harness.phases.kg_index import KGIndexPhase
from harness.phases.memory_load import MemoryLoadPhase
from harness.phases.explore_codebase import ExploreCodebasePhase
from harness.phases.orchestrate_board import OrchestrateBoardPhase
from harness.phases.coordinator_spawn import CoordinatorSpawnPhase
from harness.phases.post_run_kg_sync import PostRunKGSyncPhase
from harness.phases.l2_reflection import L2ReflectionPhase
from harness.phases.evidence_bundle import EvidenceBundlePhase
from harness.phases.finalize_job_spec import FinalizeJobSpecPhase


def _build_full_pipeline() -> RunPipeline:
    return RunPipeline(
        orchestrator=None,
        phases=[
            SandboxPreparePhase(),
            CloneRepoPhase(),
            BootstrapDepsPhase(),
            WorktreeCreatePhase(),
            CloneContextReposPhase(),
            InjectCredentialsPhase(),
            KGIndexPhase(),
            MemoryLoadPhase(),
            ExploreCodebasePhase(),
            OrchestrateBoardPhase(),
            CoordinatorSpawnPhase(),
            PostRunKGSyncPhase(),
            L2ReflectionPhase(),
            EvidenceBundlePhase(),
            FinalizeJobSpecPhase(),
        ],
    )


def test_full_pipeline_has_15_phases() -> None:
    pipeline = _build_full_pipeline()
    assert len(pipeline._phases) == 15


def test_full_pipeline_phases_in_declaration_order() -> None:
    """If anyone reorders a phase, this test flags it. The order
    matters because each phase writes to ``RunContext`` fields
    the next phase reads (e.g. ``SandboxPreparePhase`` writes
    ``ctx.sandbox``; ``CloneRepoPhase`` reads it)."""
    expected = [
        "SandboxPreparePhase", "CloneRepoPhase", "BootstrapDepsPhase",
        "WorktreeCreatePhase", "CloneContextReposPhase",
        "InjectCredentialsPhase", "KGIndexPhase", "MemoryLoadPhase",
        "ExploreCodebasePhase", "OrchestrateBoardPhase",
        "CoordinatorSpawnPhase", "PostRunKGSyncPhase",
        "L2ReflectionPhase", "EvidenceBundlePhase",
        "FinalizeJobSpecPhase",
    ]
    actual = [type(p).__name__ for p in _build_full_pipeline()._phases]
    assert actual == expected


def test_full_pipeline_every_phase_is_can_skip_aware() -> None:
    """Every phase declares ``can_skip`` (true or false). Phases
    that raise on a real failure must set can_skip=False; phases
    that swallow failures must set can_skip=True. The pipeline
    uses this to decide whether to catch + continue or fail
    fast. If a new phase forgets to declare, this test flags it."""
    for phase in _build_full_pipeline()._phases:
        assert isinstance(phase.can_skip, bool), (
            f"{type(phase).__name__} must declare can_skip"
        )


def test_full_pipeline_every_phase_has_phase_name() -> None:
    """Every phase declares ``phase_name`` &mdash; the pipeline uses
    it for the pause-checkpoint label and dashboard activity
    feed."""
    for phase in _build_full_pipeline()._phases:
        assert isinstance(phase.phase_name, str) and phase.phase_name, (
            f"{type(phase).__name__} must declare phase_name"
        )

