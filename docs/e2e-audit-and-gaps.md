# E2E Audit & Gap Analysis

> Generated 2026-06-19 from a live end-to-end test against `rails/rails` via the pipeline API.

## E2E Test Setup

- **Model:** `deepseek-v4-flash` via `opencode.ai/zen/go/v1`
- **Repo:** `https://github.com/rails/rails`
- **Endpoint:** `POST /api/pipeline/from-requirements`
- **Session ID:** `cc962db8-72f5-4a6f-aa0f-2739ac0c9449`

## What Actually Happened (Observed Flow)

| Step | Expected | Actual | Status |
|------|----------|--------|--------|
| 1. API receives request | Session created, pipeline starts | Session created (status=running), background task spawned | ✅ |
| 2. LLM configured | Provider set in DB | Provider configured successfully | ✅ |
| 3. Sandbox created | Docker container created | Container `testai-sandbox-cc962db8-72f` created (nikolaik/python-nodejs) | ✅ |
| 4. Repo cloned | `git clone --depth 1` into `/workspace/repo` | **Workspace EMPTY** — no `.git`, no files | ❌ |
| 5. KG built | CodeGraph indexes repo | KG built from PREVIOUS run (June 18), not this run | ⚠️ |
| 6. Kanban board created | Board with tasks from LLM decomposition | Board created with **0 tasks** | ❌ |
| 7. Coordinator spawned | Agent runs with `coordinator` toolset | Subagent failed: `401 Invalid API key` | ❌ |
| 8. Workers spawned | Subagents fix issues | No workers spawned (coordinator failed) | ❌ |
| 9. Kanban updated | Tasks moved to done/blocked | No tasks to update (board empty) | ❌ |
| 10. Pipeline completed | Status=completed with results | Status=completed, but **no work done** | ⚠️ |

**Root cause of failure:** The LLM API key (`sk-l3mh...`) returned `401 Invalid API key` when the subagent tried to use it. The pipeline reported "completed" despite the coordinator failing.

---

## Gap Analysis: Component-by-Component

### 1. ORCHESTRATOR → SUBAGENT FLOW

**Question:** Can the orchestrator spawn subagents that actually do work?

**Finding: PARTIALLY BROKEN**

- The pipeline creates a session and spawns a background orchestrator task ✅
- The orchestrator creates a sandbox container ✅
- The orchestrator attempts to clone the repo — but the clone appears to have failed silently ❌
- The coordinator subagent fails because the LLM API key is invalid ❌
- The pipeline reports "completed" even though the coordinator failed ❌

**Key issue:** The pipeline's error handling catches the subagent failure but still marks the session as `completed`. There's no distinction between "pipeline infrastructure worked" and "actual agent work succeeded."

**Code reference:** `api/routers/pipeline.py:820-828` — the error handler sets `status='failed'` but the success path at line 685 also sets `status='completed'` regardless of whether the coordinator actually produced output.

### 2. KNOWLEDGE GRAPH INTEGRATION

**Question:** Is the KG built and used by agents?

**Finding: KG EXISTS BUT USAGE IS UNRELIABLE**

- KG was built from a previous run (June 18), not the current run
- The pipeline emits `pipeline.kg_ready` and `pipeline.kg_building` events
- The `codegraph_explore` tool IS being called by agents (seen in logs: `DEBUG: First tool: codegraph_explore`)
- But the KG content is stale — it reflects the June 18 version of rails/rails, not the current HEAD
- The KG DB files exist on the host at `/app/agent_workspace/knowledge-graphs/`

**Gap:** No mechanism to force a fresh KG build when the repo has been updated. The `restore_db_from_host` logic in `orchestration_phases.py` restores from host cache if the sandbox volume is fresh, which means stale KG data is used.

**Code reference:** `harness/orchestration_phases.py:80-85` — restores from host cache before building fresh.

### 3. SANDBOX LIFECYCLE

**Question:** Can agents share sandboxes? Is isolation working?

**Finding: ISOLATION WORKS, SHARING IS BROKEN**

