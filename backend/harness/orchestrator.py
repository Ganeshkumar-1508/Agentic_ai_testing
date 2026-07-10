"""OrchestratorEngine — thin bootstrap, then hands control to coordinator agent.

Model B (industry-standard agent harness pattern):
1. Creates sandbox + clones repo + builds KG (infrastructure setup)
2. Runs explore agents for code context (parallel, multi-hop)
3. Creates kanban board (optional, for human visibility only)
4. Spawns ONE coordinator agent with all tools
5. Coordinator drives the work: plans via todo, spawns subagents via delegate_task,
   logs progress to kanban, commits+PRs when done
6. Returns results

Kanban is passive observability — it does NOT drive agent behavior.

Workspace layout (Option C — namespaced paths):
  /workspace/repo/              Primary repo (writable, always present)
  /workspace/context/{name}/    Context repos (read-only, opt-in)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from harness.memory.db_context import get_db
from harness.jobs.spec import _job_spec_store

logger = logging.getLogger(__name__)


async def _bootstrap_sandbox_deps(sandbox: Any, repo_path: str = "/workspace/repo") -> dict:
    """Thin delegate to :meth:`SandboxBootstrap.bootstrap` (C03 Phase 2).

    The manifest / install / log logic moved to
    :class:`harness.services.sandbox_bootstrap.SandboxBootstrap`
    so the language + install tables can be tested without a
    sandbox and the F11 deepening (warm base images per
    ``(language, manifest_hash)``) has a real home.
    """
    from harness.services.sandbox_bootstrap import SandboxBootstrap
    return await SandboxBootstrap.bootstrap(sandbox, repo_path)


def _shq(s: str) -> str:
    """Shell-quote a string for single-quoted usage."""
    return "'" + s.replace("'", "'\\''") + "'"


def _get_session_id(spec: Any) -> str:
    """Extract session_id from a JobSpec context (Pydantic or dict fallback).

    C08 Q4 migrated ``JobSpec.context`` to a typed ``JobContext`` with
    ``session_id`` as a Pydantic field. Old resume checkpoints (plain
    dicts) are handled via fallback.
    """
    ctx = spec.context
    if ctx is None:
        return ""
    if isinstance(ctx, dict):
        return ctx.get("session_id", "") or ""
    if hasattr(ctx, "session_id"):
        return ctx.session_id or ""
    return ""


class OrchestratorEngine:
    """Runs a goal through kanban-driven task execution.

    Usage:
        engine = OrchestratorEngine()
        result = await engine.run(run_id, session_id, repo_url, goal)
    """

    def __init__(self) -> None:
        pass

    @classmethod
    def create_default(cls) -> "OrchestratorEngine":
        return cls()

    async def run_resumed_job_spec(
        self,
        spec_id: str,
        *,
        resumed_by: str = "",
    ) -> dict:
        """Resume a paused job by ``spec_id``.

        The pause path (see :mod:`harness.services.pause_signal` +
        :mod:`harness.services.job_checkpoint`) saves a
        :class:`JobCheckpoint` when the user pauses a running
        job. The :http:post:`/api/jobs/{id}/resume` endpoint
        calls this method to re-spawn the orchestrator with the
        saved checkpoint.

        The new run is "fresh" in the sense that it has a new
        ``run_id`` and goes through ``run_job_spec`` from the
        top. But the spec is preserved (same ``spec_id``,
        same prompt, same repo) and the checkpoint is passed
        in via ``spec.context`` so the orchestrator can log
        "resuming from checkpoint" and surface it on the
        activity feed.

        Returns a structured result:
          - ``{"resumed": True, "spec_id": ..., "checkpoint": {...},
             "run_id": ...}`` on success
          - ``{"resumed": False, "error": ..., "spec_id": ...}``
            on failure (no spec, no checkpoint, dispatch failed)

        Side effects:
          - Pops the :class:`JobCheckpoint` (consumes it) so
            the next pause is fresh.
          - Spawns ``run_job_spec`` as a background task.
          - Emits a ``job.resumed`` stream event for the
            activity feed.
        """
        from harness.services.job_checkpoint import apop_checkpoint
        from harness.jobs.spec import _job_spec_store

        try:
            store = _job_spec_store()
        except Exception:
            store = None
        if store is None:
            return {
                "resumed": False,
                "error": "JobSpecStore not configured",
                "spec_id": spec_id,
            }

        try:
            spec_record = await store.get(spec_id)
        except Exception as exc:
            return {
                "resumed": False,
                "error": f"failed to load spec: {exc}",
                "spec_id": spec_id,
            }
        if spec_record is None:
            return {
                "resumed": False,
                "error": f"spec_id={spec_id} not found",
                "spec_id": spec_id,
            }
        if spec_record.status != "paused":
            return {
                "resumed": False,
                "error": (
                    f"spec_id={spec_id} is not paused "
                    f"(status={spec_record.status})"
                ),
                "spec_id": spec_id,
            }

        # Flip the spec to "running" BEFORE spawning the
        # background task. The cancel_watcher polls the spec
        # status; if it sees "paused" it'll think the run was
        # paused again and try to cancel it.
        try:
            await store.update_status(spec_id, "running")
        except Exception as exc:
            logger.warning(
                "run_resumed_job_spec: failed to flip status: %s", exc,
            )

        checkpoint = await apop_checkpoint(spec_id)
        if checkpoint is None:
            # No checkpoint — the user paused but the orchestrator
            # didn't get to save one before it stopped. We can
            # still resume (start fresh), but log the absence.
            logger.info(
                "run_resumed_job_spec: spec %s has no checkpoint; "
                "starting fresh",
                spec_id,
            )

        # Build a JobSpec from the record. We use ``from_dict``
        # for portability: the record is converted to a plain
        # dict first, then ``from_dict`` re-hydrates the
        # Pydantic ``JobContext`` (or dict fallback).
        from harness.jobs.spec import JobSpec
        spec_dict = {
            "spec_id": spec_record.spec_id,
            "run_id": spec_record.run_id,
            "source": spec_record.source,
            "prompt": spec_record.prompt,
            "repo_url": spec_record.repo_url,
            "branch": spec_record.branch,
            "sha": spec_record.sha,
            "tier": spec_record.tier,
            "capabilities": list(spec_record.capabilities or []),
            "approval": dict(spec_record.approval or {}),
            "context": dict(spec_record.context or {}),
        }
        spec = JobSpec.from_dict(spec_dict)

        # Annotate the context with the resume metadata so the
        # orchestrator + activity feed can surface it. We keep
        # the context as a plain dict (not a Pydantic JobContext)
        # because the orchestrator's existing code calls
        # ``spec.context.get(...)`` which only works on a dict.
        existing_ctx = spec.context
        if hasattr(existing_ctx, "model_dump"):
            ctx = existing_ctx.model_dump()
        elif isinstance(existing_ctx, dict):
            ctx = dict(existing_ctx)
        else:
            ctx = {}
        ctx["resumed_from_checkpoint"] = True
        if checkpoint is not None:
            ctx["checkpoint_paused_at"] = checkpoint.paused_at
            ctx["checkpoint_paused_by"] = checkpoint.paused_by
            # True replay (item 5): pass the saved subagent state
            # to the new run. The LLM uses this to know what
            # was already done (e.g. which subagents completed)
            # and can skip re-doing work. The orchestrator
            # itself doesn't reconstruct the subagent tree —
            # the LLM does the actual skipping based on the
            # ``resumed_subagent_state`` context.
            if checkpoint.subagent_state:
                ctx["resumed_subagent_state"] = checkpoint.subagent_state
            # If the checkpoint's last_result includes a phase,
            # surface it. The LLM can use ``resumed_at_phase``
            # to know where in the pipeline the run was paused.
            if isinstance(checkpoint.last_result, dict):
                phase = checkpoint.last_result.get("phase")
                if phase:
                    ctx["resumed_at_phase"] = phase
        if resumed_by:
            ctx["resumed_by"] = resumed_by
        # Re-assign as a plain dict (overriding the Pydantic
        # model that ``JobSpec.from_dict`` set). The rest of
        # the orchestrator treats context as a dict.
        spec.context = ctx

        # Spawn the orchestrator run as a background task.
        # We don't await it — the resume endpoint returns
        # immediately so the user gets a fast response.
        try:
            asyncio.create_task(self.run_job_spec(spec))
        except RuntimeError:
            # No event loop (e.g. in tests). The caller will
            # need to run the spec themselves.
            logger.warning(
                "run_resumed_job_spec: no event loop; cannot spawn",
            )
            return {
                "resumed": False,
                "error": "no event loop available",
                "spec_id": spec_id,
            }

        # Emit a stream event for the activity feed.
        try:
            from harness.api.state import emit_stream_event
            session_id = (
                (spec_record.context or {}).get("session_id", "")
                if isinstance(spec_record.context, dict) else ""
            )
            await emit_stream_event(
                session_id or "",
                "job.resumed",
                {
                    "spec_id": spec_id,
                    "run_id": spec.run_id,
                    "resumed_by": resumed_by,
                    "had_checkpoint": checkpoint is not None,
                    "paused_at": checkpoint.paused_at if checkpoint else None,
                },
            )
        except Exception as exc:
            logger.debug("job.resumed emit failed: %s", exc)

        return {
            "resumed": True,
            "spec_id": spec_id,
            "run_id": spec.run_id,
            "checkpoint": checkpoint.to_dict() if checkpoint else None,
        }

    async def run(self, spec: Any, context_repos: list[dict] | None = None) -> dict:
        """Primary entry point. Delegates to :meth:`run_job_spec`.

        All callers should use this method. ``run_single`` and ``run_multi``
        are low-level executors called internally by this method.
        """
        return await self.run_job_spec(spec, context_repos=context_repos)


    async def run_job_spec(
        self,
        spec: Any,
        context_repos: list[dict] | None = None,
    ) -> dict:
        logger.info("ORCHESTRATOR: run_job_spec START for spec_id=%s", spec.spec_id)
        print(f"ORCHESTRATOR: run_job_spec START for spec_id={spec.spec_id}")
        """`JobSpec`-aware entry point for the chat→orchestrator handoff.

        The chat Role's `submit_job` tool produces a `JobSpec` and hands
        it to the orchestrator. This method:
          1. Builds a tier-aware goal string for the coordinator
          2. Restricts the coordinator's toolsets to the spec's
             `capabilities` (e.g. tier-2 review-only jobs don't get
             `open_pr`)
          3. Delegates to `run_single` for the actual work

        Tier semantics (matches the Graduated Autonomy model used by
        Mabl / Bug0 / testRigor):
          - tier=1 (autonomous): full toolset, PR auto-opens on success
          - tier=2 (supervised): full toolset, but the coordinator
             stops before opening the PR and posts to the review queue
             instead. A `Proposal` row is created in `pending_review`
             status so the dashboard surfaces it; the human
             (or a CI check) approves and the orchestrator's
             commit-and-pr step runs the merge.
          - tier=3 (human-authored): the coordinator proposes a plan
             (a markdown doc in the kanban board) but does NOT write
             code or open a PR. The user reviews the proposal and
             either approves it (turning it into a tier-1 job) or
             rejects it.

        Returns the same shape as `run_single` plus a `tier` and
        `capabilities` field for downstream consumers.
        """
        # Tier 3: human-authored proposal. Don't run the agent. Just
        # create a kanban board with a placeholder "awaiting human
        # review" task so the user has something to look at.
        if spec.tier == 3:
            return await self._run_human_authored_proposal(spec)

        # Tier 2: create a `Proposal` placeholder in the review
        # queue before the work starts. The proposal is the
        # durable record the dashboard lists under
        # `ProposalStore.list_pending()`. The proposal_id is
        # threaded into the goal so the coordinator's kanban post
        # can reference it. If the ProposalStore isn't wired
        # (e.g. local dev), we still run the work — we just lose
        # the queue persistence.
        proposal_id = None
        if spec.tier == 2:
            proposal_id = await self._create_tier2_proposal(spec)

        # Tier 1 / 2: build a tier-aware goal and toolsets, then
        # delegate to the existing single-repo run.
        # Auto-extract repo_url from prompt if not provided
        repo_url = spec.repo_url
        logger.info("DEBUG run_job_spec: spec.repo_url=%s, spec.prompt=%s", repo_url, (spec.prompt or '')[:100])
        if not repo_url:
            import re as _re
            _prompt_url = _re.search(
                r'https?://github\.com/[^\s,)\]\"\'<>]+',
                spec.prompt or '',
            )
            if _prompt_url:
                repo_url = _prompt_url.group(0).rstrip('/.,;:')
                logger.info("Auto-extracted repo_url from prompt: %s", repo_url)
            else:
                logger.warning("No URL found in prompt: %s", (spec.prompt or '')[:200])
        logger.info("DEBUG run_job_spec: final repo_url=%s", repo_url)

        # C08: cancel/pause propagation. The user can hit
        # ``POST /api/jobs/{id}/cancel`` to flip the spec's
        # status to ``cancelled``. The watcher observes the
        # change and cancels the running task. We use
        # ``run_with_cancel`` (a thin wrapper) so the rest of
        # ``run_single`` doesn't need to know about the spec
        # store.
        # C08 follow-up: thread the spec_id into ``run_single``
        # via a contextvar so the multiple-pause-checkpoints
        # (item 4) can read it from inside ``run_single``.
        from harness.services.pause_signal import (
            set_current_spec_id,
            reset_current_spec_id,
        )
        spec_id_token = set_current_spec_id(spec.spec_id)

        # Item 5 (true replay): start a subagent tracker that
        # listens to ``subagent.completed`` events on the
        # EventSourceSink. The tracker's snapshot is included
        # in the JobCheckpoint on pause, so the LLM knows
        # which subagents completed and can skip re-doing work.
        # See Hermes/openclaude/ohmo research — none of them
        # do this; they all replay-the-transcript or
        # block-new-spawns. This is the cutting-edge pattern.
        from harness.services.job_checkpoint import (
            start_tracker, stop_tracker, get_tracker,
        )
        session_id = _get_session_id(spec)
        start_tracker(spec.spec_id, session_id)

        # Extract test_config from spec context for advanced pipeline settings
        test_config = None
        if hasattr(spec, "context") and spec.context is not None:
            ctx_obj = spec.context
            if hasattr(ctx_obj, "test_config") and ctx_obj.test_config is not None:
                if hasattr(ctx_obj.test_config, "model_dump"):
                    test_config = ctx_obj.test_config.model_dump()
                elif isinstance(ctx_obj.test_config, dict):
                    test_config = ctx_obj.test_config
            elif isinstance(ctx_obj, dict) and "test_config" in ctx_obj:
                test_config = ctx_obj["test_config"]

        run_coro = self.run_single(
            run_id=spec.run_id,
            session_id=session_id,
            repo_url=repo_url,
            goal=self._build_tier_aware_goal(spec, proposal_id=proposal_id),
            branch=spec.branch,
            context_repos=context_repos,
            spec_id=spec.spec_id,
            test_config=test_config,
        )
        # Overall timeout: prevent pipeline from hanging indefinitely
        # on Windows/Docker networking issues or stuck subprocesses
        PIPELINE_TIMEOUT = 900  # 15 minutes
        try:
            result = await asyncio.wait_for(
                self._run_with_cancel_watch(spec, run_coro),
                timeout=PIPELINE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("Pipeline timed out after %ds for spec %s", PIPELINE_TIMEOUT, spec.spec_id)
            result = {"status": "failed", "error": f"Pipeline timed out after {PIPELINE_TIMEOUT}s"}
        finally:
            # Stop the tracker and capture its final state.
            # We don't include it in the auto-checkpoint here
            # (the watcher handles that), but the tracker is
            # available for the resume path to inspect.
            await stop_tracker(spec.spec_id)
            reset_current_spec_id(spec_id_token)

    async def _run_with_cancel_watch(self, spec: Any, run_coro: Any) -> dict:
        """Wrap ``run_coro`` in a cancel watcher.

        C08 follow-up: the chat-facing ``/api/jobs/{id}/cancel``
        endpoint calls ``JobSpecStore.cancel()`` which flips
        the spec's status to ``cancelled``. This watcher polls
        the status and cancels the running task when it sees
        the change.

        If the ``JobSpecStore`` isn't wired (e.g. local dev),
        we fall back to running the coroutine directly — the
        cancellation just won't propagate. (The endpoint
        still returns ``True`` to the user; the cancel is
        recorded in the DB but never observed.)
        """
        try:
            from harness.jobs.spec import _job_spec_store
            store = _job_spec_store()
        except Exception:
            store = None
        if store is None:
            return await run_coro

        from harness.services.cancel_watcher import run_with_cancel
        result, outcome = await run_with_cancel(
            spec.spec_id, store, run_coro,
        )
        if outcome.triggered_cancel:
            logger.info(
                "run_job_spec: spec_id=%s was cancelled "
                "(polled_status=%s, elapsed=%.1fs)",
                spec.spec_id, outcome.polled_until_status,
                outcome.elapsed_seconds,
            )
        if outcome.triggered_pause:
            logger.info(
                "run_job_spec: spec_id=%s was paused "
                "(elapsed=%.1fs); checking for saved checkpoint",
                spec.spec_id, outcome.elapsed_seconds,
            )
            # The watcher set the pause signal. The run_single
            # call already observed it (via _check_pause_for_spec
            # below) and saved the checkpoint. Return a paused
            # result so the caller can distinguish from a
            # natural completion.
            return {
                "success": False,
                "status": "paused",
                "cancelled": False,
                "paused": True,
                "elapsed_seconds": outcome.elapsed_seconds,
            }
        if result is None:
            # The run was cancelled. Return a structured
            # ``cancelled`` result so the caller can distinguish
            # from a natural completion.
            return {
                "success": False,
                "status": outcome.polled_until_status or "cancelled",
                "cancelled": True,
                "elapsed_seconds": outcome.elapsed_seconds,
            }
        # C08 pause follow-up: check the pause signal one
        # more time after the run returns. If the user paused
        # near the end of the run (race between run_single
        # returning and the watcher's next poll), this catches
        # it.
        pause_result = await self._check_pause_for_spec(
            spec_id=spec.spec_id,
            run_id=spec.run_id,
            session_id=_get_session_id(spec),
        )
        if pause_result is not None:
            return pause_result
        return result

    async def _create_tier2_proposal(self, spec: Any) -> str | None:
        """Thin delegate to :meth:`TierPolicy.proposal_id` (C03)."""
        from harness.services.tier_policy import TierPolicy
        return await TierPolicy.proposal_id(spec)

    @staticmethod
    def _build_tier_aware_goal(spec: Any, proposal_id: str | None = None) -> str:
        """Thin delegate to :meth:`TierPolicy.build_goal` (C03)."""
        from harness.services.tier_policy import TierPolicy
        return TierPolicy.build_goal(spec, proposal_id)

    @staticmethod
    def _vars_for_job_spec(spec: Any, proposal_id: str | None = None) -> dict[str, str]:
        """Thin delegate to :meth:`TierPolicy.vars_for_spec` (C03)."""
        from harness.services.tier_policy import TierPolicy
        return TierPolicy.vars_for_spec(spec, proposal_id)

    @staticmethod
    def _run_success_detector() -> "RunSuccessDetector":
        """Return the detector strategy. Today: a single StringMatch
        adapter. Tomorrow: QualityScore and EvidenceMatch adapters
        (per F12). The seam is here so the orchestrator's
        success-derivation logic stops being a special case and
        becomes a strategy dispatch.
        """
        from harness.services.run_success_detector import RunSuccessDetector
        return RunSuccessDetector()

    def _derive_run_success(
        self, result: Any,
        *, session_id: str = "", db: Any = None,
    ) -> tuple[bool, str]:
        """Derive ``(run_succeeded, reason)`` from a delegate_task result.

        Passes ``session_id`` and ``db`` through context for the
        ``VerdictStrategy`` (C5) to read per-tool-call verdicts from
        ``agent_artifacts``. The ``StringMatch`` strategy ignores
        context, so legacy callers that don't pass session_id still
        work.
        """
        detector = self._run_success_detector()
        ctx = {}
        if session_id:
            ctx["session_id"] = session_id
        if db:
            ctx["db"] = db
        is_failure, reason = detector.detect(result, context=ctx or None)
        return (not is_failure), reason

    @staticmethod
    def _fallback_tier_aware_goal(spec: Any, proposal_id: str | None = None) -> str:
        """Thin delegate to :meth:`TierPolicy.fallback_goal` (C03)."""
        from harness.services.tier_policy import TierPolicy
        return TierPolicy.fallback_goal(spec, proposal_id)

    async def _run_human_authored_proposal(
        self,
        spec: Any,
    ) -> dict:
        """Thin delegate to :meth:`TierPolicy.human_authored_proposal` (C03)."""
        from harness.services.tier_policy import TierPolicy
        return await TierPolicy.human_authored_proposal(spec)

    async def run_single(
        self, run_id: str, session_id: str, repo_url: str, goal: str, branch: str = "",
        context_repos: list[dict] | None = None,
        spec_id: str = "",
        test_config: dict | None = None,
    ) -> dict:
        """Run orchestration for a single repo.

        Called by :meth:`run_job_spec` — most callers should use that
        instead for tier/capability/checkpoint support.

        Args:
            context_repos: List of {url, branch} dicts — cloned read-only at
                           /workspace/context/{name}/ for cross-repo analysis.
        """
        # Track the start of this run so the JobSpec row can record
        # ``latest_run_duration_s`` and ``latest_run_cost_usd`` on
        # completion. C08 chat surfaces (``list_jobs``,
        # ``get_job_status``) read these denormalized columns to
        # render summary cards without a JOIN.
        run_started_at = datetime.now(timezone.utc)
        final_status: str = "completed"
        final_error: str | None = None

        # Create the parent session in the database before the pipeline runs.
        # This is required so subagents can reference it via parent_session_id.
        session_created = False
        for attempt in range(3):
            try:
                from harness.tools.subagent import create_child_session
                await create_child_session(
                    session_id, 0, goal, "", None, run_started_at.timestamp(),
                )
                session_created = True
                break
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning("Parent session creation failed after 3 attempts: %s", exc)

        # C09: build the run pipeline. The 12 phases that transform
        # state (sandbox prepare, clone, bootstrap, worktree, kg
        # index, memory load, explore, orchestrate board, coordinator
        # spawn, post-run kg sync, l2 reflection, evidence bundle)
        # are extracted into :mod:`harness.phases`. The orchestrator
        # owns lifecycle (pause, return shape) and runs the pipeline
        # via :class:`harness.phases.pipeline.RunPipeline`. Phases
        # are individually testable with a hand-built ``RunContext``;
        # the pipeline owns the iteration + error collection.
        # Post-pipeline housekeeping (success detection, kanban
        # sweep, JobSpec finalization) stays in the orchestrator
        # below.
        from harness.phases import RunContext as _RCtx
        from harness.phases.pipeline import RunPipeline
        from harness.phases.bootstrap_deps import BootstrapDepsPhase
        from harness.phases.clone_context_repos import CloneContextReposPhase
        from harness.phases.clone_repo import CloneRepoPhase
        from harness.phases.coordinator_spawn import CoordinatorSpawnPhase
        from harness.phases.evidence_bundle import EvidenceBundlePhase
        from harness.phases.explore_codebase import ExploreCodebasePhase
        from harness.phases.finalize_job_spec import FinalizeJobSpecPhase
        from harness.phases.inject_credentials import InjectCredentialsPhase
        from harness.phases.kg_index import KGIndexPhase
        from harness.phases.l2_reflection import L2ReflectionPhase
        from harness.phases.memory_load import MemoryLoadPhase
        from harness.phases.orchestrate_board import OrchestrateBoardPhase
        from harness.phases.post_run_kg_sync import PostRunKGSyncPhase
        from harness.phases.sandbox_prepare import SandboxPreparePhase
        from harness.phases.worktree_create import WorktreeCreatePhase
        pipeline = RunPipeline(
            orchestrator=self,
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
        # The pipeline runs phases in order, threading a RunContext
        # through each. Fatal phase failures propagate as exceptions;
        # skippable-phase errors are accumulated in ctx.errors.
        # The pipeline returns the final RunContext, which the
        # orchestrator unpacks to build the run return value.
        pipeline_ctx = _RCtx(
            run_id=run_id, session_id=session_id, spec_id=spec_id,
            repo_url=repo_url, branch=branch, goal=goal,
            orchestrator=self,
            run_started_at=run_started_at.isoformat(),
            test_config=test_config,
        )
        # Stash context_repos for CloneContextReposPhase, which reads
        # them from ``ctx.orchestrator._context_repos`` during the pipeline.
        self._context_repos = list(context_repos or [])

        # Run the 15-phase pipeline. The pipeline owns phase iteration,
        # between-phase pause checks, and error collection. The
        # orchestrator handles post-pipeline housekeeping below:
        pipeline_result = await pipeline.run(pipeline_ctx)
        if isinstance(pipeline_result, dict) and pipeline_result.get("paused"):
            return pipeline_result
        pipeline_ctx = pipeline_result["_ctx"]
        coordinator_result = pipeline_ctx.coordinator_result or {}
        result = coordinator_result.get("raw_result", "")
        run_succeeded, reason = self._derive_run_success(
            result, session_id=session_id,
            db=get_db(),
        )
        board_id = pipeline_ctx.board_id
        budget_snapshot: dict = coordinator_result.get("budget_snapshot", {})
        evidence_summary = coordinator_result.get("evidence_summary")

        # Spawn coordinator agent factory plumbing is unused now
        # (the phase owns the agent-factory resolution) but the
        # ``_af`` lookup is kept for the ``delegate_task not
        # available`` early-return path.
        # Defensive sweep: the coordinator's session may end (success,
        # failure, or "max tool rounds reached") without calling
        # kanban_complete for every task it claimed. Without this sweep
        # those tasks sit in `in_progress` forever and block the board
        # from being archived. See KanbanService.sweep_orphan_in_progress.
        sweep_summary: dict = {"swept": 0, "completed": 0, "blocked": 0}
        if board_id:
            try:
                from harness.services.kanban_service import KanbanService
                db = get_db()
                if db:
                    svc = KanbanService(db)
                    sweep_summary = await svc.sweep_orphan_in_progress(
                        board_id, run_succeeded=run_succeeded, reason=reason
                    )
                    if sweep_summary.get("swept", 0) > 0:
                        logger.info(
                            "kanban sweep board=%s succeeded=%s swept=%d completed=%d blocked=%d",
                            board_id, run_succeeded,
                            sweep_summary["swept"],
                            sweep_summary["completed"],
                            sweep_summary["blocked"],
                        )
            except Exception as sweep_exc:
                logger.warning(
                    "kanban sweep failed board=%s err=%s — "
                    "tasks may remain in in_progress",
                    board_id, sweep_exc,
                )

        output_str = (
            str(result)
            if isinstance(result, str)
            else getattr(result, "output", None) or str(result)
        )

        return self._maybe_pause_result(
            run_id=run_id,
            session_id=session_id,
            result={
                "success": run_succeeded,
                "board_id": board_id,
                "tasks": [],
                "output": output_str,
                "kanban_sweep": sweep_summary,
                "budget": budget_snapshot,
                "evidence_summary": evidence_summary,
            },
        )

    def _maybe_pause_result(
        self,
        *,
        run_id: str,
        session_id: str,
        result: dict,
    ) -> dict:
        """If the pause signal is set for this spec, save a
        JobCheckpoint and return a paused result instead of the
        natural completion.

        Called at the end of :meth:`run_single` (and the other
        entry points) as the LAST step. If the user clicked
        "pause" while the run was in flight, the cancel_watcher
        set the pause signal; we save the checkpoint and flip
        the result to status="paused".

        The pause signal is then cleared so the next run starts
        with a clean state. A future sprint can use the
        checkpoint to drive an auto-resume.
        """
        # We don't have the spec_id here in the natural flow;
        # the cancel_watcher operates on spec_id, but run_single
        # is keyed by run_id. The orchestrator's run_job_spec
        # wrapper (which DOES have the spec_id) is the place
        # that does the check; this method is a no-op for
        # callers that don't have the spec_id.
        from harness.services.pause_signal import (
            check_pause_signal,
            clear_pause_signal,
        )
        # The pause signal is keyed by spec_id. Without a
        # spec_id we can't check. The real check happens in
        # the run_job_spec wrapper. This method is here so
        # the entry points have a consistent shape; the
        # wrapper layer does the actual pause handling.
        del check_pause_signal, clear_pause_signal
        return result

    async def _check_pause_for_spec(self, spec_id: str, run_id: str, session_id: str) -> dict | None:
        """Check the pause signal for a spec. If set, save a
        JobCheckpoint and return a paused result. If not set,
        return None (caller continues with the natural result).

        The orchestrator's :meth:`run_job_spec` wrapper calls
        this once around the run_single result; for the MVP
        this is the only pause check. A future sprint can
        add more checks at safe points inside the coordinator
        (e.g. between subagent spawns) to make pause more
        responsive.
        """
        from harness.services.pause_signal import (
            check_pause_signal,
            clear_pause_signal,
        )
        if not check_pause_signal(spec_id):
            return None
        # Save the checkpoint. Merge the subagent tracker's
        # snapshot so the LLM knows which subagents completed
        # (item 5 — true replay).
        subagent_state: dict = {"paused_at_phase": "post_run_single"}
        try:
            from harness.services.job_checkpoint import get_tracker
            tracker = get_tracker(spec_id)
            if tracker is not None:
                subagent_state.update(tracker.snapshot())
        except Exception as exc:
            logger.debug("_check_pause_for_spec: tracker snapshot failed: %s", exc)
        try:
            from harness.services.job_checkpoint import asave_checkpoint
            await asave_checkpoint(
                spec_id=spec_id,
                run_id=run_id,
                last_result={"phase": "post_run_single"},
                paused_by=session_id,
                subagent_state=subagent_state,
            )
        except Exception as exc:
            logger.warning("pause checkpoint save failed: %s", exc)
        clear_pause_signal(spec_id)
        logger.info(
            "orchestrator: spec %s paused; checkpoint saved; "
            "returning status=paused",
            spec_id,
        )
        return {
            "success": False,
            "status": "paused",
            "cancelled": False,
            "paused": True,
            "checkpoint_saved": True,
        }

    async def pause_checkpoint(
        self,
        run_id: str,
        session_id: str,
        phase: str,
    ) -> dict | None:
        """Async pause check used at safe points inside
        :meth:`run_single` (sandbox setup, KG index, worktree
        creation, kanban board, post-coordinator).

        Reads the active ``spec_id`` from the
        :func:`pause_signal.get_current_spec_id` contextvar
        (set by :meth:`run_job_spec`). Returns a paused-result
        dict if the pause signal is set; the caller should
        ``return`` it immediately. Returns None if the signal
        is not set (caller continues with normal work).

        Unlike :meth:`_check_pause_for_spec` (which runs AFTER
        ``run_single`` returns), this is called DURING the run,
        so the orchestrator can exit much sooner after the
        user clicks pause. The trade-off: the run's
        partial state isn't fully captured in the checkpoint
        (just the phase name). The auto-resume path re-runs
        the spec from the top, so this is sufficient.
        """
        from harness.services.pause_signal import get_current_spec_id
        spec_id = get_current_spec_id()
        if not spec_id:
            return None
        from harness.services.pause_signal import (
            check_pause_signal,
            clear_pause_signal,
        )
        if not check_pause_signal(spec_id):
            return None
        # Save the checkpoint with the current phase. Merge
        # the subagent tracker's snapshot so the LLM knows
        # which subagents completed (item 5 — true replay).
        # Per Hermes/openclaude/ohmo research: the cutting-
        # edge pattern is to capture the actual subagent
        # state at pause time, not just a phase marker.
        subagent_state: dict = {"paused_at_phase": phase}
        try:
            from harness.services.job_checkpoint import get_tracker
            tracker = get_tracker(spec_id)
            if tracker is not None:
                subagent_state.update(tracker.snapshot())
        except Exception as exc:
            logger.debug("pause_checkpoint: tracker snapshot failed: %s", exc)
        try:
            from harness.services.job_checkpoint import asave_checkpoint
            await asave_checkpoint(
                spec_id=spec_id,
                run_id=run_id,
                last_result={"phase": phase},
                paused_by=session_id,
                subagent_state=subagent_state,
            )
        except Exception as exc:
            logger.warning("pause checkpoint save failed: %s", exc)
        clear_pause_signal(spec_id)
        logger.info(
            "orchestrator: spec %s paused at phase=%s; "
            "returning status=paused",
            spec_id, phase,
        )
        return {
            "success": False,
            "status": "paused",
            "cancelled": False,
            "paused": True,
            "checkpoint_saved": True,
            "paused_at_phase": phase,
        }

    async def run_multi(
        self, run_id: str, session_id: str, repos: list[dict], goal: str,
    ) -> dict:
        """Run orchestration across multiple repos — coordinated PRs with Depends-On.

        .. deprecated::
           Use :meth:`run_job_spec` instead — it wraps this method with
           tier/capability/checkpoint support used by the chat surface,
           webhooks, and all new callers.
        """
        logger.warning("DEPRECATED: call run_job_spec() instead of run_multi() — see run_job_spec docstring")
        import datetime as _dt
        _db = get_db()
        results = []
        for i, repo in enumerate(repos):
            repo_session_id = f"{session_id}-repo-{i}"
            logger.info("Multi-repo [%d/%d]: %s (%s)", i + 1, len(repos), repo["url"], repo_session_id[:16])
            if _db and _db._pool:
                try:
                    now = _dt.datetime.now(tz=_dt.timezone.utc)
                    inherited_backend = "local"
                    parent_row = await _db.fetchrow(
                        "SELECT backend_type FROM sessions WHERE id = $1",
                        session_id,
                    )
                    if parent_row and parent_row.get("backend_type"):
                        inherited_backend = parent_row["backend_type"]
                    await _db.execute(
                        "INSERT INTO sessions (id, source, status, depth, agent_role, goal, repo_url, started_at, parent_session_id, backend_type) "
                        "VALUES ($1, 'multi-repo', 'running', 0, 'orchestrator', $2, $3, $4, $5, $6) "
                        "ON CONFLICT (id) DO NOTHING",
                        repo_session_id, goal[:500] if goal else "", repo["url"],
                        now, session_id, inherited_backend,
                    )
                except Exception as exc:
                    logger.warning("Failed to create repo session %s: %s", repo_session_id, exc)

            context = [
                {"url": r["url"], "branch": r.get("branch", "main")}
                for j, r in enumerate(repos) if j != i
            ]
            try:
                result = await self.run_single(
                    run_id=f"{run_id}-{i}",
                    session_id=repo_session_id,
                    repo_url=repo["url"],
                    goal=goal,
                    branch=repo.get("branch", "main"),
                    context_repos=context,
                )
                results.append({
                    "repo": repo["url"],
                    "success": result.get("success", False),
                    "board_id": result.get("board_id"),
                    "session_id": repo_session_id,
                    "context_repos": [r["url"] for r in context],
                    "branch": repo.get("branch", "main"),
                    "pr_url": result.get("pr_url", ""),
                    "pr_number": result.get("pr_number", 0),
                    "diff_summary": result.get("diff_summary", ""),
                    "error": result.get("error"),
                })
            except Exception as e:
                results.append({"repo": repo["url"], "success": False, "session_id": repo_session_id, "error": str(e)})

        from harness.cross_repo import coordinate_multi_repo_results
        cross = coordinate_multi_repo_results(run_id, results)
        return cross.to_dict()

    async def run(
        self, run_id: str, session_id: str, repo_url: str, goal: str, branch: str = "",
        repos: list[dict] | None = None,
    ) -> dict:
        logger.info("OrchestratorEngine: run=%s repo=%s goal=%s", run_id, repo_url, goal[:80])
        if repos:
            multi_results = await self.run_multi(run_id, session_id, repos, goal)
            return {"success": True, "multi_repo": True, "results": multi_results}
        return await self.run_single(run_id, session_id, repo_url, goal, branch)

    async def _wait_for_board(self, board_id: str, session_id: str, repo_url: str) -> dict:
        """Wait for a kanban board to reach a terminal state.

        C03 push-completion: subscribes to ``board.completed`` /
        ``board.failed`` events on the shared EventSourceSink. Wakes
        up immediately when the kanban service emits the event, with
        a 60s-then-poll safety fallback for cross-process / dropped
        events (see :class:`harness.services.board_waiter.BoardWaiter`).

        Backwards-compat: if the EventSourceSink isn't registered
        (e.g. unit tests, ad-hoc scripts), falls back to a pure
        poll loop with the same cadence as before.
        """
        from harness.services.board_waiter import BoardWaiter
        from harness.api.state import get_event_source_sink

        sink = get_event_source_sink()
        heartbeat = lambda: self._heartbeat(session_id)  # noqa: E731
        waiter = BoardWaiter(
            session_id=session_id,
            board_id=board_id,
            sink=sink,
            heartbeat_cb=heartbeat,
        )
        result = await waiter.wait()

        # Map the BoardWaitResult to the legacy _wait_for_board
        # return shape so downstream callers (and the e2e tests)
        # don't have to change.
        tasks = result.tasks
        if result.status == "completed":
            done_count = sum(1 for t in tasks if t.get("status") == "done")
            await self._send_notification(
                session_id, repo_url, "completed",
                f"All {done_count}/{len(tasks)} tasks done in {int(result.elapsed_seconds)}s",
            )
            return {
                "success": True,
                "board_id": board_id,
                "tasks": tasks,
                "elapsed_seconds": int(result.elapsed_seconds),
                "method": result.method,
                "events_received": result.events_received,
            }
        if result.status in ("stalled", "blocked", "failed"):
            await self._send_notification(
                session_id, repo_url, "failed",
                f"{len(result.stalled_tasks) + len(result.blocked_tasks)} tasks blocked of {len(tasks)}",
            )
            return {
                "success": False,
                "board_id": board_id,
                "status": result.status,
                "tasks": tasks,
                "stalled_tasks": result.stalled_tasks,
                "blocked_tasks": result.blocked_tasks,
                "error": "Tasks blocked",
                "method": result.method,
                "events_received": result.events_received,
            }
        # timed_out
        await self._send_notification(session_id, repo_url, "failed", "Orchestration timed out")
        return {
            "success": False,
            "board_id": board_id,
            "error": "Timed out",
            "method": result.method,
            "events_received": result.events_received,
            "elapsed_seconds": int(result.elapsed_seconds),
        }

    async def _heartbeat(self, session_id: str) -> None:
        """Update session heartbeat timestamp."""
        try:
            db = get_db()
            if db:
                await db.execute(
                    "UPDATE sessions SET heartbeat_at = NOW() WHERE id = $1", session_id,
                )
        except Exception:
            pass

    @staticmethod
    async def resume_abandoned(db) -> list[dict]:
        """Find and update abandoned sessions (running, no heartbeat >5min).
        Non-blocking: just marks them as failed instead of waiting for boards."""
        resumed = []
        try:
            rows = await db.fetch(
                """SELECT id, goal, repo_url FROM sessions
                   WHERE status = 'running'
                     AND heartbeat_at < NOW() - INTERVAL '5 minutes'
                   ORDER BY created_at DESC LIMIT 5"""
            )
            for row in rows:
                # Non-blocking: just mark as failed instead of waiting for boards
                await db.execute(
                    "UPDATE sessions SET status = 'failed', ended_at = NOW(), end_reason = 'abandoned-no-heartbeat' WHERE id = $1",
                    row["id"],
                )
                resumed.append({"session_id": row["id"], "status": "failed"})
                logger.info("Resume abandoned: marked %s as failed (no heartbeat)", row["id"])
        except Exception as e:
            logger.warning("Resume abandoned failed: %s", e)
        return resumed

    async def _send_notification(self, session_id: str, repo_url: str, status: str, summary: str) -> None:
        """Thin delegate to :meth:`NotificationDispatcher.dispatch` (C03 Phase 3).

        The DB query, ``DeliveryRouter`` call, and error-handling
        moved to :class:`harness.services.notification_dispatcher.NotificationDispatcher`
        so the engine stops impersonating the delivery layer.
        The 3 call sites (completed / failed / timeout) are
        unchanged &mdash; the signature is preserved.
        """
        from harness.services.notification_dispatcher import NotificationDispatcher
        await NotificationDispatcher.dispatch(
            session_id=session_id,
            repo_url=repo_url,
            status=status,
            summary=summary,
            db=get_db(),
        )
