# E2E Live Test Report — June 16, 2026

## Test Setup

- **Target Repo:** `https://github.com/rails/rails` (120k+ files, Ruby)
- **API Key:** `sk-DBG6zpzGewyl72IJfyloIynM5wbZajWkfQJMsYw0pPyND1rkXygSjWSsbtgrP34k`
- **Model:** `deepseek-v4-flash` via OpenCode Zen
- **Stack:** PostgreSQL 16, FastAPI backend, Next.js 16 frontend, Docker sandbox

## Environment State

| Component | Status |
|-----------|--------|
| Backend (FastAPI) | ✅ Healthy on `:8001` |
| Frontend (Next.js) | ✅ Running on `:3001` |
| Database (PostgreSQL) | ✅ 79 tables, healthy |
| Sandbox Container | ✅ `nikolaik/python-nodejs:python3.11-nodejs20` |
| CodeGraph (KG) | ✅ 15,464 files indexed, 293,172 nodes, 741,703 edges |

## Bugs Found & Fixed

### 1. `ApprovalRequired` Scoping Error (CRITICAL)

**File:** `backend/harness/agent/tool_dispatch.py:461`
**Error:** `cannot access local variable 'ApprovalRequired' where it is not associated with a value`
**Cause:** `ApprovalRequired` imported at module level (line 40) but re-imported inside a conditional block (line 492). Python's scoping treats it as a local variable throughout the function, causing `UnboundLocalError` when line 461 runs first.
**Fix:** Removed redundant local import at line 492.
**Impact:** Chat API completely broken — every request failed.

### 2. `repo_url` Empty in JobSpec (CRITICAL)

**File:** `backend/harness/orchestrator.py:423`
**Error:** `Clone failed: exit=128 output=fatal: repository '/workspace/repo' does not exist`
**Cause:** LLM embeds repo URL in prompt text but doesn't pass `repo_url` parameter to `submit_job`. The job spec has empty `repo_url`, so the orchestrator tries to clone from an empty string.
**Fix:** Added URL extraction regex in `run_single()` to auto-extract GitHub URLs from the goal/prompt when `repo_url` is empty.
**Impact:** Every pipeline run with a repo URL failed silently.

### 3. Kanban Board Creation Using Wrong Tool (HIGH)

**File:** `backend/harness/orchestrator.py:572-582`
**Error:** `Kanban board creation failed: Expecting value: line 1 column 1 (char 0)`
**Cause:** Orchestrator calls `registry.get("kanban_create").run(name=..., description=...)` but `kanban_create` is a **task creation tool** (creates tasks on an existing board), not a board creation tool. The tool expects `title` and `board_id`, not `name`.
**Fix:** Replaced with direct HTTP call to `POST /api/kanban/boards` via `httpx`.
**Impact:** No kanban boards were ever created despite the orchestrator running.

### 4. `--workers 4` Causes DB Connection Pool Corruption (HIGH)

**File:** `backend/Dockerfile:29`
**Error:** `ConnectionDoesNotExistError: connection was closed in the middle of operation`
**Root Cause:** asyncpg connection pools are not fork-safe. TCP connections are file descriptors shared across forked processes, causing concurrent access corruption. Uvicorn's `--workers N` forks the master process, inheriting the pool's file descriptors.
**Fix:** Changed to `--workers 1`. FastAPI is async — concurrency is handled via the event loop, not process count. Our bottleneck is I/O (LLM calls, Docker, DB), which async handles perfectly.
**Enterprise Pattern:** Dify, RAGFlow, and other production AI platforms use Gunicorn + Celery:
- Web server: Gunicorn with gevent worker (1-4 workers, each with own pool)
- Background tasks: Celery workers (separate processes, each with own pool)
- Message broker: Redis/RabbitMQ for task dispatch
- Each process owns its DB connection pool — no file descriptor sharing
**Scaling Path:** When horizontal scaling is needed, add Celery + Redis. Until then, `--workers 1` is correct.
**Impact:** Background orchestrator tasks silently failed with DB connection errors.

