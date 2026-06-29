"""EvidenceBundlePhase &mdash; build a markdown evidence summary for the run.

C09: extracted from ``OrchestratorEngine.run_single``. The bundler
reads the per-session L0 artifacts and groups them by kind
(file edits, bash commands, test results, screenshots). The
output is the markdown string the dashboard renders and (when a
PR context is present) Greptile-TREX-style posts as a PR comment.

Public surface:
    EvidenceBundlePhase (no fields)
"""
from __future__ import annotations

import logging
from dataclasses import replace

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class EvidenceBundlePhase(RunPhase):
    """Build a markdown evidence summary from the run's L0 artifacts.

    Pure phase: no side effects, no external writes. The phase
    attaches the markdown to ``ctx.coordinator_result`` under the
    ``evidence_summary`` key. The orchestrator's success-detector
    and PR-committer consume it.

    Returns the same ``RunContext`` with ``coordinator_result``
    set if the bundler produced output; unchanged otherwise.
    """

    phase_name = "evidence_bundle"
    can_skip = True  # bundler failures are non-fatal

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.session_id:
            return ctx
        try:
            from harness.memory.db_context import get_db
            from harness.evidence import EvidenceBundler

            db = get_db()
            if db is None:
                return ctx
            summary = await EvidenceBundler(db).build_finding_summary(ctx.session_id)
        except Exception as exc:
            logger.debug("evidence bundling failed (non-fatal): %s", exc)
            return ctx
        if summary is None:
            return ctx
        result = dict(ctx.coordinator_result or {})
        result["evidence_summary"] = summary
        return replace(ctx, coordinator_result=result)
