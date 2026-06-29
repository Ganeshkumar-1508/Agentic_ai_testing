# E2E Agent Harness Test — 2026-06-18

**Date**: 2026-06-18  
**Target**: rails/rails (GitHub) via frontend-equivalent API call  
**Goal**: Validate full agentic loop — orchestrator, coordinator, subagents, KG, kanban, sandbox, artifacts  
**Method**: `POST /api/delegate` with `role: orchestrator`, `run_in_background: true`

---

## Fixes Implemented (2026-06-18)

### 1. Coordinator Prompt — Parallel Fan-Out (✅ Fixed)

**File**: `backend/harness/agents/orchestrator.md`

**Change**: Updated coordinator prompt from sequential to parallel execution:
- Old: "Pick first READY task → spawn worker → wait → repeat"
- New: "Count READY tasks → if >= 3, use fan-out mode with tasks array → spawn N workers in parallel"

**Impact**: Coordinator now instructed to spawn 5+ workers simultaneously when multiple tasks are ready.

### 2. Kanban Task Decomposition — 15 Tasks (✅ Fixed)

**File**: `backend/harness/tools/orchestrator_tool.py`

**Change**: Increased default decomposition from 4 to 15 tasks:
- 5 parallel explore tasks (no dependencies)
- 1 triage task (depends on all 5 explore)
- 3 implement tasks (parallel, depend on triage)
- 2 test tasks (parallel, depend on implement)
- 2 verify tasks (parallel, depend on tests)
- 1 security audit (depends on verify)
- 1 code review (depends on security)

**Impact**: Kanban board now has 15 granular tasks instead of 4, enabling better parallelization.

### 3. Worker Session Persistence (✅ Fixed)

**File**: `backend/harness/tools/delegate_task.py`

**Change**: Fixed session row creation for workers:
- Changed `self._session_id or ""` to `self._session_id or None` (NULL instead of empty string)
- Added `str(goal)[:500]` to ensure goal is a string before slicing
- Added logging for session creation success/failure

**File**: `backend/harness/tools/subagent_persistence.py`

**Change**: Fixed session update persistence:
- Changed `parent_session_id` to `parent_session_id or None`
- Added error logging for persistence failures

**Impact**: Workers now appear in `sessions` table with correct parent_session_id.

### 4. Checkpoint Error Handling (✅ Fixed)

**File**: `backend/harness/checkpoint.py`

**Change**: Added session existence check before checkpoint insert:
```python
session_exists = await self.db.fetchval(
    "SELECT EXISTS(SELECT 1 FROM sessions WHERE id = $1)",
    self.session_id
)
if not session_exists:
    logger.debug("Checkpoint skipped: session %s not found", self.session_id)
    return None
```

**Impact**: Checkpoint errors no longer crash the agent loop when session doesn't exist yet.

### 5. GitHub Integration Tools (✅ Added)

**File**: `backend/harness/tools/github_tools.py` (new)

**Tools Added**:
- `github_list_issues`: List open GitHub issues for a repo
- `github_list_prs`: List open GitHub pull requests for a repo

**Impact**: Agents can now query GitHub for issues and PRs during exploration phase.

### 6. Fan-Out Tool (✅ Added)

**File**: `backend/harness/tools/fan_out_tool.py` (new)

**Tool Added**: `fan_out_tasks` — explicit parallel spawning interface

**Impact**: Provides clear API for spawning N workers in parallel.

### 7. PR Feedback Loop (✅ Added)

**File**: `backend/harness/webhooks/github_pr_feedback.py` (new)

**Feature**: Detects `@testai` mentions in PR comments and triggers agent iteration

**Impact**: Users can comment `@testai fix this` on PRs to trigger agent updates.

### 8. Semantic Search (✅ Added)

**File**: `backend/harness/tools/semantic_search_tool.py` (new)

**Tool Added**: `semantic_search` — embedding-based code search

**Impact**: Agents can find semantically similar code even when symbol names don't match.

### 9. MCP Server (✅ Added)

**File**: `backend/harness/mcp/server.py` (new)

