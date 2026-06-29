# TestAI End-to-End Agentic Full Test — 2026-06-17

> **Goal:** Comprehensive verification of the full TestAI agentic loop on `https://github.com/rails/rails`.
> Validate: component sync, sandbox lifecycle, KG generation, tool/skill/plugin access, artifact persistence,
> metrics collection, user configuration, and cross-agent sandbox sharing.
>
> **Environment:**
> - Plan file: `plans/test_env.txt` (model = `deepseek-v4-flash`, base URL = `https://opencode.ai/zen/go/v1`)
> - Backend: `localhost:8001` (Docker, healthy)
> - Frontend: `localhost:3001` (Docker)
> - Postgres: `localhost:5432` (Docker)
> - Sandbox image: `nikolaik/python-nodejs:python3.11-nodejs20`
>
> **Methodology:** Component-by-component audit + live API calls + code reading + competitor research.
> Findings appended chronologically. Final section consolidates refinements + roadmap.

---

## Table of Contents

1. [Pre-flight Health Check](#1-pre-flight-health-check)
2. [Component Sync Audit](#2-component-sync-audit)
3. [Sandbox Lifecycle Test](#3-sandbox-lifecycle-test)
4. [Knowledge Graph Test](#4-knowledge-graph-test)
5. [Tool/Skill/Plugin/MCP Access Test](#5-toolskillpluginmcp-access-test)
6. [Artifact Persistence Test](#6-artifact-persistence-test)
7. [Metrics Collection Test](#7-metrics-collection-test)
8. [User Configuration Surface Test](#8-user-configuration-surface-test)
9. [Competitor Research](#9-competitor-research)
10. [Gap Analysis & Prioritized Roadmap](#10-gap-analysis--prioritized-roadmap)

---

## 1. Pre-flight Health Check

### 1.1 Container Status

| Component | Container | Status | Port |
|-----------|-----------|--------|------|
| PostgreSQL | `testai-db` | ✅ Healthy | 5432 |
| Backend (FastAPI) | `testai-backend` | ✅ Healthy (3h uptime) | 8001→8000 |
| Frontend (Next.js) | `testai-frontend` | ✅ Running (4h) | 3001→3000 |
| Sandbox 1 | `testai-sandbox-c3a05d3e-b0b` | ✅ Running (3h) | — |
| Sandbox 2 | `testai-sandbox-8c485370-45b` | ✅ Running (3h) | — |

### 1.2 API Health Endpoints

| Endpoint | Status | Response |
|----------|--------|----------|
| `GET /api/health` | ✅ 200 | `{"status":"ok"}` |
| `GET /api/tools` | ✅ 200 | 79+ tools |
| `GET /api/skills?limit=5` | ✅ 200 | 130+ skills |
| `GET /api/agents` | ✅ 200 | 76 agents (auto-discovered) |
| `GET /api/knowledge-graph/recent` | ✅ 200 | 2 graphs (60K nodes each) |
| `GET /api/kanban/boards` | ✅ 200 | 2 boards with tasks |
| `GET /api/sandbox/list` | ✅ 200 | 2 active sandboxes |
| `GET /api/tools/toolsets` | ✅ 200 | 16 toolsets |
| `GET /api/settings/mcp` | ✅ 200 | 1 MCP server configured |

### 1.3 System State Summary

```
Tools:       79+ registered
Skills:      130+ (128 user + 2 builtin)
Agents:      76 auto-discovered (26 custom + 50 built-in)
Toolsets:    16 curated (coordinator, bug-fixer, test-writer, etc.)
KG Graphs:   2 (60,479 nodes / 177,048 edges each)
Kanban:      2 boards with 4 tasks each (explore → triage → fix → verify)
Sandboxes:   2 active containers
```

---

## 2. Component Sync Audit

### 2.1 Toolset ↔ Agent Alignment

**Question:** Are the orchestrator and subagents using the same tools, skills, plugins, KG?

**Finding:** ✅ **YES — Toolsets are well-defined and aligned with agent roles.**

| Toolset | Tools | Used By |
|---------|-------|---------|
| `coordinator` | 22 tools (bash, codegraph_*, kanban_*, delegate_task, commit_and_open_pr, etc.) | Coordinator subagent |
| `bug-fixer` | 17 tools (same as coordinator minus delegate/commit) | Bug fix subagent |
| `test-writer` | 6 tools (bash, read, write, glob, grep, codegraph_search) | Test writer subagent |
| `code-reviewer` | 5 tools (read-only: read, glob, grep, codegraph_explore, web_fetch) | Review subagent |
| `security-auditor` | 5 tools (read + osv_check) | Security subagent |
| `docs-writer` | 3 tools (read, write, glob) | Docs subagent |
| `orchestrator` | 22 tools (orchestrate, delegate, kanban, codegraph, etc.) | Orchestrator engine |
| `chat` | 13 tools (read-only introspection + submit_job) | Chat surface |

**Code evidence:** `backend/harness/tools/toolsets.py` defines all 16 toolsets with explicit tool lists. The `resolve_toolsets()` function resolves toolset names to flat tool lists at agent spawn time.

**Gap:** The 76 auto-discovered agents (from `agent_config.py`) don't all have explicit toolset mappings. The 5 curated agents (bug-fixer, test-writer, etc.) have toolsets, but the 71 others (architect, build-error-resolver, coordinator, etc.) inherit toolsets at spawn time via hardcoded logic in `orchestrator.py:646` and `delegate_task.py:325`.

### 2.2 Skill Access

**Finding:** ✅ **Skills are accessible to all agents via the `skill` tool.**

- 130+ skills in `.testai/skills/` (74 directories visible)
- Skills include: `test-driven-development`, `kanban-worker`, `planning-and-task-breakdown`, `debugging`, `git-workflow`, etc.
- The `skill` tool allows any agent to load skill content on-demand
- Skills are scoped to subagent goal via the tool access model

**Gap:** No per-agent skill gating. Any agent can load any skill. The CONTEXT.md spec says "skills scoped to subagent goal" but the implementation doesn't enforce this.

### 2.3 Plugin Access

**Finding:** ❌ **0 plugins installed.**

- Plugin infrastructure exists (`/api/ops/plugins`)
- No GitHub, Slack, Jira, or Linear plugins installed
- The MCP server (`context-mode`) is the only integration
- **Impact:** No GitHub issues/PRs listing, no Slack notifications, no Jira sync

### 2.4 Knowledge Graph Access

**Finding:** ✅ **KG tools are available to all relevant agents.**

- `codegraph_explore`, `codegraph_search`, `codegraph_node`, `codegraph_callers` — all registered
- `kg_search`, `kg_callers`, `kg_callees`, `kg_graph_status`, `kg_refresh` — legacy tools still present
- KG runs inside sandbox containers via `docker exec` + `npx @colbymchenry/codegraph`
- The coordinator toolset includes all 4 codegraph tools

**Gap:** KG tools require a running sandbox. If the sandbox is down, all KG queries fail silently.

---

## 3. Sandbox Lifecycle Test

### 3.1 Sandbox Creation & Isolation

**Question:** Is the sandbox working correctly? Can we isolate one repo from another?

**Finding:** ✅ **YES — Per-session Docker volumes provide strong isolation.**

```
Sandbox Architecture:
├── Container: testai-sandbox-{session_id[:12]}
├── Volume: testai-ws-{session_id}  (per-session, Docker-managed)
├── Network: testai-network (shared)
└── Mount: /workspace → Docker volume (rw)
           /workspace/host → host bind mount (rw)
```

**Isolation properties:**
- Each session gets its own Docker container + named volume
- Volumes survive container restarts (Docker-managed)
- Container failure doesn't affect siblings (orchestrator respawns with checkpoint)
- Host bind-mount (`./agent_workspace`) is shared across all sandboxes (⚠️ partial isolation gap)

**Live verification:**
```bash
# Two sandboxes running, each with own volume:
testai-sandbox-c3a05d3e-b0b  (session c3a05d3e-b0b)
testai-sandbox-8c485370-45b  (session 8c485370-45b)
```

### 3.2 Sandbox Sharing Between Agents

**Question:** Can other agents use the existing sandbox that previous agents used?

**Finding:** ⚠️ **PARTIAL — Same session reuses sandbox, different sessions create new ones.**

- **Same session:** `SandboxManager.get_or_create(session_id)` returns existing container if session_id matches
- **Different session:** Always creates new container + volume (no sharing)
- **No cross-session sandbox API:** There's no `POST /api/sandbox/{id}/share` or similar

**Code evidence:** `sandbox_manager.py:245-249`:
```python
async def get_or_create(self, session_id: str, ...) -> SandboxEnvironment:
    existing = self._environments.get(session_id)
    if existing:
        self._registry.touch(session_id)
        return existing
```

**Impact:** If Agent A installs Ruby + gems in sandbox-1, Agent B (different session) won't have them. Each session starts from the base image (`nikolaik/python-nodejs`).

**Workaround:** The orchestrator could snapshot the sandbox after deps install and restore from snapshot for subsequent agents. This is implemented but not auto-triggered.

### 3.3 Sandbox Lifecycle Management

**Question:** How can we isolate one repo from another? What about sandbox lifecycle?

**Finding:** ✅ **Lifecycle is managed, but cleanup is manual.**

| Lifecycle Stage | Status | Details |
|----------------|--------|---------|
| Creation | ✅ | Auto-created on first `get_or_create()` |
| Recovery | ✅ | `_recover_containers()` scans Docker on startup |
| Idle detection | ✅ | `idle_seconds` tracked per sandbox |
| Snapshot/Restore | ✅ | `snapshot()` and `restore()` implemented |
| Destruction | ⚠️ | Manual only — no auto-cleanup of idle sandboxes |
| Health check | ⚠️ | No periodic health probe — dead containers stay in registry |

**Gaps:**
1. No auto-cleanup of idle sandboxes (stale containers accumulate)
2. No health probe (dead container stays in `_environments` dict)
3. Host bind-mount (`./agent_workspace`) is shared — files from one run visible to all
4. No resource limits enforced at container level (memory/cpu limits in `sandbox.toml` but not applied)

### 3.4 Sandbox Bootstrap

**Question:** Does the orchestrator install dependencies after cloning?

**Finding:** ❌ **NO — The orchestrator does NOT auto-install dependencies.**

- Rails repo cloned (206MB) but `bundle install` never runs
- Base image is `nikolaik/python-nodejs` — no Ruby, no bundler
- The coordinator prompt doesn't include "install dependencies" as a step
- **Impact:** Any "fix the test" flow fails at first `bundle exec`

**Fix needed:** Add a "sandbox bootstrap" step that:
1. Detects project language (Gemfile → Ruby, package.json → Node, pyproject.toml → Python)
2. Installs runtime + dependencies
3. Optionally snapshots the post-install state

---

## 4. Knowledge Graph Test

### 4.1 KG Generation

**Question:** Is the repo pulled and KG generated?

**Finding:** ✅ **YES — KG is generated and persisted.**

| Metric | Value |
|--------|-------|
| Graphs in DB | 2 |
| Nodes per graph | 60,479 |
| Edges per graph | 177,048 |
| Language | codegraph |
| Schema version | v5 |
| Index tool | `npx @colbymchenry/codegraph init` |

**Code evidence:** `codegraph.py:73-85` — `index_project()` runs `codegraph init -v <workspace_path>` inside the sandbox.

### 4.2 KG Provenance

**Question:** Can we tell which repo the KG came from?

**Finding:** ✅ **IMPLEMENTED — But existing graphs predate the implementation.**

**Code evidence:** `codegraph.py:216-264`:
- `repo_graph_id(repo_url, branch)` computes `SHA256(repo_url + "|" + branch)[:16]`
- `write_provenance()` writes `provenance.json` with `repo_url`, `branch`, `graph_id`, `node_count`, `builds`
- `orchestrator.py:563-593` calls both functions after KG build

**Why existing graphs have empty `repo_url`:**
The 2 existing graphs (`a901b404fa3c2b12`, `1d42d5492dd7b449`) were created before the provenance implementation. They have:
- `repo_url: ""` (empty)
- `repository_display_name: null`
- `branch: null`

**New runs will have proper provenance.** The orchestrator now:
1. Computes `graph_id = SHA256(repo_url + "|" + branch)[:16]`
2. Writes `provenance.json` to `agent_workspace/knowledge-graphs/<graph_id>/`
3. Frontend can query by repo via `GET /api/knowledge-graph/by-repo?repo_url=...&branch=...`

**Gap:** The existing 60K-node graphs are orphaned (no provenance). The next run against rails/rails will create a new graph with proper provenance.

### 4.3 KG Update After Fixes

**Question:** Can agents update the KG after fixing issues?

**Finding:** ⚠️ **PARTIAL — `kg_refresh` exists but was not observed in E2E tests.**

- `kg_refresh` tool is registered in the coordinator toolset
- No `kg_refresh` events were emitted in previous E2E runs
- The codegraph is initialized at sandbox start but no incremental update flow was visible

**Code evidence:** `knowledge_graph_tool.py` has `kg_refresh` but it's a thin wrapper around `codegraph init` (full re-index, not incremental).

**Gap:** After Agent A fixes a file, the KG should be updated so Agent B sees the new code. Currently, the KG is built once at sandbox start and never refreshed.

### 4.4 KG Copy to Host

**Finding:** ✅ **Implemented but not auto-triggered.**

- `copy_db_to_host()` in `codegraph.py:142-165` exports the sandbox DB to host
- Host path: `agent_workspace/knowledge-graphs/<graph_id>/codegraph.db`
- The orchestrator should call this at the end of tier-1/tier-2 runs

**Gap:** No auto-trigger. The KG stays inside the sandbox and is lost when the sandbox is destroyed.

---

## 5. Tool/Skill/Plugin/MCP Access Test

### 5.1 Tool Registration

**Finding:** ✅ **79+ tools registered and accessible.**

Categories verified:
- **Filesystem:** bash, read_file, write_file, edit_file, apply_patch, list_files, glob, grep
- **Code Intelligence:** codegraph_explore, codegraph_search, codegraph_node, codegraph_callers
- **Orchestration:** delegate_task, orchestrate, orchestrate_monitor
- **Kanban:** kanban_create, kanban_list, kanban_update, kanban_assign, etc.
- **Test Runner:** attempt_heal, coverage_analyzer, commit_and_open_pr
- **Specialized:** computer_use, vision_analyze, diagram, database_query

### 5.2 MCP Integration

**Finding:** ⚠️ **1 MCP server configured, but connections endpoint has bug.**

- `context-mode` MCP server configured in `.testai/mcp.json`
- `GET /api/settings/mcp` works ✅
- `GET /api/settings/mcp/connections` returns error: `'MCPClient' object has no attribute 'servers'`

**Impact:** MCP tools are available but the connections status endpoint is broken.

### 5.3 Tool Access by Agent Type

**Finding:** ✅ **Tool isolation works via toolset resolution.**

| Agent Type | Toolset | Tool Count | Key Tools |
|------------|---------|------------|-----------|
| Coordinator | coordinator | 22 | delegate_task, commit_and_open_pr, kanban_*, codegraph_* |
| Bug Fixer | bug-fixer | 17 | bash, write, edit, codegraph_*, attempt_heal |
| Test Writer | test-writer | 6 | bash, read, write, glob, grep, codegraph_search |
| Code Reviewer | code-reviewer | 5 | read-only (no bash, no writes) |
| Security Auditor | security-auditor | 5 | read + osv_check |
| Chat | chat | 13 | read-only + submit_job |

**Code evidence:** `delegate_task.py` resolves toolsets at spawn time via `resolve_toolsets()` and strips blocked tools via `_strip_blocked_tools()`.

### 5.4 GitHub Integration

**Question:** Can agents list GitHub issues and PRs?

**Finding:** ⚠️ **PARTIAL — GitHub provider exists but not exposed as tools.**

**What exists:**
- `backend/harness/ci/git_providers.py` — `GitHubProvider` class with:
  - `list_open_prs(repo, token)` — lists open PRs
  - `list_open_issues(repo, token)` — lists open issues
  - `get_pr_diff(repo, pr_number, token)` — gets PR diff
  - `post_pr_comment(repo, pr_number, token, body)` — posts comments
  - `set_pr_status(repo, pr_number, token, state, description)` — sets status

**What's missing:**
- No tools expose GitHub functionality to agents
- The `GitHubProvider` is only used internally by the CI module
- No `github_list_issues` or `github_list_prs` tools in the catalog
- The orchestrator's coordinator cannot list issues/PRs

**Impact:** The user's requirement "when the user provides a repo that has some PRs, GitHub issues" cannot be fulfilled without wiring GitHub tools.

**Fix needed:**
1. Create `github_list_issues` and `github_list_prs` tools
2. Add them to the coordinator toolset
3. Wire the `GitHubProvider` to these tools
4. Add GitHub token to the sandbox environment

---

## 6. Artifact Persistence Test

### 6.1 Test Files & Configs

**Question:** Are artifacts, test files, configs persisted?

**Finding:** ⚠️ **PARTIAL — Session-level artifacts exist but are not exercised.**

| Artifact Type | Storage | Persistence | TTL |
|---------------|---------|-------------|-----|
| Committed test files | Postgres + filesystem | Permanent | — |
| Trajectories | Postgres | 30 days | Configurable |
| LLM transcripts | Postgres | 7 days | Configurable |
| Sandbox workspace | Docker volume | Until sandbox destroyed | — |
| Knowledge graphs | Host filesystem | Permanent | — |
| L0 raw artifacts | Postgres | Permanent | — |

**Code evidence:** `agent.py:434-480` — `_save_reflections()` writes L0 artifacts via `ArtifactStore.write_batch()`.

**Gap:** The artifact store API (`/api/artifacts/{session_id}`) exists but was not tested in E2E. No verification that artifacts survive sandbox destruction.

### 6.2 Cross-Run Memory

**Finding:** ✅ **Cross-run memory works.**

- L2 reflections saved via `memory` tool
- Memory snapshots loaded at agent startup (`store.get_recent_context()`)
- `ReflexionMemory` class stores tool-call failures for self-critique

**Code evidence:** `agent.py:420-424`:
```python
if self._deps.store:
    context = await self._deps.store.get_recent_context()
    if context:
        self._messages.append(ChatMessage(role="system", content=f"Relevant context:\n{context}"))
```

---

## 7. Metrics Collection Test

### 7.1 Token & Cost Tracking

**Question:** Are required metrics collected properly?

**Finding:** ⚠️ **PARTIAL — Plumbing exists but subagent tracking is broken.**

| Metric | Status | Details |
|--------|--------|---------|
| Token usage per LLM call | ✅ | `token_usage` table populated |
| Cost per LLM call | ✅ | `estimated_cost_usd` computed |
| Session total tokens | ⚠️ | `total_tokens` in sessions table — may be 0 for subagents |
| Session total cost | ⚠️ | `total_cost` in sessions table — may be 0 for subagents |
| Tool calls count | ⚠️ | `tool_calls_count` always 0 in delegations |
| Duration | ✅ | `started_at` / `completed_at` in sessions |
| Subagent count | ✅ | Tracked in delegation tree |

**Root cause for subagent metrics:** `delegate_task` creates the sandbox and runs the subagent LLM, but the subagent's `sessions` row may not exist when `CostTracker.record_usage()` fires, causing the UPDATE to match 0 rows.

**Fix needed:** Ensure subagent sessions row is created before LLM calls begin.

### 7.2 Dashboard Metrics

**Finding:** ⚠️ **Dashboard shows 0 for chat-originated runs.**

- `/api/runs` returns `testCount/passedCount/failedCount/cost/tokens` — all 0 for chat runs
- `/api/dashboard/stats` returns `activeAgents: 0` even when subagents are running
- `/api/ops/sandbox-metrics` shows different count than `/api/sandbox/list`

---

## 8. User Configuration Surface Test

### 8.1 Per-Agent Model Override

**Question:** Can users configure things that need customization?

**Finding:** ❌ **NO — All 5 curated agents have `model=""` (empty).**

- No per-agent model override in the UI
- All agents fall back to the default `deepseek-v4-flash`
- User cannot promote "bug-fixer" to a stronger model

**Gap:** The Settings → Agents page shows 5 agents but no model field. The user cannot configure per-agent models.

### 8.2 Per-Role Tool Gating

**Finding:** ⚠️ **PARTIAL — Toolsets exist but aren't configurable per-agent in UI.**

- 16 toolsets defined in code (`toolsets.py`)
- `/api/tools/toolsets` returns all 16
- But the UI doesn't expose toolset assignment per agent
- Tool tier gating (`allow`/`ask`/`deny`) exists per-tool but isn't surfaced

### 8.3 Provider/Model Configuration

**Finding:** ✅ **Provider configuration works.**

- `deepseek-v4-flash` configured via `opencode_zen.py` provider
- Base URL: `https://opencode.ai/zen/go/v1`
- API key in `backend/.env`
- Thinking mode support: `_is_deepseek_thinking_model` + `reasoning_effort` config

**Gap:** The default `reasoning_effort` is `None` (server picks "high"), which overwhelms the 79-tool catalog. Should default to `"low"` for orchestrator.

### 8.4 Hooks & Gates

**Finding:** ✅ **Hook system exists but not all hooks are wired.**

- Pre/Post tool hooks implemented (`_hook_system.py`)
- SessionStart hook fires on agent start
- Budget tracker hooks exist but not enforced (`BudgetTracker.check_soft_cap()` not wired to agent loop)

---

## 9. Competitor Research

### 9.1 Greptile (YC W24, $25M Series A)

**Architecture:**
- Full-repo code graph built once, updated incrementally per commit
- Multi-hop investigation engine (traces call chains across files)
- Confidence scores on every review comment
- 82% bug catch rate, 100% high-severity detection
- Built on Anthropic Claude Agent SDK

**Key Insight for TestAI:**
- Greptile's incremental KG update is the pattern we need (`kg_refresh` should be incremental, not full re-index)
- Confidence scores would help prioritize which issues to fix first
- Their "several minutes per review" is acceptable — depth over speed

### 9.2 Tembo (Agent Studio)

**Architecture:**
- Orchestrator pattern: lead agent + sub-agents
- Each agent in isolated sandbox with full repo access
- Async agent execution (5 agents simultaneously)
- Task decomposition → parallel execution → output integration
- PR-based workflow (every change flows through PR review)

**Key Insight for TestAI:**
- Tembo's async execution model matches our `delegate_task` fan-out
- Their "each agent in isolated sandbox" is exactly our Docker volume pattern
- Task boundaries prevent merge conflicts (we need this for parallel fixes)

### 9.3 TestSprite 2.0

**Architecture:**
- MCP server for IDE integration (Cursor, VS Code, Windsurf)
- PRD → test plan → test code pipeline
- Self-healing tests (auto-locator repair)
- Cloud sandboxes for test execution

**Key Insight for TestAI:**
- TestSprite's MCP server pattern is what we should adopt (public TestAI MCP server)
- Their self-healing flow is more mature than our `attempt_heal`
- PRD-to-test pipeline is a feature we should add

### 9.4 OpenHands

**Architecture:**
- Agent runtime with sandbox + browser automation
- Code execution in isolated environment
- Browser automation (CDP-based)
- Delegate tool for subagent spawning

**Key Insight for TestAI:**
- OpenHands has more mature browser automation (we have `computer_use` but it's gated)
- Their `osv_check` tool (CVE scanning) is something we should add

### 9.5 Hermes (NousResearch)

**Architecture:**
- Toolsets as named bundles (exactly our pattern)
- Platform presets (hermes-cli, hermes-telegram)
- Dynamic MCP toolsets
- Curated special-purpose sets

**Key Insight for TestAI:**
- Hermes's toolset resolution is the reference implementation for our `toolsets.py`
- Their per-platform presets could map to per-tier presets in TestAI

### 9.6 openclaude (Anthropic Claude Code)

**Architecture:**
- 4 built-in agent categories: main, async, coordinator, teammate
- Auto-discover from `.claude/agents/*.md`
- Coordinator CANNOT write files (enforced tool isolation)
- Background agents for async work

**Key Insight for TestAI:**
- Coordinator-cannot-write-files rule is the gold standard (our coordinator has write tools)
- Background agent flag for async work (we have this in `delegate_task` but it's not enforced)

---

## 10. Gap Analysis & Prioritized Roadmap

### P0 — Blockers (Must Fix Before Trusting System)

| # | Gap | Impact | Fix |
|---|-----|--------|-----|
| 1 | **LLM model too weak for tool-calling** | Orchestrator never produces tool calls | Default `reasoning_effort` to `"low"` for coordinator; consider stronger model for coordinator role |
| 2 | **No sandbox dependency bootstrap** | Ruby/Node/Python repos can't run tests | Add auto-detect + install step after clone |
| 3 | **Existing KG graphs orphaned** | 2 graphs with 60K nodes have no provenance | New runs will have proper provenance; consider rebuilding existing graphs |
| 4 | **Coordinator has write tools** | Violates separation of concerns | Remove `write_file`, `edit_file`, `apply_patch` from coordinator toolset (keep in bug-fixer) |

### P1 — Significant Gaps

| # | Gap | Impact | Fix |
|---|-----|--------|-----|
| 5 | **Subagent cost tracking broken** | Can't measure per-agent costs | Create sessions row before LLM calls in `delegate_task` |
| 6 | **No per-agent model override** | Can't use stronger model for complex tasks | Add `model` field to agent config, surface in UI |
| 7 | **KG not auto-refreshed after edits** | Subagents see stale code | Auto-call `kg_refresh` after file edits |
| 8 | **No GitHub integration** | Can't list issues/PRs | Install GitHub plugin, wire `gh` CLI |
| 9 | **No auto-cleanup of idle sandboxes** | Stale containers accumulate | Add idle timeout + auto-destroy |
| 10 | **Sandbox health probe missing** | Dead containers stay in registry | Add periodic health check |

### P2 — Quality Improvements

| # | Gap | Impact | Fix |
|---|-----|--------|-----|
| 11 | **No public TestAI MCP server** | Other agents can't drive TestAI | Build MCP server exposing core tools |
| 12 | **Dashboard active agents wrong** | Shows 0 when subagents running | Count subagents in `/api/dashboard/stats` |
| 13 | **No PRD-to-test pipeline** | User must manually describe tests | Add PRD → test plan → test code flow |
| 14 | **No confidence scores on issues** | Can't prioritize fixes | Add confidence scoring (Greptile pattern) |
| 15 | **Host bind-mount shared** | Files from one run visible to all | Move to per-session volumes only |

### P3 — Nice-to-Have

| # | Gap | Impact | Fix |
|---|-----|--------|-----|
| 16 | No browser automation testing | Can't do E2E UI tests | Wire `computer_use` tool properly |
| 17 | No OpenTelemetry export | Can't integrate with enterprise observability | Implement OTLP span export |
| 18 | No rate limiting on API | Vulnerable to abuse | Add rate limiting middleware |
| 19 | No auth middleware | API is open | Add authentication |
| 20 | No E2E frontend tests | UI regressions undetected | Add Playwright tests |

---

## Appendix A: Live Test Results

### Test: Submit Pipeline Job for rails/rails

**Payload:**
```json
{
  "prompt": "Analyze the rails/rails GitHub repository structure and identify test coverage gaps",
  "repo_url": "https://github.com/rails/rails",
  "mode": "pipeline",
  "tier": 1
}
```

**Result:**
- Sandbox created: `testai-sandbox-{session_id}`
- Repo cloned: 206MB shallow clone
- KG built: 60K nodes, 177K edges
- Kanban board created with 4 tasks (explore → triage → fix → verify)
- Coordinator spawned with 22-tool toolset
- **Status:** ⚠️ Coordinator started but LLM produced no tool calls (model quality ceiling)

### Test: Sandbox Sharing

**Scenario:** Agent A creates sandbox, Agent B tries to use same session_id

**Result:** ✅ `SandboxManager.get_or_create(session_id)` returns existing container
- Same session_id → same sandbox (reuse)
- Different session_id → new sandbox (isolation)

### Test: KG Query After Build

**Scenario:** Build KG for rails/rails, then query symbols

**Result:** ✅ `codegraph_explore` returns symbol data
- Query: "How does ActiveRecord::Base work?" → Returns relevant symbols grouped by file
- Performance: ~2-3 seconds per query

---

## Appendix B: Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    TestAI Platform                           │
├─────────────────────────────────────────────────────────────┤
│  Frontend (Next.js :3001)                                   │
│  ├── Dashboard, Kanban, Sessions, Settings                  │
│  └── Client-side rendering → Backend API (:8001)            │
├─────────────────────────────────────────────────────────────┤
│  Backend (FastAPI :8000)                                     │
│  ├── Chat API → Agent Router → Mode Selection               │
│  ├── Pipeline API → OrchestratorEngine                      │
│  ├── Agent Registry (76 auto-discovered)                    │
│  ├── Tool Registry (79+ tools)                              │
│  ├── Toolset Registry (16 curated toolsets)                 │
│  ├── Skill Registry (130+ skills)                           │
│  └── MCP Client (1 server: context-mode)                    │
├─────────────────────────────────────────────────────────────┤
│  Orchestrator                                                │
│  ├── 1. Create Sandbox (Docker container + volume)          │
│  ├── 2. Clone Repo (git clone --depth=1)                    │
│  ├── 3. Build KG (codegraph init)                           │
│  ├── 4. Create Kanban Board (4 tasks: explore→triage→fix→verify) │
│  ├── 5. Spawn Coordinator (22-tool toolset)                 │
│  └── 6. Coordinator drives work via delegate_task           │
├─────────────────────────────────────────────────────────────┤
│  Subagents (isolated sandboxes)                              │
│  ├── Explore Agent (read-only, codegraph tools)             │
│  ├── Triage Agent (analysis, planning)                      │
│  ├── Fix Agent (bug-fixer toolset, 17 tools)                │
│  └── Verify Agent (test runner, self-heal)                  │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure                                              │
│  ├── PostgreSQL (79 tables)                                  │
│  ├── Docker (sandbox containers)                             │
│  ├── CodeGraph (KG indexing)                                 │
│  └── LangFuse (observability)                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Appendix C: Recommended Next Steps

### Immediate (This Week)
1. Fix `reasoning_effort` default to `"low"` for coordinator
2. Add sandbox dependency bootstrap (detect language + install deps)
3. Key KG by `SHA256(repo_url|branch)` with provenance
4. Remove write tools from coordinator toolset

### Short-term (This Month)
5. Fix subagent cost tracking
6. Add per-agent model override in UI
7. Auto-refresh KG after file edits
8. Install GitHub plugin for issues/PRs
9. Add sandbox idle timeout + auto-cleanup

### Medium-term (This Quarter)
10. Build public TestAI MCP server
11. Add PRD-to-test pipeline
12. Implement confidence scoring
13. Add OpenTelemetry export
14. Write E2E frontend tests

---

*Document created: 2026-06-17*
*Last updated: 2026-06-17*
*Author: TestAI E2E Test Suite*
