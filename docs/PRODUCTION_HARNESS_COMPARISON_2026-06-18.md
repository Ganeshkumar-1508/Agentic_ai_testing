# Production-Grade Agent Harness Comparison

**Date**: 2026-06-18  
**Purpose**: Compare TestAI's agent harness with production-grade implementations from Claude Code, Codex, Devin, and Tembo

---

## Executive Summary

TestAI's agent harness is **functionally equivalent** to production harnesses in core capabilities but **lags in polish and reliability**. The recent fixes have brought parallel agent spawning to parity with industry standards, but several gaps remain.

---

## Parallel Agent Spawning: Feature Comparison

### Claude Code (Anthropic)

**Architecture**:
- **4 Parallelization Modes**:
  1. **Subagents** — Delegated workers inside one session, return summary
  2. **Agent View** — Background sessions, monitor via `claude agents`
  3. **Agent Teams** — Multiple coordinated sessions with shared task list (experimental)
  4. **Dynamic Workflows** — Script-driven multi-agent orchestration

**Key Features**:
- **Worktree Isolation**: Each agent gets separate git checkout to prevent conflicts
- **Foreground/Background Modes**: Agents can run inline or in background
- **Custom Subagent Profiles**: YAML-based agent definitions with tool restrictions
- **Nesting Control**: Configurable max nesting depth (default: 1 level)
- **Resume Capability**: Cancelled/failed agents can be resumed

**Spawning Mechanism**:
```yaml
# Agent spawns subagents via Task tool
Task(description="Explore auth module", subagent_type="explore")
```

**Result Collection**:
- Foreground: Parent waits for result
- Background: Parent notified on completion, reads result summary

### Codex (OpenAI)

**Architecture**:
- **Manager-Worker Pattern**: Parent agent spawns specialized workers
- **Config-Driven**: TOML-based agent definitions
- **Sandbox Isolation**: Each worker runs in isolated sandbox
- **Parallel Execution**: Workers run concurrently, results consolidated

**Key Features**:
- **Custom Agent Definitions**: TOML files with model overrides, tool restrictions
- **spawn_agents_on_csv**: Batch spawning from CSV task lists
- **Thread Management**: `/agent` command to switch between active threads
- **Approval Inheritance**: Workers inherit parent's tool permissions

**Spawning Mechanism**:
```toml
# codex.toml
[agents.explore]
model = "gpt-4-turbo"
tools = ["read", "grep", "glob"]
```

**Result Collection**:
- Parent waits for all workers to complete
- Consolidated response returned to user

### Devin (Cognition Labs)

**Architecture**:
- **Foreground/Background Modes**:
  - **Foreground**: Runs inline, parent waits
  - **Background**: Runs in parallel, parent notified on completion
- **Profile-Based Spawning**: `subagent_explore` (read-only) and `subagent_general` (full access)
- **Nesting Control**: Default max depth = 1, configurable via `max-nesting` field

**Key Features**:
- **Tool Permission Inheritance**: Background agents inherit parent's permissions
- **Resume Capability**: Cancelled/failed agents can be resumed
- **Custom Profiles**: YAML-based agent definitions with model overrides
- **Subagent Panel**: UI for monitoring active/completed agents

**Spawning Mechanism**:
```python
# Agent spawns subagent via run_subagent tool
run_subagent(profile="subagent_explore", task="Research auth module")
```

**Result Collection**:
- Foreground: Parent waits, reads full output
- Background: Parent notified, reads summary

### Tembo

**Architecture**:
- **Background Coding Agents**: Asynchronous execution in sandboxed environments
- **Parallel Execution**: Multiple agents work simultaneously
- **Cloud-Based**: Agents run in Tembo's cloud infrastructure

**Key Features**:
- **Sandbox Isolation**: Each agent runs in isolated container
- **Continuous Execution**: Agents run 24/7 without human intervention
- **PR-Based Workflow**: Agents open PRs for review
- **Multi-Repo Support**: Agents can work across multiple repositories

