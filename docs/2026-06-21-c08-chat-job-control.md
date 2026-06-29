# C08 follow-up — Chat-side job lifecycle tools

**Date**: 2026-06-21
**Status**: Implemented
**Closes the loop on**: C08 (JobSpec canonicalisation) + C08 cancel propagation

## What this delivers

The chat can now **control its own jobs**, not just submit them.
Four new tools wired into the chat's toolset:

| Tool | Purpose | Mutates? |
|---|---|---|
| `submit_job` (existing) | Hand a prompt to the orchestrator | ✅ (already there) |
| `cancel_job` | Stop a running job by spec_id (or "the most recent one") | ✅ |
| `pause_job` | Pause a job (today: same effect as cancel; future: checkpoint) | ✅ |
| `list_jobs` | List recent jobs in the current session | ❌ |
| `get_job_status` | Read a single job's status + timing | ❌ |

**Why this matters**: before this sprint, the user could submit a
job via the chat, then had to switch to the `/jobs` UI to
cancel it. The chat — the user's primary surface — was
one-shot. Now the chat can answer "is it done?" or "cancel
that one" without leaving the conversation.

## How cancel flows end-to-end

The cancel path is now:

```
user: "cancel that one"
  ↓
chat LLM:  tool_call(cancel_job, {recent: 1})
  ↓
ToolDispatcher._handle_cancel_job
  ↓
JobSpecStore.cancel(spec_id)        ← flips status to "cancelled"
  ↓                                    ↓ emit_stream_event("job.cancelled", ...)
ActivityFeed (UI)                    ↓
  ↓
OrchestratorEngine.run_job_spec
  ↓ wrapped in:
CancelWatcher.watch_for_cancel       ← polls get_status() every 2s
  ↓ when status flips:
asyncio.Task.cancel()               ← stops the orchestrator's run
  ↓
run returns {"cancelled": True, "elapsed_seconds": 2.3}
```

The chat never reaches into the orchestrator directly. It just
flips a flag in the store. The watcher does the work. This
matches the C08 design rule: **the store is the seam** — the
chat is the only producer; the orchestrator is the only
consumer.

## What changed

### `backend/harness/agent/tool_dispatch.py`

- **4 new handlers** (~280 lines): `_handle_cancel_job`,
  `_handle_pause_job`, `_handle_list_jobs`,
  `_handle_get_job_status`, plus the shared
  `_resolve_job_target` helper
- **Dispatch**: extended the if-chain in `execute` to route
  the 4 new tool names
- **SPECIAL_TOOL_NAMES**: extended from `{delegate_task,
  tool_search, submit_job}` to add `{cancel_job, pause_job,
  list_jobs, get_job_status}` (the closed set of tools that
  are special-cased and role-gated)

### `backend/harness/tools/toolsets.py`

- **CHAT_READONLY_TOOLSET**: added the 4 new tools
- **chat toolset description**: updated to reflect that the
  chat can also control its own jobs (not just submit them)

### `backend/tests/test_chat_job_control_tools.py` (NEW, 18 tests)

- **cancel_job**: explicit spec_id, most-recent resolution,
  session scoping (can't cancel a different session's job),
  already-terminal rejection, missing-spec error
- **pause_job**: explicit spec_id, completed-job rejection,
  session scoping
- **list_jobs**: formatted table, empty session, session
  filter
- **get_job_status**: structured summary, missing-spec error
- **Resolution helper**: explicit, recent=1, recent=2,
  no-jobs fallback
- **Toolsets integration**: all 4 new tools in
  `CHAT_READONLY_TOOLSET`; `SPECIAL_TOOL_NAMES` updated
- **Dispatcher routing**: all 4 names present in the
  `execute` if-chain

### `backend/tests/test_tool_dispatch_role_gating.py` (UPDATED)

- Updated `test_special_tool_names_constant_is_closed_set`
  to reflect the extended closed set (7 tools instead of 3).
  Test docstring documents the rationale (chat is the user's
  front door — they submit, then ask "is it done?" or
  "cancel that one").

## Design decisions

### Why 4 tools, not 1

The chat's existing tools (`list_runs`, `get_run`) operate on
**run records** (the legacy `runs` table), not JobSpecs. The
C08 surface is `JobSpec`s. Different storage, different shape,
different lifecycle. Merging would muddle the model.

### Why session-scoped

The chat can only `cancel`/`pause`/`list` jobs from its own
session. This prevents the chat from accidentally affecting
another user's job (e.g. if the user pastes a spec_id from
elsewhere). The check is at the handler level: if the
record's `context.session_id` doesn't match the chat's
`session_id`, we return a clear error.

The check is **advisory**, not enforced by the store. A
future sprint could move the check to the `JobSpecStore`
itself, but the chat is the only writer today, so the
advisory check is sufficient.

### Why "most recent" fallback

