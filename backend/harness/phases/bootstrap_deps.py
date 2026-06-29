"""BootstrapDepsPhase &mdash; detect project language + install dependencies.

C09: extracted from ``OrchestratorEngine.run_single``. Delegates
to the existing ``SandboxBootstrap`` (C03 deepening). Pure
delegation &mdash; the bootstrap logic is already in
``harness.services.sandbox_bootstrap``.
"""
from __future__ import annotations

import logging

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class BootstrapDepsPhase(RunPhase):
    """Detect the project language and install dependencies."""

    phase_name = "bootstrap_deps"
    can_skip = True  # bootstrap failures are non-fatal

    async def execute(self, ctx: RunContext) -> RunContext:
        if ctx.sandbox is None:
            return ctx
        try:
            from harness.services.sandbox_bootstrap import SandboxBootstrap
            await SandboxBootstrap.bootstrap(ctx.sandbox, "/workspace/repo")
            logger.info("Bootstrap completed for %s", ctx.repo_url)
        except Exception as exc:
            logger.debug("bootstrap failed (non-fatal): %s", exc)
        return ctx