**Spawning Mechanism**:
- Tembo uses a different model — agents are spawned by the platform, not by other agents
- Users submit tasks via UI/API, platform spawns agents

### TestAI (Current Implementation)

**Architecture**:
- **Coordinator-Worker Pattern**: Coordinator spawns workers via `delegate_task`
- **Fan-Out Mode**: `delegate_task(tasks=[...], run_in_background=True)` spawns N workers
- **Background Execution**: Workers run as asyncio tasks
- **Result Collection**: `collect_results(subagent_ids=[...])` waits for workers

**Key Features**:
- **Parallel Execution**: Workers run concurrently
- **Session Persistence**: Workers appear in `sessions` table
- **Tool Isolation**: Workers get restricted toolsets
- **Kanban Integration**: Coordinator manages tasks via kanban board

**Spawning Mechanism**:
```python
# Coordinator spawns workers via delegate_task
delegate_task(tasks=["Task 1", "Task 2", ...], run_in_background=True)
```

**Result Collection**:
```python
# Coordinator collects results
collect_results(subagent_ids=["sa-bg-xxx", "sa-bg-yyy", ...])
```

---

## Gap Analysis: TestAI vs Production Harnesses

### ✅ Parity (TestAI matches production)

| Feature | Claude Code | Codex | Devin | TestAI |
|---------|-------------|-------|-------|--------|
| Parallel agent spawning | ✅ | ✅ | ✅ | ✅ |
| Background execution | ✅ | ✅ | ✅ | ✅ |
| Result collection | ✅ | ✅ | ✅ | ✅ |
| Tool isolation | ✅ | ✅ | ✅ | ✅ |
| Custom agent profiles | ✅ | ✅ | ✅ | ✅ |
| Nesting control | ✅ | ✅ | ✅ | ✅ |

### ⚠️ Gaps (TestAI lags behind)

| Feature | Claude Code | Codex | Devin | TestAI | Issue |
|---------|-------------|-------|-------|--------|-------|
| **Worktree isolation** | ✅ | ✅ | ✅ | ❌ | Workers share same filesystem, can conflict |
| **Foreground/Background switching** | ✅ | ❌ | ✅ | ❌ | Can't switch modes mid-execution |
| **Resume capability** | ✅ | ❌ | ✅ | ❌ | Can't resume failed workers |
| **UI monitoring** | ✅ | ✅ | ✅ | ⚠️ | Dashboard exists but limited |
| **Approval inheritance** | ✅ | ✅ | ✅ | ⚠️ | Partial — workers inherit parent permissions |
| **Nesting depth control** | ✅ | ✅ | ✅ | ⚠️ | Hardcoded to 5, not configurable |
| **Agent cancellation** | ✅ | ✅ | ✅ | ⚠️ | Cancellation exists but not exposed to UI |
| **Error recovery** | ✅ | ❌ | ✅ | ❌ | No automatic retry on worker failure |

### 🔴 Critical Missing Features

1. **Worktree Isolation**
   - **Problem**: Workers share the same filesystem. If two workers edit the same file, they can conflict.
   - **Production Solution**: Claude Code uses git worktrees — each agent gets a separate checkout.
   - **TestAI Impact**: High risk of merge conflicts in parallel execution.

2. **Resume Capability**
   - **Problem**: If a worker fails, it can't be resumed. Must restart from scratch.
   - **Production Solution**: Devin allows resuming cancelled/failed agents.
   - **TestAI Impact**: Wasted compute on failures.

3. **Error Recovery**
   - **Problem**: No automatic retry on worker failure.
   - **Production Solution**: Claude Code has built-in retry logic for transient failures.
   - **TestAI Impact**: Fragile execution — single failure can break entire workflow.

4. **Foreground/Background Switching**
   - **Problem**: Can't switch a worker from background to foreground mid-execution.
   - **Production Solution**: Claude Code and Devin allow switching via Ctrl+B.
   - **TestAI Impact**: Less flexibility for debugging.

---

## Architecture Comparison

### Claude Code: Subagent-First

