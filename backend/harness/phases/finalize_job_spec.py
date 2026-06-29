"""FinalizeJobSpecPhase &mdash; write the terminal JobSpec row to the store.

C09: extracted from ``OrchestratorEngine.run_single``. The phase
runs at the end of the pipeline (after ``EvidenceBundlePhase``).
It writes the terminal status, error, cost, and duration to
the ``JobSpecStore`` and persists the run output (evidence
bundle summary) so ``get_output`` returns it for the dashboard.

The phase uses three ``RunContext`` fields:

- ``ctx.spec_id`` &mdash; the JobSpec to finalize
- ``ctx.run_started_at`` &mdash; ISO timestamp, set by the
  orchestrator at pipeline construction. Used to compute
  ``duration_s``.
- ``ctx.coordinator_result["raw_result"]`` &mdash; the
  coordinator's raw result. The phase derives
  ``run_succeeded`` via the orchestrator's
  ``_derive_run_success``.
- ``ctx.coordinator_result["budget_snapshot"]`` &mdash; the
  per-run budget snapshot, used to populate ``cost_usd``.

Best-effort: any failure is logged and swallowed. The
in-memory ``_FakeStore`` used by most tests has no-op
``update_status`` so this is a no-op for the unit suite. The
Postgres adapter uses these fields to populate the
denormalized ``latest_run_*`` columns read by ``list_jobs``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class FinalizeJobSpecPhase(RunPhase):
    """Write the terminal JobSpec row to the store."""

    phase_name = "finalize_job_spec"
    can_skip = True  # missing spec_id is a valid state (legacy callers)

    async def execute(self, ctx: RunContext) -> RunContext:
        if not ctx.spec_id:
            return ctx
        try:
            run_ended_at = datetime.now(timezone.utc)
            duration_s = self._compute_duration(ctx, run_ended_at)
            coordinator_result = ctx.coordinator_result or {}
            raw = coordinator_result.get("raw_result", "")
            run_succeeded, reason = self._derive_success(ctx, raw)
            final_status = "completed" if run_succeeded else "failed"
            final_error = None if run_succeeded else (
                reason or "run did not succeed"
            )
            from harness.jobs.spec import _job_spec_store
            store = _job_spec_store()
            if store is None:
                return ctx
            spent_usd = float(
                (coordinator_result.get("budget_snapshot") or {})
                .get("spent_usd", 0.0) or 0.0
            )
            await store.update_status(
                ctx.spec_id, final_status,
                completed_at=run_ended_at,
                error=final_error,
                cost_usd=spent_usd,
                duration_s=duration_s,
            )
            if hasattr(store, "add_output"):
                try:
                    from harness.store.protocols import JobOutput
                    evidence_summary = coordinator_result.get(
                        "evidence_summary",
                    )
                    summary_text = (
                        json.dumps(evidence_summary)
                        if isinstance(evidence_summary, dict)
                        else str(evidence_summary or "")
                    )
                    await store.add_output(
                        JobOutput(
                            spec_id=ctx.spec_id,
                            status=final_status,
                            summary=summary_text,
                            artifacts=[],
                            pr_url=None,
                            cost_usd=spent_usd,
                            duration_s=duration_s,
                            completed_at=run_ended_at,
                        ),
                    )
                except Exception as exc:
                    logger.debug(
                        "FinalizeJobSpecPhase add_output failed for %s: %s",
                        ctx.spec_id, exc,
                    )
        except Exception as exc:
            logger.debug(
                "FinalizeJobSpecPhase update_status failed for %s: %s",
                ctx.spec_id, exc,
            )
        return ctx

    def _compute_duration(
        self, ctx: RunContext, run_ended_at: datetime,
    ) -> float:
        if not ctx.run_started_at:
            return 0.0
        try:
            started_at = datetime.fromisoformat(
                ctx.run_started_at.replace("Z", "+00:00"),
            )
            return (run_ended_at - started_at).total_seconds()
        except (ValueError, TypeError):
            return 0.0

    def _derive_success(
        self, ctx: RunContext, raw: Any,
    ) -> tuple[bool, str]:
        """Delegate to the orchestrator's success detector.

        The orchestrator is on ``ctx.orchestrator``; if it's
        not wired, we default to ``(False, "no orchestrator")``.
        """
        orchestrator = ctx.orchestrator
        if orchestrator is None or not hasattr(
            orchestrator, "_derive_run_success",
        ):
            return False, "no orchestrator"
        return orchestrator._derive_run_success(raw)
