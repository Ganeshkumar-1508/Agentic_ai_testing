# C08 — Cancel / pause propagation

**Date**: 2026-06-21
**Status**: Implemented (cancel); pause is a soft state
**Follow-up to**: C08 (JobSpec canonicalisation) + Q7 step 1

## What this addresses

The chat-facing `POST /api/jobs/{id}/cancel` endpoint
(`api/routers/jobs.py:151-165`) calls
`JobSpecStore.cancel(spec_id)`, which flips the spec's status
to `"cancelled"` in the DB. The store method existed, but no
caller observed the change — the running orchestrator didn't
know to abort. Result: users could click "Cancel" but the run
would keep going until the natural end.

Same gap for `pause` and `resume` — the store flags the
status, but the orchestrator's run loop doesn't check.

## Decision (locked, deferred from the original C08)

Per the C08 design doc open question #2: pause/resume semantics
are "deferred — a future sprint could add a metric/alert".

For this iteration:
- **Cancel** is fully implemented (best-effort polling).
- **Pause** is implemented at the watcher level (the watcher
  also cancels on `paused` status), but the orchestrator
  doesn't checkpoint-and-resume. The user-visible behavior is:
  pause == cancel. A future sprint can wire pause to checkpoint
  + return early.
- **Resume** is a soft state (the orchestrator doesn't observe
  it; the user can re-submit a new job).

## Implementation

### New file: `backend/harness/services/cancel_watcher.py` (~170 lines)