```
User → Main Agent → Task Tool → Subagent (foreground/background)
                                    ↓
                              Tool Execution
                                    ↓
                              Return Result
```

**Strengths**:
- Simple mental model
- Clear separation of concerns
- Worktree isolation prevents conflicts

**Weaknesses**:
- No built-in orchestration (relies on LLM to coordinate)
- No kanban/task tracking

### Codex: Config-Driven

```
User → Main Agent → TOML Config → Worker Agents (parallel)
                                      ↓
                                Sandbox Execution
                                      ↓
                              Consolidated Response
```

**Strengths**:
- Explicit configuration
- Sandbox isolation
- Batch spawning support

**Weaknesses**:
- No dynamic orchestration
- No task tracking

### Devin: Profile-Based

```
User → Main Agent → run_subagent → Worker (foreground/background)
                                        ↓
                                  Tool Execution
                                        ↓
                              Return Result/Summary
```

**Strengths**:
- Profile-based spawning (explore vs general)
- Resume capability
- UI monitoring

**Weaknesses**:
- No worktree isolation
- Limited nesting control

### TestAI: Coordinator-Worker

```
User → Orchestrator → Coordinator → delegate_task → Workers (parallel)
                                                        ↓
                                                  Tool Execution
                                                        ↓
                                              collect_results → Consolidated Response
```

**Strengths**:
- Kanban integration for task tracking
- Database persistence for all agents
- Explicit result collection

**Weaknesses**:
- No worktree isolation
- No resume capability
- No error recovery
- Limited UI monitoring

---

## Recommendations

### Immediate (This Week)

1. **Add Worktree Isolation**
   - Create separate git worktrees for each worker
   - Workers edit in isolated checkouts
   - Coordinator merges changes after workers complete
   - **Effort**: 3-5 days
   - **Impact**: Eliminates merge conflicts

2. **Add Error Recovery**
   - Implement automatic retry for transient failures
   - Add circuit breaker for persistent failures
   - **Effort**: 2-3 days
   - **Impact**: Improves reliability

3. **Add Resume Capability**
   - Store worker state in database
   - Allow resuming failed workers from last checkpoint
   - **Effort**: 3-5 days
   - **Impact**: Reduces wasted compute

### Short-Term (This Month)

4. **Add Foreground/Background Switching**
   - Allow switching workers between modes mid-execution
   - Expose via API and UI
   - **Effort**: 2-3 days
   - **Impact**: Improves debugging flexibility

5. **Improve UI Monitoring**
   - Add real-time worker status to dashboard
   - Show tool calls, progress, errors
   - **Effort**: 3-5 days
   - **Impact**: Better observability

6. **Add Nesting Depth Control**
   - Make max nesting depth configurable per agent
   - Add to agent YAML definitions
   - **Effort**: 1 day
   - **Impact**: Prevents unbounded nesting

### Medium-Term (This Quarter)

7. **Add Agent Cancellation UI**
   - Expose cancellation via dashboard
   - Allow cancelling individual workers
   - **Effort**: 2-3 days
   - **Impact**: Better control

8. **Add Approval Inheritance**
   - Workers inherit parent's tool permissions
   - Background workers auto-deny unapproved tools
   - **Effort**: 2-3 days
   - **Impact**: Better security

9. **Add Dynamic Workflows**
   - Script-driven multi-agent orchestration
   - Support for complex workflows (audit, migration)
   - **Effort**: 5-7 days
   - **Impact**: Enables advanced use cases

---

## Conclusion

TestAI's agent harness is **functionally equivalent** to production harnesses in core capabilities (parallel spawning, background execution, result collection). However, it **lags in reliability and polish** (no worktree isolation, no resume capability, no error recovery).

The recent fixes have brought TestAI to **parity with production harnesses** in terms of parallel agent spawning. The remaining gaps are in **reliability features** that production harnesses have evolved over time.

**Priority**: Focus on worktree isolation and error recovery first — these are the most critical gaps that affect reliability in production use.

---

*Document created: 2026-06-18*  
*Author: TestAI E2E Test Suite*  
*Status: COMPLETE*
