"""CloneContextReposPhase &mdash; clone read-only context repos for cross-repo analysis.

C09: extracted from ``OrchestratorEngine.run_single``. Context
repos are cloned to ``/workspace/context/{name}/`` and indexed
in a dict on ``ctx.coordinator_result["context_paths"]``.

Context repos are NOT knowledge-graphed and NOT worktree-isolated
&mdash; they're read-only references.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class CloneContextReposPhase(RunPhase):
    """Clone each context repo read-only into the sandbox."""

    phase_name = "clone_context_repos"
    can_skip = True  # no context repos is a valid state

    async def execute(self, ctx: RunContext) -> RunContext:
        context_repos = getattr(ctx.orchestrator, "_context_repos", None) or []
        if not context_repos or ctx.sandbox is None:
            return ctx
        context_paths: dict[str, str] = {}
        for entry in context_repos:
            url = entry.get("url", "")
            if not url:
                continue
            branch = entry.get("branch", "") or ""
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            path = f"/workspace/context/{name}"
            clone_cmd = (
                f"git clone --depth 1 --branch {branch} --single-branch {url} {path} 2>&1"
                if branch
                else f"git clone --depth 1 {url} {path} 2>&1"
            )
            try:
                await ctx.sandbox.run(clone_cmd, timeout=120)
                context_paths[name] = path
            except Exception as exc:
                logger.debug("context repo clone %s failed: %s", name, exc)
        result = dict(ctx.coordinator_result or {})
        result["context_paths"] = context_paths
        return replace(ctx, coordinator_result=result)
