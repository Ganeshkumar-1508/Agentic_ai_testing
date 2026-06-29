# C08 Q7 — Legacy endpoint migration (first step)

**Date**: 2026-06-21
**Status**: Implemented (first of two steps)
**Follow-up to**: C08 (JobSpec canonicalisation)

## Goal

Per C08 Q7 (locked): "Remove + rewrite in same sprint (~2-3 weeks
combined work)." The user constraint was "no legacy. remove them
or rewrite them."

This sprint implements **Step 1**: the three legacy endpoints
(`/api/agent/run`, `/api/delegate`,
`/api/pipeline/from-requirements`) are now thin wrappers that
additionally call `submit_job_to_orchestrator` so every
submission becomes durable. **Step 2** (delete the endpoints
after frontend migration) is still pending.

## What changed

### New file: `backend/harness/jobs/legacy_adapters.py` (~190 lines)

Three adapter functions that translate the legacy request
bodies into `JobSpec` objects:

- `agent_run_to_job_spec(prompt, mode, session_id, repo_url, tier)`
  — for `/api/agent/run` (chat + pipeline modes).
- `delegate_to_job_spec(prompt, repo_url, branch, tasks, context,
  toolsets, role, model, mcp_servers)` — for `/api/delegate`.
  Uses `effective_goal` logic (prompt, else first task).
- `pipeline_to_job_spec(prompt, project_id, repo_url, ...)` — for
  `/api/pipeline/from-requirements`. Stuffs the 30+ test-specific
  fields into `context.test_config` (the typed `TestConfig` from
  C08 Q3) and the rest into `context.request_metadata`.

Each adapter produces a fully-formed `JobSpec` ready to be
persisted via `submit_job_to_orchestrator`. The adapter is
**pure** (no I/O) so it's easy to test and easy to call from
multiple call sites.

### Modified: 3 routers

**`/api/agent/run`** — added a `_persist_legacy_spec` call
before the dispatch. The legacy response shape is unchanged.

**`/api/delegate`** — added a `submit_job_to_orchestrator` call
before the `delegate_task` dispatch. Best-effort (errors
logged, request continues).

**`/api/pipeline/from-requirements`** — added a
`submit_job_to_orchestrator` call with the full 30+ fields
mapped to `context.test_config` + `context.request_metadata`.

In all 3 cases, the persistence call is **best-effort**: a DB
error doesn't fail the request, but a missing spec means the
user can't recover the job via `/api/jobs`. The existing
dispatch logic is unchanged so the response shape stays
stable.

### New file: `backend/tests/test_legacy_adapters.py` (16 tests, all passing)

Covers:
- `agent_run_to_job_spec` — chat + pipeline modes, unique IDs
- `delegate_to_job_spec` — goal/tasks/toolsets/MCP servers,
  default capabilities, empty goal
- `pipeline_to_job_spec` — typed TestConfig fields, diff_base as
  branch, request_metadata records all options, retry_count
  respects `retry_on_failure`
- Roundtrip — all 3 specs survive `to_dict` → `from_dict`

## Behavior change (observable)

| | Before Q7 | After Q7 (step 1) |
|---|---|---|
| `/api/agent/run` durable | no (chat sessions table only) | yes (JobSpec in `job_specs`) |
| `/api/delegate` durable | no (sessions table only) | yes (JobSpec) |
| `/api/pipeline/from-requirements` durable | no (sessions + tasks) | yes (JobSpec + TestConfig) |
| Frontend can use `/api/jobs/{id}/status` | no (legacy not in store) | yes (now queryable via spec_id) |
| 30+ pipeline fields in DB | lost after dispatch | durable via `context.test_config` + `context.request_metadata` |
| `list_jobs` shows all submissions | no | yes (all 4 paths surface) |

## What didn't change

- The 3 legacy endpoints still exist (Step 2 — delete them —
  is still pending). The frontend still works against them.
- The response shapes are unchanged so the frontend doesn't need
  to update yet.
- The dispatch logic is unchanged.

## Step 2 (completed 2026-06-21)

**Hard delete** — no deprecation window. Per user directive
("no legacy") and after researching the alternative patterns
(see "Research" below).

### What was deleted

- **Deleted files**:
  - `backend/harness/jobs/legacy_adapters.py` (~190 lines,
    server-side adapter functions)
  - `backend/tests/test_legacy_adapters.py` (16 tests for the
    deleted adapters)
- **Deleted HTTP endpoints**:
  - `POST /api/agent/run` (entire handler + supporting code
    in `api/routers/agent.py`)
  - `POST /api/pipeline/from-requirements` (entire handler +
    the `PipelineFromRequirements` request model + the
    `_build_orchestration_goal` and `_run_pipeline_orchestrator`
    helpers in `api/routers/pipeline.py`)
  - `POST /api/delegate` root handler (the legacy delegation
    entry point in `api/routers/delegate.py`, plus the
    `_run_orchestration` and `_run_delegation` helpers)
