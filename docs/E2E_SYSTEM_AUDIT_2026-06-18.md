# E2E System Audit & Comparative Analysis

**Date**: 2026-06-18  
**Purpose**: System-wide audit of TestAI's agentic architecture against industry peers (Tembo, Greptile, GitHub Copilot, OpenAI Codex) — identifying gaps in sandbox lifecycle, knowledge graph evolution, artifact persistence, metrics, and configurability.

---

## E2E Test Results — 2026-06-18

**Target**: rails/rails (GitHub) via frontend-equivalent API call  
**Goal**: "Analyze the rails/rails GitHub repository. List open issues and PRs using github tools. Create a kanban board with tasks to fix the top issues."  
**Method**: `POST /api/delegate` with `role: orchestrator`, `run_in_background: true` (same payload as frontend Pipeline page → Orchestrate mode)  
**API Key Used**: sk-pwCcyzJI3i8J1p8PAlGlJEjSIpbehesFS5d6EpSGnHgx6wlW5opVqm06SIO1XXP5 (configured as env in Docker backend)

### 1. Job Submission ✅
- Session created: `dbb54d39-8300-410e-9fd5-0c8eb4f066ae`
- 3 frontend entry points exist: Agent page (`/agent`), Pipeline page (`/pipeline`), QuickPipeline floating button
- All 3 call the same backend APIs (`POST /api/agent/run`, `POST /api/delegate`, `POST /api/pipeline/from-requirements`)

### 2. Sandbox Creation ✅
- Docker container created: `testai-sandbox-dbb54d39-830`
- rails/rails repo cloned at `/workspace/repo/` with full file tree
- 6 sandbox containers from previous runs also running (not cleaned up — `keep_volume=true` by default)
- Sandbox has Node.js v20, npm, npx available

### 3. Knowledge Graph Indexing ⚠️
- CodeGraph DB created at `/workspace/repo/.codegraph/codegraph.db` (4KB, SQLite)
- Host-side cache copied: `agent_workspace/knowledge-graphs/a901b404fa3c2b12/`
- **0 nodes, 0 edges** — CodeGraph's tree-sitter parsers may not support Ruby
- Provenance metadata correct: tracks graph_id, repo_url, branch, session_id, build count (24)
- Second KG `1d42d5492dd7b449` (145MB, 60K nodes) exists — likely indexed the testai-production codebase with JS/TS/Python parsers
- **provenance.json does NOT track node_count or edge_count correctly** — shows null while actual DB has data

### 4. Kanban Board Creation ✅
- Board created: `c7e78687-2773-4ac5-a2d2-8dcdf246344f`
- 4 tasks with proper columns and agent types:
  - **Explore** (ready) — agent:explore
  - **Analyze and plan** (backlog) — agent:triage
  - **Implement** (backlog) — agent:fix
  - **Verify fix** (backlog) — agent:verify
- Board configuration: source=orchestrator, failure_limit=3, WIP limit=3 for in_progress
- 7 previous boards from earlier runs against rails/rails also present

### 5. Coordinator Subagent Spawn ⚠️
- Subagent `sa-0-6d54e3e8` created
- Status: **error** — `NameError: name 'agent_factory' is not defined`
- Duration: 0.03 seconds (immediate failure)
- The high-level orchestrator (source=api) completed successfully despite coordinator failure
- The orchestrator's `run_job_spec` → `run_single` flow completed but the coordinator couldn't execute its tool loop

### 6. Session Events ✅
- 4 events captured in stream_events table:
  1. `session.started` — 03:43:08
  2. `orchestration.started` — 03:43:08
  3. `subagent.completed` (error) — 03:43:39
  4. `orchestration.completed` — 03:43:39
- Total run time: ~31 seconds

### 7. Cross-Run State ⚠️
- Sandbox volume persists (`keep_volume=true` default) — 6 stale containers from previous runs
- KG host cache accumulates — 2 graph entries (testai-production + rails)
- No cross-run memory injection observed (L2 memories not checked)
- Sandbox `reap_stale` has 168h (7 day) default TTL

### 8. Specific Issues Found

| Issue | Severity | Component |
|-------|----------|-----------|
| CodeGraph doesn't support Ruby → 0 nodes for rails/rails | High | KG |
| `agent_factory` not defined — coordinator crashes | Critical | Delegation |
| provenance.json doesn't track node/edge counts | Low | KG |
| Stale sandboxes accumulate (6 from one night) | Medium | Cleanup |
| `_bootstrap_sandbox_deps` found Gemfile but didn't install deps | Medium | Orchestrator |
| KG node_count 0 but API says 60479 for larger KG | Low | API |

### 9. Frontend Routes Found
- `/dashboard` — landing page with widgets, stats, recent activity
- `/analytics` — cost, model usage, trends
- `/digest` — daily/weekly digests
- `/agent` — **primary chat + pipeline interface** (mode toggle + text input + repo URL)
- `/pipeline` — **dedicated pipeline page** (Quick Test + Orchestrate modes)
- `/` — root redirects to `/dashboard`

### 10. Key Architecture Pattern: 3 Separate Auth/Submission Flows

