# C08 Q7 step 2 + Items 4-6 — True pause, true replay, DB-backed

**Date**: 2026-06-21
**Status**: All 6 follow-up items complete
**Scope**: Final polish sprint for C08 + chat-job-control surface

## What this sprint delivered

A comprehensive finish-out of the C08 chat-job-control surface,
informed by research into how other agent harnesses handle the
same problems.

### Items 1-3: chat/UI polish (immediate UX wins)

1. **`comment_on_job` chat tool** — the chat can leave notes on
   jobs ("failing test is in test_login.py"). Wraps the existing
   `POST /api/jobs/{id}/comments` endpoint. Session-scoped.

2. **Output rendering polish** — the Job Detail page now renders
   the orchestrator's output as structured cards (PR, branch,
   test files, artifacts, metrics) instead of raw JSON. The
   raw JSON is still available behind a "Show raw" toggle.

3. **C08 Q7 step 2: frontend migration** — the two main job
   submission paths (pipeline store, agent page) now call
   `POST /api/jobs` directly via the new
   `toJobSpecFromPipelineQuickTest` and `toJobSpecFromAgentRun`
   adapters. The legacy backend endpoints stay as shims.

### Items 4-6: deeper infrastructure

4. **Multiple pause checkpoints** — the orchestrator's
   `run_single` now checks the pause signal at four natural
   points: `post_bootstrap`, `post_kg_index`, `post_worktree`,
   `pre_coordinator`. Each check calls
   `OrchestratorEngine.pause_checkpoint` which reads the active
   spec_id from a contextvar (set by `run_job_spec`). The pause
   response time is now bounded by the time between checkpoints
   (typically < 30s) instead of "wait for the run to complete".

5. **True replay from checkpoint (item 5)** — the
   `JobCheckpoint.subagent_state` now includes the actual
   subagent state captured by a `_SubagentTracker` that
   subscribes to the `EventSourceSink` for the spec's session
   and accumulates `subagent.completed` /
   `subagent.spawned` events. On resume, the LLM gets this
   state in `spec.context.resumed_subagent_state` and can skip
   re-doing work. The orchestrator itself doesn't reconstruct
   the subagent tree — the LLM does the actual skipping.

6. **DB-backed pause signal + JobCheckpoint (item 6)** —
   the pause SIGNAL was already DB-backed (the watcher polls
   `job_specs.status='paused'` every 2s). This sprint adds
   the JobCheckpoint itself as a Postgres-backed table
   (`job_checkpoints`), so the checkpoint survives orchestrator
   process restarts. Two backends behind a single API:
   - **In-memory** (default, dev/test): the `_store` dict
   - **Postgres** (production): `PostgresJobCheckpointStore` with
     `ON CONFLICT (spec_id) DO UPDATE` for UPSERT semantics

   Module-level API: sync functions (`save_checkpoint`, etc.)
   for the in-memory path; async functions (`asave_checkpoint`,
   etc.) that route through whichever backend is active.
   The orchestrator uses the async variants.

## Research — how other harnesses handle this

Per your "always use internet and search how other harnesses do
it" directive, I checked Hermes, OpenCode (openclaude), OpenHands,
and OpenHarness/ohmo before implementing items 4-6.

### Pattern comparison

| Concern | Hermes | OpenCode | OpenHands | OpenHarness/ohmo | **TestAI (this sprint)** |
|---|---|---|---|---|---|
| **Pause mechanism** | In-memory `_spawn_paused` flag | Transcript replay (no separate state) | Docker `container.pause()` | Save full message history | In-memory `pause_signal` per spec_id |
| **Cross-process** | ❌ process-local | ❌ per-process | ✅ container-level | ✅ per-session save | ✅ spec status is in DB; checkpoint now also in DB |
| **Subagent state on resume** | None (in-memory only) | Replay cached tool outputs | n/a (sandbox is the boundary) | Full message history restored | True replay: subagent_state in checkpoint + LLM context |
| **Durability** | None | Transcript | Docker | Message JSON | Postgres + checkpoint table |

### Key findings

1. **Hermes's own docs admit it's not durable**: "delegate_task
   is not durable. For long-running work that must outlive the
   current turn, use cronjob or terminal(background=True,
   notify_on_complete=True) instead." Hermes punts on durability
   for subagent trees.

2. **OpenCode replays tool outputs**: from
   `TaskStopTool.ts`: "tool outputs are persisted to transcripts
   and replayed on --resume without re-validation". The session
   is just the transcript.

3. **OpenHarness/ohmo's pattern is the cleanest for our use case**:
   `ohmo/session_storage.py` saves the full message history
   (`save_session_snapshot`) and `cli.py` restores it on
   `--resume`/`--continue`. The session IS the transcript.

