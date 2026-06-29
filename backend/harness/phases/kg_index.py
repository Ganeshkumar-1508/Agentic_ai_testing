"""KGIndexPhase — index the codebase into the knowledge graph.

Thin wrapper around KnowledgeGraphSyncer.index(). If indexing fails,
the Phase is skipped (can_skip=True) and the run continues without KG
context — slower but functional.
"""

from __future__ import annotations

import logging

from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class KGIndexPhase(RunPhase):
    """Index the primary repo into the knowledge graph for code-aware agents."""

    phase_name = "kg_index"
    can_skip = True
    _max_retries = 2

    async def execute(self, ctx: RunContext) -> RunContext:
        from harness.services.knowledge_graph_syncer import (
            KnowledgeGraphSyncer, SandboxKGContext,
        )

        kg_ctx = SandboxKGContext.build(
            repo_url=ctx.repo_url or "",
            branch=ctx.branch or "main",
            session_id=ctx.session_id,
        )

        last_exc = None
        for attempt in range(self._max_retries):
            try:
                await KnowledgeGraphSyncer.index(
                    ctx.sandbox, "/workspace/repo", kg_ctx,
                )
                logger.info(
                    "KGIndexPhase completed for %s (attempt %d/%d)",
                    ctx.repo_url, attempt + 1, self._max_retries,
                )
                return replace(ctx, kg_ctx=kg_ctx)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "KGIndexPhase attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries, exc,
                )

        logger.error("KGIndexPhase failed after %d attempts: %s", self._max_retries, last_exc)
        raise last_exc  # type: ignore[misc]