| Flow | Frontend | Backend Endpoint | JobSpec Used? |
|------|----------|-----------------|---------------|
| Agent page → Pipeline | `src/app/(dashboard)/agent/page.tsx` | `POST /api/agent/run` | N/A |
| Pipeline → Orchestrate | `src/app/(dashboard)/pipeline/page.tsx` | `POST /api/delegate` | N/A |
| Pipeline → Quick Test | `src/stores/pipeline-store.ts` | `POST /api/pipeline/from-requirements` | N/A |

**No frontend code references `JobSpec`, `submit_job`, or `runSingle`.** The CONTEXT.md concept of JobSpec as the "handoff payload" exists only in the backend orchestrator. The frontend bypasses it entirely.

---

## Subtask 1: Orchestrator–Subagent Tool Chain Alignment

### Finding

TestAI's orchestrator (`OrchestratorEngine` in `harness/orchestrator.py`) delegates to a coordinator subagent via `DelegateTaskTool`. The coordinator is the "manager" that drives all work. This matches industry pattern: **orchestrator is thin bootstrap, subagent does real work**.

### How peers handle it

| System | Delegation Model | Depth Control |
|--------|-----------------|---------------|
| **TestAI** | Hybrid Adaptive Tree: flat→hierarchical on trigger. 6-layer tool isolation | Max depth=5, adaptive depth triggers |
| **Tembo** | Delegates to external harnesses (Claude Code, Codex, Cursor). Orchestrator manages lifecycle, not tool access | Controlled by external agent |
| **Greptile** | Single agent pipeline: index → review → suggest fix. No subagent tree | N/A — single-pass |
| **GitHub Copilot Agents** | Assigns issues to agents. Agents run asynchronously in cloud. No explicit subagent tree | Fixed 1-level delegation |
| **OpenAI Codex** | Single agent instance per task. CLI-based tool loop | No sub-delegation |

### Gaps in TestAI

- **No A2A wire protocol** — agents communicate via shared Postgres, not standard agent-to-agent protocol. Tembo delegates to external harnesses (Claude Code, Codex) via API, not custom agents.
- **Toolset resolution is filesystem-first** — tools in `harness/tools/` are auto-discovered, but `DELEGATE_BLOCKED_TOOLS` is a hardcoded set. No runtime dynamic tool negotiation.
- **Coordinator cannot write files or run bash directly** — must delegate to leaf workers. This adds round-trip latency for simple tasks.

### Research source  
Codebase exploration (`harness/orchestrator.py`, `harness/tools/delegate_task.py`, `harness/tools/toolsets.py`), Tembo docs (`docs.tembo.io/features/agents.md`), GitHub Copilot docs (`github.com/features/copilot/agents`)

---

## Subtask 2: Knowledge Graph Initialization and Usage

### Finding

TestAI uses **CodeGraph** (tree-sitter AST parser, npm-based) to build a per-project symbol-level knowledge graph. The KG lives in a SQLite DB inside the sandbox (`/workspace/repo/.codegraph/codegraph.db`), with a host-side cache at `agent_workspace/knowledge-graphs/<graph_id>/codegraph.db`.

### How peers handle it

| System | Indexing Approach | Storage | Query Surface |
|--------|------------------|---------|---------------|
| **TestAI** | CodeGraph (tree-sitter AST), incremental re-index on `codegraph init` | SQLite DB in sandbox + host cache | `codegraph_explore`, `codegraph_search`, `codegraph_callers/callees`, `lsp` tools |
| **Greptile** | Builds a graph of functions, classes, dependencies using tree-sitter. Indexes entire repo before any review. Uses Hatchet for async job queue. | Cloud-hosted, per-repo graph DB | PR review comments with full context references. API queries for code search |
| **Tembo** | No explicit knowledge graph. Relies on external agent's own indexing (Claude Code's built-in code search, Codex's file-level understanding) | N/A — defers to harness | N/A — uses agent's native capabilities |
| **GitHub Copilot** | Built-in codebase indexing for context-aware suggestions. Uses embeddings + symbol index | GitHub cloud infrastructure | Inline suggestions, chat with context, code review |

### Gaps in TestAI

- **KG is NOT updated after agent fixes code.** The `codegraph init` runs once at orchestrator setup. After a subagent edits files, the KG is stale. `L1Indexer.promote()` extracts facts from tool calls but does NOT re-run `codegraph sync` in the sandbox consistently.
- **No semantic/vector search** — CodeGraph is symbol-level (functions, classes, imports). No embedding-based semantic search. Greptile uses LLM-powered understanding on top of their graph.
- **Host-side KG is a one-time copy (docker cp).** If the sandbox KG changes during agent execution, the host cache is NOT updated until the next orchestrator run.
- **L1 promoter uses heuristic text parsing** (strings like "path=") instead of structured data extraction — fragile for non-standard tool calls.

### Research source  
Codebase exploration (`harness/codegraph.py`, `harness/services/artifact_store.py`), Hatchet/Greptile case study (`hatchet.run/customers/greptile`), Greptile docs (`greptile.com/docs/introduction`)

---

## Subtask 3: Knowledge Graph Update After Fixes

### Finding

**Current state**: KG is built once at orchestrator start. There is no mechanism for subagents to trigger KG re-indexing after making changes.

### What's needed

