# TestAI End-to-End Agentic Test â€” 2026-06-16

> **Goal:** Verify the full TestAI agentic loop on a real GitHub repo (`https://github.com/rails/rails`).
> The user provides a repo. The orchestrator pulls it, explores via subagents, builds a KG,
> triages via the parent, drives fixes, runs tests, self-heals, and updates the Kanban board.
>
> **Environment:**
> - Plan file: `plans/test_env.txt` (model = `deepseek-v4-flash`, base URL = `https://opencode.ai/zen/go/v1`)
> - API key in use: `sk-DBG6zpzGew...` (matches `backend/.env` and the running container)
> - Backend: `localhost:8001` (Docker, healthy)
> - Frontend: `localhost:3001` (Docker)
> - Postgres: `localhost:5432` (Docker)
> - Sandbox image: `nikolaik/python-nodejs` (per CONTEXT.md)
>
> **Methodology:** each finding appended to this file under a dated section. The doc accumulates
> as the test progresses. Final section will consolidate refinements + roadmap.

---

## Sections

1. Pre-flight health check
2. Component sync audit
3. Sandbox lifecycle test
4. Knowledge graph test
5. Toolset/skills/MCP/credentials test
6. Artifact persistence test
7. Metrics collection test
8. User configuration surface test
9. Framework research (Greptile, Testim, TestSprite, Devin, Claude Code, opencode, etc.)
10. Refinements + prioritized roadmap

---

## 1. Pre-flight health check

| Check | Endpoint | Result |
|---|---|---|
| Containers | docker ps | All 3 testai-* up + healthy |
| Backend health | GET /api/health | 200 {"status":"ok"} |
| Tools registry | GET /api/tools | 200 |
| Skills registry | GET /api/skills?limit=5 | 200 |
| Agents (roles) | GET /api/agents | 200 |
| Kanban boards | GET /api/kanban/boards | 200 |
| Admin plugins | GET /api/admin/plugins | 200 |
| MCP config | GET /api/settings/mcp | 200 |
| MCP connections | GET /api/settings/mcp/connections | 200 |
| KG list | GET /api/knowledge-graph/recent?limit=10 | 200 (2 graphs) |
| Wrong KG path | GET /api/knowledge-graph/stats | 404 (route does not exist) |
| Wrong MCP path | GET /api/ops/mcp-servers | 404 (path is /api/settings/mcp) |

**OpenAPI paths for KG** (all real):
- GET /api/knowledge-graph/by-repo (Q4.1 — looks up by repo_url+branch)
- GET /api/knowledge-graph/recent
- GET /api/knowledge-graph/{graph_id}
- GET /api/knowledge-graph/{graph_id}/file-content

**Existing KGs in DB:** 2 entries, both with 60,466 nodes and 176,960 edges. These are the legacy rails KG (orphaned from pre-Q4.1 session-id keying; both have empty epo_url and graph_id).

**Sandbox state:** 8 	estai-ws-* volumes on disk (rails per-repo + 6 per-session + 1 60K-node legacy). See Section 3.


---

## 2. Component sync audit (static, before live test)

### 2.1 Agent registry — GAP FOUND

**Built-in agent prompt files** at /app/.testai/prompts/agents/ (in container, mounted from gent_workspace/agents/):

`
architect.txt                build-error-resolver.txt     code-reviewer.txt
coordinator.txt              cpp-build-resolver.txt       cpp-reviewer.txt
database-reviewer.txt        doc-updater.txt              docs-lookup.txt
e2e-runner.txt               go-build-resolver.txt        go-reviewer.txt
harness-optimizer.txt        java-build-resolver.txt      java-reviewer.txt
kotlin-build-resolver.txt    kotlin-reviewer.txt          loop-operator.txt
php-reviewer.txt             planner.txt                  python-reviewer.txt
refactor-cleaner.txt         rust-build-resolver.txt      rust-reviewer.txt
security-reviewer.txt        subagent-delegator.txt       subagent-worker.txt
`

**That's 26+ prompt files.** But /api/agents returns only 5 — ug-fixer, code-reviewer, docs-writer, security-auditor, 	est-writer.

**Root cause:** AgentStore._seed_defaults() (agent_config.py:219) only seeds the 5 entries from _DEFAULT_AGENT_META (lines 21-47). The orchestrator's coordinator, explore, nalyzer, eaper, curator, digest, discovery, chat agents all exist in code but are NOT in the store.

**Impact:** The dashboard "Agents" page only shows 5 configurable agents. Users cannot configure / inspect / override prompts for coordinator, e2e-runner, planner, rchitect, etc. The orchestrator's coordinator prompt is hardcoded at orchestrator.py:583.

