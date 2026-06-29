"""RunPipeline &mdash; iterates a list of ``RunPhase`` instances over a
``RunContext``, checking the pause signal between each phase.

C09: extracted from the inlined 18-step ``OrchestratorEngine.run_single``
pipeline. The pipeline owns lifecycle (pause-checkpoints, error
collection, the immutable ``RunContext`` chain). Phases own domain
logic and are individually testable with a hand-built ``RunContext``.

Usage::

    pipeline = RunPipeline(
        orchestrator=self,
        phases=[
            SandboxPreparePhase(),
            CloneRepoPhase(),
            BootstrapDepsPhase(),
            # ...
            FinalizeJobSpecPhase(),
        ],
    )
    result = await pipeline.run(ctx)

The pipeline:

1. Iterates phases in declared order.
2. Calls ``await phase.execute(ctx)`` and threads the returned
   ``RunContext`` into the next phase.
3. Checks the pause signal (via the orchestrator's
   ``pause_checkpoint``) between phases. If the user paused,
   the pipeline returns a paused-result dict; the caller is
   expected to surface it.
4. Catches per-phase exceptions. Phases with ``can_skip=True``
   are caught and the failure is added to ``ctx.errors``;
   the pipeline continues. Phases with ``can_skip=False``
   propagate the exception &mdash; the run fails fast.
5. Emits a ``phase.<name>.completed`` (or ``.failed``) event
   for each phase for the dashboard activity feed.

The pipeline does NOT touch the orchestrator's pause-checkpoint
*internals*; it calls the orchestrator's existing
``pause_checkpoint(phase=...)`` method so the pause logic stays
in one place.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from harness.phases import RunContext, RunPhase

logger = logging.getLogger(__name__)


class RunPipeline:
    """Iterate a list of :class:`RunPhase` over a :class:`RunContext`.

    The orchestrator owns lifecycle (pause signal, return-shape
    dict). The pipeline owns the per-phase dispatch + error
    collection.
    """

    def __init__(
        self,
        orchestrator: Any,
        phases: list[RunPhase],
        *,
        on_phase_complete: Callable[[str, RunContext], Awaitable[None]] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._phases = list(phases)
        self._on_phase_complete = on_phase_complete

    async def run(self, ctx: RunContext) -> dict:
        """Execute each phase in order. Returns a final result dict.

        On success: returns the ``run_complete`` shape the
        orchestrator builds in ``run_single`` (the caller is
        expected to add the rest of the payload &mdash; budget,
        evidence, etc. &mdash; after the pipeline returns).
        On pause: returns the paused-result dict (the caller
        surfaces it).
        On phase failure (non-skippable): the exception
        propagates so the orchestrator's error path runs.
        """
        for phase in self._phases:
            ctx, paused = await self._run_phase(ctx, phase)
            if paused is not None:
                return paused
        return {"_pipeline_completed": True, "_ctx": ctx}

    async def _run_phase(
        self, ctx: RunContext, phase: RunPhase,
    ) -> tuple[RunContext, dict | None]:
        phase_name = phase.phase_name
        logger.info("pipeline: starting phase=%s", phase_name)
        try:
            ctx = await phase.execute(ctx)
        except Exception as exc:
            if getattr(phase, "can_skip", False):
                logger.warning(
                    "pipeline: phase=%s failed (can_skip=True, continuing): %s",
                    phase_name, exc,
                )
                ctx = _append_error(ctx, f"{phase_name}: {exc}")
                return ctx, None
            logger.exception("pipeline: phase=%s failed (fatal)", phase_name)
            raise
        # Pause check between phases.
        paused = await self._check_pause(ctx, phase_name)
        if paused is not None:
            return ctx, paused
        if self._on_phase_complete is not None:
            try:
                await self._on_phase_complete(phase_name, ctx)
            except Exception as exc:
                logger.debug("on_phase_complete hook failed: %s", exc)
        return ctx, None

    async def _check_pause(
        self, ctx: RunContext, phase_name: str,
    ) -> dict | None:
        """Delegate to the orchestrator's pause_checkpoint if it
        has one. Returns the paused-result dict, or ``None`` if
        the run should continue.
        """
        pause_fn = getattr(self._orchestrator, "pause_checkpoint", None)
        if pause_fn is None:
            return None
        try:
            return await pause_fn(
                run_id=ctx.run_id, session_id=ctx.session_id,
                phase=phase_name,
            )
        except Exception as exc:
            logger.debug("pause_checkpoint raised (continuing): %s", exc)
            return None


def _append_error(ctx: RunContext, error: str) -> RunContext:
    """Return a new ``RunContext`` with ``error`` appended to ``errors``.

    ``RunContext`` is frozen, so we use ``dataclasses.replace``.
    """
    from dataclasses import replace
    return replace(ctx, errors=ctx.errors + (error,))