The user often says "cancel that one" without naming the
spec_id. The resolution helper accepts either explicit
`spec_id` OR a `recent=N` (default 1) parameter. The chat
can pass `recent=1` and the helper resolves to the most
recent job in the session. The handler returns the
resolution label in the output ("resolved via recent=1")
so the user can see what was actually cancelled.

### Why `_resolve_job_target` is shared

All 4 handlers need the same resolution logic. Putting it in
a shared method avoids drift. It returns
`(spec_id, label)` so the handler can include the label in
its output for transparency.

### Why the closed set grew

`SPECIAL_TOOL_NAMES` is the set of tools that are
special-cased and role-gated. Adding 4 entries is the
correct call: these are mutations on the JobSpecStore and
need to be restricted to roles that declare them. The chat
declares them; the orchestrator doesn't need to (the
orchestrator talks to the store directly via the
`submit_job_to_orchestrator` path).

### What about the legacy `/api/agent/run` cancel path?

It still works. The 3 legacy endpoints (`/api/agent/run`,
`/api/delegate`, `/api/pipeline/from-requirements`) were
wired through the new `submit_job_to_orchestrator` in
C08 Q7 step 1, so they produce JobSpecs. Cancel via the UI
works on the spec_id, not the legacy run id. C08 Q7 step 2
(frontend migration) is the next step.

## What the chat LLM sees

When the chat LLM calls the new tools, the response is a
plain-text string the LLM can read and quote to the user:

```
cancel_job({spec_id: "spec-abc123"}):
> "Cancelled spec_id=spec-abc123 (resolved via spec_id).
>  Status: running → cancelled. The orchestrator's
>  cancel_watcher will stop the running task within ~2s."

list_jobs({limit: 3}):
> "Recent jobs in session sess-1:
> - spec-1              status=completed  tier=1  cost=$0.000  dur=12.3s  Generate tests for the auth API
> - spec-2              status=running    tier=2  cost=—        dur=—       Add e2e tests for checkout
> - spec-3              status=completed  tier=1  cost=$0.123  dur=45.7s  Audit the rate-limiter"

get_job_status({spec_id: "spec-2"}):
> "spec_id=spec-2 (resolved via spec_id)
>   status:   running
>   run_id:   run-xyz
>   started:  2026-06-21T00:00:01Z
>   finished: —
>   error:    —"
```

The output is human-readable AND machine-parseable (each row
is a fixed-width column).

## C08 status — final

| C08 item | Status |
|---|---|
| Pydantic `JobContext` with `extra='allow` | ✅ done |
| Typed `TestConfig` for from-requirements | ✅ done |
| All 4 paths durable via `JobSpecStore` | ✅ done |
| `JobSpecStore` extended with 7 new methods | ✅ done |
| New `POST /api/jobs` endpoint | ✅ done |
| 8 chat tools via the 7 new endpoints | ✅ done |
| `list_jobs` returns `JobSummary` | ✅ done |
| Q7 step 1: legacy endpoints route through `submit_job_to_orchestrator` | ✅ done |
| Q7 step 2: delete legacy endpoints + frontend migration | ⏳ pending (out of scope for backend) |
| **Cancel propagation** | ✅ done (cancel_watcher) |
| **Chat-side cancel/pause/list/status** | ✅ done (this iteration) |
| Pause semantics (checkpoint + return early) | ⏳ future sprint |
| Resume semantics (re-run with checkpoint) | ⏳ future sprint (depends on pause) |

## Verification

- **18/18** new tests pass in `test_chat_job_control_tools.py`
- **269/269** tests pass in the focused suite (C01-C08 +
  cancel_watcher + new chat tools + role gating)
- Type check: `python -c "from harness.agent.tool_dispatch
  import ToolDispatcher"` works; class has all 16 methods
  (`__init__`, `_emit`, `_emit_and_store`, `execute`,
  `_reject_special_tool`, `_handle_submit_job`,
  `_handle_cancel_job`, `_handle_pause_job`,
  `_handle_list_jobs`, `_handle_get_job_status`,
  `_resolve_job_target`, `_handle_delegate_task`,
  `_handle_tool_search`, `_handle_discovered_tool`,
  `_handle_regular_tool`, `_dispatch_delegate_task`)

## Next natural follow-ups (out of scope)

1. **C08 Q7 step 2: Frontend migration** — rewrite the 3
   legacy pages to call `POST /api/jobs` directly. Delete
   the legacy endpoints. (Out of scope for backend; touches
   existing pages.)
2. **Pause checkpoint semantics** — proper pause (checkpoint
   + return early) instead of pause == cancel. The chat
   tool's UX already supports this; only the watcher's
   behavior needs to change.
3. **Resume semantics** — the `/api/jobs/{id}/resume`
   endpoint exists but the orchestrator doesn't observe
   it. A future sprint can wire checkpoint-replay on
   resume.
4. **Output rendering polish** — the `/jobs/[id]` page
   shows raw JSON; could detect test_files / pr_url and
   render as a structured card.
5. **Chat tool: comment on a job** — the chat can already
   add comments via `POST /api/jobs/{id}/comments`; just
   needs a tool wrapper.