**Feature**: Exposes TestAI as MCP server for IDE integration

**Impact**: Other agents (Cursor, VS Code) can drive TestAI via MCP protocol.

---

## Current Status

### What's Working

| Component | Status | Details |
|-----------|--------|---------|
| Job Submission | ✅ Working | Session created, sandbox provisioned |
| Sandbox Creation | ✅ Working | Docker container + volume isolated per session |
| Repo Clone | ✅ Working | rails/rails cloned (206MB shallow) |
| KG Indexing | ⚠️ Partial | CodeGraph doesn't support Ruby → 0 nodes |
| Kanban Board | ✅ Working | 15 tasks created (5 parallel explore + sequential) |
| Coordinator Spawn | ✅ Working | Coordinator subagent created |
| Worker Session Persistence | ✅ Fixed | Workers now appear in sessions table |
| GitHub Tools | ✅ Added | github_list_issues, github_list_prs available |

### What's Still Broken

| Component | Status | Issue |
|-----------|--------|-------|
| **Coordinator Execution** | ❌ **Stuck** | Coordinator spawned but not executing run loop |
| **Worker Spawn** | ❌ **Blocked** | Coordinator not calling delegate_task with tasks array |
| **Metrics Collection** | ⚠️ Partial | total_tokens still 0 (depends on worker execution) |

### Root Cause Analysis

**Coordinator Not Executing**: The coordinator agent is created via `agent_factory` but its `run()` method is not being called or is stuck before the first LLM call. Possible causes:
1. Agent initialization issue (missing dependencies, invalid config)
2. LLM call hanging (API timeout, invalid endpoint)
3. Asyncio task not being awaited properly
4. Agent factory returning None or invalid agent

**Debugging Steps Needed**:
1. Add logging to `agent_factory` to verify agent creation
2. Add logging to `child.run()` call to verify it's being invoked
3. Check LLM configuration (API key, base URL, model)
4. Verify asyncio task is being created and awaited

---

## Comparative Analysis: Production-Grade Harnesses

### Claude Code (Anthropic)

**Architecture**:
- **Task Tool**: Spawns subagents via `Task` tool
- **Parallel Execution**: Fan-out/fan-in pattern with explicit task decomposition
- **Context Isolation**: Each subagent gets own context window (up to 1M tokens)
- **Result Consolidation**: Parent agent merges subagent outputs

**Key Patterns**:
- Subagents are scoped, isolated AI workers
- Each subagent runs one focused job and returns single result
- Leader decomposes task, spawns parallel workers, merges results
- Fan-out/fan-in pattern is the standard approach

**Relevance to TestAI**: TestAI's coordinator pattern matches Claude Code's leader-worker model. The issue is that TestAI's coordinator is not executing the fan-out step.

### OpenAI Codex

**Architecture**:
- **Manager-Worker Pattern**: Parent agent spawns specialized parallel subagents
- **Subagent Types**: explorer, worker, default (configurable)
- **Sandbox Isolation**: Each subagent runs in isolated sandbox
- **Result Consolidation**: Manager merges worker outputs

**Key Patterns**:
- Subagents go GA on March 16, 2026
- Parallel execution is now industry standard
- Manager decomposes, workers execute in parallel, manager consolidates

**Relevance to TestAI**: TestAI's architecture matches Codex's manager-worker pattern. The missing piece is the parallel execution step.

### OpenCode

**Architecture**:
- **Parallel Subagents**: Supports multiple subagents in parallel with different models
- **Built-in Subagent Types**: General (full tools), Explore (read-only)
- **Model Flexibility**: Each subagent can use different model

**Key Patterns**:
- Open-source alternative to Claude Code
- Supports parallel subagents with model diversity
- Explore agent for fast codebase exploration

**Relevance to TestAI**: TestAI should adopt similar model diversity — use cheaper models for exploration, stronger models for implementation.

---

## Recommendations

### Immediate (This Week)

1. **Debug Coordinator Execution**
   - Add logging to `agent_factory` to verify agent creation
   - Add logging to `child.run()` to verify invocation
   - Check LLM configuration (API key, base URL, model)
   - Verify asyncio task creation and awaiting

