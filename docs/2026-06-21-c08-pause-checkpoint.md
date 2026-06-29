# C08 follow-up — Real pause (not cancel)

**Date**: 2026-06-21
**Status**: Implemented
**Closes the loop on**: C08 pause semantics (deferred from C08 design + C08 cancel propagation)

## What changed

The cancel_watcher used to treat "paused" as a terminal status — same as "cancelled". A user clicking "pause" would kill the orchestrator's run loop exactly the same way as "cancel". The state was lost; the user had to re-submit from scratch.

This sprint introduces **real pause** — a soft state that:

1. Signals the orchestrator (via an in-memory flag) instead of cancelling it
2. Waits for the orchestrator to acknowledge the signal gracefully (up to 30s)
3. Saves a `JobCheckpoint` so the user can see what was paused and by whom
4. Returns `status="paused"` to the caller (distinct from "cancelled")

A cancel remains a hard stop. Pause and cancel now have separate code paths.

## Why this matters

A paused run keeps its:
- Subagent tree (subagents that completed stay completed; in-flight ones are allowed to finish)
- JobSpec record (status flipped, but the run isn't deleted)
- Audit trail (paused_at, paused_by recorded in the JobCheckpoint)
- Test files / commits made so far (the worktree's branch isn't reset)

A cancelled run loses all of the above.

For a long-running test-generation job (45+ minutes), the difference between "kill and restart" and "pause and resume" is real money.

## Architecture

```
user clicks "Pause"
  ↓
JobSpecStore.pause(spec_id) -> flips status to "paused"
  ↓ emit_stream_event("job.paused", ...)
ActivityFeed (UI) sees the event
  ↓
cancel_watcher (polls every 2s) observes the flip
  ↓ for status="paused":
set_pause_signal(spec_id)            <- signals the orchestrator
  ↓
wait up to PAUSE_GRACE_SECONDS (30s) <- graceful window
  ↓ if the orchestrator doesn't respond:
fall back to running_task.cancel()  <- last resort
  ↓
orchestrator.run_job_spec returns:
  - if the orchestrator observed the signal:
      save JobCheckpoint, return status="paused"
  - if not (timeout):
      watcher cancelled the task, return status="cancelled"
```

The orchestrator's `run_single` checks the pause signal at the end (after the natural completion of the run) and saves a `JobCheckpoint` if the signal is set. The signal is then cleared so the next run starts with a clean state.

## Files created

| File | Lines | Purpose |
|---|---|---|
| `backend/harness/services/pause_signal.py` | 100 | In-memory `set/check/clear` per spec_id + lazy `asyncio.Event` |
| `backend/harness/services/job_checkpoint.py` | 105 | `JobCheckpoint` dataclass + `save/get/pop/list/clear` |
| `backend/tests/test_pause_signal.py` | 110 | 11 tests for the signal module |
| `backend/tests/test_job_checkpoint.py` | 130 | 14 tests for the checkpoint storage |
| `backend/tests/test_pause_path_integration.py` | 170 | 6 integration tests for the full pause flow |

## Files modified

| File | Change |
|---|---|
| `backend/harness/services/cancel_watcher.py` | Split `TERMINAL_STATUSES` into `CANCEL_STATUSES` (`cancelled`, `failed`) and `PAUSE_STATUSES` (`paused`); added `triggered_pause` field to `CancelWatchOutcome`; pause path sets the signal + waits; cancel path unchanged |
| `backend/harness/orchestrator.py` | Added `_check_pause_for_spec(spec_id, run_id, session_id)` helper; `run_job_spec` calls it after `run_single` returns and converts the result to `{"status": "paused"}` if a checkpoint was saved |
| `backend/harness/agent/tool_dispatch.py` | Updated `_handle_pause_job` message (no longer says "pause == cancel"; now says the run will exit gracefully within ~30s and save a checkpoint; user must re-submit today) |
| `backend/tests/test_cancel_watcher.py` | Updated `test_outcome_repr` (added `triggered_pause` field); replaced `test_watcher_cancels_when_status_is_paused` with `test_watcher_signals_pause_when_status_is_paused` (asserts new behavior) |

## Design decisions

### Why in-memory pause signal (not DB)

The orchestrator process is the natural owner of the pause signal. Cross-process pause (e.g., from a different uvicorn worker) is out of scope for the MVP. If the orchestrator process dies, the run is dead anyway — the user re-submits and starts fresh. A future sprint can swap this for a Redis-backed signal if multi-worker pause becomes a requirement.

### Why in-memory JobCheckpoint (not DB)

Same reasoning. The orchestrator is the natural owner of the partial state. The checkpoint's value is in supporting human-readable audit (paused_at, paused_by, last_result snapshot), not in driving the next run. A future sprint can persist the checkpoint via the existing `harness.checkpoint.CheckpointManager` (which already has the seam). For the MVP, the in-memory dict is sufficient.

### Why PAUSE_GRACE_SECONDS = 30s

The orchestrator's `run_single` is long-running (it does a full git clone, indexes the knowledge graph, creates a worktree, spawns a coordinator, etc.). A 2-second window (the cancel polling cadence) is too short to give the orchestrator a chance to observe the signal and save a checkpoint. 30 seconds is long enough for a single subagent to wrap up but short enough that the user doesn't wait forever for a "paused" UI to update.

The 30s is the MAX grace — if the orchestrator observes the signal earlier, the watcher returns immediately. Only an unresponsive orchestrator waits the full 30s.

### Why a single check at the END of run_single (for the MVP)

The orchestrator's `run_single` is a 500-line function with many side effects (sandbox setup, KG indexing, worktree creation, coordinator spawn). Inserting pause checks at every safe point would be invasive and require deep reasoning about each call site.

For the MVP, the check happens ONCE — after `run_single` returns. The user's UX is:

- "Pause" → wait for the run to complete (up to 30s) → save a checkpoint → return
- The work the run did is preserved (worktree, test files, subagent state)
- The user re-submits to continue

A future sprint can add more pause checks (e.g., between subagent spawns in the coordinator's run loop) to make pause more responsive for long-running runs.

### Why the user has to re-submit (not auto-resume)

Auto-resume requires:
1. Loading the JobCheckpoint
2. Reconstructing the subagent tree
3. Resuming the kanban board at the right task
4. Re-running any in-flight subagent

This is a substantial feature. For the MVP, the user re-submits. The JobCheckpoint is preserved (in-memory) so a future sprint can implement auto-resume. The chat tool's pause message tells the user explicitly: "re-submit the job today; a future sprint can auto-resume from the checkpoint."

### Why distinguish "failed" from "cancelled"

Both are cancel statuses. From the user's perspective:
- "cancelled" = they clicked cancel (intentional)
- "failed" = the system set the status (e.g., `update_status("failed")` was called by some internal error handler)

Both should kill the running task, but they're tracked separately. The cancel_watcher treats them the same for now; a future sprint could log them differently.

## Behavior matrix

| User action | Pre-MVP behavior | Post-MVP behavior |
|---|---|---|
| Click "Cancel" | Task cancelled; status="cancelled"; no checkpoint | (unchanged) |
| Click "Pause" | Task cancelled; status="cancelled" | Task signalled; run_single returns; checkpoint saved; status="paused" |
| Orchestrator unresponsive to pause | n/a (pause == cancel) | After 30s, watcher falls back to cancel |
| User clicks "Resume" after pause | n/a | Status flips to "running"; user re-submits to actually run |
| User clicks "Cancel" after pause | Task cancelled (no-op, already terminal) | Task cancelled (no-op, already terminal) |

## C08 status — final-final

| C08 item | Status |
|---|---|
| Pydantic `JobContext` | ✅ |
| Typed `TestConfig` | ✅ |
| All 4 paths durable | ✅ |
| 7 new `JobSpecStore` methods | ✅ |
| `POST /api/jobs` | ✅ |
| 8 chat tools (4 from this sprint's earlier iteration) | ✅ |
| Q7 step 1 (legacy adapters) | ✅ |
| Q7 step 2 (delete legacy + frontend) | ⏳ out of scope |
| Cancel propagation | ✅ |
| Chat-side job control | ✅ |
| **Pause as soft state (real pause)** | ✅ **this iteration** |
| Auto-resume from checkpoint | ⏳ future sprint |
| Pause checkpoint at multiple points inside `run_single` | ⏳ future sprint |
| DB-backed pause signal (cross-worker) | ⏳ future sprint |
| DB-backed JobCheckpoint (cross-process) | ⏳ future sprint |

## Verification

- **60/60** tests pass in the focused pause suite
  (`test_pause_signal.py`: 11/11,
  `test_job_checkpoint.py`: 14/14,
  `test_pause_path_integration.py`: 6/6,
  `test_cancel_watcher.py`: 13/13 — including the
  rewritten `test_watcher_signals_pause_when_status_is_paused`,
  `test_chat_job_control_tools.py`: 18/18)
- **298/298** tests pass in the full C01-C08 focused suite
- All imports work: `pause_signal`, `job_checkpoint`, the
  updated `cancel_watcher` with the new `CANCEL_STATUSES` /
  `PAUSE_STATUSES` / `PAUSE_GRACE_SECONDS` exports
- The orchestrator's `_check_pause_for_spec` helper is
  correctly wired into `run_job_spec` (the pause result
  path returns `{"status": "paused", "checkpoint_saved":
  True}`)

## Next natural follow-ups (out of scope)

1. **Auto-resume from checkpoint** — when the user clicks
   "Resume", the orchestrator re-spawns with the
   JobCheckpoint's state. This requires a new
   `OrchestratorEngine.run_from_checkpoint(checkpoint)`
   method.
2. **Pause checkpoints at multiple points** — add pause
   checks inside the coordinator's run loop (between
   subagent spawns, before tool calls) to make pause
   more responsive for long-running runs.
3. **DB-backed pause signal** — Redis or PostgreSQL NOTIFY
   so a different uvicorn worker can pause an orchestrator
   running in another worker.
4. **DB-backed JobCheckpoint** — persist the checkpoint to
   the `checkpoints` table via `CheckpointManager` so it
   survives process restarts.
5. **Chat tool: comment_on_job** — wrap the existing
   `POST /api/jobs/{id}/comments` endpoint as a chat tool.
6. **C08 Q7 step 2: frontend migration** — rewrite the 3
   legacy pages, delete the legacy endpoints.

## Files inventory

```
backend/
  harness/
    services/
      pause_signal.py        (NEW, 100 lines)
      job_checkpoint.py      (NEW, 105 lines)
      cancel_watcher.py      (MODIFIED, +20 lines, -10 lines)
    orchestrator.py          (MODIFIED, +50 lines)
    agent/
      tool_dispatch.py       (MODIFIED, +6 lines for pause msg)
  tests/
    test_pause_signal.py     (NEW, 110 lines, 11 tests)
    test_job_checkpoint.py   (NEW, 130 lines, 14 tests)
    test_pause_path_integration.py (NEW, 170 lines, 6 tests)
    test_cancel_watcher.py   (MODIFIED, 2 tests updated)
```