| Concern | Current TestAI | Ideal State | Tembo Approach |
|---------|---------------|-------------|----------------|
| AGIter edits file → KG stale | `L1Indexer.promote()` runs at end, extracts facts from tool calls but does NOT re-index sandbox KG | Subagent calls `kg_refresh` tool → `codegraph sync` increments sandbox KG → host cache copies back | No KG concept — each session is fresh. Snapshot system pre-builds environments instead |
| Cross-session memory | L2 memories written to `~/.testai/memories/<repo_slug>/MEMORY.md` at run end | L2 memory should be injected into KG as metadata nodes | No equivalent |
| Multi-agent visibility | Agents share Postgres DB but not KG state | KG should be readable/writable by all agents in same session tree | Uses external standalone harnesses — no multi-agent coordination needed |

### Recommendation

Add a `kg_refresh` tool to the coordinator toolset that:
1. Runs `codegraph sync` in the sandbox
2. Copies updated KG DB to host cache
3. Emits `KGUpdated` event on EventBus
4. Injects updated symbol index into agent context via FIM (fill-in-middle) or diff summary

### Research source  
Codebase exploration (`harness/codegraph.py`, `harness/services/artifact_store.py`, `harness/tools/codegraph_tools.py`)

---

## Subtask 4: Sandbox Lifecycle and Isolation

### Finding

TestAI uses Docker containers with a **session-scoped** sandbox model. `SandboxManager.get_or_create()` reuses existing containers for the same session.

### How peers handle it

| System | Isolation Model | Persistence | Snapshot/Restore | Custom Dependencies |
|--------|----------------|-------------|------------------|-------------------|
| **TestAI** | Per-session Docker container. Named volumes persist across restarts. `RESTRICTED` profile (non-root, read-only rootfs, capabilities dropped) | Container destroyed on session end unless `keep_volume=True`. Volumes reaped by cron (7 day TTL) | `docker commit`-based snapshots (`snapshot/restore`). Labeled images in local Docker cache | `_bootstrap_sandbox_deps()` auto-detects manifest files, runs package managers |
| **Tembo** | Per-session dedicated Linux VM. No two sessions share same VM. 5 sizes (Micro to Ultra). Docker-in-Docker with nested virtualization | Ephemeral — destroyed when session done. No code/state persists. **Snapshots** pre-build VM disks with repos + deps | Pre-built snapshots (VM disk image). Scheduled rebuilds to stay fresh | `tembo.nix` (Nix dev shell) for extra tools. Pre-installed: Node 22, Python 3.12, Ruby 3.3, .NET 9, Docker 28, Go, Rust, Java via Nix |
| **GitHub Copilot Agents** | Cloud-hosted sandbox per task. Microsoft-managed infrastructure | Ephemeral per task | N/A | N/A |
| **Greptile** | Cloud-hosted indexing pipeline. Each repo indexed independently via Hatchet async jobs | Persistent per-repo graph DB | N/A | N/A |

### Gaps in TestAI

- **No per-repo VM isolation** — TestAI uses Docker containers, not VMs. Tembo uses full VMs for stronger isolation boundary (especially important for untrusted code from forks).
- **Volume isolation is session-scoped, not repo-scoped.** Named volumes use session_id, so two runs against the same repo share the same volume. This is good for caching but can cause cross-run contamination if the repo is modified across sessions.
- **No dependency caching at the image level** — `_bootstrap_sandbox_deps()` runs on every new container. Tembo's snapshots pre-build VM disks with deps installed. TestAI's `snapshot/restore` exists but is not integrated into the orchestrator flow (no auto-snapshot before execution).
- **`tembo.nix` equivalent doesn't exist** — custom dependencies require modifying Python code (`_bootstrap_sandbox_deps()`). No user-facing config file for project-specific toolchains.
- **No container size selection** — Tembo offers 5 VM sizes. TestAI uses single Docker image `nikolaik/python-nodejs`.

### Research source  
Codebase exploration (`harness/sandbox_manager.py`, `harness/sandbox_scope.py`, `harness/sandbox/registry.py`), Tembo docs (`docs.tembo.io/features/sandbox/overview.md`, `docs.tembo.io/features/snapshots.md`, `docs.tembo.io/features/sandbox/custom-dependencies.md`)

---

## Subtask 5: Cross-Agent Sandbox Sharing

### Finding

TestAI's `create_worker_env()` creates sibling containers on a shared bridge network (`testai-net-<session_id>`). Siblings share a named volume for artifact exchange but not execution environments. This is the best-in-class pattern.

### How peers handle it

| Feature | TestAI | Tembo | GitHub Copilot Agents |
|---------|--------|-------|----------------------|
| Parallel worker containers | Yes — `create_worker_env()` on bridge network | No — single agent per VM | No — single agent per task |
| Volume sharing between agents | Yes — named volume `testai-ws-<session_id>` | No — sandboxes are fully isolated | No |
| Container recovery on restart | Yes — `_recover_containers()` scans Docker by name pattern | N/A — VMs are ephemeral | N/A |
| Container protocol abstraction | Yes — `ContainerRegistry` Protocol with `InProcessContainerRegistry` adapter | N/A | N/A |

### Gaps

- **Only `InProcessContainerRegistry` is implemented.** The Protocol supports Postgres and Docker-daemon-polling adapters but they don't exist. This means container state is lost on backend process restart (though recovery via Docker name scan partially mitigates this).
- **No explicit cross-container communication model** — siblings share a volume but have no message passing. Artifacts are exchanged via filesystem.
- **No `ContainerRegistry` adapter for Tembo-style Postgres tracking** — cross-process container discovery doesn't exist.

