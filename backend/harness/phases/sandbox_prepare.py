"""SandboxPreparePhase &mdash; auto-extract repo URL, get/create the sandbox, DNS check.

C09: extracted from ``OrchestratorEngine.run_single``. This is
the first phase in the pipeline; everything downstream depends
on the sandbox existing.

Behaviour:

1. If ``ctx.repo_url`` is empty, try to extract a GitHub URL from
   the goal + (optionally) the JobSpec prompt.
2. Get or create the sandbox from the orchestrator's
   ``sandbox_manager`` (keyed by session_id + repo_url).
3. Run a DNS check to log network connectivity.

The phase mutates ``ctx.repo_url`` (if it was empty and the
extractor found one) and sets ``ctx.sandbox`` (the live
sandbox manager env). The orchestrator's pause-checkpoint
contract is honoured by the pipeline &mdash; the phase itself
does not pause.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class SandboxPreparePhase(RunPhase):
    """Get or create the sandbox, extract repo URL if needed."""

    phase_name = "sandbox_prepare"
    can_skip = False  # no sandbox means no run

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.repo_url:
            ctx = await self._extract_repo_url(ctx)
        # Backend is created per-session via BackendFactory; no
        # up-front sandbox creation needed here.
        return ctx

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
