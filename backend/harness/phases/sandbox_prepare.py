"""SandboxPreparePhase &mdash; auto-extract repo URL, get/create the sandbox, DNS check.

C09: extracted from ``OrchestratorEngine.run_single``. This is
the first phase in the pipeline; everything downstream depends
on the sandbox existing.

Behaviour:

1. If ``ctx.repo_url`` is empty, try to extract a GitHub URL from
   the goal + (optionally) the JobSpec prompt.
2. Get or create the sandbox from the backend factory
   (``get_backend()``), keyed by session_id.
3. Run a DNS check to log network connectivity.

The phase mutates ``ctx.repo_url`` (if it was empty and the
extractor found one) and sets ``ctx.sandbox`` (the live
sandbox manager env). The orchestrator's pause-checkpoint
contract is honoured by the pipeline &mdash; the phase itself
does not pause.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import replace
from typing import Any

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class SandboxPreparePhase(RunPhase):
    """Get or create the sandbox, extract repo URL if needed."""

    phase_name = "sandbox_prepare"
    can_skip = False  # no sandbox means no run

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.repo_url:
            ctx = await self._extract_repo_url(ctx)

        # Create the sandbox via the backend factory
        sandbox = await self._create_sandbox(ctx)
        if sandbox is None:
            logger.warning("SandboxPreparePhase: could not create sandbox for session %s", ctx.session_id)
            return ctx

        # Run DNS check
        await self._dns_check(sandbox)

        return replace(ctx, sandbox=sandbox)

    async def _create_sandbox(self, ctx: RunContext) -> Any:
        """Create a sandbox environment for this session."""
        try:
            # Try to get backend_factory from the orchestrator's app state
            backend_factory = None
            if ctx.orchestrator is not None:
                backend_factory = getattr(ctx.orchestrator, "_backend_factory", None)
            if backend_factory is not None:
                sandbox = backend_factory(ctx.session_id, cwd="/workspace/repo", timeout=120)
                logger.info("SandboxPreparePhase: created sandbox for session %s (type=%s)",
                           ctx.session_id, type(sandbox).__name__)
                return sandbox

            # Fallback: create DockerEnvironment directly
            from harness.backends.docker import DockerEnvironment
            sandbox = DockerEnvironment(
                session_id=ctx.session_id,
                cwd="/workspace/repo",
                timeout=120,
                image="nikolaik/python-nodejs:python3.11-nodejs20",
            )
            logger.info("SandboxPreparePhase: created Docker sandbox for session %s",
                       ctx.session_id)
            return sandbox
        except Exception as exc:
            logger.warning("SandboxPreparePhase: sandbox creation failed: %s", exc)
            # Final fallback: LocalEnvironment
            try:
                from harness.backends.local import LocalEnvironment
                is_win = sys.platform.startswith("win")
                sandbox = LocalEnvironment(
                    session_id=ctx.session_id,
                    cwd="/workspace/repo" if not is_win else os.path.join(os.getcwd(), "workspace", "repo"),
                    timeout=120,
                )
                logger.info("SandboxPreparePhase: created local sandbox for session %s (fallback type=%s)",
                           ctx.session_id, type(sandbox).__name__)
                return sandbox
            except Exception as exc2:
                logger.warning("SandboxPreparePhase: local fallback also failed: %s", exc2)
                return None

    async def _extract_repo_url(self, ctx: RunContext) -> RunContext:
        try:
            from harness.services.url_extractor import URLAutoExtractor
            spec = getattr(ctx.orchestrator, "_current_spec", None)
            spec_prompt = ""
            if spec is not None:
                spec_prompt = getattr(spec, "prompt", "") or ""
            url = URLAutoExtractor.extract(ctx.goal, spec_prompt) or ""
        except Exception as exc:
            logger.debug("URL extract failed (non-fatal): %s", exc)
            return ctx
        return replace(ctx, repo_url=url)

    async def _dns_check(self, sandbox: Any) -> None:
        try:
            dns_check = await sandbox.run(
                "getent hosts github.com 2>/dev/null || echo 'DNS_FAIL'",
                timeout=15,
            )
            resolved = (
                dns_check.stdout.strip()
                if dns_check.returncode == 0
                else "unknown"
            )
            logger.info(
                "Sandbox DNS check: github.com → %s (exit=%d)",
                resolved[:60], dns_check.returncode,
            )
        except Exception as exc:
            logger.debug("DNS check failed (non-fatal): %s", exc)
