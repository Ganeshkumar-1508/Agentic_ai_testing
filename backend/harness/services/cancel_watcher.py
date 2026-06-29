"""Cancel watcher - propagate JobSpecStore.cancel() / pause() to the running task.

C08 follow-up (deferred from the original design): the chat-facing
``POST /api/jobs/{id}/cancel`` endpoint calls
``JobSpecStore.cancel()`` which flips the spec's status
to ``"cancelled"`` in the DB. The store method existed, but no
caller observed the change - the running orchestrator didn't
know to abort.

This module is the seam. The :func:`watch_for_cancel` function
polls the spec's status every ``interval`` seconds. When the
status becomes terminal, it acts on the running task:

  - ``"cancelled"`` / ``"failed"`` -> cancel the task (the
    orchestrator's try/except translates the cancel into a
    clean shutdown).
  - ``"paused"`` -> set the pause signal (see
    :mod:`harness.services.pause_signal`); the orchestrator
    observes the signal at safe points, saves a
    :class:`JobCheckpoint`, and returns cleanly with
    status="paused".

The pause path is distinct from the cancel path: a paused run
saves its state and can be re-submitted; a cancelled run is
discarded.

Public surface (stable):
  watch_for_cancel, CancelWatchOutcome, run_with_cancel
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Default polling cadence. Tunable via the ``interval`` parameter;
# 2 seconds is the C08 open question's "reasonable" default.
DEFAULT_CANCEL_POLL_INTERVAL_SECONDS = 2.0

# Statuses that should cancel the running task (hard stop).
CANCEL_STATUSES: frozenset[str] = frozenset({
    "cancelled", "failed",
})

# Statuses that should pause the running task (graceful stop).
PAUSE_STATUSES: frozenset[str] = frozenset({
    "paused",
})

# Backward-compat alias used by callers that still think of
# "paused" as a terminal status. New code should import
# CANCEL_STATUSES + PAUSE_STATUSES separately.
TERMINAL_STATUSES: frozenset[str] = CANCEL_STATUSES | PAUSE_STATUSES

# How long to wait for the running task to acknowledge a pause
# signal before giving up. If the task is still running after
# this timeout, the watcher falls back to cancelling it (the
# pause path is best-effort - the user still gets a stopped
# run, just not as gracefully).
PAUSE_GRACE_SECONDS = 30.0


class CancelWatchOutcome:
    """What the cancel watcher observed during its lifetime.

    Returned by :func:`watch_for_cancel` so the orchestrator can
    log the outcome (the spec status, how long the task ran,
    whether the watcher triggered a cancel or pause).
    """

    __slots__ = (
        "spec_id",
        "polled_until_status",
        "triggered_cancel",
        "triggered_pause",
        "elapsed_seconds",
        "interval",
    )

    def __init__(
        self,
        spec_id: str,
        polled_until_status: str | None,
        triggered_cancel: bool,
        triggered_pause: bool,
        elapsed_seconds: float,
        interval: float,
    ) -> None:
        self.spec_id = spec_id
        self.polled_until_status = polled_until_status
        self.triggered_cancel = triggered_cancel
        self.triggered_pause = triggered_pause
        self.elapsed_seconds = elapsed_seconds
        self.interval = interval

    def __repr__(self) -> str:
        return (
            f"CancelWatchOutcome(spec_id={self.spec_id!r}, "
            f"polled_until_status={self.polled_until_status!r}, "
            f"triggered_cancel={self.triggered_cancel}, "
            f"triggered_pause={self.triggered_pause}, "
            f"elapsed_seconds={self.elapsed_seconds:.1f}, "
            f"interval={self.interval:.1f})"
        )


async def watch_for_cancel(
    spec_id: str,
    running_task: asyncio.Task,
    job_spec_store: Any,
    *,
    interval: float = DEFAULT_CANCEL_POLL_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
) -> CancelWatchOutcome:
    """Poll ``job_spec_store.get_status`` until ``running_task`` is
    done or the spec's status becomes ``cancelled`` / ``paused`` /
    ``failed``.

    Behavior by status:
      - ``cancelled`` / ``failed`` -> cancel the running task.
      - ``paused`` -> set the pause signal and wait for the
        task to acknowledge it (graceful exit, with a
        :class:`JobCheckpoint` saved). Falls back to
        cancelling if the task doesn't respond within
        :data:`PAUSE_GRACE_SECONDS`.

    Args:
      spec_id: The spec id to poll. We call
        ``job_spec_store.get_status(spec_id)`` on each cycle.
      running_task: The orchestrator's run task. Cancelled
        for cancel statuses; signalled (not cancelled) for
        pause statuses.
      job_spec_store: The :class:`JobSpecStore` (any implementation
        - Postgres, in-memory, etc). Must have an async
        ``get_status(spec_id) -> JobStatus | None`` method.
      interval: Polling cadence in seconds. Default 2.0.
      stop_event: Optional ``asyncio.Event``; when set, the
        watcher exits cleanly. Useful for tests.

    Returns:
      :class:`CancelWatchOutcome` describing what the watcher
      observed. ``triggered_cancel=True`` means the spec's
      status was ``cancelled``/``failed`` and we cancelled
      the running task. ``triggered_pause=True`` means the
      status was ``paused`` and we set the pause signal
      (the task may or may not have responded within the
      grace window).
    """
    import time
    started = time.time()
    polled_status: str | None = None
    triggered_cancel = False
    triggered_pause = False

    while not running_task.done():
        # Stop early if the caller asked us to.
        if stop_event is not None and stop_event.is_set():
            break
        try:
            status_obj = await job_spec_store.get_status(spec_id)
        except Exception as exc:
            # Defensive: a transient DB error doesn't kill the
            # watcher. Log and retry on the next cycle.
            logger.debug(
                "cancel_watcher: get_status failed (continuing): %s",
                exc,
            )
            await asyncio.sleep(interval)
            continue

        polled_status = status_obj.status if status_obj is not None else None
        if polled_status in CANCEL_STATUSES:
            logger.info(
                "cancel_watcher: spec %s status=%s; cancelling running task",
                spec_id, polled_status,
            )
            running_task.cancel()
            triggered_cancel = True
            # Wait briefly for the task to acknowledge the cancel.
            try:
                await asyncio.wait_for(
                    asyncio.shield(running_task), timeout=5.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            break

        if polled_status in PAUSE_STATUSES:
            # Set the pause signal; the orchestrator will see it
            # at its next safe point and save a JobCheckpoint
            # before returning. We don't cancel the task - the
            # user wants the run to stop gracefully, not be killed.
            logger.info(
                "cancel_watcher: spec %s status=%s; setting pause signal",
                spec_id, polled_status,
            )
            from harness.services.pause_signal import set_pause_signal
            set_pause_signal(spec_id)
            triggered_pause = True
            # Wait for the task to acknowledge the signal.
            try:
                await asyncio.wait_for(
                    asyncio.shield(running_task),
                    timeout=PAUSE_GRACE_SECONDS,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # The task didn't respond in time. Fall back to
                # cancelling - the user still gets a stopped run,
                # just not as gracefully.
                logger.warning(
                    "cancel_watcher: spec %s did not acknowledge pause "
                    "within %ss; falling back to cancel",
                    spec_id, PAUSE_GRACE_SECONDS,
                )
                if not running_task.done():
                    running_task.cancel()
                    triggered_cancel = True
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(running_task), timeout=5.0,
                        )
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
            break

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break

    return CancelWatchOutcome(
        spec_id=spec_id,
        polled_until_status=polled_status,
        triggered_cancel=triggered_cancel,
        triggered_pause=triggered_pause,
        elapsed_seconds=time.time() - started,
        interval=interval,
    )


async def run_with_cancel(
    spec_id: str,
    job_spec_store: Any,
    run_coro: Any,
    *,
    interval: float = DEFAULT_CANCEL_POLL_INTERVAL_SECONDS,
) -> tuple[Any, CancelWatchOutcome]:
    """Run ``run_coro`` while watching for cancel/pause.

    Wraps ``run_coro`` in an :class:`asyncio.Task` and spawns a
    watcher that polls ``job_spec_store.get_status``. When the
    spec's status becomes ``cancelled`` / ``failed``, the task
    is cancelled. When it becomes ``paused``, the pause signal
    is set (the task should observe it and exit gracefully).

    Returns ``(result, outcome)``:
      - ``result``: the result of ``run_coro`` (or ``None`` if
        cancelled). A paused run returns its own result with
        ``status="paused"`` baked in.
      - ``outcome``: the watcher's observation summary.

    Usage:
      async def my_run(): ...
      result, outcome = await run_with_cancel(
          "spec-1", store, my_run(),
      )
    """
    task = asyncio.create_task(run_coro)
    outcome = await watch_for_cancel(
        spec_id, task, job_spec_store, interval=interval,
    )
    # Wait for the task to finish (it may have been cancelled
    # or it may have exited gracefully after observing the
    # pause signal).
    try:
        result = await task
    except asyncio.CancelledError:
        result = None  # Caller can inspect outcome.triggered_cancel
    return result, outcome


__all__ = [
    "watch_for_cancel",
    "run_with_cancel",
    "CancelWatchOutcome",
    "DEFAULT_CANCEL_POLL_INTERVAL_SECONDS",
    "PAUSE_GRACE_SECONDS",
    "CANCEL_STATUSES",
    "PAUSE_STATUSES",
    "TERMINAL_STATUSES",
]
