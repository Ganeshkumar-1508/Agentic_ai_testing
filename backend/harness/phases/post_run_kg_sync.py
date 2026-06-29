"""PostRunKGSyncPhase &mdash; incremental KG sync after the coordinator edits files.

C09: extracted from ``OrchestratorEngine.run_single``. Runs
``codegraph sync`` so the host cache reflects the agent's
edits, and seeds the ``kg_refresh`` tool's baseline so its
first in-run call computes a delta.
"""
from __future__ import annotations

import logging

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class PostRunKGSyncPhase(RunPhase):
    """Run ``codegraph sync`` after the coordinator finishes."""

    phase_name = "post_run_kg_sync"
    can_skip = True  # sync failures are non-fatal

    async def execute(self, ctx: RunContext) -> RunContext:
        if ctx.sandbox is None or ctx.kg_ctx is None:
            return ctx
        try:
            from harness.services.knowledge_graph_syncer import (
                KnowledgeGraphSyncer,
            )
            fresh = await KnowledgeGraphSyncer.sync(
                ctx.sandbox, "/workspace/repo", ctx.kg_ctx,
            )
            if fresh:
                try:
                    from harness.tools.kg_refresh_tool import KgRefreshTool
                    from harness.tools.registry import registry
                    kg_tool = registry.get("kg_refresh")
                    if isinstance(kg_tool, KgRefreshTool):
                        kg_tool._seed_baseline(fresh)
                except Exception as exc:
                    logger.debug("kg_refresh baseline seed failed: %s", exc)
        except Exception as exc:
            logger.debug("post-coordinator KG sync failed (non-fatal): %s", exc)
        return ctx
