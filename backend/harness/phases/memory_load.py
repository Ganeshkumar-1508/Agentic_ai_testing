"""MemoryLoadPhase &mdash; load cross-run memory for the repo.

C09: extracted from ``OrchestratorEngine.run_single``. The phase
reads the per-repo memory snapshot and attaches it to
``ctx.memory_block`` so the coordinator's goal string can
include a CROSS-RUN MEMORY section.

Public surface:
    MemoryLoadPhase (no fields)
"""
from __future__ import annotations

import logging
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class MemoryLoadPhase(RunPhase):
    """Load cross-run memory for the repo from the memory tool.

    Pure phase: no side effects, no writes. The phase sets
    ``ctx.memory_block`` to the snapshot string. The coordinator
    consumes it when building the goal string.

    Returns the same ``RunContext`` with ``memory_block`` set
    (possibly to the empty string if no memory exists).
    """

    phase_name = "memory_load"
    can_skip = True  # no memory is a valid state

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.repo_url:
            return ctx
        try:
            from harness.tools.memory_tool import get_memory_snapshot
            snapshot = get_memory_snapshot(ctx.repo_url)
        except Exception as exc:
            logger.debug("memory load failed (non-fatal): %s", exc)
            return ctx
        return replace(ctx, memory_block=snapshot or "")
