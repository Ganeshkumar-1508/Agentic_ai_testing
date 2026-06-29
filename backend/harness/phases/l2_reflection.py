"""L2ReflectionPhase &mdash; write a 1-paragraph L2 reflection to per-repo memory.

C09: extracted from ``OrchestratorEngine.run_single``. Fire-and-forget
&mdash; the dashboard's HTTP response doesn't wait for the L2
LLM call. The L2 reflection is consumed by the next run on
this repo via the memory tool.
"""
from __future__ import annotations

import logging

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class L2ReflectionPhase(RunPhase):
    """Write a 1-paragraph L2 reflection (fire-and-forget)."""

    phase_name = "l2_reflection"
    can_skip = True  # reflection is best-effort

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.repo_url:
            return ctx
        try:
            from harness.l2_reflection import schedule_l2_reflection
            coordinator_result = ctx.coordinator_result or {}
            raw = coordinator_result.get("raw_result")
            output_str = (
                str(raw)
                if isinstance(raw, str)
                else getattr(raw, "output", None) or str(raw or "")
            )
            run_succeeded, _ = (
                ctx.orchestrator._derive_run_success(raw)
                if ctx.orchestrator and hasattr(ctx.orchestrator, "_derive_run_success")
                else (False, "")
            )
            schedule_l2_reflection(
                repo_url=ctx.repo_url, run_id=ctx.run_id,
                output=output_str, success=run_succeeded,
            )
        except Exception as exc:
            logger.debug("schedule_l2_reflection failed: %s", exc)
        return ctx