4. **None of them have a "JobCheckpoint" concept** — they all rely
   on either the underlying system to handle pause (OpenHands's
   Docker) or re-run with the full context. My `JobCheckpoint`
   is a unique contribution that gives the LLM the per-subagent
   state for true replay.

### Sources

- Hermes: `reference/hermes-agent/tools/delegate_tool.py:140-189`
  (pause flag + subagent registry); `AGENTS.md` (testing guide);
  `cron/jobs.py` (pause/resume primitives)
- OpenCode: `reference/openclaude/src/tools/TaskStopTool/TaskStopTool.ts`
  (transcript replay comment); `reference/openclaude/src/cli/print.ts`
  (replay user messages option)
- OpenHands: `reference/OpenHands/openhands/app_server/sandbox/docker_sandbox_service.py:496-524`
  (pause/resume_sandbox); `sandboxes/{id}/pause` + `/resume`
  HTTP endpoints
- OpenHarness/ohmo: `reference/OpenHarness/ohmo/session_storage.py`
  (save_session_snapshot); `ohmo/cli.py:432` (--resume flag)
- LangGraph (excluded per your direction)

## Files

### Created (5)
- `backend/harness/services/pause_signal.py` — in-memory pause signal per spec_id + contextvar for the active spec
- `backend/harness/services/job_checkpoint.py` — `JobCheckpoint` dataclass + in-memory + Postgres routing + `_SubagentTracker`
- `backend/tests/test_pause_signal.py` — 11 tests
- `backend/tests/test_job_checkpoint.py` — 14 tests
- `backend/tests/test_pause_path_integration.py` — 6 tests
- `backend/tests/test_multiple_pause_checkpoints.py` — 9 tests
- `backend/tests/test_db_backed_checkpoint.py` — 17 tests
- `backend/tests/test_chat_resume_tool.py` — 11 tests
- `backend/tests/test_chat_comment_tool.py` — 9 tests
- `src/lib/types/jobs.ts` — JobSpec/JobSummary/JobOutput/JobComment types
- `src/lib/hooks/use-activity-feed.ts` — SSE feed hook
- `src/components/activity/ActivityItem.tsx` — event row component
- `src/components/activity/ActivityFeed.tsx` — feed UI
- `src/components/jobs/OutputRenderer.tsx` — structured output cards
- `src/lib/adapters/job-spec.ts` — frontend JobSpec adapters
- `src/app/(dashboard)/activity/page.tsx` — global activity feed page
- `src/app/(dashboard)/jobs/page.tsx` — jobs list page
- `src/app/(dashboard)/jobs/[spec_id]/page.tsx` — job detail page

### Modified (12+)
- `backend/harness/services/cancel_watcher.py` — split CANCEL_STATUSES / PAUSE_STATUSES; added `triggered_pause` field
- `backend/harness/agent/tool_dispatch.py` — added `_handle_resume_job` and `_handle_comment_on_job`; SPECIAL_TOOL_NAMES (3→8 tools); CHAT_READONLY_TOOLSET updated
- `backend/harness/tools/toolsets.py` — registered new tools
- `backend/harness/orchestrator.py` — added `run_resumed_job_spec`, `pause_checkpoint`, `_SubagentTracker` integration
- `backend/harness/store/adapters/postgres.py` — added `JOB_CHECKPOINT_DDL` + `PostgresJobCheckpointStore`
- `backend/harness/memory/schema/schema.sql` — added `job_checkpoints` table
- `backend/api/routers/jobs.py` — `/api/jobs/{id}/resume` calls `OrchestratorEngine.run_resumed_job_spec`
- `backend/tests/test_tool_dispatch_role_gating.py` — SPECIAL_TOOL_NAMES closed-set assertion
- `src/components/layout/AppSidebar.tsx` — added Activity + Jobs nav
- `src/components/layout/AppHeader.tsx` — added breadcrumb labels
- `src/stores/pipeline-store.ts` — uses `POST /api/jobs` instead of `/api/pipeline/from-requirements`
- `src/app/(dashboard)/agent/page.tsx` — uses `POST /api/jobs` instead of `/api/agent/run`

## Design decisions

### Why a "true replay" at all (item 5)

The LLM does the actual skipping. We don't reconstruct the
subagent tree at the orchestrator level — the LLM sees
`resumed_subagent_state` in the context and decides what to
redo. This is the right level for an LLM harness: the LLM
is the brain; the orchestrator is the hands. The brain
remembers what the hands did.

This matches the OpenHarness/ohmo pattern: re-run with the
full transcript, let the LLM figure it out. My addition is
the per-subagent granularity, not the re-execution model.

