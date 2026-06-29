# C01 — Subagent worktree sandbox runner propagation

**Date**: 2026-06-21
**Status**: Implemented
**Follow-up to**: C01 (worktree isolation) + stabilization sprint 1

## What this addresses

The stabilization sprint wired `sandbox_git_runner(env)` into
the **orchestrator's** per-session worktree creation. The
**per-subagent** worktree creation in `delegate_task.py` was
still using `WorktreeManager()` (which defaults to
`local_git_runner`). Result: in production, the orchestrator's
worktree landed in the Docker container (correct), but each
subagent's worktree landed on the host filesystem (wrong) —
breaking the isolation the per-subagent worktree is supposed
to provide.

## Implementation

### New contextvar: `set_current_git_runner` / `get_current_git_runner` / `reset_current_git_runner`

`backend/harness/services/worktree_manager.py` (top of file):

```python
_current_git_runner: contextvars.ContextVar["GitRunner | None"] = (
    contextvars.ContextVar("testai_current_git_runner", default=None)
)

def set_current_git_runner(runner: GitRunner | None) -> Token: ...
def get_current_git_runner() -> GitRunner | None: ...
def reset_current_git_runner(token: Token) -> None: ...
```

Mirrors the C04 `set_current_kg_context` pattern in
`services/knowledge_graph_syncer.py:39-55`. The contextvar is
**asyncio-task-scoped**: a new `asyncio.create_task` gets a copy
of the parent's context, so subagents inherit the parent's
runner automatically.

### `WorktreeManager.__init__` falls back to the contextvar

```python
def __init__(self, git_runner=None, base_dir=None, *, symlink_cache_dirs=True):
    if git_runner is not None:
        self._git_runner = git_runner
    else:
        ctx_runner = get_current_git_runner()
        self._git_runner = ctx_runner or local_git_runner
    ...
```

Priority order: **explicit argument > contextvar > local**.

### Modified: `backend/harness/orchestrator.py`

In the per-session worktree creation:

```python
git_runner = None
if sandbox is not None and getattr(sandbox, "run", None) is not None:
    try:
        git_runner = sandbox_git_runner(sandbox)
    except Exception as exc:
        logger.debug(...)

# C01: set the git runner as a contextvar so subagents spawned
# by delegate_task inherit the same runner. Mirrors the C04
# set_current_kg_context pattern.
set_current_git_runner(git_runner)
wt_manager = WorktreeManager(git_runner=git_runner)
```

The contextvar is set **before** the WorktreeManager is created
so the per-session worktree's runner is also reflected. But
the important propagation is to **subagents spawned later** in
this task's lifetime — the orchestrator's run_single coroutine
keeps the contextvar set throughout.

### Modified: `backend/harness/tools/delegate_task.py`

In the per-subagent worktree creation:

```python
wt_manager = WorktreeManager()  # No explicit runner — picks up the contextvar
```

The `WorktreeManager()` call is unchanged. The new contextvar
fallback means the subagent's `WorktreeManager` uses whatever
runner the orchestrator set. In production: `sandbox_git_runner`.
In tests: `local_git_runner` (no contextvar set).

Updated the comment to explain the contextvar mechanism:

```python
# C01 contextvar: WorktreeManager() with no explicit runner
# falls back to get_current_git_runner() — the orchestrator's
# set_current_git_runner(sandbox_git_runner(sandbox)) makes
# the subagent inherit the sandbox runner (production: git
# inside the container). Tests: the default local_git_runner
# is used.
```

### New file: `backend/tests/test_worktree_git_runner_contextvar.py` (13 tests, all passing)

