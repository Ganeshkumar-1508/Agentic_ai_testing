"""WorktreeCreatePhase &mdash; create the per-session git worktree.

C09: extracted from ``OrchestratorEngine.run_single``. Wraps
the existing ``WorktreeManager`` (C01 deepening) and sets the
``current_git_runner`` contextvar so subagents spawned later
inherit the runner.

Best-effort: if worktree creation fails, the run continues
without it (subagents just lose isolation). The phase stashes
the worktree info on ``ctx.worktree_path`` for downstream
phases.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class WorktreeCreatePhase(RunPhase):
    """Create the per-session git worktree (C01 deepening)."""

    phase_name = "worktree_create"
    can_skip = True  # worktree failures are non-fatal

    async def execute(self, ctx: RunContext) -> RunContext:
        if ctx.sandbox is None:
            return ctx
        try:
            from harness.services.worktree_manager import (
                WorktreeManager,
                session_branch,
                session_slug,
                sandbox_git_runner,
                set_current_git_runner,
            )
            git_runner = None
            if ctx.sandbox is not None and getattr(ctx.sandbox, "run", None) is not None:
                try:
                    git_runner = sandbox_git_runner(ctx.sandbox)
                except Exception as exc:
                    logger.debug(
                        "sandbox_git_runner init failed (local fallback): %s",
                        exc,
                    )
            set_current_git_runner(git_runner)
            wt_manager = WorktreeManager(git_runner=git_runner)
            info = await wt_manager.create_worktree(
                Path("/workspace/repo"),
                session_slug(ctx.session_id),
                branch=session_branch(ctx.session_id),
            )
            logger.info(
                "Per-session worktree created: slug=%s branch=%s",
                info.slug, info.branch,
            )
            return replace(ctx, worktree_path=str(info.path))
        except Exception as exc:
            logger.warning(
                "Per-session worktree creation failed (continuing without): %s",
                exc,
            )
            return ctx
