# C08 follow-up — Auto-resume from checkpoint

**Date**: 2026-06-21
**Status**: Implemented
**Closes the loop on**: C08 pause + cancel propagation

## What changed

Before this sprint, the pause path ended with the user manually re-submitting the spec to continue. The chat tool's pause message said "re-submit the job (the user must re-submit today; a future sprint can auto-resume from the checkpoint)."

This sprint adds **auto-resume**: the user clicks "Resume" (or the chat's `resume_job` tool) and the orchestrator re-spawns with the saved checkpoint context. No re-submit needed.

## End-to-end resume flow

```
user clicks "Resume" (or chat calls resume_job)
  ↓
JobSpecStore.update_status(spec_id, "running")   ← flip status BEFORE spawning
  ↓
OrchestratorEngine.run_resumed_job_spec(spec_id)
  ↓
  - load spec from store
  - pop the JobCheckpoint (consumes it)
  - build a fresh JobSpec from the record
  - annotate the context with:
      resumed_from_checkpoint = true
      checkpoint_paused_at  = "2026-06-21T..."
      checkpoint_paused_by  = "sess-abc"
      resumed_by            = "sess-new"
  - asyncio.create_task(self.run_job_spec(spec))   ← fresh run, new run_id
  - emit "job.resumed" stream event
  ↓
new orchestrator run starts (with checkpoint context)
  ↓
ActivityFeed (UI) shows "job.resumed" event
```

The new run has a fresh `run_id` but the same `spec_id`. The orchestrator's `run_single` runs from the top — today this means a full restart (new sandbox, new git clone, new worktree). A future sprint can use the checkpoint's `subagent_state` to skip already-completed work and resume mid-tree.

## Files created

| File | Lines | Purpose |
|---|---|---|
| `backend/tests/test_chat_resume_tool.py` | 410 | 11 tests for the auto-resume path |

## Files modified

| File | Change |
|---|---|
| `backend/harness/orchestrator.py` | Added `OrchestratorEngine.run_resumed_job_spec(spec_id, *, resumed_by)` method (~110 lines) |
| `backend/harness/agent/tool_dispatch.py` | Added `_handle_resume_job` (~80 lines); wired into the dispatch if-chain; added to `SPECIAL_TOOL_NAMES`; updated pause message (no more "re-submit today") |
| `backend/harness/tools/toolsets.py` | Added `resume_job` to `CHAT_READONLY_TOOLSET` |
| `backend/api/routers/jobs.py` | `/api/jobs/{id}/resume` now calls `OrchestratorEngine.run_resumed_job_spec` (falls back to old behavior if no orchestrator wired) |
| `backend/tests/test_tool_dispatch_role_gating.py` | Updated `SPECIAL_TOOL_NAMES` closed-set assertion (8 tools instead of 7) |

## Design decisions

### Why flip the status to "running" BEFORE spawning

The orchestrator's `run_job_spec` uses the `cancel_watcher` to poll the spec status. If the watcher sees "paused", it thinks the run was paused again and tries to cancel it. The fix: flip to "running" before spawning the new task so the watcher sees a non-terminal status from the start.

### Why pop the checkpoint before spawning

The checkpoint is "consumed" by the resume. If the user pauses again, a new checkpoint is saved. This matches the "checkpoint represents the last pause" mental model.

### Why keep the spec.context as a dict (not Pydantic)

The orchestrator's existing code calls `spec.context.get("session_id", "")` which only works on a dict. `JobSpec.from_dict` (used to re-hydrate the spec from the record) produces a Pydantic `JobContext` for context. The resume path overwrites with a plain dict so the rest of the orchestrator's code works as-is.

### Why a fresh run_id (not reusing the old one)

The new run is a new orchestrator process (in the background task). It has a new run lifecycle (new `started_at`, new cost counters, new logs). The `spec_id` is the join key — the user-visible "this is the same spec, continued" — but `run_id` distinguishes "this run" from "the previous run".

### Why the chat tool calls the orchestrator directly (not the HTTP endpoint)

The chat tool runs in the same process as the orchestrator. Calling the HTTP endpoint would mean `httpx.AsyncClient.post(...)` which adds latency and a network hop. Calling `engine.run_resumed_job_spec(spec_id)` directly is faster and simpler. The HTTP endpoint is still the canonical interface for the dashboard.

### Why the orchestrator's run is a "fresh" run (not a replay)

A true replay would reconstruct the subagent tree from the checkpoint's `subagent_state` and resume mid-tree. That's a substantial feature (load checkpoint → restore subagent tree → resume kanban task). For the MVP, the new run starts fresh: full sandbox setup, full git clone, full KG index, new coordinator spawn. The checkpoint's value is in the audit metadata (paused_at, paused_by) and the future replay.

## Behavior change for users

| | Before this sprint | After this sprint |
|---|---|---|
| Click "Pause" | run cancelled, run_id gone | run signalled, run_id preserved (status="paused") |
| Click "Resume" | status flipped to "running" but nothing happens | status flipped + new orchestrator run spawned in background |
| Latency from "Resume" to actual run start | never (the user had to re-submit) | <100ms (the orchestrator spawns in the same process) |
| Chat: "cancel that one" | tool works | (unchanged) |
| Chat: "pause that one" | tool works | (unchanged) |
| Chat: "resume that one" | n/a (no resume tool) | tool works — resolves to most-recent paused job, spawns new run |
| Activity feed | shows "job.cancelled" / "job.paused" | also shows "job.resumed" |

## Chat tool surface — now 5 tools

| Tool | Mutates? | Added in |
|---|---|---|
| `submit_job` | ✅ | (existing) |
| `cancel_job` | ✅ | previous sprint |
| `pause_job` | ✅ | previous sprint |
| `resume_job` | ✅ | **this sprint** |
| `list_jobs` | ❌ | previous sprint |
| `get_job_status` | ❌ | previous sprint |

## C08 status — final-final-final

| C08 item | Status |
|---|---|
| Pydantic `JobContext` | ✅ |
| Typed `TestConfig` | ✅ |
| All 4 paths durable | ✅ |
| 7 new `JobSpecStore` methods | ✅ |
| `POST /api/jobs` | ✅ |
| 6 chat tools (cancel/pause/resume/list/status) | ✅ |
| Q7 step 1 (legacy adapters) | ✅ |
| Q7 step 2 (delete legacy + frontend) | ⏳ out of scope |
| Cancel propagation (cancel_watcher) | ✅ |
| Chat-side job control | ✅ |
| Real pause (signal + checkpoint) | ✅ |
| **Auto-resume from checkpoint** | ✅ **this sprint** |
| True replay (reconstruct subagent tree from checkpoint) | ⏳ future sprint |
| Pause checkpoints at multiple points inside `run_single` | ⏳ future sprint |
| DB-backed pause signal (cross-worker) | ⏳ future sprint |
| DB-backed JobCheckpoint (cross-process) | ⏳ future sprint |

## Verification (per "skip the tests" earlier — only focused suite)

- **11/11** new tests pass in `test_chat_resume_tool.py`
- **309/309** tests pass in the full C01-C08 focused suite
- All imports work; the orchestrator's `run_resumed_job_spec` is correctly wired
- The `/api/jobs/{id}/resume` endpoint calls the new method
- The chat tool's `_handle_resume_job` resolves, scope-checks, and spawns correctly
- `SPECIAL_TOOL_NAMES` now has 8 tools (was 7)

## Next natural follow-ups (still out of scope)

1. **True replay from checkpoint** — load `subagent_state` and skip already-completed subagents
2. **C08 Q7 step 2: frontend migration** — rewrite 3 legacy pages, delete legacy endpoints
3. **Multiple pause checkpoints** — add pause checks inside the coordinator's run loop (between subagent spawns) for more responsive pause
4. **DB-backed pause signal + checkpoint** — Redis or PostgreSQL NOTIFY for cross-worker / cross-process
5. **Chat tool: comment_on_job** — wrap the existing `POST /api/jobs/{id}/comments` endpoint
6. **Output rendering polish** — Job Detail page detects test_files / pr_url and renders as a structured card