Covers:
- **Contextvar basics** (6):
  - Returns `None` when unset
  - Set/get roundtrip
  - Reset restores previous value
  - Nested set/reset (the inner reset doesn't bleed)
  - `set(None)` clears
  - Task isolation: child task sees parent's runner via
    `asyncio.create_task` (the property that makes this work
    for delegate_task)
- **WorktreeManager integration** (3):
  - Explicit `git_runner=` argument wins over contextvar
  - No explicit → contextvar
  - No contextvar → `local_git_runner`
- **End-to-end** (3):
  - Orchestrator's `sandbox_git_runner` propagates to subagent
  - No contextvar → subagent uses `local_git_runner` (dev/test)
  - Subagent can override with explicit argument
- **Module surface** (1): all 6 public symbols are exported

## Behavior change (observable)

| | Before | After |
|---|---|---|
| Per-session worktree location | container (via `sandbox_git_runner` in orchestrator) | container (unchanged) |
| Per-subagent worktree location (production) | **host** filesystem (via `local_git_runner` default) | **container** filesystem (via inherited `sandbox_git_runner`) |
| Per-subagent worktree location (tests/dev) | host | host (unchanged — no contextvar set) |
| Subagent overrides with explicit `git_runner=` | n/a (no contextvar) | still works (explicit > contextvar) |

## How the propagation works

```
Orchestrator.run_single()                   [asyncio task]
  ├── set_current_git_runner(sandbox_git_runner(sandbox))
  │
  ├── wt_manager = WorktreeManager(git_runner=sandbox_git_runner)
  │   → per-session worktree in container
  │
  └── delegate_task(goal=...)              [same asyncio task]
       ├── await subagent.run()            [asyncio.create_task(child_task)]
       │   ← contextvar inherited (asyncio copies context to subtask)
       │
       └── wt_manager = WorktreeManager()  ← picks up contextvar
           → per-subagent worktree in container
```

`asyncio.create_task` copies the current context (including
contextvars) to the new task. When the orchestrator's
`set_current_git_runner` is set, the subagent's
`WorktreeManager()` sees it via `get_current_git_runner()`.

## Failure modes

| Failure | Behavior |
|---|---|
| `set_current_git_runner` never called (e.g. orchestrator in dev mode) | `WorktreeManager()` falls back to `local_git_runner` — same as pre-contextvar behavior |
| Subagent spawned outside the orchestrator's context (e.g. from a different task tree) | `get_current_git_runner()` returns `None`, falls back to `local_git_runner` |
| Explicit `git_runner=` argument wins | Subagent can override inherited runner if needed (e.g. for tests that need a different runner) |
| `reset_current_git_runner` not called (token leaked) | Future tasks see the leaked value — same as any contextvar misuse. The `try/finally` pattern in the orchestrator prevents this. |

## Why a contextvar (not a class attribute)

Three alternatives considered:
1. **Class attribute on `WorktreeManager`** — no, because
   `WorktreeManager` is constructed independently in each
   subagent's call site. A class attribute would be a global,
   breaking task isolation.
2. **Pass through the orchestrator's state explicitly** —
   would require `delegate_task` to take a `git_runner`
   parameter, which would need threading through the agent
   factory, the `DelegateTaskTool`, and every call site. High
   churn.
3. **Contextvar** (chosen) — already a pattern in the codebase
   (C04 `set_current_kg_context`). Minimal code change. Task
   isolation is built-in (asyncio copies context to subtasks).
   Tests are easy (just `set_current_git_runner(...)` in the
   fixture).

## Files changed

| File | Change |
|---|---|
| `backend/harness/services/worktree_manager.py` | +60 lines (contextvar + `__init__` fallback) |
| `backend/harness/orchestrator.py` | +3 lines (`set_current_git_runner(git_runner)` before the WorktreeManager call) |
| `backend/harness/tools/delegate_task.py` | +12 lines (updated comment explaining the contextvar) |
| `backend/tests/test_worktree_git_runner_contextvar.py` | NEW (13 tests, all passing) |

## Verification

- 13/13 new tests pass
- 317/317 tests in all touched/related test files pass
  (C08, team_service, worktree_manager, kg_refresh_tool,
  codegraph_tools, tool_dispatch_role_gating, event_source_sink,
  events_sse_route, board_waiter, heartbeat, submit_job_handoff,
  job_spec_store, team_sweeper, sandbox_git_runner,
  legacy_adapters, worktree_git_runner_contextvar)

## Sprint state

C01 is now truly production-ready:
- Per-session worktree in the container ✓
- Per-subagent worktree in the container (via contextvar) ✓
- Auto-cleanup of per-subagent worktree after subagent finishes ✓
- Auto-cleanup of per-session worktree via the 7-day volume TTL ✓
- Per-subagent worktree lock (Claude Code pattern) — still deferred

Remaining C01 deferred items:
- Per-subagent worktree lock (while running)
- Auto PR-open at subagent completion
- `.worktreeinclude` for gitignored env files