- Each subagent gets its **own** container (different `session_id` → different container)
- The coordinator does NOT share the orchestrator's sandbox — it gets a fresh, empty container
- This means the repo clone, deps install, and KG build done by the orchestrator are **wasted** for the coordinator
- The coordinator must re-clone, re-install, and re-build from scratch
- Volumes are keyed on `repo_url` (orchestrator path) or `session_id` (pipeline path), so different sessions get different volumes

**Critical gap:** `delegate_task.py:352` creates `child_session_id = f"subagent-{subagent_id}"` — this doesn't inherit the parent's `volume_key`. The coordinator gets a fresh, empty workspace.

**Code reference:** `harness/tools/delegate_task.py:352` — child session ID generation; `harness/sandbox_manager.py:309-314` — `get_or_create` keyed on session_id.

### 4. KANBAN BOARD & TASK MANAGEMENT

**Question:** Does the kanban board get populated and updated?

**Finding: BOARD CREATED EMPTY, NEVER POPULATED**

- The pipeline creates a kanban board with 0 tasks (`pipeline.py:431-449`)
- The coordinator is told to "Call orchestrate(goal=...) to decompose" but doesn't have the `orchestrate` tool
- The `toolsets` passed to the coordinator are `["read", "write", "intelligence", "healing", "delegate"]` — no `orchestrate`
- Previous runs created tasks (10 tasks in backlog from earlier runs), but the current run's board is empty
- The `kanban_update` tool referenced in `orchestrator.md:55` doesn't exist — only `kanban_complete` exists

**Gaps:**
1. Pipeline doesn't call `cmd_orchestrate()` to pre-populate tasks
2. Coordinator can't call `orchestrate()` (missing from toolset)
3. `kanban_update` tool doesn't exist (prompt references nonexistent tool)

**Code reference:** `api/routers/pipeline.py:473` — toolset doesn't include `orchestrate`; `harness/tools/kanban_agent_tools.py` — no `kanban_update` registered.

### 5. ARTIFACT PERSISTENCE

**Question:** Are test files, configs, and agent outputs persisted?

**Finding: ARTIFACT TABLE IS EMPTY FOR THIS RUN**

- The `artifacts` table has 0 rows for this session
- The pipeline has code to save artifacts (`pipeline.py:504-528, 569-595`) but it depends on the coordinator producing output
- Since the coordinator failed (401), no artifacts were saved
- The `pipeline_completed` event was emitted but with no actual output

**Gap:** Artifacts are only saved if the coordinator succeeds. There's no "attempted work" artifact for debugging failed runs.

### 6. METRICS COLLECTION

**Question:** Are metrics (token usage, cost, test results) collected?

**Finding: METRICS ARE PARTIAL**

- `quality_metrics` table has 5 entries for this run:
  - `pipeline_status: 1.0` (completed)
  - `total_tests: 0.0`
  - `passed_tests: 0.0`
  - `failed_tests: 0.0`
  - `pass_rate: 0.0`
