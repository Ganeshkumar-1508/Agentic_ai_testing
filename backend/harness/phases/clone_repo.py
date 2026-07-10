"""CloneRepoPhase &mdash; clone the primary repo into the sandbox.

The phase raises RuntimeError on failure. The pipeline
propagates the exception (can_skip=False), and the orchestrator's
error path catches it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class CloneRepoPhase(RunPhase):
    """Clone the primary repo into the sandbox."""

    phase_name = "clone_repo"
    can_skip = False

    async def execute(self, ctx: RunContext) -> RunContext:
        if ctx.orchestrator is None or ctx.sandbox is None:
            raise RuntimeError("CloneRepoPhase requires orchestrator + sandbox")
        repo_url = ctx.repo_url
        if not repo_url:
            raise RuntimeError("CloneRepoPhase requires a non-empty repo_url")
        if repo_url.startswith("file://") or repo_url.startswith("/"):
            await self._local_copy(ctx, repo_url)
        else:
            await self._git_clone(ctx, repo_url)
        return ctx

    async def _local_copy(self, ctx: RunContext, repo_url: str) -> None:
        if repo_url.startswith("file://"):
            local_path = repo_url[7:]
        else:
            local_path = repo_url
        if not os.path.isdir(local_path):
            raise RuntimeError(f"Local path not found: {local_path}")
        sandbox = ctx.sandbox
        container_id = getattr(sandbox, "container_id", "")
        await sandbox.run("mkdir -p /workspace/repo", timeout=30)
        shq = getattr(ctx.orchestrator, "_shq", lambda s: f"'{s}'")
        cp_cmd = f"docker cp {shq(local_path)}/. {shq(container_id)}:/workspace/repo/"
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cp_cmd, capture_output=True, text=True,
                timeout=300, shell=True,
            ),
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"Local repo copy failed: {err[:200]}")
        await sandbox.run(
            "cd /workspace/repo && git init && "
            "git add -A && "
            "git -c user.email=test@test.com -c user.name=test commit -m 'initial' "
            "2>/dev/null",
            timeout=60,
        )

    async def _git_clone(self, ctx: RunContext, repo_url: str) -> None:
        sandbox = ctx.sandbox
        branch = ctx.branch
        await sandbox.run("rm -rf /workspace/repo && mkdir -p /workspace/repo", timeout=30)
        if branch:
            clone_cmd = f"git clone --depth 1 --branch {branch} {repo_url} /workspace/repo 2>&1"
        else:
            clone_cmd = f"git clone --depth 1 {repo_url} /workspace/repo 2>&1"
        result = await sandbox.run(clone_cmd, timeout=300)
        if result.returncode == 0:
            return
        err = (result.stderr or result.stdout or "").strip()
        # Branch fallback: if the branch doesn't exist on remote, try default branch
        if branch and ("Remote branch" in err and "not found" in err):
            logger.warning("Branch '%s' not found on remote, trying default branch", branch)
            fallback_cmd = f"git clone --depth 1 {repo_url} /workspace/repo 2>&1"
            await sandbox.run("rm -rf /workspace/repo && mkdir -p /workspace/repo", timeout=10)
            fallback_result = await sandbox.run(fallback_cmd, timeout=300)
            if fallback_result.returncode == 0:
                return
            fallback_err = (fallback_result.stderr or fallback_result.stdout or "").strip()
            raise RuntimeError(f"Clone failed (tried branch={branch}, then default): {fallback_err[:1000]}")
        raise RuntimeError(f"Clone failed: {err[:1000]}")