### Research source  
Codebase exploration (`harness/sandbox/registry.py`, `harness/sandbox_manager.py`)

---

## Subtask 6: Artifact Persistence

### Finding

TestAI implements a three-layer architecture (L0/L1/L2) that aligns with industry best practices.

### How peers handle it

| Layer | TestAI | Tembo | Greptile |
|-------|--------|-------|----------|
| **L0 — Raw artifacts** | `agent_artifacts` table (tool calls, results, reflections) | No persistence — sandboxes are ephemeral | PR comments + fixes |
| **L1 — Indexed facts** | `kg_nodes`/`kg_edges` tables via `L1Indexer.promote()` | No equivalent | Knowledge graph (AST-based) |
| **L2 — Cross-run lessons** | Filesystem `~/.testai/memories/<repo_slug>/MEMORY.md` | No equivalent. Hooks (`postClone`, `prePush`) run per-session | Learning system adapts to team feedback (👍/👎 reactions) |

### Gaps

- **L0 → L1 promotion is fragile** — uses text-parsing heuristics on tool call arguments. Should use structured `data` field from tool results instead.
- **Retention TTL is configured but no content-aware archiving** — L2 memories accumulate without size management or relevance decay.
- **No per-artifact configurable TTL** — the design mentions this but only `purge_older_than()` exists at the table level.
- **Artifacts are written at run end only** — `Agent._save_reflections()` runs after the agent completes. Mid-run artifacts (failed attempts, intermediate files) are lost if the session crashes.

### Research source  
Codebase exploration (`harness/services/artifact_store.py`, `harness/memory/schema/schema.sql`)

---

## Subtask 7: Metrics Collection

### Finding

TestAI has extensive metrics infrastructure: EventBus → multiple sinks (DB, SSE, OTel, log). Multiple tables track different metric categories.

### How peers handle it

| Metric | TestAI | Tembo | Greptile | GitHub Copilot |
|--------|--------|-------|----------|---------------|
| Token usage | `token_usage` table per-session per-model | Cloud dashboard (usage-based billing) | N/A | Enterprise dashboard |
| Cost tracking | `budget_tracker.py` + `pricing_cache` | Cloud dashboard | N/A | Enterprise billing |
| Test results | `test_results`, `coverage_reports`, `flaky_tests` | N/A | N/A | N/A |
| Execution timing | `trace_events`, `EventBus` timestamps | Session duration tracking | ~3 min avg review time | N/A |
| Sandbox metrics | `sandbox_metrics` (CPU, memory, IO) | Cloud dashboard | N/A | N/A |
| Quality metrics | `quality_metrics` table + L1 extraction | N/A | Learning system (reactions) | N/A |

### Gaps

- **Metrics are fragmented** — `pipeline_metrics`, `sandbox_metrics`, `quality_metrics`, `trace_events` all track similar concerns without a unified schema.
- **Budget auto-throttle is partially implemented** — `BudgetTracker` snapshots are collected but the 4-step throttle ladder (switch HITL → demote parallel → cheaper model → pause) is not wired to change agent behavior.
- **No standardized observability schema** — OTel integration exists but is optional. Teams relying on the DB tables get inconsistent metric shapes.
- **No code review quality metrics** — unlike Greptile's learning system (tracks 👍/👎 reactions to tune review suggestions), TestAI doesn't measure whether its suggestions are actually useful.

### Research source  
Codebase exploration (`harness/events.py`, `harness/budget_tracker.py`, `harness/cost_tracker.py`, `harness/memory/schema/schema.sql`), Greptile docs, Tembo docs

---

## Subtask 8: Configuration and Customization

### Finding

TestAI has a rich configuration system: environment variables, DB-backed settings tables, YAML agent definitions, filesystem skill discovery, MCP configs.

### How peers handle it

| Feature | TestAI | Tembo | Greptile | GitHub Copilot |
|---------|--------|-------|----------|---------------|
| Rule files | Agent .md YAML frontmatter | `tembo.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules` — first-found | Custom context files (style guides, arch docs) | `.github/copilot-instructions.md` |
| Skills | `SKILL.md` filesystem registry + DB mirror | `.claude/`, `.codex/`, `.opencode/`, `.cursor/` in repo root. UI-managed skills in Settings | N/A | N/A |
| Hooks | Plugin system (`hooks/`) + event-driven | `.tembo.json` hooks: `postClone`, `prePush` | N/A | N/A |
| Custom deps | `_bootstrap_sandbox_deps()` auto-detects | `tembo.nix` (Nix dev shell) | N/A | N/A |
| MCP | `mcp.json` → `mcp_configs` table. Full MCP client with OAuth, circuit breaker | MCP servers — agents access integrations through MCP | CLI bridge to external agents | Custom MCP servers in GitHub |
| Model selection | `provider_configs` table + env overrides. LLMRouter | Cloud UI: choose harness + model per session | Self-hosted: custom LLMs. Cloud: managed | UI: choose Copilot, Claude, Codex |
| Agent definitions | YAML frontmatter `.md` files. Resolution: DB → project `_custom/` → built-in | Agent Studio: agent defs as files in Git repo | N/A (single-purpose) | UI: custom agents via Copilot Extensions |

