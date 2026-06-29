"""InjectCredentialsPhase &mdash; inject GH_TOKEN so commit_and_open_pr works.

C09: extracted from ``OrchestratorEngine.run_single``. Reads
the GitHub integration config from the database and appends
``GH_TOKEN=...`` to ``/workspace/.testai_env`` in the sandbox.
"""
from __future__ import annotations

import json
import logging

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class InjectCredentialsPhase(RunPhase):
    """Inject GH_TOKEN from integration_configs into the sandbox."""

    phase_name = "inject_credentials"
    can_skip = True  # missing GitHub config is a valid state

    async def execute(self, ctx: RunContext) -> RunContext:
        if ctx.sandbox is None:
            return ctx
        try:
            from harness.memory.db_context import get_db
            db = get_db()
            if db is None:
                return ctx
            row = await db.fetchrow(
                "SELECT config FROM integration_configs "
                "WHERE platform = 'github' AND enabled = true LIMIT 1",
            )
            if not row:
                return ctx
            config = row["config"]
            if isinstance(config, str):
                config = json.loads(config)
            token = config.get("token", "") if isinstance(config, dict) else ""
            if not token:
                return ctx
            shq = getattr(ctx.orchestrator, "_shq", lambda s: f"'{s}'")
            await ctx.sandbox.run(
                f"echo 'export GH_TOKEN={shq(token)}' >> /workspace/.testai_env",
                timeout=10,
            )
        except Exception as exc:
            logger.debug("credentials inject failed (non-fatal): %s", exc)
        return ctx
