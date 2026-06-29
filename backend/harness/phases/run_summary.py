"""RunSummaryPhase — captures run outcome and stores as cross-run memory.

Hidden agent pattern (inspired by OpenClaude): runs invisibly after the
coordinator completes. Captures the coordinator's final result, run
metrics, and key decisions, then persists them as L2 curated lessons
for future runs to reference.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class RunSummaryPhase(RunPhase):
    """Post-run summary: captures outcome, stores cross-run memory, names session."""

    phase_name = "run_summary"
    can_skip = True

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.coordinator_result:
            logger.info("RunSummaryPhase: no coordinator result, skipping")
            return ctx

        summary = self._build_summary(ctx)
        await self._store_memory(ctx, summary)
        await self._name_session(ctx, summary)

        logger.info("RunSummaryPhase: stored summary for run %s", ctx.run_id)
        return replace(ctx, errors=(*ctx.errors, f"run_summary: completed"))

    def _build_summary(self, ctx: RunContext) -> dict:
        coord = ctx.coordinator_result or {}
        return {
            "run_id": ctx.run_id,
            "session_id": ctx.session_id,
            "repo_url": ctx.repo_url,
            "goal": ctx.goal[:200] if ctx.goal else "",
            "success": coord.get("success", False),
            "board_id": ctx.board_id,
            "error": coord.get("error"),
            "task_count": coord.get("task_count", 0),
            "completed_tasks": coord.get("completed_tasks", 0),
            "failed_tasks": coord.get("failed_tasks", 0),
        }

    async def _store_memory(self, ctx: RunContext, summary: dict) -> None:
        """Store key decisions as L2 cross-run memory."""
        try:
            from harness.tools.memory_tool import add_memory
            if summary.get("success"):
                await add_memory(
                    ctx.repo_url,
                    f"Run {ctx.run_id}: {summary['goal'][:100]}",
                    metadata={
                        "type": "run_summary",
                        "run_id": ctx.run_id,
                        "board_id": ctx.board_id,
                        "success": True,
                    },
                )
        except Exception as e:
            logger.debug("RunSummaryPhase: store_memory failed: %s", e)

    async def _name_session(self, ctx: RunContext, summary: dict) -> None:
        """Update the session title with a descriptive name."""
        try:
            if not ctx.db:
                return
            status = "✓" if summary.get("success") else "✗"
            title = f"{status} {summary['goal'][:80]}"
            await ctx.db.execute(
                "UPDATE sessions SET title = $1 WHERE id = $2",
                title, ctx.session_id,
            )
        except Exception as e:
            logger.debug("RunSummaryPhase: name_session failed: %s", e)