### 5. Max Tool Rounds Too Low for Large Repos (MEDIUM)

**File:** `backend/api/main.py:405`
**Error:** `Max tool rounds reached without final response.`
**Cause:** `max_tool_rounds=20` hardcoded in `agent_factory`. For large repos like rails/rails (120k+ files), the coordinator needs more rounds to clone, index KG, explore, and produce results.
**Fix:** Increased default to 20, made it configurable via `max_tool_rounds` parameter in `DelegateTaskTool.run()`, and set coordinator to 50 rounds.
**Impact:** Coordinator timed out before completing analysis of large repos.

### 6. Bare `except Exception: pass` Swallows Errors (MEDIUM)

**File:** `backend/harness/orchestrator.py:581`
**Cause:** Kanban board creation wrapped in `try/except Exception: pass` — all errors silently swallowed.
**Fix:** Replaced with `logger.warning("Kanban board creation failed: %s", exc)`.
**Impact:** Impossible to diagnose why kanban boards weren't being created.

## What Worked

| Feature | Status | Details |
|---------|--------|---------|
| Chat API | ✅ | SSE streaming, job submission working |
| JobSpec creation | ✅ | Persisted to DB, tier routing correct |
| Orchestrator spawn | ✅ | Background task created via `asyncio.create_task` |
| Sandbox creation | ✅ | Docker container with network, volume isolation |
| Git clone (rails/rails) | ✅ | Shallow clone, ~219MB workspace |
| Knowledge Graph indexing | ✅ | CodeGraph: 3,705 files, 60,466 nodes, 176,960 edges |
| Coordinator delegation | ✅ | `delegate_task` spawns subagent with coordinator toolset |
| Coordinator execution | ✅ | Subagent completes with full results |
| Kanban board creation | ✅ | After fix: board created with proper columns |
| API health checks | ✅ | `/api/health` endpoint responsive |
| Frontend dashboard | ✅ | 36 pages, kanban page loads correctly |
| Database schema | ✅ | 79 tables, all migrations applied |
| Tool registration | ✅ | 79 tools discovered (in worker process) |
| CodeGraph tools | ✅ | `codegraph_explore`, `codegraph_search`, `codegraph_node` |
| Cross-run memory | ✅ | L2 reflections saved, memory snapshots loaded |

## What Didn't Work / Partial

| Feature | Status | Issue |
|---------|--------|-------|
| Kanban task creation | ⚠️ | Coordinator did work directly instead of decomposing into tasks |
| Tool calls count tracking | ⚠️ | `tool_calls_count` always 0 in delegations |
| Cost tracking | ⚠️ | `cost` always 0 in sessions |
| GitHub issues/PRs listing | ❌ | Not tested — requires GitHub API integration |
| Self-healing tests | ❌ | Not tested — requires failing tests |
| PR creation | ❌ | Not tested — requires GitHub token |
| Multi-worker support | ❌ | Broken with `--workers 4` — DB pool corruption |
| L1 Artifact Indexer | ❌ | Stub only — background LLM extraction not implemented |
| Budget Tracker enforcement | ❌ | Plumbing only — per-step hooks not wired |
| OpenTelemetry export | ❌ | Requirements listed but commented out |

## Architecture Assessment

### Greptile Comparison
Greptile's approach: Full-repo indexing → semantic codegraph → PR review with cross-file context. TestAI's CodeGraph achieves similar functionality with `codegraph_explore`, `codegraph_search`, `codegraph_node` tools. Key difference: Greptile is read-only review; TestAI is read+write with sandbox execution.

### Tembo Comparison
Tembo's approach: Orchestrator pattern (lead agent + sub-agents), isolated sandboxes per agent, parallel execution. TestAI matches this with `OrchestratorEngine` → `delegate_task` → subagent spawning. Key difference: Tembo supports multiple coding agents (Claude Code, Cursor, Codex); TestAI uses a single LLM backend.