**Fix priority:** HIGH. The agent registry should auto-discover all *.txt files in /app/.testai/prompts/agents/ and seed them with the curated 	oolsets defaults. The 5 currently seeded look like a leftover from a V1; the V2 (Q5) system needs a real Role registry.

### 2.2 	oolsets=[] empty in /api/agents — COSMETIC

**Cause:** _DEFAULT_AGENT_META has no 	oolsets key; AgentConfig.toolsets defaults to []. The orchestrator picks the toolset implicitly at spawn time (e.g. orchestrator.py:642 hardcodes 	oolsets=["coordinator"] for the coordinator subagent). The API can't show the user "this agent will use the X toolset" because the user-side config has no override yet.

**Fix:** include the curated default toolset in the API response (e.g. effective_toolsets computed from the mode).

### 2.3 Toolset API path mismatch

| Tried | Result |
|---|---|
| GET /api/toolsets | 404 (not found) |
| GET /api/tools/toolsets | 200 (correct path) |

The router is at 	ools_management.py:75 with prefix /api/tools. Frontend should use /api/tools/toolsets or this should be aliased to /api/toolsets.


---

## 3. Agent registry deep-dive — Component sync key finding

### 3.1 The 5-agent problem

_DEFAULT_AGENT_META at ackend/harness/agent_config.py:21-47 defines 5 agents:

`python
{"test-writer", "code-reviewer", "bug-fixer", "security-auditor", "docs-writer"}
`

These match the 5 curated subagent toolsets at ackend/harness/tools/toolsets.py:124-167. They are **V1 artifacts**: when the filesystem at gent_workspace/agents/ is empty, _seed_defaults() creates .md files for these 5 names so the dashboard has *something* to show.

**Problem:** There are 26+ real prompt files at /app/.testai/prompts/agents/ that represent real subagent roles:
rchitect, uild-error-resolver, code-reviewer, coordinator, cpp-reviewer, database-reviewer, doc-updater, e2e-runner, go-reviewer, java-reviewer, planner, python-reviewer, efactor-cleaner, security-reviewer, subagent-delegator, subagent-worker, etc.

But the orchestrator path (orchestrator.py, orchestrator_tool.py, delegate_task.py) hardcodes role names and toolset assignments:

| Location | File | Hardcoded |
|---|---|---|
| Coordinator spawn | orchestrator.py:646 | ole=\"orchestrator\", 	oolsets=[\"coordinator\"] |
| Explore subagent | orchestrator_tool.py:319 | ole=\"orchestrator\", 	oolsets=[\"coordinator\"] |
| Analyzer subagent | orchestrator_tool.py:345 | ole=\"leaf\", 	oolsets=[\"bug-fixer\"] |
| Leaf worker | delegate_task.py:325 | ole=\"leaf\" when depth exceeded |

### 3.2 Two separate registries — don't talk to each other