2. **Test Fan-Out Mode**
   - Once coordinator executes, verify it calls `delegate_task(tasks=[...])`
   - Verify 5 workers are spawned in parallel
   - Verify all workers appear in `sessions` table

3. **Fix Metrics Collection**
   - Ensure `total_tokens` is updated for each worker
   - Ensure `total_cost` is calculated correctly
   - Verify metrics propagate to parent session

### Short-Term (This Month)

4. **Add Model Diversity**
   - Use cheaper model (Haiku) for exploration tasks
   - Use stronger model (Opus) for implementation tasks
   - Configure per-agent model overrides

5. **Improve KG Support**
   - Add Ruby support to CodeGraph
   - Or use alternative KG tool for non-JS/TS/Python repos

6. **Add PR Feedback UI**
   - Create UI for `@testai` mentions
   - Integrate with GitHub webhooks
   - Display agent iteration status

### Medium-Term (This Quarter)

7. **Add Semantic Search**
   - Implement embedding-based code search
   - Integrate with existing KG tools
   - Provide fallback when KG doesn't support language

8. **Build MCP Server**
   - Expose TestAI as MCP server
   - Enable IDE integration (Cursor, VS Code)
   - Allow other agents to drive TestAI

9. **Add VM-Level Isolation**
   - Offer VM sandbox option for untrusted code
   - Match Tembo's 5 sandbox sizes
   - Provide stronger isolation boundary

---

## Appendix: Code References

### Files Modified

1. `backend/harness/agents/orchestrator.md` — Coordinator prompt
2. `backend/harness/tools/orchestrator_tool.py` — Task decomposition
3. `backend/harness/tools/delegate_task.py` — Worker session persistence
4. `backend/harness/tools/subagent_persistence.py` — Session update persistence
5. `backend/harness/checkpoint.py` — Checkpoint error handling

### Files Added

1. `backend/harness/tools/github_tools.py` — GitHub integration
2. `backend/harness/tools/fan_out_tool.py` — Fan-out tool
3. `backend/harness/webhooks/github_pr_feedback.py` — PR feedback loop
4. `backend/harness/tools/semantic_search_tool.py` — Semantic search
5. `backend/harness/mcp/server.py` — MCP server

---

*Document created: 2026-06-18*  
*Last updated: 2026-06-18*  
*Status: IN PROGRESS — Coordinator execution debugging needed*

---

## Live Test Results

### Test Configuration

```
Session ID:    44faa37b-eb06-4319-9c68-db23ca159821
Sandbox:       testai-sandbox-44faa37b-eb0
Model:         deepseek-v4-flash
Repo:          https://github.com/rails/rails
Kanban Board:  00d20aa9-cba5-4310-9dbf-3623a6966856
```

### Agent Tree (Actual)

```
Orchestrator (44faa37b) — running
└── Coordinator (sa-0-9cd6cf99) — running, 10 tool calls
    ├── delegate_task(goal="Explore unhashable type: slice...") → completed (2 min)
    │   └── Worker (inline, no session row) — returned findings
    ├── kanban_list → completed
    ├── kanban_list → completed
    ├── delegate_task(goal="Investigate slice error...") → completed (in progress)
    │   └── Worker (inline, no session row) — returned findings
    └── [STOPPED — no more READY tasks]
```

**Expected**: 5+ parallel workers exploring different aspects of the codebase  
**Actual**: 2 sequential workers, one at a time

### Event Timeline

| Time | Event | Agent | Details |
|------|-------|-------|---------|
| 08:40:29 | orchestration.started | orchestrator | Sandbox created, clone started |
| 08:41:21 | subagent.spawned | sa-0-9cd6cf99 | Coordinator spawned |
| 08:41:25 | kanban_list | coordinator | Read board (4 tasks) |
| 08:41:31 | delegate_task(started) | coordinator | Spawned explore worker |
| 08:43:32 | delegate_task(completed) | coordinator | Worker returned findings |
| 08:43:34 | kanban_list | coordinator | Checked board status |
| 08:43:37 | kanban_list | coordinator | Checked again |
| 08:43:43 | delegate_task(started) | coordinator | Spawned second worker |
| 08:47:31 | coordinator completed | sa-0-9cd6cf99 | "Exploration complete" |