### TestSprite Comparison
TestSprite's approach: MCP-integrated testing, cloud sandboxes, self-healing tests, PRD→test plan→test code pipeline. TestAI has similar capabilities with `attempt_heal`, `visual_diff`, `test_generator`. Key difference: TestSprite is test-focused; TestAI is broader (orchestration + testing + fixing).

### OpenHands Comparison
OpenHands' approach: Agent runtime with sandbox, browser automation, code execution. TestAI's sandbox manager with `docker exec` is similar. Key difference: OpenHands has a more mature browser automation layer; TestAI has stronger kanban/project management integration.

## Remaining Gaps

### Critical
1. **Multi-worker support** — Need to solve DB connection pool sharing across forked workers. Options: use `multiprocessing.Queue` for IPC, switch to Redis-backed session store, or use `uvloop` with proper fork handling.
2. **Kanban task decomposition** — Coordinator does work directly instead of creating kanban tasks. Need to update coordinator prompt to enforce task creation before execution.

### High
3. **Cost tracking** — Token usage not being recorded. Check `_record_cost` in agent.py.
4. **Tool calls count** — `tool_calls_count` always 0 in delegations. Check `_record_tool_call` in subagent_persistence.py.
5. **GitHub integration** — No testing of GitHub issues/PRs listing. Need to wire `gh` CLI or GitHub API.
6. **Budget enforcement** — Auto-throttle ladder not wired. Need to connect `BudgetTracker.check_soft_cap()` to agent loop.

### Medium
7. **L1 Artifact Indexer** — Background LLM extraction of facts from L0 raw artifacts.
8. **Context compression** — Reactive compact (retry on prompt_too_long) not fully implemented.
9. **A2A wire protocol** — Internal Postgres communication only. No external agent interop.
10. **SSL/TLS** — No certificates configured for production deployment.
11. **Rate limiting** — No API rate limiting middleware.
12. **Authentication** — No auth middleware. API is open.

### Low
13. **E2E test suite** — No Playwright/Cypress tests for frontend.
14. **Postgres-backed container registry** — Only in-memory implementation.
15. **Multi-repo PR coordination** — Sequential only, no coordinated PR strategy.

## Competitor Research Summary

| Feature | Greptile | Tembo | TestSprite | Testim | TestAI |
|---------|----------|-------|------------|--------|--------|
| Knowledge Graph | ✅ Semantic | ❌ | ❌ | ❌ | ✅ CodeGraph |
| Multi-agent orchestration | ❌ | ✅ | ❌ | ❌ | ✅ |
| Sandbox execution | ❌ | ✅ | ✅ Cloud | ✅ Cloud | ✅ Docker |
| Self-healing tests | ❌ | ❌ | ✅ | ✅ Smart Locators | ✅ attempt_heal |
| Kanban/project mgmt | ❌ | ❌ | ❌ | ❌ | ✅ |
| PR review | ✅ Primary | ❌ | ❌ | ❌ | ✅ |
| MCP integration | ❌ | ❌ | ✅ | ❌ | ✅ |
| Cost tracking | ❌ | ✅ | ❌ | ❌ | ✅ |
| Browser automation | ❌ | ❌ | ✅ | ✅ | ✅ computer_use |

## Files Modified

1. `backend/harness/agent/tool_dispatch.py` — Fixed `ApprovalRequired` scoping, added logging to background task
2. `backend/harness/orchestrator.py` — Added URL extraction, fixed kanban board creation, improved error logging
3. `backend/Dockerfile` — Changed `--workers 4` to `--workers 1`
4. `backend/api/main.py` — Made `max_tool_rounds` configurable in agent factory
5. `backend/harness/tools/delegate_task.py` — Added `max_tool_rounds` parameter passthrough