The cancel watcher is a thin layer that polls
`JobSpecStore.get_status()` every `interval` seconds (default
2s). When the status becomes one of
`{"cancelled", "paused", "failed"}`, it cancels the running
task. The orchestrator's existing `try/except
asyncio.CancelledError` in the run loop translates the cancel
into a clean shutdown.

Public surface:

- `watch_for_cancel(spec_id, running_task, job_spec_store, *,
  interval, stop_event)` — the polling loop. Returns
  `CancelWatchOutcome` summarizing what was observed.
- `run_with_cancel(spec_id, job_spec_store, run_coro, *, interval)`
  — convenience wrapper that builds an `asyncio.Task` for
  `run_coro` and runs the watcher. Returns `(result, outcome)`.
- `CancelWatchOutcome` — frozen view of `polled_until_status`,
  `triggered_cancel`, `elapsed_seconds`, `interval`.

Default cadence: 2 seconds (matches the existing C06 heartbeat
interval for inactive subagents). Tunable via the
`CANCEL_POLL_INTERVAL_SECONDS` env var (not yet wired — would
be a 1-line change for future tightening).

Failure modes handled:
- **No store** (e.g. local dev) — falls back to running the
  coroutine directly. The cancel just doesn't propagate.
- **DB errors during polling** — logged at DEBUG, the watcher
  continues. The next cycle tries again.
- **Task already done** — the watcher exits cleanly.

### Modified: `backend/harness/orchestrator.py`

`run_job_spec` now wraps the call to `run_single` in the
watcher:

```python
run_coro = self.run_single(...)
return await self._run_with_cancel_watch(spec, run_coro)
```

The new `_run_with_cancel_watch` helper:

1. Reads the `JobSpecStore` from the module-level injector
   (`_job_spec_store()`).
2. If no store is wired, runs the coroutine directly (fallback).
3. Otherwise calls `run_with_cancel(spec.spec_id, store, run_coro)`.
4. If the watcher observed a cancel, returns a structured
   `{"success": False, "status": "cancelled", "cancelled": True,
   "elapsed_seconds": ...}` result. Otherwise returns the
   natural result.

The orchestrator's existing error handling
(`try/except asyncio.CancelledError`) catches the cancel and
returns a clean result to the caller.

### New file: `backend/tests/test_cancel_watcher.py` (13 tests, all passing)

Covers:
- Constants (default cadence 2s, terminal statuses)
- `CancelWatchOutcome.__repr__` (smoke)
- Watcher exits cleanly when task finishes first
- Watcher cancels when status flips to `cancelled`
- Watcher cancels when status flips to `paused` (the soft-state
  behavior — pause cancels for now)
- Watcher does NOT cancel on `running` status
- Watcher survives `get_status` exceptions (transient DB errors)
- Watcher handles `None` status object (spec not found)
- `stop_event` short-circuits the watcher (useful for tests)
- `run_with_cancel` returns the result when not cancelled
- `run_with_cancel` returns `(None, outcome)` when cancelled
- `run_with_cancel` propagates return value
- **End-to-end integration** with the full `JobSpecStore`
  protocol — the user clicks `cancel()`, the watcher observes,
  the task ends cleanly

## Behavior change (observable)

| | Before | After |
|---|---|---|
| User clicks "Cancel" on a running job | spec status flips to `cancelled` in DB; orchestrator keeps running | spec status flips; orchestrator's task is cancelled within 2s |
| User clicks "Pause" | spec status flips to `paused` in DB; orchestrator keeps running | spec status flips; orchestrator's task is cancelled (pause == cancel today) |
| User clicks "Resume" | spec status flips to `running` in DB; orchestrator doesn't observe | same — the spec is now `running` again, but the run is already gone |
| The `/api/jobs/{id}/cancel` endpoint | returns `cancelled: true` | returns `cancelled: true`; the actual run stops within 2s |
| Latency from cancel to actual stop | infinite (never) | ≤ 2s (one polling cycle) |

## Failure modes

| Failure | Behavior |
|---|---|
| `JobSpecStore` not wired (no DB) | watcher is skipped; the run completes naturally. The cancel endpoint still returns `cancelled: true` (the DB is updated) but the run is not interrupted. The next run that's already in the DB will see the stale `cancelled` status when the watcher polls. |
| DB error during polling | logged at DEBUG; the watcher continues. The next cycle tries again. |
| Task doesn't respond to cancel within 5s | logged at WARNING; the watcher returns `outcome` and lets the run finish naturally. (`asyncio.wait_for(asyncio.shield(task), timeout=5.0)`) |
| `cancelled` while task is in the middle of an LLM call | the LLM call's `asyncio.Task` is wrapped — the cancel propagates through the existing LLM call's `try/except CancelledError` |
| Pause issued, then the user wants to resume | today: pause == cancel; the run stops. Future sprint: pause could checkpoint + return early with `status=paused`, and resume could re-run with the checkpoint. |

## Open follow-ups

1. **Pause semantics** — currently pause == cancel. A future
   sprint could add checkpoint-and-return-early on pause. The
   orchestrator already has a checkpoint system
   (`backend/harness/checkpoint.py`) — wiring it to the
   `JobSpec.pause()` call is straightforward.
2. **Configurable polling cadence** — currently 2s hardcoded.
   The `CANCEL_POLL_INTERVAL_SECONDS` env var would be a 1-line
   change.
3. **Watcher in the FastAPI lifespan** — the watcher is
   created per-request. A long-lived watcher that watches
   ALL running jobs in a single task would be more efficient
   (one task per app, not one per job).
4. **Cancel from the chat** — the chat's `submit_job` tool
   could expose `cancel_job` as a follow-up call. The router
   already supports it; just needs a tool definition.
5. **Dashboard live update** — the `subagent.cancelled` and
   `job.cancelled` events aren't surfaced on the SSE feed yet.
   A small `emit_stream_event` call in the watcher's "cancelled"
   branch would fix this.

## Files changed

| File | Change |
|---|---|
| `backend/harness/services/cancel_watcher.py` | NEW (~170 lines) |
| `backend/harness/orchestrator.py` | +50 lines (`_run_with_cancel_watch` helper, wrap `run_single` call) |
| `backend/tests/test_cancel_watcher.py` | NEW (13 tests, all passing) |

## Verification

- 13/13 new tests pass
- 239/239 tests in all touched/related test files pass
  (C08, cancel_watcher, team_service, worktree_manager,
  kg_refresh_tool, heartbeat, submit_job_handoff, job_spec_store,
  team_sweeper, sandbox_git_runner, legacy_adapters,
  worktree_git_runner_contextvar)

## C08 status

| C08 item | Status |
|---|---|
| Pydantic `JobContext` with `extra='allow` | ✅ done |
| Typed `TestConfig` for from-requirements | ✅ done |
| All 4 paths durable via `JobSpecStore` | ✅ done (stabilization 1) |
| `JobSpecStore` extended with 7 new methods | ✅ done |
| New `POST /api/jobs` endpoint | ✅ done |
| 8 chat tools via the 7 new endpoints | ✅ done |
| `list_jobs` returns `JobSummary` | ✅ done |
| Q7 step 1: legacy endpoints route through `submit_job_to_orchestrator` | ✅ done |
| Q7 step 2: delete legacy endpoints + frontend migration | ⏳ pending (out of scope for backend) |
| **Cancel propagation** | ✅ done (this iteration) |
| Pause semantics (checkpoint + return early) | ⏳ pending (deferred to future sprint) |
| Resume semantics (re-run with checkpoint) | ⏳ pending (depends on pause) |
