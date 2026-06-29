# E2E Assessment: TestAI Production Readiness

**Date:** 2026-06-10  
**Scope:** Full-stack audit of orchestrator, subagents, sandbox, knowledge graph, kanban, tools, MCP, skills, artifacts, metrics  
**Sample Repo:** `Ganeshkumar-1508/bank_poc_agentic_ai` (Django + CrewAI banking POC, 66 commits, ~45 MB)  
**Competitors Referenced:** Greptile, TestSprite, Tembo AI, Testim, OpenSWE, LangGraph

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [End-to-End Flow Trace](#2-end-to-end-flow-trace)
3. [Component Analysis](#3-component-analysis)
4. [Gap Analysis](#4-gap-analysis)
5. [Competitor Comparison](#5-competitor-comparison)
6. [Recommendations](#6-recommendations)
7. [Appendix: Sample Repo Analysis](#7-appendix-sample-repo-analysis)

---

## 1. Executive Summary

The TestAI architecture is **remarkably well-structured** — it has all the right building blocks in place: a three-tier agent registry, Swarm-topology task decomposition, kanban-driven execution, Docker sandboxing, CodeGraph-based knowledge graph, 60+ agent tools, MCP client/server, skill registry, cost tracking, quality scoring, and a typed event system. The code quality is high, with clear separation of concerns.

**However, several critical gaps exist** that prevent a fully autonomous end-to-end flow. The most significant:

| # | Gap | Severity | Status |
|---|-----|----------|--------|
| 1 | **KG is read-only** — agents cannot write facts/lessons back | HIGH | ✅ `kg_refresh`, `memory` tool with `search` + per-repo scope |
| 2 | **No GitHub Issues/PR ingestion** — system has no bridge to read issues, PRs, or webhooks | HIGH | ✅ Webhook → engine + discovery loop |
| 3 | **Sandbox reuse is fragile** — volume keys may collide | HIGH | ✅ Option C paths fixed |
| 4 | **No sandbox isolation between repos** — same session can share containers | MEDIUM | ✅ Context repos at `/workspace/context/` |
| 5 | **Artifact persistence is ad-hoc** — no structured artifact creation by agents | MEDIUM | ✅ `artifact_save`/`list`/`read` + auto-capture |
| 6 | **KG not rebuilt after fixes** — CodeGraph runs once at ANALYZE phase only | MEDIUM | ✅ `kg_refresh` tool |
| 7 | **No PR/Issue creation flow** — system can fix bugs but can't create PRs | MEDIUM | ✅ `commit_and_open_pr` + `open_pr_if_needed` middleware |
| 8 | **Kanban dispatcher runs on last board only** — no multi-board support | LOW | ✅ Removed (coordinator agent model) |
| 9 | **Triage is rule-based, not KG-aware** — triage doesn't use code graph | LOW | ✅ KG-aware triage with call chain + git history |
| 10 | **No user-configurable sandbox templates** — image, mounts, limits are hardcoded | LOW | ⬜ Open |
| 11 | **No tool search at runtime** — agents can't discover tools dynamically | LOW | ✅ Already implemented in `tool_search.py` |
| 12 | **No session persistence** — sandbox lost on backend restart | LOW | ✅ `_recover_containers()` scans Docker on startup |

---

## 2. End-to-End Flow Trace

### 2.1 Intended Flow (from plans + code)

```
User provides repo URL or asks to fix something
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 1: ENTER                                               │
│ OrchestratorEngine.run() → resolve repo, branch, SHA, auth   │
│ → Create sandbox → git clone --depth 1 → /workspace/repo    │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 2: ANALYZE                                             │
│ codegraph init → build .codegraph/codegraph.db via tree-sitter│
│ → copy_db_to_host() → agent_workspace/knowledge-graphs/     │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 3: SETUP (if new deps needed)                          │
│ → pip install, npm install, smoke test framework             │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 4: WORK                                                │
│ orchestrate tool → LLM decomposes goal → Swarm topology:     │
│   workers[parallel] → verifier → synthesizer                  │
│ → kanban board created with columns:                         │
│   backlog → ready → in_progress → review → done → blocked    │
│ → KanbanDispatcher background loop picks up tasks            │
│ → Spawns worker agents via agent_factory()                   │
│ → Workers call kg_search, kg_callers, bash, edit, write...   │
│ → Workers run tests, self-heal via attempt_heal              │
│ → Workers call kanban_complete or kanban_block               │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 5: REVIEW                                              │
│ ReviewAgent polls tasks in "review" column → LLM evaluates   │
│ → Approve (→ done) or Reject (→ in_progress with notes)     │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 6: PUBLISH (if code changes made)                      │
│ → Commit on branch → Push → Open PR with summary             │
└──────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ PHASE 7: PERSIST                                             │
│ → Save artifacts, L1 indexed facts, L2 curated lessons       │
│ → Update knowledge graph with new symbols/fixes              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 What Actually Exists in Code

| Phase | Status | Code Location | Notes |
|-------|--------|---------------|-------|
| PHASE 1: ENTER | ✅ Implemented | `stages/__init__.py:34-67` | Creates sandbox, clones repo. Auth/branch/SHA resolution is minimal. |
| PHASE 2: ANALYZE | ✅ Implemented | `codegraph.py:46-70` | Runs `codegraph init`, copies DB to host. No tech stack detection yet. |
| PHASE 3: SETUP | ⬜ Placeholder | Not in stages code | No dep installation phase visible in engine. Workers do this ad-hoc. |
| PHASE 4: WORK | ✅ Implemented | `orchestrator_tool.py`, `kanban/dispatcher.py` | Full Swarm topology + kanban dispatch + worker spawning |
| PHASE 5: REVIEW | ✅ Implemented | `kanban/dispatcher.py` `run_review_agent` | Review agent polls every 30s, LLM evaluates quality |
| PHASE 6: PUBLISH | ❌ Missing | Not implemented | No git commit/push/PR creation logic in engine |
| PHASE 7: PERSIST | ⬜ Partial | `codegraph.py:146-171` | KG DB copied to host. No structured artifact save, no lesson curation |

### 2.3 Critical Missing Pieces

**Missing: GitHub Issues/PR ingestion pipeline**
- The system has `pr_webhook.py` and `pr_manager.py` routers, but they are not wired into the orchestration engine
- No tool fetches issues from GitHub API
- No webhook-to-kanban bridge converts incoming PRs/issues into kanban tasks
- Result: the orchestrator can only act on an explicit `goal` string — it cannot autonomously discover work

**Missing: KG write-back**
- All 4 KG tools (`kg_search`, `kg_callers`, `kg_callees`, `kg_graph_status`) are read-only
- After fixing code, the KG becomes stale — new symbols, changed functions are not re-indexed
- No mechanism to store "lessons learned" (L2 curated knowledge) from one run to the next
- Result: each run is effectively amnesiac

**Missing: Artifact persistence API for agents**
- No agent tool to `artifact_save(path, description, tags)`
- Test results, coverage, config files are only on the Docker volume or in trace_events table
- No structured `artifacts` table insertion from agent tools

---

## 3. Component Analysis

### 3.1 Orchestrator Engine (`backend/harness/stages/__init__.py`)

**Strengths:**
- Clean single-responsibility: creates infra, delegates to kanban, polls for completion
- Multi-repo support via `run_multi()` with sequential execution
- Resume-abandoned logic for crash recovery
- Heartbeat notifications to prevent auto-reclaim

**Weaknesses:**
- No parallel multi-repo (sequential only)
- `_wait_for_board` polls every 15s — no event-driven notification
- Sandbox `volume_key=repo_url` — identical URL = same volume, cross-contamination risk
- No phase tracking model — the 7-phase pipeline is not actually modeled in the engine

### 3.2 Agent Registry & Dispatch (`backend/harness/agents/registry.py`, `backend/harness/dispatcher.py`)

**Strengths:**
- Three-tier dispatch: explicit @mention → keyword → LLM classifier
- Filesystem-first with DB mirror — works offline
- Clean `DelegationContext` dataclass replaces magic setattr patterns
- Cascading cancellation tree via `CancellationTree`

**Weaknesses:**
- Tier 2 LLM classifier falls back to Haiku — expensive for every dispatch
- No agent capability discovery at runtime (no "which agent can do X")
- Dispatch returns first match — no ranking by confidence
- Agent roles are resolved from keywords in goal text — brittle for complex goals

### 3.3 Subagent Delegation (`backend/harness/tools/delegate_task.py`)

**Strengths:**
- Three modes: Sync, Fan-Out, Background — covers all architectural patterns
- Depth cap at 5 prevents runaway delegation
- Budget enforcement at spawn time
- Exponential backoff with jitter (3 retries)
- Tool intersection model (child ∩ parent tools)
- MCP allow-list per subagent
- Fan-out streams results in completion order (not waiting for slowest)

**Weaknesses:**
- No tool conflict resolution when child requests tools parent doesn't have (silent intersection → confusing failures)
- No timeout per subagent task (only budget caps)
- Background mode has no completion callback — parent must poll `collect_results`

### 3.4 Kanban System (`backend/harness/kanban/`, `backend/api/routers/kanban.py`)

**Strengths:**
- 11 agent-facing tools for full lifecycle management
- DAG-aware task decomposition with topological sort
- Auto-decompose for triage tasks (Hermes-style)
- Automation rules engine (when-then rules)
- Review agent for quality gating
- Event log per task for audit trail

**Weaknesses:**
- `_active_board_id()` returns the **last created board** — multiple concurrent runs will collide
- No board lifecycle management: boards are never archived/closed
- Review agent is hardcoded to poll every 30s — not configurable
- No webhook notification when tasks complete
- Auto-decompose uses LLM but doesn't pass repo context

### 3.5 Sandbox System (`backend/harness/sandbox_manager.py`)

**Strengths:**
- Per-session Docker containers with `--cap-drop=ALL`, `--security-opt no-new-privileges`
- Deterministic subnets from SHA256(volume_key) for network isolation
- Worker and sidecar containers on bridge networks
- Named volumes (`testai-ws-*`) for persistence across container restarts
- Idle reaping via `reap_idle_containers()`

**Weaknesses:**

| Issue | Detail |
|-------|--------|
| **Volume key collision** | `volume_key=repo_url` means two runs on same repo share the volume |
| **No repo isolation** | Sandboxes are keyed by `session_id`, not by `repo_url` — same session = same sandbox |
| **Workspace path inconsistency** | `stages/__init__.py` uses `/workspace/repo`, KG tool uses `/workspace/{session_id[:12]}` — mismatch |
| **No resource quotas** | Default container has no CPU/mem limits (different from `sandbox.toml` which sets 512m/1.0) |
| **Host filesystem access** | No bind mounts for artifacts — everything lives on Docker volume, hard to access from host |
| **No dependency caching** | Each new sandbox starts from scratch — `pip install` runs every time |
| **Container prefix collision** | `testai-sandbox-{session_id[:12]}` — session_id is UUID, 12-char prefix has collision risk |
| **No init process** | `sleep infinity` as container CMD — no proper init (zombie reaping), though `--init` flag helps |

### 3.6 Knowledge Graph (`backend/harness/codegraph.py`, `backend/harness/tools/knowledge_graph_tool.py`)

**Strengths:**
- CodeGraph CLI provides production-quality tree-sitter AST parsing across 20+ languages
- 4 agent tools for querying the graph
- SQLite-based — fast, no external dependencies
- `copy_db_to_host()` makes graph available to API server for dashboard

**Weaknesses:**

| Issue | Detail |
|-------|--------|
| **Read-only** | No agent tool writes to KG |
| **One-time index** | Built once at ANALYZE phase, never refreshed |
| **Re-indexing is expensive** | `codegraph init` on a 45MB repo takes 60-180s |
| **No incremental updates** | After fixing code, changed symbols are not updated in graph |
| **No semantic layer** | L0 = raw artifacts, L1 = indexed facts, L2 = curated lessons — none are implemented |
| **No memory tool integration** | The `memory_tool.py` exists but is not connected to KG |
| **API reads host copy** | `knowledge_graph_api.py` reads from `agent_workspace/knowledge-graphs/` — stale if sandbox has newer copy |

### 3.7 Tools System (`backend/harness/tools/`)

**Inventory: 60+ tool files**

| Category | Count | Key Tools |
|----------|-------|-----------|
| Filesystem | 5 | read, write, edit, glob, grep |
| Code Intelligence | 5 | ast_grep, code_search, dependency_graph, lsp, kg_* |
| Orchestration | 8 | delegate_task, orchestrate, collect_results, cancellation |
| Kanban | 11 | kanban_show, complete, block, heartbeat, etc. |
| MCP/Skills | 4 | skill_tools, skills_guard, schema_sanitizer |
| Web | 3 | web_fetch, web_search, tool_search |
| Security | 3 | credential_scanner, path_security, osv_check |
| Quality | 3 | self_healing_tool, error_classifier, fuzzy_match |
| Memory | 4 | memory_tool, file_state, tool_result_storage, todo_store |
| Budget | 4 | budget, budget_config, circuit_breaker, retry_utils |
| Specialized | 6 | browser, computer_use, vision_analyze, diagram, database_query, image_generate |
| Runner | 1 | docker_executor (100+ languages) |

**Strengths:**
- `ToolRegistry` is a thread-safe singleton with caching, discovery, and output limiting
- Check-fn gating (binary exists, env var set) for conditional availability
- Toolset system allows composing tools by mode (auto, debug, explore, review, etc.)
- Dynamic schema overrides for context-dependent parameters
- Output size limiting with spill storage

**Weaknesses:**
- No tool versioning — tools evolve without backward compat guarantees
- No tool dependency graph — tools can't declare "I need tool X to be available"
- Agent-facing tool docs are minimal — descriptions are single-line

### 3.8 MCP System (`backend/harness/mcp/`)

**Strengths:**
- Full MCP client with 3 transport modes (SSE, Streamable HTTP, Stdio)
- Circuit breaker pattern (5 consecutive errors → 60s cooldown)
- OAuth 2.1 with PKCE for protected MCP servers
- TestAI can act as both MCP client (calls external) and MCP server (exposes self)
- Tool caching with configurable TTL
- Parallel tool calls per-server opt-in
- Credential sanitization in error messages

**Weaknesses:**
- No MCP server health dashboard — admins can't see which servers are connected
- No timeout per MCP tool call (only overall connection timeout)
- No retry for transient MCP failures (circuit breaker is binary: open/closed)
- MCP servers registered before LLM context — no lazy-loading

### 3.9 Metrics & Observability

**Strengths:**
- `CostTracker` with 3-tier pricing resolution (MCP → DB → fallback)
- `QualityScore` engine with 5 weighted components
- Typed `StreamEvent` hierarchy for bus-based observability
- Budget enforcement: soft warning at 80%, hard cap at 100%
- Budget auto-throttle ladder (4 steps: HITL → sequential → cheaper model → pause)

**Weaknesses:**
- No real-time dashboard for active runs (SSE events exist but no frontend consumer)
- No per-repo metrics aggregation
- No flaky test trend analysis over time
- No cost breakdown by kanban task — only by session

---

## 4. Gap Analysis

### 4.1 Critical Gaps (Block E2E Flow)

#### GAP-1: No GitHub Issues/PR Ingestion
**Files affected:** Missing — would need new tool  
**Impact:** Orchestrator cannot autonomously discover work items. The system can only act on an explicit goal string passed via API.  
**Fix:** Create `gh_issues_list`, `gh_pr_list` tools in a new `github_tool.py`. Wire `pr_webhook.py` into `OrchestratorEngine`. Add an "ingest" step in the 7-phase pipeline that auto-creates kanban tasks from open issues.

#### GAP-2: Knowledge Graph is Read-Only
**Files affected:** `backend/harness/tools/knowledge_graph_tool.py`  
**Impact:** Agents cannot persist what they learned. No accumulation of facts, no cross-run memory.  
**Fix:** Add `kg_reindex(path)` and `kg_add_fact(subject, predicate, object)` tools. Wire `codegraph init` as a post-fix step. Create a `memory_tool.py` → KG bridge.

#### GAP-3: Sandbox Workspace Path Inconsistency (✅ FIXED)
**Files affected:** `knowledge_graph_tool.py:51-61`, `stages/__init__.py:39-100`  
**Fix applied:** Option C — namespaced paths. Primary at `/workspace/repo`, context repos at `/workspace/context/{name}`.  
- `_resolve_workspace_path()` defaults to `/workspace/repo`, accepts optional `repo` param for context repos  
- `run_single()` accepts `context_repos: list[dict]`, clones them read-only under `/workspace/context/`  
- `run_multi()` passes sibling repos as context repos automatically  
- All 4 KG tools (`kg_search`, `kg_callers`, `kg_callees`, `kg_graph_status`) gain optional `repo` field

#### GAP-4: No PR Creation / Git Push
**Files affected:** New `commit_and_open_pr` tool + `kanban/dispatcher.py`  
**Fix (planned):** Option A — OpenSWE pattern.
- `commit_and_open_pr` tool: agent-callable, runs `git add` + `git commit` + `gh pr create --draft` inside sandbox
- `open_pr_if_needed` middleware: hooks into kanban dispatcher after a worker completes. If files changed but no PR was created, creates one automatically
- `GH_TOKEN` injected into sandbox at creation time from `integration_configs` (GitHub PAT configured via UI at Settings → Integrations → GitHub)

### 4.2 Medium Gaps (Degrade E2E Quality)

#### GAP-5: No Dependency Installation Phase
**Files affected:** `stages/__init__.py` (missing setup phase)  
**Impact:** Each kanban worker must independently install deps. Redundant work, no shared dep cache.  
**Fix:** Add SETUP phase in `OrchestratorEngine.run_single()` that runs dep installation once.

#### GAP-6: Kanban Board Collision on Last-Board-Only
**Files affected:** `kanban/dispatcher.py:145`  
**Impact:** Multi-run environments will have kanban dispatchers fighting over the last board.  
**Fix:** Make dispatcher board-aware — pass `board_id` explicitly, support multiple active boards.

#### GAP-7: No Artifact Save Tool
**Files affected:** Missing agent tool  
**Impact:** Test outputs, coverage reports, config files have no structured persistence path.  
**Fix:** Add `artifact_save(path, description, tags)` tool that copies file from sandbox to host and inserts into `artifacts` table.

#### GAP-8: Stale KG After Fixes
**Files affected:** `codegraph.py`  
**Impact:** After code changes, the symbol graph doesn't reflect reality. Next agent querying KG gets stale results.  
**Fix:** Add `kg_refresh` step after each kanban task that modified files. Or run `codegraph init` incrementally.

### 4.3 Minor Gaps (Polish)

#### GAP-9: Triage Not KG-Aware (✅ FIXED)
`triage.py` now accepts an optional `sandbox_env` parameter. When a sandbox with KG is available, triage runs 3-phase KG analysis:
1. **Symbol search** — finds source files related to each failing test
2. **Call chain trace** — traces callers to identify impact beyond the test
3. **Git history** — checks `git log` for recent changes to source files
KG data is used to escalate severity (recent changes → likely regression), assign owner (source file path patterns), and enrich fix suggestions with file paths and call chains. Falls back to rule-based when no KG available.

#### GAP-10: No User-Configurable Sandbox
`sandbox.toml` and `SandboxScope` exist but are not exposed to users. Image, mounts, memory, cpu are hardcoded in `sandbox_manager.py`.

#### GAP-11: No Tool Search at Runtime
The `tool_search` tool exists in the tool list but is not wired into mode configurations. Agents can't discover available tools dynamically.

#### GAP-12: No Session Persistence for Sandboxes
When the backend restarts, in-memory sandbox sessions are lost. Running containers become orphaned (though `atexit` + `reap_idle` provide partial cleanup).

---

## 5. Competitor Comparison

### 5.1 Greptile
**Focus:** AI code review — PR-level code analysis  
**Architecture:** Graph index → swarm of agents → PR comments  
**Key strengths we should borrow:**
- **3-step process:** Index → Swarm review → Learns from human feedback — elegant and minimal
- **"Learns your codebase over time"** — reads other engineers' comments to understand coding standards
- **Impact analysis** — agents assess impact beyond the diff, not just changed lines
- **Graph-first** — constructs a graph index BEFORE analysis (same approach as our CodeGraph)

**What we do better:**
- End-to-end automation (fix + test + PR) vs Greptile's review-only
- Multi-agent orchestration (subagents, delegation, kanban)
- Richer tool ecosystem (60+ tools vs Greptile's specialized review tools)

### 5.2 TestSprite
**Focus:** Autonomous testing agent — generates and runs Playwright/Cypress tests from URL + PRD  
**Architecture:** MCP integration → agent crawls app → generates tests → runs → debugs → reports  
**Key strengths we should borrow:**
- **MCP as the primary integration point** — connects to Claude Code, Cursor, VS Code via MCP
- **PRD-to-test pipeline** — accepts product requirements documents and generates test plans
- **Visual test editing** — human-in-the-loop for generated tests
- **Test code output is standard Playwright/Cypress** — not proprietary format — users can edit

**What we do better:**
- Full code fixing capability, not just testing
- Multi-repo orchestration
- Self-healing and retry logic
- Cost budgeting and enforcement

### 5.3 Tembo AI
**Focus:** Agentic testing for data pipelines and databases  
**Note:** Limited public documentation found. Appears focused on production data validation.

### 5.4 Testim (Tricentis)
**Focus:** AI-powered test automation for Salesforce, web, mobile  
**Architecture:** AI locators + self-healing tests + quality intelligence  
**Key strengths:**
- **Self-healing locators** — AI/ML learns your app and fixes broken element selectors automatically
- **Quality intelligence** — connects with SeaLights to test what matters most based on code changes
- **Codeless test creation** — natural language → agent workers build tests

**What we do better:**
- Full open-source flexibility
- Multi-agent orchestration with subagents
- Code intelligence via CodeGraph

### 5.5 OpenSWE (LangChain)
**Focus:** SWE-bench automated bug fixing  
**Architecture:** Orchestrator → subagents → isolated sandboxes  
**Key strengths we should borrow:**
- **Per-subagent sandbox isolation** — every subagent gets its own dedicated sandbox instance
- **Isolated git auth** — proxy authentication per sandbox
- **Multiple sandbox providers** — LangSmith, Modal, Daytona, Runloop
- **Separate repo clone per subagent** — no filesystem sharing

**What we do better:**
- Kanban workflow management
- Self-healing and retry with exponential backoff
- Cost tracking and budget enforcement
- MCP integration (OpenSWE doesn't support MCP natively)

### 5.6 LangGraph (LangChain)
**Focus:** Multi-agent orchestration framework  
**Key strengths:**
- **State machine model** — nodes + edges with explicit state management
- **Graph persistence** — save/load agent state at any point
- **Human-in-the-loop** — built-in interrupt/resume patterns
- **Streaming** — first-class streaming support for agent output

**What we do better:**
- Kanban-driven workflow is more accessible than LangGraph's state graphs
- Tools system is richer and more flexible
- MCP client/server gives us protocol-level interoperability LangGraph lacks

---

## 6. Recommendations

### 6.1 Immediate (Must Fix for E2E)

| Priority | Item | Effort | Files |
|----------|------|--------|-------|
| P0 | ✅ Unify workspace path — Option C implemented | Done | `knowledge_graph_tool.py`, `stages/__init__.py` |
| P0 | ✅ Webhook → OrchestratorEngine | Done | `pr_webhook.py`, `main.py` |
| P0 | ✅ Workspace path — Option C | Done | `knowledge_graph_tool.py`, `stages/__init__.py` |
| P0 | ✅ `commit_and_open_pr` tool + `open_pr_if_needed` middleware | Done | New tool + kanban dispatcher hook |
| P0 | ✅ GitHub PAT UI (Settings → Integrations → GitHub) | Done | `IntegrationSettings.tsx` |
| P0 | ✅ `GH_TOKEN` injection into sandbox at creation | Done | `stages/__init__.py:77-91` |
| P0 | ✅ Parallel Explore agents before decomposition | Done | `orchestrator_tool.py:_explore_codebase()` |
| P0 | ✅ Artifact persistence system | Done | `tools/artifact_tools.py` + `kanban/dispatcher.py:_capture_artifacts()` |

### 6.2 Short Term (Next Sprint)

| Priority | Item | Effort | Files |
|----------|------|--------|-------|
| P1 | Add `artifact_save` agent tool | 1 day | New tool registration |
| P1 | Make sandbox image/resource configurable per user | 2 days | `SandboxScope` + API endpoint |
| P1 | Add SETUP phase (shared dep installation) | 1 day | `stages/__init__.py` |
| P1 | Board-aware dispatcher (multi-board support) | 3 days | `kanban/dispatcher.py` |
| P1 | Memory tool → KG bridge (L1/L2 facts) | 3 days | `memory_tool.py` + new table |

### 6.3 Medium Term

| Priority | Item | Effort |
|----------|------|--------|
| P2 | Per-subagent sandbox isolation (OpenSWE model) | 5 days |
| P2 | Incremental KG updates (re-index only changed files) | 3 days |
| P2 | Real-time dashboard for active runs | 5 days |
| P2 | Dependency caching layer (pre-built Docker images) | 3 days |
| P2 | Tool versioning + dependency declaration | 3 days |
| P3 | Event-driven board completion (replace polling) | 2 days |
| P3 | KG-aware triage (impact analysis for test failures) | 3 days |
| P3 | Session persistence for sandboxes (survive backend restart) | 3 days |
| P3 | Agent capability discovery at runtime | 2 days |

### 6.3.5 Claude Code System Prompt Patterns Applied

The following patterns from `docs/claude-code-system-prompts/` have been adopted:

| Pattern | Source File | Applied In |
|---------|------------|------------|
| **Coordinator synthesis** — "Never delegate understanding." Orchestrator reads findings, synthesizes, produces precise file-aware task specs | `system-prompt-coordinator-mode-orchestration.md` | `orchestrator_tool.py:_llm_decompose()` |
| **Worker post-implementation checklist** — code review → tests → commit+PR → single-line report (`PR: <url>` or `PR: none — <reason>`) | `system-prompt-worker-instructions.md` | `kanban/dispatcher.py:_spawn_worker()` system prompt |
| **Explore subagent constraints** — strictly read-only, parallel tool calls, no file mutations, Haiku model, efficient search | `agent-prompt-explore.md` | `orchestrator_tool.py:_explore_codebase()` agent prompts |
| **Continue vs. spawn fresh** — reuse context when research found exact files; spawn fresh for verification or wrong-approach retries | `system-prompt-writing-subagent-prompts.md` | Worker lifecycle in kanban dispatcher |
| **Line-by-line code review** — read every hunk, read enclosing function, check for inverted conditions, off-by-one, null deref, missing await | `agent-prompt-code-review-part-1-base-finder-angles.md` | Worker post-implementation step |
| **Communication style** — brief state before first call, short updates at key moments, no narration, one/two sentence end-of-turn summary | `system-prompt-communication-style.md` | Agent response format guidance |
| **Fix the root cause, not the symptom** — workers directed toward durable fixes | `system-prompt-coordinator-mode-orchestration.md` | `kanban/dispatcher.py:234` |

### 6.3.6 Architecture Shift: Kanban as Observability (✅ DONE)

**What changed:**
- `stages/__init__.py`: `run_single()` no longer calls `orchestrate` tool → kanban board → dispatcher. Instead it runs explore agents for context, optionally creates a kanban board for visibility, then spawns ONE coordinator agent via `delegate_task`.
- The coordinator agent receives the goal, explore findings, and all tools. It uses `todo` for planning, `delegate_task` for subagents, `commit_and_open_pr` for PRs, and optionally `kanban_comment` for logging.
- Kanban is a **passive log** — it tracks what agents do but does NOT drive their behavior (mirrors Hermes' kanban model: multi-agent observability, not primary orchestration).
- Kanban dispatcher removed — its in-process worker spawning role is fully replaced by the coordinator agent's `delegate_task`. The kanban API (board/task CRUD) stays for human UI visibility.
- Added `todo_tool.py`: simple in-memory per-session todo list (Hermes + Claude Code pattern).

**Files changed:**
| File | Change |
|------|--------|
| `stages/__init__.py` | Replaced kanban-driven dispatch with coordinator agent spawn |
| `tools/todo_tool.py` | New — lightweight task tracking for coordinator agents |
| `main.py` | Removed `start_dispatcher()` — no longer needed |

### 6.4 Architecture Recommendations

1. **Move toward OpenSWE's per-subagent sandbox model** — each subagent gets its own Docker container with a fresh clone. This provides true isolation. The current shared-volume model is simpler but has isolation gaps.

2. **Adopt Greptile's learning loop** — after each PR/issue cycle, update the KG with lessons learned. Use a `lessons` table: `(repo_hash, pattern, recommendation, source_agent)`.

3. **Adopt OpenSWE's commit_and_open_pr pattern** — single tool for git commit + `gh pr create --draft`. `open_pr_if_needed` middleware as safety net. `GH_TOKEN` injected into sandbox from `integration_configs` (PAT configured via UI). No external API calls from orchestrator — all git operations run inside the sandbox.

4. **Adopt TestSprite's MCP-first integration** — expose TestAI's full capability as MCP tools so it can be used from any IDE/agent. Currently only partial MCP server exists (`server_mcp.py`).

5. **Implement LangGraph-style state graphs** for complex multi-step workflows — the kanban model works for tree topologies but struggles with cyclic or conditional workflows.

6. **Final: Option C paths + Option A (no context KG)** — Primary repo at `/workspace/repo`, context repos at `/workspace/context/{name}` with raw file access only. Context repos are NOT KG-indexed — agents use grep/read/glob to explore them. Already implemented:
   - `knowledge_graph_tool.py`: Defaults to `/workspace/repo`, accepts optional `repo` param for context repos
   - `stages/__init__.py`: `run_single()` accepts `context_repos: list[dict]`, clones them read-only under `/workspace/context/`
   - `run_multi()` passes sibling repos as context repos automatically
   - Agents query primary KG by default, or pass `repo="repo-name"` for grep/read/glob access to a context repo

---

## 7. Appendix: Sample Repo Analysis

### `Ganeshkumar-1508/bank_poc_agentic_ai`

| Property | Value |
|----------|-------|
| Language | Python 52%, HTML 24% |
| Framework | Django 6.0.4 + CrewAI 1.9.1 |
| DB | SQLite (dev), Neo4j (graph), ChromaDB (vectors) |
| ML | XGBoost, LightGBM, CatBoost, scikit-learn |
| Tests | 17 test files (unit + integration + healthcheck) |
| Open Issues | 0 |
| Open PRs | 0 |
| Commits | 66 |
| Size | ~45 MB |

### Test Execution
- Framework: `pytest`
- Command: `python -m pytest -v unit_testing/`
- Test files: `unit_testing/` (7 files) + `Test/` (8 files)
- Key test areas: AML scoring, credit risk, FD advisor, smart assistant, RAG integration

### Potential Fixes (for demo purposes)
Since there are no open issues, a synthetic demo could:
1. **Purpose: Test the E2E flow** — Inject a known bug (e.g., break a test assertion), let the system detect, diagnose via KG, fix, and verify
2. **Real improvement** — Add test coverage for the largest untested modules (crew_api_views.py at 42KB has no dedicated test file)
3. **Dependency upgrade** — Update `crewai` from 1.9.1 to latest, fix any breaking changes
