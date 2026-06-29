"""Team sweeper — background auto-dissolve for completed teams.

C02 (per docs/2026-06-21-architecture-decision-tree.md#c02) Q5:
  "Auto-dissolve when all members are done" — the system sweeps
  teams where every member's status is ``done`` or ``failed`` and
  marks the team ``dissolved`` so the dashboard doesn't show
  zombies.

This module is the long-lived background task that calls
``TeamService.cleanup_completed()`` every ``TEAM_SWEEPER_INTERVAL``
seconds. It's wired into the FastAPI app via
:func:`start_team_sweeper` (called from ``api/main.py``),
mirroring the kanban review agent at
``services/kanban_service.py:689-756``.

Public surface (stable):
  run_team_sweeper, start_team_sweeper, stop_team_sweeper
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from harness.services.team_service import TeamService

logger = logging.getLogger(__name__)


# Default cadence. Tunable via env var for tight loops in tests.
import os
_DEFAULT_INTERVAL_SECONDS = 60.0
SWEEPER_INTERVAL_SECONDS: float = float(
    os.environ.get("TEAM_SWEEPER_INTERVAL_SECONDS", _DEFAULT_INTERVAL_SECONDS)
)


# Module-level handle for the running task. Set by
# :func:`start_team_sweeper`; cleared by :func:`stop_team_sweeper`.
_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


async def run_team_sweeper(
    app: Any,
    *,
    interval: float = SWEEPER_INTERVAL_SECONDS,
    initial_delay: float = 10.0,
) -> None:
    """Run the team auto-dissolve sweeper forever.

    Mirrors the kanban review agent pattern at
    ``services/kanban_service.py:689`` (free async function,
    started via :func:`start_team_sweeper`).

    Each cycle:
      1. Wait for the configured interval (cancelled by
         :func:`stop_team_sweeper`).
      2. Build a :class:`TeamService` from the wired DB.
      3. Call ``cleanup_completed()`` — auto-dissolves teams
         where every member is ``done`` or ``failed``.
      4. Log the result (count dissolved, errors).

    The first cycle is delayed by ``initial_delay`` seconds (default
    10s) to let the app finish its other startup work (sandbox,
    DB, dispatcher, etc). Pass ``initial_delay=0`` from tests.
    """
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            if not hasattr(app.state, "db") or app.state.db is None:
                await asyncio.sleep(interval)
                continue

            svc = TeamService(app.state.db)
            dissolved = await svc.cleanup_completed()
            if dissolved:
                logger.info(
                    "team_sweeper: auto-dissolved %d teams: %s",
                    len(dissolved), dissolved,
                )
        except asyncio.CancelledError:
            logger.info("team_sweeper: cancelled, exiting")
            raise
        except Exception as exc:
            # Defensive: a transient DB error shouldn't kill the
            # sweeper loop. Log and continue.
            logger.warning("team_sweeper: cycle error (continuing): %s", exc)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("team_sweeper: sleep cancelled, exiting")
            raise


def start_team_sweeper(app: Any) -> asyncio.Task:
    """Start the team auto-dissolve sweeper as a background task.

    Called from ``api/main.py`` during the app's startup phase.
    Returns the asyncio task so the caller can hold a reference
    (useful for tests that want to wait for the sweeper to run).

    Idempotent: a second call returns the existing task rather
    than spawning a duplicate.
    """
    global _task, _stop_event
    if _task is not None and not _task.done():
        logger.debug("start_team_sweeper: already running, returning existing task")
        return _task
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(
        run_team_sweeper(app, interval=SWEEPER_INTERVAL_SECONDS),
        name="team-sweeper",
    )
    logger.info("team_sweeper started (interval=%.1fs)", SWEEPER_INTERVAL_SECONDS)
    return _task


async def stop_team_sweeper() -> None:
    """Stop the team auto-dissolve sweeper.

    Sets the stop event and waits for the task to drain. Safe to
    call multiple times. No-op if the sweeper was never started.
    """
    global _task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("team_sweeper stop error: %s", exc)
    _task = None
    _stop_event = None


__all__ = [
    "run_team_sweeper", "start_team_sweeper", "stop_team_sweeper",
    "SWEEPER_INTERVAL_SECONDS",
]
