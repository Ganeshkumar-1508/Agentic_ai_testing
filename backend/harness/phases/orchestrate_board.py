"""OrchestrateBoardPhase &mdash; LLM-decompose the goal into a kanban board.

C09: extracted from ``OrchestratorEngine.run_single``. Calls the
``orchestrate`` tool which asks the LLM to produce a task DAG.
Attaches the board_id to ``ctx.board_id`` so the coordinator
can read it.

Fail-open: if the LLM decomposition fails, the phase falls
back to creating a single-task kanban board via the HTTP API.
"""
from __future__ import annotations

import json
import logging

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class OrchestrateBoardPhase(RunPhase):
    """Decompose the goal into a kanban board + task DAG."""

    phase_name = "orchestrate_board"
    can_skip = True  # no board means coordinator uses direct kanban

    async def execute(self, ctx: RunContext) -> RunContext:
        try:
            from harness.tools.orchestrator_tool import cmd_orchestrate
            kg_node_count = (
                getattr(getattr(ctx, "kg_ctx", None), "node_count", 0) or 0
            )
            repo_context = json.dumps({
                "repo_url": ctx.repo_url,
                "branch": ctx.branch or "main",
                "kg_symbols": kg_node_count,
                "kg_files": 0,
                "explore": ctx.explore_findings[:3000] if ctx.explore_findings else "",
            })
            orchestrate_result = await cmd_orchestrate(
                goal=ctx.goal,
                repo_context=repo_context,
                board_name=f"Run {ctx.run_id[:8]}: "
                           f"{ctx.repo_url.split('/')[-1] or ctx.repo_url}",
                session_id=ctx.session_id,
            )
            orch_data = json.loads(orchestrate_result)
            board_id = orch_data.get("board_id")
            task_count = orch_data.get("task_count", 0)
            logger.info(
                "Orchestrate completed: board=%s, tasks=%d",
                board_id, task_count,
            )
            from dataclasses import replace
            return replace(ctx, board_id=board_id)
        except Exception as exc:
            logger.warning(
                "Orchestrate failed (falling back to direct kanban): %s", exc,
            )
            return await self._fallback_board(ctx)

    async def _fallback_board(self, ctx: RunContext) -> RunContext:
        """Create a single-task kanban board via the HTTP API."""
        try:
            import httpx
            from dataclasses import replace
            board_name = (
                f"Run {ctx.run_id[:8]}: "
                f"{ctx.repo_url.split('/')[-1] or ctx.repo_url}"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:8000/api/kanban/boards",
                    json={"name": board_name, "description": ctx.goal[:500]},
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    board_data = resp.json()
                    board_id = (
                        board_data.get("id") or board_data.get("board_id")
                    )
                    return replace(ctx, board_id=board_id)
        except Exception as exc:
            logger.warning("fallback kanban creation also failed: %s", exc)
        return ctx