### Gaps

- **Filesystem vs DB dual source** — Agent definitions, skills, and MCP configs are filesystem-first with DB mirrors. Sync happens at startup with `ON CONFLICT DO NOTHING`. Filesystem changes during runtime don't reflect until restart.
- **No Tembo-style `tembo.nix`** — custom dependencies require code changes to `_bootstrap_sandbox_deps()`. A Nix-based approach would let users declaratively specify toolchains.
- **No `.tembo.json` equivalent** — missing hooks at the `postClone` and `prePush` lifecycle points that users can configure without touching backend code.
- **Agent definition resolution is complex** — 3-tier lookup (DB → project custom → built-in YAML) with startup warning on override. Could be simplified with a single override file per agent.

### Research source  
Codebase exploration (`harness/agent_config.py`, `harness/agent_discovery.py`, `harness/tools/skill_tools.py`, `harness/mcp/config_manager.py`), Tembo docs (`docs.tembo.io/features/rule-files.md`, `docs.tembo.io/features/hooks.md`, `docs.tembo.io/features/agent-skills.md`), GitHub docs

---

## Subtask 9: Repo Pull and Bootstrap Flow

### Finding

TestAI clones repos into sandbox via shallow clone (depth=1), auto-detects language from manifest files, installs deps, builds KG, then runs explore agents.

### How peers handle it

| Step | TestAI | Tembo | Greptile |
|------|--------|-------|----------|
| Clone | `git clone --depth 1 --branch {branch}`. Local repos via `docker cp` + `git init` | Internal clone. Snapshots pre-clone for speed | Clones via GitHub/GitLab integration. Indexes via Hatchet |
| Branch handling | Specified or default branch | Configurable per session | All branches on PR events |
| Dep install | Auto-detect from manifest files (package.json, requirements.txt, Gemfile, go.mod, Cargo.toml, build.gradle, pom.xml) | Pre-installed in base image + `tembo.nix` extras. Snapshots pre-build | Not applicable (read-only indexing) |
| Context repos | Optional read-only `/workspace/context/{name}/` | Not supported | Not supported |
| GH_TOKEN injection | Loads from `integration_configs` DB table | Configured in integration settings | OAuth app installation |

### Gaps

- **No sparse checkout** — monorepos with 10K+ files clone everything. Could use `git clone --filter=blob:none` for partial clone.
- **Dep install is all-or-nothing** — `_bootstrap_sandbox_deps()` runs every detected package manager. No way to skip or customize per project.
- **No progress streaming from sandbox to UI** — clone and dep install happen as blocking function calls. User sees nothing until setup completes.
- **No snapshot pre-build** — Tembo's snapshot system pre-builds VM disks with repos + deps. TestAI runs setup fresh every time.

### Research source  
Codebase exploration (`harness/orchestrator.py` `run_single()` method, `_bootstrap_sandbox_deps()`)

---

## Subtask 10: Kanban / Task Tracking Integration

### Finding

TestAI uses Kanban as **passive observability** — the coordinator creates tasks, completes them, but the board is a tracking surface, not a driver of agent behavior.

### How peers handle it

| Feature | TestAI | Tembo | GitHub Copilot |
|---------|--------|-------|---------------|
| Task creation | `orchestrate()` decomposes goal into 2-6 tasks on kanban board | Session created via API. Agent assigned to task | Issue assigned to Copilot via UI |
| Task tracking | Kanban columns: backlog→ready→in_progress→review→done→flaky_heat | Session status: pending→in_progress→completed→failed | Agent task status in dashboard |
| Task blocking | `kanban_block/unblock` with auto-block after `failure_limit` failures | Not exposed — Tembo handles internally | Not exposed |
| Dependency tracking | `kanban_dependencies` table with `kanban_link` tool | Not supported | Not supported |
| WIP limits | Board-level WIP limits configurable | Not supported | Not supported |
| Board scoping | `TESTAI_KANBAN_BOARD` env var isolates subagent access | Not applicable (single agent) | Not applicable (single agent) |

### Gaps

- **Kanban is not the driver** — the dispatcher loop reconciles but doesn't actively steer agents. Tembo/GitHub Copilot let the external system (Linear, GitHub Issues, Slack) drive task assignment.
- **Review agent uses LLM** — `run_review_agent` polls every 30s and calls LLM to approve/reject. Expensive and adds latency. Greptile uses 👍/👎 reactions (simpler, cheaper).
- **No external event integration into kanban flow** — GitHub Issues, Linear tickets, and Sentry errors are tracked in the DB (`discovery_loop` polls them) but don't auto-create kanban tasks.

### Research source  
Codebase exploration (`harness/services/kanban_service.py`, `harness/tools/kanban_agent_tools.py`, `harness/dispatcher.py`)

---

## Subtask 11: Self-Healing and Error Recovery

### Finding

TestAI has basic self-healing: retry + backoff + jitter, circuit breaker for subagent calls, checkpoint/resume, stale claim reaper.

### How peers handle it