- **Kept endpoints** (not legacy — they're session control, not
  job submission):
  - `POST /api/delegate/{session_id}/steer`
  - `POST /api/delegate/{session_id}/cancel`
  - `POST /api/delegate/{session_id}/interrupt`
  - `POST /api/delegate/{session_id}/pause`
  - `GET /api/delegate/{session_id}`
  - `POST /api/delegate/{session_id}/resume`
  - `GET /api/delegate/{session_id}/stream`
  - `POST /api/delegate/approve`
  - `GET /api/delegate/approvals/pending`
  - `POST /api/delegate/{session_id}/fork`
  - `GET /api/delegate/{session_id}/shadow/stream`
- **Doc comments updated** to reflect the new state:
  - `backend/harness/jobs/spec.py` (Q5 + Q7 step 2 notes)
  - `backend/harness/jobs/submitter.py` (no legacy)
  - `backend/harness/cross_repo.py` (POST example points to
    `/api/jobs`)
  - `backend/api/routers/agent.py` (placeholder file)
  - `backend/api/routers/pipeline.py` (router docstring)
  - `backend/api/routers/jobs.py` (Q7 step 2 + canonical)
  - `backend/api/routers/runs.py` (no more pipeline runs)
- **Frontend** (already migrated in earlier sprint):
  - `src/lib/adapters/job-spec.ts` (frontend JobSpec adapters
    are pure functions, separate from the deleted backend
    legacy_adapters.py)

### Research: how other harnesses handle legacy endpoint deprecation

Per the "always research how other harnesses do it" directive,
I checked Hermes, OpenCode, OpenHands, and OpenHarness/ohmo
before deciding on hard delete:

- **Hermes**: deprecation window pattern. `warn_deprecated_cwd_env_vars`
  in `hermes_cli/config.py:3950` warns but keeps working.
  Tests confirm: "Emits a deprecation log line but keeps their
  config working" (`tests/agent/test_curator.py:933`).
- **OpenCode**: doesn't have legacy endpoints (single canonical
  surface from the start; the `TaskStopTool` comment says
  "tool outputs are persisted to transcripts and replayed on
  --resume" — same model, no deprecation needed).
- **OpenHands**: Docker container pause is the durability
  mechanism; HTTP endpoints don't get deprecated, the underlying
  sandbox does. Their `pause_sandbox`/`resume_sandbox` are
  orthogonal to HTTP API lifecycle.
- **OpenHarness/ohmo**: session IDs are the primary handle;
  legacy code paths stay until they're truly unused
  (the `ohmo/session_storage.py:save_session_snapshot` is the
  source of truth, and `cli.py:432` adds a `--resume` flag for
  loading it).

The hard-delete path was chosen because:
1. The user explicitly mandated "no legacy" multiple times
2. The frontend has been migrated (no internal callers)
3. The new surface is fully featured (6 chat tools cover
   all submission patterns)
4. External callers can be migrated to `POST /api/jobs` with
   a single API call (the response shape is documented)

If a caller hits a deleted endpoint, they get a 404 — clear
signal to migrate. The opposite (silently deprecating while
keeping the endpoint working, per Hermes) hides the migration
requirement.

## Files changed

| File | Change |
|---|---|
| `backend/harness/jobs/legacy_adapters.py` | NEW (~190 lines) |
| `backend/api/routers/agent.py` | +40 lines (build + persist spec) |
| `backend/api/routers/delegate.py` | +25 lines (build + persist spec) |
| `backend/api/routers/pipeline.py` | +45 lines (build + persist spec) |
| `backend/tests/test_legacy_adapters.py` | NEW (16 tests, all passing) |

## Verification

- 16/16 new adapter tests pass
- 304/304 tests in all touched/related test files pass
  (C08, team_service, worktree_manager, kg_refresh_tool,
  codegraph_tools, tool_dispatch_role_gating, event_source_sink,
  events_sse_route, board_waiter, heartbeat, submit_job_handoff,
  job_spec_store, team_sweeper, sandbox_git_runner,
  legacy_adapters)
- All 4 routers import cleanly (no syntax/import errors)

## Failure modes

| Failure | Behavior |
|---|---|
| DB unavailable for spec persistence | Logged at DEBUG; the request continues with the existing dispatch path (the user's session still runs, just not queryable via `/api/jobs/{id}`) |
| Persistence raises an unexpected exception | Same — logged, request continues |
| Store returns the existing spec | `JobSpecStore.save` is documented as "no-op if spec_id already exists" — idempotent |

## Open follow-ups (tracked)

1. **Frontend migration** — `toJobSpecFromAgentPage(state)`,
   `toJobSpecFromPipelineOrchestrate(state)`,
   `toJobSpecFromPipelineQuickTest(state)`. Out of scope for
   backend work.
2. **Delete legacy endpoints** — after frontend migrates.
3. **Tighten persistence error handling** — currently we log
   and continue. A future sprint could add a metric/alert for
   "spec persistence failures" so we notice if the DB is
   silently broken.