| System | Class | Source | Used by |
|---|---|---|---|
| AgentStore | ackend/harness/agent_config.py | gent_workspace/agents/*.md | /api/agents dashboard |
| AgentRegistry | ackend/harness/agents/registry.py | FS + DB scan (yaml + md) | Orchestrator dispatch |

The AgentRegistry (registry.py) has the correct resolution order:
1. DB user-created agents
2. .testai/agents/_custom/ (YAML overrides)
3. .testai/agents/ (built-in YAML)
4. gent_workspace/agents/ (legacy markdown)

But it's only used in 	ools/orchestrator_tool.py for trigger-based resolution — NOT for the primary orchestration path. The coordinator, explore, and analyzer roles are hardcoded string literals.

### 3.3 What a Role should look like

The 	oolsets.py file has the right curated toolsets for 6 roles (coordinator, 	est-writer, ug-fixer, code-reviewer, security-auditor, docs-writer) plus 9 base toolsets (chat, ead, write, intelligence, delegate, healing, kanban, specialized). Each curated toolset is a named bundle that resolves to a flat list of tools. This matches what CONTEXT.md calls a \"Role\" — YAML + Pydantic schema mapping an agent name to a system prompt, toolset, model, and delegation depth. But the Role-to-AgentConfig mapping is not wired.


---

## 4. Agent registry fix — auto-discover all 76 agents

**Before:** _DEFAULT_AGENT_META hardcoded 5 agents (	est-writer, code-reviewer, ug-fixer, security-auditor, docs-writer).

**After:** _agent_meta_autodiscover() scans:
1. /app/.testai/prompts/agents/*.txt ? 26 custom agents (architect, build-error-resolver, coordinator, cpp-reviewer, e2e-runner, etc.)
2. /app/harness/prompts/agent-prompt-*.md ? 50+ built-in agent prompts

**Result: 76 agents** auto-discovered, each with a real system prompt from the prompt files.

**Changes to gent_config.py:**
- Replaced _DEFAULT_AGENT_META (5 hardcoded) with _agent_meta_autodiscover() (filesystem scan)
- _prompt_for_role() now tries built-in prompts first, then .testai custom prompts
- _seed_defaults() uses the auto-discovered meta
- Reference research confirmed this matches openclaude (tiered registry) and OpenHarness (YAML+MD discovery)

## 5. Fixed RuntimeWarning: coroutine 'SandboxManager.get_env' was never awaited

4 files had sm.get_env() without wait:
- isual_diff_tool.py:288 — _get_env was sync def but missing wait ? fixed
- rtifact_tools.py:43 — _get_env was sync def ? changed to sync def + wait
- commit_and_open_pr_tool.py:115 — same pattern as visual_diff ? fixed
- codegraph.py:68 — get_sandbox_env() was sync ? changed to sync def + wait
- codegraph_tools.py — _require_sandbox() ? sync def, all 4 callers ? wait
- knowledge_graph_tool.py — 2 callers ? wait get_sandbox_env()

This fixes the \"coroutine 'SandboxManager.get_env' was never awaited\" warning at registry.py:405.

## 6. Reference framework research — key findings

Compared Hermes, OpenHarness, OpenHands, and openclaude (Anthropic's Claude Code):

| Pattern | TestAI (before) | openclaude (best) |
|---|---|---|
| Agent registry | 5 hardcoded | 4 built-in + auto-discover from .claude/agents/*.md |
| Toolsets | Curated defaults + per-role | Per-agent allow/deny sets + coordinator/worker split |
| Roles | orchestator/leaf (hardcoded) | main/async/coordinator/teammate (4 categories) |
| Coordinator | Has delegate_task | CANNOT write files — must delegate all work |
| Sandbox | Per-subagent Docker | Per-subagent worktree (ephemeral git checkout) |
| Knowledge Graph | Built-in codegraph (60K nodes) | Orama conversation memory (entity-relation) |

**What TestAI should adopt from openclaude:**
1. Coordinator-cannot-write-files rule (enforced tool isolation)
2. ackground: true agent flag for async agents
3. equiredMcpServers gate for agent availability
4. Worktree isolation as lightweight alternative to Docker

---

## 7. Pipeline E2E test — execution results

Submitted pipeline job for rails/rails (session 9c68b7e5). Results:

| Step | Status | Detail |
|------|--------|--------|
| Sandbox creation | ? | Created 	estai-sandbox-9c68b7e5-1ec |
| Repo clone | ? | 206MB, shallow clone |
| KG build | ? | 139MB, incremental (builds: 2) |
| KG copy to host | ? | /agent_workspace/knowledge-graphs/a901b404fa3c2b12/ |
| Provenance update | ? | uilds: 2, last_session_id updated |
| Subagent spawn | ? | Second sandbox 7109a808-4ba created by delegate_task |
| Pipeline completion | ? | Status=completed, end_reason=completed, 4 min runtime |
| Subagent session in DB | ? | No subagent-sa-* entry created for this run |
| Cost/tokens tracking | ? | 	otal_cost=0, 	otal_tokens=0 on pipeline session |

## 8. Cost tracking — root cause

The 	oken_usage table tracks per-LLM-call data (tokens + cost) and the sessions table has 	otal_tokens/	otal_cost summary columns. The flow is:

1. LLM provider returns usage ? gent.py:512-522 calls INSERT INTO token_usage + UPDATE sessions SET total_tokens, total_cost
2. The CostTracker class in cost_tracker.py wraps this with model-based pricing
3. Subagent sessions need a sessions row to exist for the UPDATE to work

Root cause: delegate_task creates the sandbox container and runs the subagent LLM, but the subagent's sessions row may not exist when CostTracker.record_usage() fires, causing the UPDATE to match 0 rows.

## 9. Key Architecture Gaps (from Hermes/OpenHarness/openclaude reference)

| Area | TestAI current state | Best practice (from reference) |
|------|---------------------|-------------------------------|
| Agent registry | 76 auto-discovered (fixed) | + 3-tier override: built-in ? plugin ? user |
| Toolsets | Named toolsets with includes | + Per-role allow/deny sets (openclaude) |
| Coordinator | Has delegate_task + write tools | Should NOT write files (openclaude/OpenHarness) |
| Sandbox per subagent | ? Worker_env creates per-subagent container | ? Matches Hermes pattern |
| KG persistence | Per-repo, incremental rebuilds | Unique to TestAI — no reference framework has this |
| Cost tracking | token_usage table + sessions summary | Needs subagent session binding |
| Stream events | Events emitted but not visible in E2E test | Check /api/delegate/{id}/stream wiring |