| Mechanism | TestAI | Tembo | Greptile |
|-----------|--------|-------|----------|
| Retry | `_call_child_with_enhancements()` — exponential backoff + jitter | Internal agent retry | N/A (single-pass indexing) |
| Circuit breaker | 5 failures → 60s cooldown (MCP client) | N/A | N/A |
| Checkpoint | `checkpoint.py` — session state serialization | N/A | N/A |
| Resume abandoned | `resume_abandoned()` — finds sessions with no heartbeat >5min | Not supported | Not supported |
| Stale claim reaper | Every 120s — reclaims tasks with expired TTL (1 hour) | Not supported | Not supported |
| Auto-fix hook failures | Not implemented | `autoFix: true` in `.tembo.json` — agent analyzes hook failures and retries | Not supported |
| Feedback loop | Not natively supported — user must re-submit job | `@tembo` in PR comments → iterates and pushes new commits | `@greptileai` in PR comments → conversational interaction |

### Gaps

- **No Tembo-style feedback loop** — user can't comment `@tembo` on a PR to request changes. They must submit a new job or edit the kanban board.
- **Checkpoint/resume is not integrated with kanban** — resuming restarts the agent from scratch rather than picking up at the last completed kanban task.
- **Auto-fix for hook failures doesn't exist** — Tembo's `autoFix: true` lets the agent analyze CI failures and retry. TestAI fails open if a hook command fails.
- **No PR feedback iteration** — Greptile supports conversational follow-up on review comments. TestAI has no equivalent.

### Research source  
Codebase exploration (`harness/checkpoint.py`, `harness/tools/delegate_task.py`, `harness/mcp/client.py`, `harness/dispatcher.py`), Tembo docs (`docs.tembo.io/features/hooks.md`, `docs.tembo.io/features/feedback-loop.md`), Greptile docs

---

## Subtask 12: Comparative Analysis Summary

### Overall Architecture Comparison

| Dimension | TestAI | Tembo | Greptile | GitHub Copilot Agents |
|-----------|--------|-------|----------|----------------------|
| **Orchestrator** | Custom Python (OrchestratorEngine) | Cloud orchestration layer | Cloud pipeline with Hatchet | GitHub cloud infra |
| **Agent runtime** | Custom Agent (LLM + tool loop) | External: Claude Code, Codex, Cursor | N/A (single-purpose reviewer) | External: Copilot, Claude, Codex |
| **Sandbox** | Docker per session | VM per session | Cloud workers (Hatchet) | Cloud-managed |
| **Knowledge Graph** | CodeGraph (tree-sitter SQLite) | None (defers to agent) | Custom graph (AST-based) | Built-in codebase index |
| **Artifacts** | L0→L1→L2 (DB + filesystem) | Ephemeral (snapshots optional) | PR comments + suggestions | GitHub ecosystem |
| **Config** | YAML agent defs + env vars + DB | Agent config + tembo.nix + rules | Web UI + custom context | copilot-instructions.md |
| **Task tracking** | Kanban board (passive) | Session-based (API) | GitHub PR integration | GitHub Issues |
| **Feedback loop** | Re-submit job | `@tembo` PR comments | `@greptileai` PR comments | PR mentions + chat |

### Where TestAI Leads

1. **Subagent tree depth** — Hybrid Adaptive Tree with depth control. Tembo/Greptile don't have multi-level subagent hierarchies.
2. **Kanban with dependency tracking** — `kanban_dependencies` table, WIP limits, board scoping. Unique feature.
3. **Three-layer memory** — L0 raw artifacts → L1 indexed facts → L2 cross-run lessons. Greptile has only graph, Tembo has none.
4. **Multi-repo orchestration** — `run_multi()` for cross-repo changes. Tembo supports this via Agent Actions but TestAI's approach is more structured.
5. **Container abstraction Protocol** — Multiple backends possible (Postgres, Docker daemon). Not fully utilized yet.

### Where TestAI Lags

1. **VM-level isolation** — Tembo uses VMs with 5 sizes and nested Docker. TestAI uses only Docker containers.
2. **SNAPSHOT Pre-build** — Tembo's snapshot system pre-builds VM images with repos + deps. TestAI's snapshot is not integrated into the orchestrator flow.
3. **Nix-based custom dependencies** — `tembo.nix` is elegant. TestAI's approach requires code changes.
4. **Feedback loop on PRs** — `@tembo` in PR comments is simpler than re-submitting jobs. Greptile's `@greptileai` is similarly seamless.
5. **Hooks lifecycle** — `postClone`/`prePush` with `autoFix`. TestAI has hooks but no user-configurable pre-commit/pre-push hooks.
6. **KG updates after agent work** — Tembo doesn't need this (ephemeral). Greptile doesn't modify code. TestAI modifies code but doesn't re-index KG.
7. **Browser automation / computer use** — Tembo agents can use Playwright via Kernel integration. TestAI has `computer_use` tool but it's gated and not as well-integrated.
8. **Third-party agent harness compatibility** — Tembo lets you use Claude Code OR Codex OR Cursor interchangeably. TestAI has its own custom Agent.

### Research source  
All of the above — compiled from codebase exploration and 15+ fetched documentation pages from Tembo, Greptile, GitHub Copilot, and Hatchet.

---

## Subtask 13: Consolidated Recommendations

### Immediate (High Impact, Low Effort)

