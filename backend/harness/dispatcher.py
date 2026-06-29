"""Dispatcher daemon — Hermes-style 60s tick loop.

A long-lived `asyncio.create_task` that runs every 60 seconds. Each
tick reconciles three things:

  1. **Reclaim stale claims.** Tasks stuck in `in_progress` whose
     `claim_expires_at` is in the past are bumped to `ready`, their
     `claim_token` cleared, and their `failure_count` incremented.
     This catches the case where a subagent crashed mid-work and
     never released the claim.

  2. **Auto-block spin-loops.** Tasks whose `failure_count` has hit
     the board's `config.failure_limit` and that are NOT already
     blocked are moved to `blocked`. This is the same check the
     `claim_task` service method does, but proactive: even if no
     one re-claims the task, the dispatcher sees it and blocks it
     so the board doesn't keep cycling.

  3. **Sweep orphan in-progress tasks.** For each board with
     `in_progress` tasks, call `KanbanService.sweep_orphan_in_progress`
     (renamed internally) to mark stragglers as done or blocked
     based on a run-succeeded flag. (The orchestrator's end-of-run
     sweep handles the same case at run-end; the dispatcher handles
     it for runs that crashed before reaching the sweep.)

The daemon is **non-essential** — losing a tick is fine. The
sweeper, the failure counter, and the orchestrator's end-of-run
sweep are all belt-and-suspenders for the same problem. The
daemon is the *structural* fix: it runs even when the orchestrator
process crashes.

Reference: `reference/hermes-agent/AGENTS.md:861-866` describes the
Hermes dispatcher (every 60s, reclaims stale claims, promotes ready
tasks, atomically claims, spawns assigned profiles). TestAI's
version is narrower: it doesn't spawn new runs from here; the
orchestrator's coordinator is still the only thing that creates
new work. The dispatcher's job is purely to reconcile state, not
to create it.

Reference: `reference/hermes-agent/AGENTS.md:879-881` describes
`kanban.failure_limit=2` auto-block. TestAI uses the same default
(2) with a per-board override via `config.failure_limit`.

Tested behavior:
  - 60s sleep between ticks (configurable)
  - Exceptions in one tick are logged, do not stop the loop
  - `start()` and `stop()` are idempotent
  - `tick()` can be invoked manually via the admin endpoint for
    debugging / E2E tests
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class Dispatcher:
    """Long-lived reconciliation loop for the kanban.

    The loop is intentionally simple: a `while not stop_event.is_set()`
    with `await asyncio.wait_for(stop_event.wait(), timeout=interval)`.
    When the timeout fires (no one called stop), we run a tick and
    loop. When someone calls `stop()`, the wait returns immediately
    and we exit cleanly.

    Tick body:
      1. `_reclaim_stale_claims()` — `SELECT ... WHERE claim_expires_at
         < NOW() AND column_name='in_progress'`, move to `ready`,
         increment `failure_count`, clear `claim_token`.
      2. `_auto_block_spin_loops()` — for each over-limit task, set
         column to `blocked`.
      3. `_sweep_orphans()` — for each board with in_progress tasks,
         call `KanbanService.sweep_orphan_in_progress` to mark
         stragglers. (The orchestrator's end-of-run sweep calls the
         same service method; this is the safety net for crashed
         runs.)
    """

    def __init__(self, db: Any, sweep_interval_seconds: float = 60.0) -> None:
        self.db = db
        self.interval = sweep_interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.ticks: int = 0
        self.last_tick_at: datetime | None = None
        self.last_summary: dict[str, int] = {
            "reclaimed": 0, "auto_blocked": 0, "orphan_swept": 0,
            "orphan_completed": 0, "orphan_blocked": 0,
        }
        self._failure_limit_default = 2

    # ── lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the tick loop. Idempotent — calling twice is a no-op."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="dispatcher-tick-loop")
        logger.info("dispatcher started (interval=%.1fs)", self.interval)

    async def stop(self) -> None:
        """Signal the tick loop to exit. Idempotent."""
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=self.interval + 5.0)
        except asyncio.TimeoutError:
            logger.warning("dispatcher stop timed out — cancelling task")
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        logger.info("dispatcher stopped")

    # ── tick loop ────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception as exc:
                logger.exception("dispatcher tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> dict[str, int]:
        """Run a single reconciliation pass and return the summary.

        Manually invokable from the admin endpoint for debugging.
        """
        self.ticks += 1
        self.last_tick_at = datetime.now(timezone.utc)
        reclaimed = await self._reclaim_stale_claims()
        auto_blocked = await self._auto_block_spin_loops()
        orphan_summary = await self._sweep_orphans()
        self.last_summary = {
            "reclaimed": reclaimed,
            "auto_blocked": auto_blocked,
            "orphan_swept": orphan_summary.get("swept", 0),
            "orphan_completed": orphan_summary.get("completed", 0),
            "orphan_blocked": orphan_summary.get("blocked", 0),
        }
        if any(v > 0 for v in self.last_summary.values()):
            logger.info("dispatcher tick %d: %s", self.ticks, self.last_summary)
        return self.last_summary

    # ── reconciliation passes ────────────────────────────────────────

    async def _reclaim_stale_claims(self) -> int:
        """Move `in_progress` tasks whose claim expired back to `ready`.

        Increments `failure_count` so a chronically stuck task is
        auto-blocked on a future tick (see `_auto_block_spin_loops`).
        Emits a `task.claim_expired` event per task.
        """
        rows = await self.db.fetch(
            "UPDATE kanban_tasks SET column_name='ready', claim_token=NULL, "
            "failure_count=failure_count+1, updated_at=NOW() "
            "WHERE column_name='in_progress' AND claim_expires_at < NOW() "
            "RETURNING id, board_id, failure_count"
        )
        for r in rows:
            await self.db.execute(
                "INSERT INTO kanban_events (board_id, task_id, event_type, payload) "
                "VALUES ($1, $2, $3, $4)",
                r["board_id"], r["id"], "task.claim_expired",
                json.dumps({"failure_count": r["failure_count"]}),
            )
        return len(rows)

    async def _auto_block_spin_loops(self) -> int:
        """Move over-limit tasks to `blocked`.

        Honors the per-board `config.failure_limit` override. Tasks
        already in `blocked` are skipped. Emits `task.auto_blocked`.
        """
        rows = await self.db.fetch(
            "SELECT t.id, t.board_id, t.failure_count, b.config "
            "FROM kanban_tasks t JOIN kanban_boards b ON b.id = t.board_id "
            "WHERE t.column_name NOT IN ('blocked', 'done', 'review') "
            "AND t.failure_count >= 2"
        )
        blocked = 0
        for r in rows:
            limit = self._failure_limit_from_config(r["config"])
            if r["failure_count"] < limit:
                continue
            await self.db.execute(
                "UPDATE kanban_tasks SET column_name='blocked', claim_token=NULL, "
                "updated_at=NOW() WHERE id=$1",
                r["id"],
            )
            await self.db.execute(
                "INSERT INTO kanban_events (board_id, task_id, event_type, payload) "
                "VALUES ($1, $2, $3, $4)",
                r["board_id"], r["id"], "task.auto_blocked",
                json.dumps({
                    "reason": "failure_limit",
                    "failure_count": r["failure_count"],
                    "failure_limit": limit,
                }),
            )
            blocked += 1
        return blocked

    async def _sweep_orphans(self) -> dict[str, int]:
        """Mark orphan `in_progress` tasks for each board.

        Calls the existing `KanbanService.sweep_orphan_in_progress`
        for every board that has at least one in-progress task. The
        sweep auto-completes or auto-blocks based on a per-board
        run-succeeded signal — but in the dispatcher's case, we
        don't have that signal, so we default to `block` (conservative:
        prefer a false-positive block over a false-positive completion).

        Returns aggregate counts across all boards.
        """
        from harness.services.kanban_service import KanbanService

        boards = await self.db.fetch(
            "SELECT DISTINCT board_id FROM kanban_tasks "
            "WHERE column_name='in_progress'"
        )
        if not boards:
            return {"swept": 0, "completed": 0, "blocked": 0}
        svc = KanbanService(self.db)
        total = {"swept": 0, "completed": 0, "blocked": 0}
        for row in boards:
            summary = await svc.sweep_orphan_in_progress(
                row["board_id"],
                run_succeeded=False,  # conservative: prefer block over complete
                reason="dispatcher_tick_orphan",
            )
            total["swept"] += summary.get("swept", 0)
            total["completed"] += summary.get("completed", 0)
            total["blocked"] += summary.get("blocked", 0)
        return total

    # ── helpers ──────────────────────────────────────────────────────

    def _failure_limit_from_config(self, config: Any) -> int:
        """Same defensive extraction as `KanbanService._failure_limit_from_config`."""
        default = self._failure_limit_default
        if not config:
            return default
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (TypeError, ValueError):
                return default
        if not isinstance(config, dict):
            return default
        raw = config.get("failure_limit", default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        if value < 1:
            return default
        return value

    # ── status ───────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Snapshot for the admin endpoint and the dashboard."""
        return {
            "running": self._task is not None and not self._task.done(),
            "interval_seconds": self.interval,
            "ticks": self.ticks,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_summary": self.last_summary,
        }