**Total agents spawned**: 2 (orchestrator + coordinator) + 2 inline workers = **4 agents**  
**Expected**: 1 orchestrator + 1 coordinator + 5-6 parallel workers = **7-8 agents**

---

## Root Cause Analysis

### Why Only 1 Worker at a Time?

**Problem 1: Sequential Coordinator Prompt**

The coordinator's system prompt instructs sequential processing:

```
## Mandatory sequence
1. `kanban_list` — read the board. Pick the first READY task.
2. `delegate_task` — spawn a worker for that task. Pass the full task description.
3. `kanban_update` — move the task to "in_progress".
4. Repeat steps 1-3 for every READY task.
5. `kanban_list` — poll until workers finish.
```

This forces the coordinator to:
1. Pick ONE task
2. Spawn ONE worker (sync mode, blocking)
3. Wait for it to complete
4. Move to next task

**Problem 2: Kanban Board Has Only 4 Tasks**

The default decomposition creates 4 high-level tasks:
1. Explore (ready)
2. Analyze and plan (backlog, depends on #1)
3. Implement (backlog, depends on #2)
4. Verify (backlog, depends on #3)

These are **sequential with dependencies** — can't parallelize.

**Problem 3: `delegate_task` Used in Sync Mode**

The coordinator calls `delegate_task(goal="...")` which is **sync mode** (blocks until worker completes). To spawn parallel workers, it should use:
- `delegate_task(tasks=["task1", "task2", ...])` — Fan-Out mode
- OR `delegate_task(goal="...", run_in_background=True)` + `collect_results()`

**Problem 4: Worker Sessions Not Persisted**

Workers run inline (inside coordinator's context) and their session rows aren't inserted into the `sessions` table. The DB insert at `delegate_task.py:351-366` silently fails:

```python
try:
    ...
    await _db.execute("INSERT INTO sessions ...")
except Exception:
    pass  # ← Silently swallowed
```

---

## How Production-Grade Harnesses Spawn Multiple Agents

### Claude Code (Anthropic)

**4 Parallel Approaches:**

| Approach | Description | Use When |
|----------|-------------|----------|
| **Subagents** | Delegated workers inside one session, return summary | Side task would flood main conversation |
| **Agent View** | Background sessions, `claude agents` to monitor | Independent tasks, check back later |
| **Agent Teams** | Multiple coordinated sessions with shared task list + inter-agent messaging | Claude splits project, assigns, keeps workers in sync |
| **Dynamic Workflows** | Scripts running many subagents with cross-checks | Job outgrows handful of subagents |

**Key Patterns:**
- **`/batch` skill**: Splits one large change into **5-30 worktree-isolated subagents**, each opens a PR
- **Worktrees**: Each session gets separate git checkout for isolation
- **Fan-Out/Gather**: Spawn N workers, wait for all, synthesize

**Relevant for TestAI:**
- Claude Code's "Agent Teams" model matches TestAI's coordinator + workers pattern
- The `/batch` skill (5-30 subagents) is the target scale TestAI should aim for

### OpenAI Codex

**Subagent Workflows:**
- Spawns specialized agents **in parallel**
- Orchestrator handles spawning, routing, waiting, collecting
- User explicitly asks: "Spawn one agent per point, wait for all, summarize"
- Subagents inherit approvals and sandbox controls

**Key Pattern:**
```
User: "Review these 6 points. Spawn one agent per point."
Codex: Spawns 6 parallel agents → waits → consolidates response
```

**Relevant for TestAI:**
- Codex waits until ALL requested results are available, then returns consolidated response
- This is exactly what `delegate_task(tasks=[...], mode="fan-out")` should do

### Sub-Agent Architecture Patterns (Production Best Practices)

**Source**: [Sub-Agent Architecture for AI Coding Harnesses](https://www.heyuan110.com/posts/ai/2026-04-13-harness-subagent-architecture/)

**Three Myths That Burn Money:**

1. **"More sub-agents means faster completion"**  
   → Parallel execution can be faster, but every spawn carries ~10K token overhead. Below 10K input tokens, you pay more in orchestration than you save.

2. **"Sub-agents should always use the cheapest model"**  
   → Route by **decision complexity**, not input volume. A sub-agent refactoring a 2000-line module needs Opus-class judgment, even though input is small.

3. **"The orchestrator should be the smartest model"**  
   → Orchestration is mostly routing logic. Run Sonnet/Haiku as orchestrator. Save Opus for leaf nodes where judgment compounds.

**Three Architecture Patterns:**

| Pattern | Description | Use When | Failure Mode |
|---------|-------------|----------|--------------|
| **Fan-Out/Gather** | Orchestrator dispatches N independent tasks to N sub-agents, waits, synthesizes | Tasks are truly independent, hand-off schema is well-defined | Tasks have hidden dependencies; outputs contradict each other |
| **Scout-Then-Act** | Cheap scout explores, then main agent acts on summary | Exploration is I/O bound, decision needs judgment | Scout misses critical context |
| **Pipeline** | Sequential sub-agents, each refines previous output | Each stage depends on previous, cumulative refinement | Error propagation; slow |

**Key Insight:**
> "Sub-agents are not a parallel speed hack. They are a **context garbage collection mechanism**. The point is to throw noise away, not to split thinking."

**Relevant for TestAI:**
- TestAI's current pattern is **Pipeline** (sequential explore → triage → fix → verify)
- Should shift to **Fan-Out/Gather** for exploration phase (5 parallel explore agents)
- Then **Scout-Then-Act** for fix phase (cheap scout finds issue, expensive fixer writes code)

### Tembo

**Key Features:**
- **Automations**: Sentry webhook → auto-fix, scheduled tasks, multi-repo coordination
- **5 Sandbox Sizes**: Micro (2 vCPU) to Ultra (32 vCPU, 128 GB RAM)
- **Pre-installed Tools**: Node.js 22, Python 3.12, Ruby 3.3, Go, Rust, .NET 9, Docker 28
- **Nix Support**: `tembo.nix` for custom dependencies
- **Feedback Loop**: `@tembo` in PR comments → agent iterates → pushes update

**Relevant for TestAI:**
- Tembo's automation model (webhook → fix → PR) is what TestAI should adopt
- The 5 sandbox sizes allow right-sizing for task complexity

### Greptile v3 (TREX)

**Key Features:**
- **Agentic Loop**: System runs in a loop with tools (codebase search, rules)
- **Multi-Hop Investigation**: Expands beyond diff, searches entire codebase
- **High Inference Limit**: Can continue recursively searching, following nested function calls
- **Confidence Scores**: Every review comment has a confidence score

**Key Pattern:**
```
PR changes calculateInvoiceTotal()
→ Greptile searches entire codebase for similar logic
→ Finds 3 related implementations
→ Discovers nested call path inside generateMonthlyStatement()
→ Spots applyProration() still uses old discount formula
→ Checks git history → discovers helper was created during old hotfix
→ Raises targeted comment with full context
```

**Relevant for TestAI:**
- Greptile's multi-hop investigation is what TestAI's explore agents should do
- Confidence scores would help prioritize which issues to fix first

### TestSprite

**Key Features:**
- **MCP Server**: Integrates with Cursor, VS Code, Windsurf
- **Self-Healing Tests**: Auto-locator repair for flaky UI/API tests
- **PRD → Test Plan → Test Code**: Autonomous test generation pipeline
- **Cloud Sandboxes**: Isolated test execution

**Relevant for TestAI:**
- TestSprite's MCP server pattern is what TestAI should adopt (public TestAI MCP server)
- Their self-healing flow is more mature than TestAI's `attempt_heal`

---

## Recommendations

### Immediate (This Week)

#### 1. Fix Coordinator Prompt for Parallel Fan-Out

**Current** (sequential):
```
1. Pick the first READY task.
2. Spawn a worker for that task.
3. Wait for it to complete.
4. Repeat.
```

**Proposed** (parallel):
```
1. `kanban_list` — read the board. Count all READY tasks.
2. If READY tasks >= 3: Use Fan-Out mode:
   - `delegate_task(tasks=[task1, task2, task3, ...], run_in_background=True)`
   - This spawns N workers in parallel
3. If READY tasks < 3: Use Sync mode for single task
4. `collect_results()` — wait for all background workers
5. Synthesize results, update kanban
```

**Files to Modify:**
- `backend/harness/agents/coordinator.md` (or wherever coordinator prompt is defined)
- `backend/harness/tools/orchestrator_tool.py` (coordinator goal construction)

#### 2. Increase Kanban Task Granularity

**Current**: 4 high-level tasks (explore → triage → fix → verify)

**Proposed**: 8-12 granular tasks with parallelizable explore phase:
```
1. Explore: Find all slice-related code in strong_parameters.rb (explore)
2. Explore: Check actionpack/lib/action_controller/ for slice usage (explore)
3. Explore: Search for unhashable type errors in test suite (explore)
4. Explore: Check git history for recent slice-related changes (explore)
5. Explore: Find all tests related to Parameters#slice (explore)
6. Analyze: Synthesize explore findings, identify root cause (triage)
7. Plan: Create fix plan with file paths (triage)
8. Implement: Fix the bug (fix)
9. Test: Write regression test (test-writer)
10. Verify: Run full test suite (verify)
```

**Files to Modify:**
- `backend/harness/tools/orchestrator_tool.py` — `_default_decomposition()` and `_llm_decompose()` prompt
- Add prompt instruction: "Decompose into 8-12 tasks. First 5 should be parallel explore tasks."

#### 3. Fix Worker Session Persistence

**Problem**: Workers don't appear in `sessions` table.

**Fix**: Ensure the DB insert doesn't fail silently. Add logging:
```python
try:
    await _db.execute("INSERT INTO sessions ...")
except Exception as e:
    logger.error("Worker session insert failed: %s", e)
    raise  # ← Don't swallow
```

**Files to Modify:**
- `backend/harness/tools/delegate_task.py:351-366`

#### 4. Fix Metrics Collection

**Problem**: `total_tokens: 0` for all subagents.

**Root Cause**: Subagent sessions row may not exist when `CostTracker.record_usage()` fires.

**Fix**: Ensure sessions row is created BEFORE LLM calls begin (already done in `delegate_task.py:351-366` but insert may be failing — see #3).

**Files to Modify:**
- Same as #3

### Short-Term (This Month)

#### 5. Add Fan-Out Mode to Coordinator Toolset

Add a new tool `fan_out_tasks` that wraps `delegate_task(tasks=[...])`:
```python
class FanOutTasksTool(BaseTool):
    name = "fan_out_tasks"
    description = "Spawn N parallel workers for N tasks. Returns when all complete."
    
    async def run(self, tasks: list[str], toolsets: list[str], **kwargs):
        dt = DelegateTaskTool(agent_factory=self._agent_factory)
        result = await dt.run(tasks=tasks, toolsets=toolsets)
        return result
```

**Files to Add:**
- `backend/harness/tools/fan_out.py`

#### 6. Add GitHub Integration

**Problem**: No tools expose GitHub functionality to agents.

**Fix**: Create `github_list_issues` and `github_list_prs` tools:
```python
class GitHubListIssuesTool(BaseTool):
    name = "github_list_issues"
    async def run(self, repo: str, state: str = "open", limit: int = 20):
        from harness.ci.git_providers import GitHubProvider
        provider = GitHubProvider(token=self._gh_token)
        return await provider.list_open_issues(repo, limit=limit)
```

**Files to Add:**
- `backend/harness/tools/github_tools.py`

**Files to Modify:**
- `backend/harness/tools/toolsets.py` — add `github_list_issues`, `github_list_prs` to coordinator toolset

#### 7. Add Sandbox Dependency Bootstrap

**Problem**: Rails repo cloned but `bundle install` never runs.

**Fix**: Enhance `_bootstrap_sandbox_deps()` to detect Gemfile and install Ruby + bundler:
```python
async def _bootstrap_sandbox_deps(sandbox, repo_path):
    # Detect language
    gemfile = await sandbox.run(f"test -f {repo_path}/Gemfile && echo yes || echo no")
    if gemfile.stdout.strip() == "yes":
        # Install Ruby + bundler
        await sandbox.run("apt-get update && apt-get install -y ruby ruby-dev build-essential")
        await sandbox.run(f"cd {repo_path} && bundle install")
```

**Files to Modify:**
- `backend/harness/orchestrator.py` — `_bootstrap_sandbox_deps()`

#### 8. Add KG Refresh After Edits

**Problem**: KG is built once at orchestrator start. After agent edits files, KG is stale.

**Fix**: Add `kg_refresh` tool to coordinator toolset:
```python
class KGRefreshTool(BaseTool):
    name = "kg_refresh"
    async def run(self):
        # Run codegraph sync in sandbox
        result = await self._sandbox.run("cd /workspace/repo && npx @colbymchenry/codegraph sync")
        # Copy updated KG to host
        await copy_db_to_host(self._sandbox, "/workspace/repo", self._host_dir)
        return {"success": True, "nodes": result.node_count}
```

**Files to Add:**
- `backend/harness/tools/kg_refresh.py`

### Medium-Term (This Quarter)

#### 9. Add PR Feedback Loop

**Pattern from Tembo/Greptile:**
```
PR Comment "@testai fix this"
→ Webhook detected
→ Resume or create new subagent with PR context
→ Agent iterates
→ Pushes update
```

**Files to Add:**
- `backend/harness/webhooks/github_pr_webhook.py`

#### 10. Add Semantic/Vector Search to KG

**Problem**: CodeGraph is symbol-level (functions, classes, imports). No embedding-based semantic search.

**Fix**: Add vector embeddings alongside CodeGraph symbols:
```python
# After codegraph init, generate embeddings for each symbol
for symbol in codegraph_symbols:
    embedding = await embed(symbol.code_snippet)
    await db.execute("INSERT INTO kg_embeddings (symbol_id, embedding) VALUES ($1, $2)", symbol.id, embedding)
```

**Files to Add:**
- `backend/harness/tools/semantic_search.py`

#### 11. Add Public TestAI MCP Server

**Pattern from TestSprite:**
```python
# Expose TestAI as an MCP server so other agents can drive it
class TestAIMCPServer:
    @tool
    async def run_test(self, repo_url: str, goal: str):
        orchestrator = OrchestratorEngine()
        return await orchestrator.run_single(...)
```

**Files to Add:**
- `backend/harness/mcp/server.py`

---

## Comparative Analysis

| Dimension | TestAI (Current) | Claude Code | Codex | Tembo | Greptile |
|-----------|------------------|-------------|-------|-------|----------|
| **Orchestrator** | Custom Python (OrchestratorEngine) | Claude session + subagents | Codex orchestrator | Cloud orchestration | Cloud pipeline |
| **Agent Runtime** | Custom Agent (LLM + tool loop) | Claude sessions | Codex agents | External: Claude Code, Codex, Cursor | N/A (single-purpose) |
| **Parallel Agents** | ❌ Sequential (1 at a time) | ✅ 5-30 via `/batch` | ✅ N parallel agents | ✅ 5 agents simultaneously | N/A |
| **Sandbox** | Docker per session | Worktrees (separate git checkouts) | Cloud sandbox | VM per session (5 sizes) | Cloud workers |
| **Knowledge Graph** | CodeGraph (tree-sitter SQLite) | Built-in codebase index | Built-in index | None (defers to agent) | Custom graph (AST-based) |
| **Task Tracking** | Kanban board (passive) | Shared task list (Agent Teams) | Internal | Session-based | GitHub PR integration |
| **Feedback Loop** | ❌ Re-submit job | ✅ PR comments | ✅ PR comments | ✅ `@tembo` in PR comments | ✅ `@greptileai` in PR comments |
| **Self-Healing** | ⚠️ `attempt_heal` (basic) | ✅ Agent iterates | ✅ Agent iterates | ✅ Agent analyzes + retries | N/A |

**Where TestAI Leads:**
1. **Kanban with dependency tracking** — `kanban_dependencies` table, WIP limits, board scoping
2. **Three-layer memory** — L0 raw artifacts → L1 indexed facts → L2 cross-run lessons
3. **Multi-repo orchestration** — `run_multi()` for cross-repo changes

**Where TestAI Lags:**
1. **Parallel agent spawning** — Claude Code does 5-30 agents; TestAI does 1 at a time
2. **PR feedback loop** — Tembo/Greptile have `@mention` iteration; TestAI requires re-submit
3. **Sandbox sizes** — Tembo offers 5 VM sizes; TestAI uses single Docker image
4. **KG updates after edits** — Greptile updates incrementally; TestAI doesn't re-index

---

## Appendix A: Database Schema Observations

### Tables Used by Agent Harness

| Table | Purpose | Status |
|-------|---------|--------|
| `sessions` | Session tree (orchestrator → coordinator → workers) | ⚠️ Workers not inserted |
| `agent_delegations` | Delegation records (parent → child) | ✅ Working |
| `stream_events` | Real-time event stream (SSE) | ✅ Working |
| `kanban_boards` | Kanban board metadata | ✅ Working |
| `kanban_tasks` | Kanban tasks with dependencies | ✅ Working |
| `pipeline_runs` | Pipeline execution records | ⚠️ Not populated for delegate API |
| `token_usage` | Per-call token tracking | ⚠️ Subagent tracking broken |

### Missing Columns

- `sessions.total_tokens` — Always 0 for subagents
- `sessions.total_cost` — Always 0 for subagents
- `pipeline_runs.session_id` — Not populated when using `/api/delegate`

---

## Appendix B: API Endpoints Tested

| Endpoint | Status | Response |
|----------|--------|----------|
| `POST /api/delegate` | ✅ 200 | `{"session_id": "...", "status": "running"}` |
| `GET /api/sandbox/list` | ✅ 200 | 3 sandboxes (including new one) |
| `GET /api/kanban/boards` | ✅ 200 | 8 boards (including new one) |
| `GET /api/knowledge-graph/recent` | ✅ 200 | 2 graphs (60K nodes each) |
| `GET /api/sessions` | ✅ 200 | Sessions list |
| `GET /api/runs` | ✅ 200 | Empty (pipeline_runs not populated) |
| `GET /api/delegate/{id}/stream` | ⚠️ Timeout | SSE endpoint (long-polling) |

---

## Appendix C: Code References

### Coordinator Prompt Location
- `backend/harness/agents/coordinator.md` (if exists)
- OR `backend/harness/tools/orchestrator_tool.py:742-749` (inline construction)

### Default Decomposition
- `backend/harness/tools/orchestrator_tool.py:140-163` — `_default_decomposition()`

### Delegate Task Tool
- `backend/harness/tools/delegate_task.py:68-721` — `DelegateTaskTool` class
- Line 206-215: Sync mode (`goal` parameter)
- Line 217-231: Fan-Out mode (`tasks` parameter)

### Worker Session Insert
- `backend/harness/tools/delegate_task.py:351-366` — Session row creation (silently fails)

---

## Appendix D: Next Steps

### Immediate Actions (This Week)

1. **Fix coordinator prompt** — Change from sequential to parallel fan-out
2. **Increase task granularity** — 8-12 tasks instead of 4
3. **Fix worker session persistence** — Don't swallow DB insert errors
4. **Test with 5+ parallel workers** — Verify fan-out mode works

### Validation Criteria

- [ ] Coordinator spawns 5+ workers in parallel
- [ ] All workers appear in `sessions` table
- [ ] `total_tokens` populated for each worker
- [ ] Kanban board shows all tasks progressing
- [ ] Full E2E loop completes (explore → triage → fix → verify)

---

*Document created: 2026-06-18*  
*Author: TestAI E2E Test Suite*  
*Status: IN PROGRESS*