1. **Add `kg_refresh` tool** — let agents trigger `codegraph sync` after edits. ~2 days.
2. **Wire budget auto-throttle** — implement the 4-step ladder in `BudgetTracker`. ~3 days.
3. **Add `.tembo.json`-style hooks** — user-configurable `postClone`/`prePush` in `.testai/config.json`. ~2 days.
4. **Add feedback PR loop** — `@testai` mentions in PR comments trigger iteration. ~5 days.
5. **Stream sandbox setup progress** — emit `StatusEvent` events during clone/dep install for SSE consumers. ~2 days.

### Medium (High Impact, Medium Effort)

6. **Implement `tembo.nix` equivalent** — `.testai/sandbox.nix` for declarative toolchain dependencies. ~5 days.
7. **Integrate snapshots into orchestrator** — auto-snapshot sandbox before execution, restore on retry. ~5 days.
8. **Replace L1 text heuristics with structured data** — use tool result `data` fields instead of `old_string`/`new_string` parsing. ~3 days.
9. **Add sparse checkout support** — `git clone --filter=blob:none` for monorepo efficiency. ~1 day.
10. **Implement Postgres `ContainerRegistry`** — cross-process container tracking. ~4 days.

### Long-Term (High Impact, High Effort)

11. **A2A wire protocol adapter** — enable standard agent-to-agent communication alongside Postgres. ~3 weeks.
12. **OpenTelemetry unified schema** — merge pipeline_metrics, sandbox_metrics, quality_metrics into a single OTel schema. ~2 weeks.
13. **Add semantic/vector search to KG** — commit-level embeddings alongside symbol-level CodeGraph index. ~3 weeks.
14. **External harness compatibility** — support running Claude Code / Codex as subagents instead of custom Agent. ~4 weeks.
15. **VM-level sandbox option** — optional VM isolation for untrusted code execution. ~4 weeks.

---

## Subtask 14: Deep Dive — Sandbox Ephemeral vs Persistent Pattern (Tembo Model)

### Additional finding from Tembo blog

Tembo's model is **fully ephemeral**: "Sandboxes are ephemeral: spun up for the session, destroyed when it's done. No code or state persists after execution." This is a deliberate design choice that solves:

| Problem | Tembo Solution | TestAI Implication |
|---------|---------------|-------------------|
| State corruption across runs | Fresh VM per session — impossible | Named volumes with session_id — possible but mitigated by keep_volume=True |
| Dependency drift | Snapshot pre-build with scheduled rebuild | Dep install runs every time — inconsistent if upstream packages change |
| Security from untrusted code | VM boundary (optional enforced) | Docker container boundary with RESTRICTED profile |
| Repo isolation | Dedicated VM per repo per session | Shared named volume per session_id — two sessions for same repo share state |

### Key architectural insight

Tembo's sandbox flow:
1. VM boots from latest snapshot (pre-built with repos + deps) OR fresh
2. `tembo.nix` dev shell activated for project-specific toolchains
3. Agent works in isolated environment
4. On completion: PR opened, VM destroyed, no state kept

TestAI's sandbox flow:
1. Container created/reused via `get_or_create()`
2. `_bootstrap_sandbox_deps()` auto-detects and installs
3. Agent works in container
4. On completion: kanban updated, container kept (volume persisted), KG cached to host

**The fundamental difference**: Tembo is **stateless-by-design** — each session is a fresh start. TestAI is **stateful-by-design** — sessions accumulate state across runs via volumes + KG cache. Both are valid, but TestAI's approach requires more careful state management (volume lifecycle, KG staleness, memory accumulation).

### Recommendation

Keep the stateful approach for TestAI (it enables L2 cross-run memory and incremental KG). But add:
- Explicit "reset" mode that wipes the volume for a clean start
- Volume per (repo, branch) combo, not just session_id, to prevent cross-issue contamination
- Snapshot integration: auto-snapshot before agent starts, restore if retry needed

### Research source  
Tembo blog (`tembo.io/blog/background-coding-agents`), Tembo sandbox docs (`docs.tembo.io/features/sandbox/overview.md`), codebase exploration (`harness/sandbox_manager.py`)

---

## Subtask 15: Deep Dive — Feedback Loop and PR Iteration

### Finding from Tembo and Greptile

Both Tembo and Greptile support **asynchronous PR iteration** via mentions:

**Tembo**: `@tembo` in PR comments → agent analyzes comment → updates code → pushes new commits
**Greptile**: `@greptileai` in PR comments → agent responds conversationally, explains reasoning

TestAI: No equivalent mechanism. User must submit a new `JobSpec` or edit the kanban board.

### The gap matters because

The feedback loop is the primary way developers interact with agentic systems in production:
- Tembo: "Add retry logic with exponential backoff" → agent does it → PR updated
- Greptile: "Why did you flag this?" → agent explains → developer learns
- TestAI: User must go back to chat → re-submit job → new session starts from scratch

### Implementation model

```
┌──────────┐     ┌──────────────┐     ┌────────────┐
│ PR Comment│────▶│ @testai      │────▶│ Agent reads │
│ "@testai  │     │ mention      │     │ comment +   │
│  fix this"│     │ detected     │     │ code        │
└──────────┘     └──────────────┘     └──────┬─────┘
                                            │
                                            ▼
                                     ┌──────────────┐
                                     │ Agent makes   │
                                     │ changes,      │
                                     │ pushes commit │
                                     └──────────────┘
```

Webhook from GitHub PR comment → `@testai` detection → resume or create new subagent with PR context → agent iterates → pushes update.