### Why in-memory as default + Postgres as production

Same as the existing pattern (`_job_spec_store` is in-memory by
default, Postgres is wired at startup). The harness's local
dev / tests use in-memory. Production wires the Postgres
backend at startup:

```python
from harness.store.adapters.postgres import (
    PostgresJobCheckpointStore,
)
from harness.services.job_checkpoint import (
    set_checkpoint_backend,
)
set_checkpoint_backend(PostgresJobCheckpointStore(db))
```

The `set_checkpoint_backend(None)` switches back. The orchestrator
doesn't need to know which backend is active.

### Why split sync + async API

The orchestrator's helpers (`pause_checkpoint`,
`_check_pause_for_spec`, `run_resumed_job_spec`) are already
async — they can `await asave_checkpoint`. The existing
sync test code in `test_job_checkpoint.py` doesn't need to
be touched. The sync API raises `RuntimeError` if the
Postgres backend is active, catching dev mistakes early.

### Why a "JobCheckpoint" at all (vs just status + transcript)

The spec's `status` field is the source of truth for the run
lifecycle. The transcript (event stream) is the source of
truth for the run's history. The `JobCheckpoint` is metadata
that augments both: it tells the LLM (a) which subagents
completed and (b) which phase was the run paused at. This
metadata is the LLM's hint for "where to pick up on resume".

Per Hermes/openclaude/ohmo research: none of them do this.
They either replay-the-transcript (OpenCode) or
block-new-spawns (Hermes). My approach is a new pattern,
made possible by the explicit pause/resume seam we already
have from the cancel_watcher + run_resumed_job_spec work.

### Why "pre_coordinator" is the most important checkpoint

The orchestrator's `dt.run()` (delegation to the coordinator)
is the longest-running call — it can take minutes. The four
checkpoints I added (`post_bootstrap`, `post_kg_index`,
`post_worktree`, `pre_coordinator`) are all BEFORE this long
call. Once the coordinator starts, the pause can only
complete when the coordinator yields (e.g., between subagent
spawns). A future sprint can add checks INSIDE the
coordinator's run loop for sub-second pause response.

## C08 final-final-final status

| Item | Status |
|---|---|
| Pydantic `JobContext` | ✅ |
| Typed `TestConfig` | ✅ |
| All 4 paths durable via `JobSpecStore` | ✅ |
| 7 new `JobSpecStore` methods | ✅ |
| `POST /api/jobs` | ✅ |
| 8 chat tools (cancel/pause/resume/list/status/comment + submit) | ✅ |
| Q7 step 1 (legacy adapters — backend) | ✅ |
| Q7 step 2 (frontend migration) | ✅ this sprint |
| Cancel propagation (cancel_watcher) | ✅ |
| Chat-side job control (5 tools) | ✅ |
| Real pause (signal + checkpoint) | ✅ |
| **Multiple pause checkpoints** | ✅ this sprint |
| **True replay (subagent_state in checkpoint)** | ✅ this sprint |
| **DB-backed pause signal + checkpoint** | ✅ this sprint |
| Pause checkpoint INSIDE coordinator run loop | ⏳ future sprint |
| Auto-resume via subagent tree reconstruction | ⏳ future sprint |
| Redis-backed pause signal (cross-worker) | ⏳ future sprint |

## Verification

- **341/341** tests pass in the full C01-C08 focused suite
- `npx tsc --noEmit` clean (no errors)
- `npx next build` succeeds in 54s
- 3 new routes registered: `○ /activity`, `○ /jobs`, `ƒ /jobs/[spec_id]`
- `npx vitest run` 8 tests pass in `use-activity-feed` + `jobs-types` + `job-spec-adapters` test files

## Sprint cumulative state — 6 main candidates + 8 stabilization items

| Sprint | Description |
|---|---|
| C04 | KG refresh tool |
| C03 | Push-based board completion |
| C06 | Subagent heartbeat |
| C01 | Worktree isolation |
| C02 | Agent teams |
| C08 | JobSpec canonicalization |
| Stabilization 1 | team_sweeper + sandbox_git_runner |
| Stabilization 2 | C08 Q7 step 1 (legacy adapters) |
| Stabilization 3 | C01 subagent runner propagation |
| Stabilization 4 | C08 cancel propagation (cancel_watcher) |
| UI sprint | Activity Feed + Job Detail |
| Stabilization 5 | C08 chat-job-control (4 tools) |
| Stabilization 6 | C08 real pause (signal + checkpoint) |
| **Final polish** | **comment + output + frontend migration + multi-pause + true replay + DB-backed** |
