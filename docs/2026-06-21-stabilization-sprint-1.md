# Stabilization Sprint 1 — Q5 hybrid lifecycle + production C01 wiring

**Date**: 2026-06-21
**Status**: Implemented
**Follow-up to**: C01 (worktree isolation), C02 (agent teams)

## What this addresses

Two high-impact gaps from the previous candidates' open-questions
sections:

1. **C02 Q5 was missing the auto-dissolve trigger.** The
   `TeamService.cleanup_completed()` method was exposed but no
   caller invoked it. Teams would sit in the DB until manually
   dissolved. This sprint adds the long-lived sweeper that
   invokes it on a schedule.
2. **C01 was using the local-host git runner in production.**
   `WorktreeManager()` defaulted to `local_git_runner` which runs
   `git` on the host, not in the sandbox. The orchestrator's
   per-session worktree was being created on the host filesystem,
   not inside the container. This sprint wires
   `sandbox_git_runner(env)` so git runs in the Docker sandbox.

## Implementation

### New file: `backend/harness/services/team_sweeper.py` (~120 lines)

The long-lived auto-dissolve sweeper. Mirrors the kanban review
agent pattern at `services/kanban_service.py:689-756`:

- **Free async function** (`run_team_sweeper(app, *, interval,
  initial_delay)`) — runs forever, awaits interval between
  cycles, calls `TeamService.cleanup_completed()` on each cycle.
- **`start_team_sweeper(app)`** — schedules the function as a
  background task. Idempotent (a second call returns the
  existing task).
- **`stop_team_sweeper()`** — cancels the running task and
  cleans up the module-level handle. No-op if not running.

Failure modes handled:
- **No DB** (`app.state.db is None`) — the sweeper sleeps and
  retries. Doesn't crash.
- **DB errors during cleanup** — logged at WARNING, loop
  continues. The next cycle tries again.
- **Cancellation** — `CancelledError` propagates cleanly, the
  task exits without printing stack traces.

Default cadence: **60 seconds** (matches the kanban review
agent). Configurable via the `TEAM_SWEEPER_INTERVAL_SECONDS`
env var. The 10s initial delay gives the rest of the app time
to finish its startup (sandbox bootstrap, dispatcher, etc).

Wired into `api/main.py` next to `start_review_agent`:

```python
try:
    from harness.services.team_sweeper import start_team_sweeper
    start_team_sweeper(app)
except Exception as e:
    logger.warning("Team sweeper not started: %s", e)
```

### Modified: `backend/harness/orchestrator.py`

Added the `sandbox_git_runner(env)` wiring in the per-session
worktree creation:

```python
git_runner = None
if sandbox is not None and getattr(sandbox, "run", None) is not None:
    try:
        git_runner = sandbox_git_runner(sandbox)
    except Exception as exc:
        logger.debug("sandbox_git_runner init failed (falling back to local): %s", exc)
wt_manager = WorktreeManager(git_runner=git_runner)
```

Production: git runs inside the Docker container. The worktree's
working copy is the sandbox's filesystem (not the host's). Tests:
falls back to `local_git_runner` if no sandbox is wired.

The log line now shows which runner is in use:
`runner=sandbox` in prod, `runner=local` in tests.

### New file: `backend/tests/test_team_sweeper.py` (9 tests, all passing)

Covers:
- Constants (default 60s cadence)
- `start_team_sweeper` returns the task; idempotent
- `stop_team_sweeper` is safe when never started
- `stop_team_sweeper` cancels a running task
- The loop calls `TeamService.cleanup_completed` on every cycle
- The loop survives DB errors (logs + continues)
- The loop skips when no DB is wired (no crash)
- Cancellation exits cleanly
- Dissolved teams are logged

### New file: `backend/tests/test_sandbox_git_runner.py` (11 tests, all passing)

Covers:
- `local_git_runner` runs git on the host (sanity check)
- `sandbox_git_runner` builds the correct `cd <cwd> && git ...` command
- Path with spaces is quoted
- Args with spaces (e.g. branch names) are quoted
- Returns 0 on success, non-zero on failure
- Exception from `env.run` is treated as non-zero exit
- Timeout is passed to `env.run`
- Strips trailing whitespace
- Handles `None` stdout/stderr
- **End-to-end**: `WorktreeManager` + `sandbox_git_runner` create a
  real worktree via a fake sandbox (verifies the integration)

## Behavior change (observable)

| | Before | After |
|---|---|---|
| Team auto-dissolve | never (manual only) | every 60s, teams with all-done members auto-dissolve |
| Per-session worktree location | host filesystem (in `local_git_runner` mode) | container filesystem (via `sandbox_git_runner`) |
| Orphan teams in DB | accumulate forever | cleaned up within 60s of last member finishing |
| Worktree creation in prod | silently created on host (no isolation) | created in the container (proper isolation) |

## Failure modes

| Failure | Behavior |
|---|---|
| DB unavailable when sweeper starts | sweeper sleeps + retries; doesn't crash the app |
| `cleanup_completed` raises | logged at WARNING, loop continues |
| `env.run` raises in sandbox_git_runner | runner returns `(1, "", "sandbox git runner failed: ...")` |
| WorktreeManager init fails | falls back to `local_git_runner`; logged at DEBUG |
| `start_team_sweeper` called twice | returns the existing task; no duplicate |

## Configuration

| Env var | Default | Description |
|---|---|---|
| `TEAM_SWEEPER_INTERVAL_SECONDS` | 60 | How often the sweeper calls `cleanup_completed()` |
| `initial_delay` (parameter) | 10s | First-cycle delay to let the app finish startup |

## Files changed

| File | Change |
|---|---|
| `backend/harness/services/team_sweeper.py` | NEW (~120 lines) |
| `backend/harness/orchestrator.py` | +20 lines (sandbox_git_runner wiring) |
| `api/main.py` | +5 lines (start_team_sweeper) |
| `backend/tests/test_team_sweeper.py` | NEW (9 tests, all passing) |
| `backend/tests/test_sandbox_git_runner.py` | NEW (11 tests, all passing) |

## Verification

- 20 new tests pass (9 sweeper + 11 sandbox_git_runner)
- 288/288 tests in all touched/related test files pass
  (C08, team_service, worktree_manager, kg_refresh_tool,
  codegraph_tools, tool_dispatch_role_gating, event_source_sink,
  events_sse_route, board_waiter, heartbeat, submit_job_handoff,
  job_spec_store, team_sweeper, sandbox_git_runner)

## Next steps

- **C08 full migration** (Q7): rewrite the 3 legacy endpoints
  (`/api/agent/run`, `/api/delegate`,
  `/api/pipeline/from-requirements`) as thin wrappers around
  `submit_job_to_orchestrator`. Delete them in the same sprint.
- **C01 subagent worktree in sandbox**: `delegate_task` currently
  uses `local_git_runner` because the subagent doesn't carry
  its own sandbox. The same `sandbox_git_runner(sandbox)` pattern
  can be applied when the subagent is in a sandbox.
- **C01 PR auto-open**: the per-subagent branch is created but
  the draft PR isn't auto-opened when the subagent finishes.
  Today the agent has to call `commit_and_open_pr` itself.
