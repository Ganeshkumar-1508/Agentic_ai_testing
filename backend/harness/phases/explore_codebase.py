"""ExploreCodebasePhase &mdash; run parallel KG queries for code context.

C09: extracted from ``OrchestratorEngine.run_single``. The phase
runs the parallel explore agents (``_explore_codebase`` from
``harness.tools.orchestrator_tool``) and attaches the output to
``ctx.explore_findings``.

Public surface:
    ExploreCodebasePhase (no fields)
"""
from __future__ import annotations

import logging
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class ExploreCodebasePhase(RunPhase):
    """Run parallel KG queries to gather code context for the goal.

    The explore phase is best-effort: a failure here doesn't block
    the run. The coordinator gets an empty string in
    ``ctx.explore_findings`` and proceeds.

    Note: ``_explore_codebase`` is the *internal* helper. The
    public surface is the ``orchestrate`` tool &mdash; this phase
    bypasses the tool registry and calls the helper directly so
    the explore happens in the orchestrator's process, not the
    coordinator's.
    """

    phase_name = "explore_codebase"
    can_skip = True  # explore failures are non-fatal

    async def execute(self, ctx: RunContext) -> RunContext:
        try:
            from harness.tools.orchestrator_tool import _explore_codebase
            findings = await _explore_codebase(ctx.goal)
        except Exception as exc:
            logger.debug("explore_codebase failed (non-fatal): %s", exc)
            return ctx
        return replace(ctx, explore_findings=findings or "")