- `sandbox_metrics` shows the container was created and is running
- No `token_usage` entries (the LLM call failed before tokens were generated)
- No `agent_delegations` table (table doesn't exist with expected schema)

**Gap:** Metrics show "0 tests, 0 passed, 0 failed" which is misleading — no tests were run at all because the coordinator failed. The metrics don't distinguish between "no tests found" and "tests couldn't be run."

### 7. USER CONFIGURATION

**Question:** Can users configure things?

**Finding: CONFIGURATION WORKS**

- LLM provider was configurable via `POST /api/settings/providers` ✅
- The provider was set and recognized by the system ✅
- Settings are persisted in the DB ✅

**Gap:** No way to configure the API key via environment variable that overrides the DB setting. The `OPENAI_API_KEY` env var is checked at startup but the pipeline path doesn't use it.

---

## Comparison: TestAI vs Production Harnesses

| Capability | TestAI | Tembo | Greptile | TestSprite |
|------------|--------|-------|----------|------------|
| Task decomposition | LLM-based (when `cmd_orchestrate` works) | Platform-level explicit decomposition | Codebase-indexed decomposition | N/A (test-focused) |
| Sandbox isolation | Per-session containers | Per-task containers with 8GB/4CPU | N/A (API-only) | Per-test containers |
| KG integration | CodeGraph (tree-sitter) | N/A | Custom codebase indexing | N/A |
| Error recovery | Budget-based throttle + circuit breaker | Human-in-the-loop via PR comments | Retry with context | Self-healing tests |
| Artifact persistence | DB-backed (when coordinator succeeds) | Git-backed (PRs) | API-backed | Screenshot/video artifacts |
| Metrics | Partial (quality_metrics, sandbox_metrics) | Full CI/CD metrics | Usage analytics | Test pass/fail/flake metrics |

---

## Prioritized Fix List

### P0 — Critical (blocks all E2E flows)

1. **Fix LLM API key handling** — The pipeline must validate the API key before spawning the coordinator. Currently it fails mid-run with `401` and reports "completed."

2. **Fix sandbox sharing between orchestrator and coordinator** — The coordinator must inherit the parent's `volume_key` so it gets the same sandbox with the cloned repo, installed deps, and built KG. This is the single biggest waste in the current system.

3. **Fix pipeline kanban task creation** — Either:
   - Add `orchestrate` toolset to the pipeline's coordinator, OR
   - Call `cmd_orchestrate()` before spawning the coordinator (like the orchestrator path does)

### P1 — High (degrades quality)

4. **Fix `kanban_update` tool reference** — The coordinator prompt references a tool that doesn't exist. Either create `kanban_update` or update the prompt to use `kanban_complete`.

5. **Fix pipeline error propagation** — The pipeline should report `status=failed` when the coordinator fails, not `status=completed`.

6. **Force fresh KG build** — The `restore_db_from_host` logic should check if the KG is stale (e.g., based on repo last-commit date) and rebuild if needed.

### P2 — Medium (improves reliability)

7. **Add reaper for orphaned containers** — `reap_stale()` is a static method that must be called externally. Schedule it as a background task.

8. **Add volume cleanup** — Orphaned volumes have no reclaim path. Add a volume reaper that removes volumes for destroyed sessions.

9. **Add artifact persistence for failed runs** — Save "attempted work" artifacts (logs, partial output) even when the coordinator fails, so debugging is possible.

10. **Fix duplicate `_explore_codebase` calls** — The orchestrator path calls `_explore_codebase` twice (once in `run_single`, once inside `cmd_orchestrate`). Remove the redundant call.

### P3 — Low (improves UX)

11. **Add `pipeline_runs` table** — The pipeline path doesn't write to `pipeline_runs`, so the dashboard can't track pipeline history.

12. **Add `agent_delegations` table schema** — The table exists but the schema doesn't match what `persist_delegation()` expects.

13. **Fix `sandbox/exec-containers` 500 error** — The endpoint returns 500 Internal Server Error consistently.

---

## Files Modified in This Session

| File | Change |
|------|--------|
| `backend/harness/memory/db_context.py` | NEW — replaces `Database._instance` singleton |
| `backend/harness/lifecycle.py` | NEW — `ManagedTask` + `StartupPhase` |
| `backend/harness/orchestration_phases.py` | NEW — shared orchestration phases |
| `backend/harness/tools/subagent_session.py` | NEW — extracted DB/budget/persistence helpers |
| `src/stores/pipeline-event-reducer.ts` | NEW — extracted event reducer |
| `src/components/pipeline/index.ts` | NEW — barrel export |
| `backend/api/main.py` | Lifespan refactored to use `ManagedTask` |
| `backend/harness/agent/deps.py` | Added `db` field to `AgentDependencies` |
| `backend/harness/tools/delegate_task.py` | Uses extracted helpers |
| `backend/api/routers/pipeline.py` | Uses `orchestration_phases` |
| `src/lib/api/api-client.ts` | Canonical API client |
| `src/lib/api/client.ts` | Re-export barrel |
| `src/stores/pipeline-store.ts` | Uses event reducer |
| 32 files | `getattr(Database, "_instance", None)` → `get_db()` |