### Research source  
Tembo docs (`docs.tembo.io/features/feedback-loop.md`), Greptile docs (`greptile.com/docs/developer-quick-reference`)

---

## Subtask 16: Deep Dive — Codebase Indexing Pipeline Comparison

### Finding

The indexing pipeline is the most architecturally divergent feature between frameworks:

| Aspect | TestAI (CodeGraph) | Greptile | Tembo |
|--------|-------------------|----------|-------|
| **Parser** | tree-sitter (via CodeGraph npm package) | tree-sitter (custom) | None (defers to agent harness) |
| **Storage** | SQLite DB (sandbox + host cache) | Cloud graph DB (Hatchet-managed) | None |
| **Symbols** | Functions, classes, imports, variables, methods | Functions, classes, files, directories, dependencies | None |
| **Relationships** | Callers/callees, imports, class hierarchy | Full codebase dependency graph | None |
| **Query** | `codegraph_search`, `codegraph_explore`, `codegraph_node` | API queries + PR review context | Agent-native (Claude Code's built-in search) |
| **Incremental** | Yes — `codegraph init` re-indexes changed files | Yes — new PRs trigger partial re-index | N/A |
| **Vector search** | No — symbol-only | No — AST-only, but LLM-powered understanding on top | N/A |

### Greptile's key differentiator

Greptile indexes the **entire repo before reviewing any PR**. This is their core value prop. From the Hatchet case study:
> "Greptile tackles the challenge of providing full codebase comprehension, using LLMs to accurately answer difficult questions by understanding the context of large, complex, and even multiple repositories."

They use **Hatchet** as an async job queue to handle large repo indexing without blocking. TestAI does similar async work (explore agents, coordinator spawn) but the KG build happens synchronously in the orchestrator's `run_single()`.

### Recommendation

- Convert KG build to async (like Greptile with Hatchet) so the orchestrator can proceed with setup while indexing completes
- Add Hatchet / Celery / temporal.io-style async job queue for heavy operations (KG build, dep install, large repo clone)
- Consider adding vector embeddings alongside CodeGraph symbols for semantic search

### Research source  
Hatchet/Greptile case study (`hatchet.run/customers/greptile`), Greptile docs (`greptile.com/docs/introduction`), codebase exploration (`harness/codegraph.py`, `harness/orchestrator.py`)

---

## Subtask 17: Deep Dive — Three-Layer Memory vs Ephemeral Session

### The architectural choice

| | TestAI (Stateful) | Tembo (Stateless) | Greptile (Hybrid) |
|---|---|---|---|
| Memory model | L0→L1→L2 persistence across sessions | No cross-session state | Graph persists, reviews don't |
| KG evolution | Manual — `codegraph init` at setup, no mid-session update | None | Persistent graph, updated on new PRs |
| Cross-run lessons | MEMORY.md files per repo, injected at session start | None | Learning system (👍/👎 reactions) adjusts review behavior |
| Failure recovery | Checkpoint/resume with kanban task state | Fresh retry from scratch | N/A |

### The key insight

TestAI's three-layer architecture is **more ambitious** than peers. Tembo chose ephemeral simplicity. Greptile chose persistent graph + ephemeral sessions. TestAI chose persistent everything.

This means TestAI has:
- **More value** when it works (cross-run learning, artifact tracking, KG evolution)
- **More surface area for bugs** when it doesn't (KG staleness, L1 heuristic fragility, memory accumulation without decay)

### What's missing for this to work at scale

1. **KG evolution** — must update after agent writes code
2. **Memory relevance decay** — L2 memories accumulate without age-based or relevance-based pruning
3. **Artifact retention** — `purge_older_than()` at table level, not per-artifact TTL
4. **Vector search for memories** — L2 lessons are plain markdown files with no semantic retrieval

### Research source  
Codebase exploration (`harness/services/artifact_store.py`, `harness/codegraph.py`), Tembo blog, Greptile docs

---

## Subtask 18: Deep Dive — Cross-Sandbox Communication and Coordination

### Finding

TestAI has the most sophisticated cross-agent communication of any reviewed framework, but it's all internal (Postgres + direct function calls).

| Scenario | TestAI | Tembo | Greptile |
|----------|--------|-------|----------|
| Parent→child communication | Direct function call (`DelegateTaskTool.run()`), return value via Python | N/A — single agent per session | N/A |
| Sibling communication | Shared named volume (`testai-ws-<session_id>`) | N/A — single agent per VM | N/A |
| Cross-session data sharing | Postgres + filesystem memories | No cross-session | Persistent graph DB |
| External coordination | EventBus → SSE, webhook, Slack | API → webhook | GitHub PR comments |
| Multi-repo coordination | `run_multi()` — serial per-repo execution | Agent Actions — single session, multiple repos | N/A |

### The gap

No **push-based completion notification**. The orchestrator polls kanban (`_wait_for_board` with 15s interval, up to 90 min). Tembo's API returns session results directly. Greptile posts PR comments.

### Recommendation

Add event-driven completion: when kanban board moves to "done", emit `BoardCompleted` event on EventBus → orchestrator subscriber picks it up immediately instead of polling.

### Research source  
Codebase exploration (`harness/events.py`, `harness/orchestrator.py`), Tembo API docs (`docs.tembo.io/api/index.md`)
