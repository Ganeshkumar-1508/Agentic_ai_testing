# TestAI Production Research Findings

## Date: June 25, 2026
## Objective: End-to-End System Validation & Research

### Initial Plan
The goal is to validate the TestAI production system end-to-end using a real GitHub repository (rails/rails). We need to verify:

1. **Orchestrator-Subagent Sync**: Can orchestrator spawn subagents with proper tool/skill/MCP access?
2. **Sandbox Lifecycle**: Is repo pulled correctly? Is sandbox isolated? Can agents reuse sandboxes?
3. **Knowledge Graph**: Is KG generated? Can agents query and update it after code changes?
4. **Kanban Board**: Are tasks tracked properly (open/closed/blocked/under-review)?
5. **Artifact Persistence**: Are test files, configs, and other artifacts stored durably?
6. **Metrics Collection**: Are token usage, costs, and other metrics tracked?
7. **User Experience**: Can users see sandbox activity, select issues/PRs, and interact with agents?
8. **Entry Points**: Unify run_single/run_multi into a single user-friendly interface.

### API Configuration
- Model: deepseek-v4-flash
- URL: https://opencode.ai/zen/go/v1
- API Key: [REDACTED]

---

## Research Findings - Track 1: Production-Grade Agent Harnesses

### 1. GREPTILE — AI Code Review with Execution Layer

**Overview:** Greptile is a $25M Series A funded AI code review platform used by Brex, Nvidia, Klaviyo, Retool, and PostHog. It constructs a graph index of repositories and uses a swarm of specialized agents to review PRs with full codebase context.

**Key Architecture Points:**
- **Graph Indexing**: Builds a full graph of every repository — files, functions, classes, and dependencies
- **Multi-Agent Orchestration**: Main orchestrator + TREX subagents running in parallel
- **Context Sharing**: TREX inherits main agent context (key insight: separate agents with separate contexts leads to wasted compute and overlapping work)
- **Sandbox**: Disposable per-review sandbox, reusable base images + per-repo snapshots
- **Cache Strategy**: "A cache that includes too little is slow. A cache that includes too much becomes haunted."
- **Artifacts**: Multi-modal (screenshots, logs, API traces, execution scripts, video capture)
- **PR Integration**: Results as PR comments with "Fix with your Agent" button (Claude Code, Codex, Cursor, Devin)

### 2. TEMBO AI — Orchestration Layer for Coding Agents

**Overview:** Tembo is a coding agent orchestration platform that works autonomously with Claude Code, Cursor, Codex, etc. Offers both cloud and self-hosted (Tembo Agent Studio, TAS) options.

**Key Architecture Points:**
- **Sandbox**: Docker containers + Full VMs (8GB RAM, 4 CPUs) — each task in isolated sandbox
- **Agent Delegation**: Platform-level orchestration dispatches separate agents per repository
- **Knowledge Sharing**: realtor `AGENTS.md` / `tembo.md` files define coding standards, API contracts, inter-service boundaries
- **Isolation-First**: Rather than synchronizing state in real time, Tembo resolves conflicts at merge time. Each agent works on its own branch in its own sandbox.
- **PR-Based Integration**: Changes only leave the sandbox as pull requests
- **Observability**: Real-time log streaming, Task Inbox for human review, operational dashboards

### 3. MABL — Agentic Testing Platform

**Overview:** Low-code, cloud-native, AI-native testing platform. "Coverage that builds itself, runs itself, and recovers itself."

**Key Architecture Points:**
- **Test Creation Agent (TCA)**: Conversational and collaborative test planning
- **Self-Healing**: GenAI-powered auto-healing for UI changes, timing issues, data drift
- **Auto TFA (Test Failure Analysis)**: Autonomously triages all test failures
- **Enterprise Dashboards**: Account-level dashboards, quality scores, audit trails
- **MCP Server**: Expands context and integration with Jira, X-Ray, IDEs, and third-party agents

### 4. TESTSPRITE — Autonomous AI Testing (MCP-Native)

**Overview:** The most "agent-native" testing platform — built explicitly as an agentic testing platform that lives inside AI IDEs and communicates via MCP.

**Key Architecture Points:**
- **Multi-Agent Architecture**: Parallel agent fleet opening live app at once and clicking through every feature
- **Cloud Sandbox Execution**: Tests run in isolated cloud environments — never mocks
- **Failure Bundles for Agents**: Single self-consistent bundle: failing step + neighbors, screenshots, DOM snapshots, test source, root-cause hypothesis, recommended fix
- **Coverage Compounding**: Every passing test is kept. Each phase, TestSprite adds dozens more, so coverage grows in lockstep with the build
- **Requirements Met Metric**: With verification loop, feature delivery climbs from 42% to 92%

### 5. Comparative Matrix

| Dimension | Greptile | Tembo | Mabl | TestSprite |
|-----------|----------|-------|------|------------|
| **Primary Use** | AI Code Review | Code Agent Orchestration | Test Automation | Agentic Testing |
| **Agent Model** | Swarm of Review Agents | Multi-Harness Orchestrator | Single Agentic Tester | Parallel Agent Fleet |
| **Sandbox** | Disposable per-review (TREX) | Docker / VM isolation | Cloud environments | Cloud sandboxes |
| **Multi-Agent** | Orchestrator + TREX subagents | Yes, per-repo per-agent | No (single platform) | Yes, parallel fleet |
| **Knowledge Graph** | Full graph index of repos | AGENTS.md / tembo.md rules | Test semantic search | PRD parsing + structured internal PRD |
| **Self-Healing** | N/A (reviewer, not tester) | N/A | Auto-healing (UI changes) | Auto-healing (selectors, timing, data) |
| **Observability** | PR comments, artifacts (screenshots, video) | Dashboard, Slack, Linear, Task Inbox | Enterprise dashboards, MCP server | Live preview grid, video replay, CLI |
| **Artifact Persist** | PR comments, multi-modal artifacts | Linked PRs, append-only audit trails | Logs, screenshots, videos, diffs | Test suites, failure bundles |
| **Context Sharing** | TREX inherits main agent context | Shared rule files, isolation-first | Test library semantic search | Failure bundles for agents |

### Key Patterns Across Systems

1. **Orchestrator + Subagent is the Dominant Pattern**: Every production system uses orchestration rather than single monolithic agent.
2. **Sandbox Isolation is Non-Negotiable**: All systems run agents in isolated environments.
3. **Context Inheritance > Separate Contexts**: Greptile's key insight — separate agents with separate contexts leads to wasted compute.
4. **Artifacts Are the Trust Signal**: Heavy investment in evidence that proves the agent did what it claimed.
5. **PR-Based Integration Creates Natural Checkpoints**: Agents propose changes, humans review.
6. **Knowledge Sharing Uses File-Based Contracts**: AGENTS.md, tembo.md, graph indexes, PRDs.

---

## CODEBASE DEEP-DIVE: TestAI Architecture Review

Codebase stats: 10,809 files, 221,917 nodes, 543,802 edges, 1.15 GB codegraph DB

---

### A. ORCHESTRATOR & SUBAGENT SYNC — STATUS: WORKING

Flow: `POST /api/jobs` -> `submit_job_to_orchestrator()` -> `OrchestratorEngine.run_job_spec()` -> `run_single()` -> sandbox + clone + bootstrap + KG index + explore agents + kanban create + coordinator spawn

Key files:
- `backend/harness/orchestrator.py:76` — `OrchestratorEngine` class
- `backend/harness/tools/delegate_task.py` — `delegate_task` tool
- `backend/harness/agent/agent.py:64` — `Agent` class with `create_subagent()`

Subagent spawning uses context variable pattern to propagate runtime state:
- `set_current_tracker(tracker)` — budget tracker per subagent
- `set_current_kg_context(kg_ctx)` — KG context for subagent kg_refresh tool
- `set_current_git_runner(git_runner)` — shared git runner for worktree isolation
- `set_current_spec_id(spec_id)` — spec_id for pause/cancel propagation

Tool isolation is 6-layer model: child tools = requested intersection parent, always-blocked set for leaf workers, orchestrator exception retains delegate_task, MCP allow-list per subagent, skills scoped to subagent goal, credentials injected per-task at spawn time.

Delegation modes in `delegate_task` (line 2074):
- Sync: single child, blocks until done
- Fan-Out: tasks array -> parallel ThreadPoolExecutor (default max 12 concurrent)
- Background: fire-and-steer, results delivered via completion queue

Subagents are properly spawned with inherited context. Activity recorded via `Agent.get_activity_summary()` for heartbeat/stale detection. Tool calls persisted in messages.

---

### B. SANDBOX LIFECYCLE — STATUS: WORKING, MINOR GAPS

Key files:
- `backend/harness/sandbox_manager.py:311` — SandboxManager.get_or_create()
- `backend/harness/sandbox/registry.py` — InProcessContainerRegistry
- `backend/harness/services/sandbox_bootstrap.py` — SandboxBootstrap

Lifecycle flow:
1. sandbox_manager.get_or_create(session_id, volume_key=repo_url)
2. Creates Docker container with per-session volume
3. Clones repo to /workspace/repo (depth=1)
4. _bootstrap_sandbox_deps() detects language + installs deps
5. Creates per-session worktree (isolated branch)
6. KnowledgeGraphSyncer.index() builds KG on volume
7. Coordinator + subagents run
8. KnowledgeGraphSyncer.sync() updates KG after edits
9. Worktree cleanup, container stays for reuse

Isolation strategy:
- Per-run Docker container with its own filesystem
- Volume keyed by repo_url — same repo gets same volume (dependency caching)
- Per-session worktree — each orchestrator run gets its own branch
- Per-subagent worktree — each subagent branches off session worktree
- Container registry with TTL-based stale reaping (reap_stale)
- destroy_env is optional, defaults to keep_volume=True
- Host-side KG cache at agent_workspace/knowledge-graphs/<repo_hash>/

Reuse: Same session_id + same volume_key -> same container. Dependencies cached inside volume. Worktrees cleaned up after run but base image + deps persist.

Gap: No warm base-image layering yet. C03 Phase 2 mentions (language, manifest_hash) warm images as F11 deepening but not implemented. No docker image prune or disk quota monitoring.

---

### C. KNOWLEDGE GRAPH — STATUS: WORKING, KG MUTATION SUPPORTED

Key files:
- `backend/harness/services/knowledge_graph_syncer.py:147` — KnowledgeGraphSyncer.index()
- `backend/harness/services/knowledge_graph_syncer.py:242` — KnowledgeGraphSyncer.sync()
- `backend/harness/codegraph.py` — index_project, copy_db_to_host, restore_db_from_host, get_status
- `backend/harness/tools/kg_refresh_tool.py` — KgRefreshTool
- `backend/harness/agent/agent.py:505` — _schedule_kg_refresh()

Build flow (KnowledgeGraphSyncer.index):
1. Check sandbox volume for existing KG, restore from host cache if available
2. Run codegraph init --index (incremental build on existing DB)
3. Mirror freshly-built DB to host cache
4. Write provenance (repo URL, branch, graph_id, session_id, node/edge counts)

Update flow (KnowledgeGraphSyncer.sync post-coordinator):
1. Run codegraph sync (incremental re-index after agent edits)
2. Mirror updated DB to host cache
3. Update provenance

Auto-refresh (Agent._schedule_kg_refresh):
- Fires after write_file, edit_file, apply_patch tool calls
- Debounced to 60 seconds
- Non-blocking (fire-and-forget via asyncio.create_task)
- Uses KgRefreshTool.run(force=False) which skips if < 60s since last refresh

Provenance: provenance.json at host dir stores last_indexed_at timestamp compared against git log to detect staleness.

KG is built, queried, AND updated after code changes. This is ahead of Greptile and Tembo which are read-only.

---

### D. KANBAN BOARD — STATUS: WORKING

Key files:
- `backend/harness/tools/orchestrator_tool.py` — cmd_orchestrate, orchestrate_monitor
- `backend/harness/kanban/` — board management
- `src/app/(dashboard)/kanban/page.tsx` — frontend kanban UI

Flow:
1. cmd_orchestrate(goal, repo_context, board_name, session_id) decomposes goal into tasks, creates board in DB
2. Board ID threaded into coordinator goal: KANBAN BOARD: {board_id}
3. Coordinator uses orchestrate_monitor to track progress
4. Task states: open, in_progress, completed, blocked, under_review
5. board.completed / board.failed events routed via EventSourceSink

Board creation, task tracking, and event emission are all functional.

---

### E. ARTIFACT PERSISTENCE — STATUS: WORKING

Key files:
- `backend/harness/recording.py` — SessionRecorder
- `backend/harness/events.py` — EventBus, EventSourceSink, StreamEvent
- `backend/harness/results_store.py` — result persistence
- `backend/harness/store/` — Postgres-backed JobSpecStore

Persistence layers:
1. Messages: every agent message recorded via SessionRecorder
2. Job specs: persisted in JobSpecStore with status, output, comments
3. Cost/token data: tracked in token_ledger, cost_tracker -> Postgres
4. KG data: host cache at agent_workspace/knowledge-graphs/ + provenance.json
5. Test files: committed to git branches in sandbox volumes
6. Artifact TTLs: committed test files = permanent, trajectories = 30d, LLM transcripts = 7d

Artifacts surfaced via /api/jobs/{spec_id}/output, EventSourceSink SSE stream, and dashboard kanban view.

---

### F. METRICS & COST TRACKING — STATUS: WORKING

Key files:
- `backend/harness/cost_tracker.py` — per-LLM-call cost tracking
- `backend/harness/budget_tracker.py` — BudgetTracker with 4 scopes
- `backend/harness/pricing_cache.py` — model pricing data
- `src/components/settings/BudgetSettings.tsx` — frontend budget config

Budget scopes: subagent ($0.50 soft / $1.00 hard), phase ($2.00 / $3.00), run ($5-10 / $10-20), user_day ($50 / $75).

Auto-throttle ladder (4 steps): HITL mode -> sequential -> cheaper model -> pause.

Child cost aggregation: delegate_task folds subagent costs into parent session_estimated_cost_usd across the tree.

---

### G. USER EXPERIENCE & OBSERVABILITY — STATUS: MOSTLY WORKING, GAPS

Key files:
- `backend/api/routers/jobs.py:228` — submit, list, get, cancel, pause, resume
- `backend/harness/events.py` — EventSourceSink (SSE stream)
- `backend/harness/chat/` — chat interface

Working: submit job, list jobs, get job details, cancel, pause/resume, chat comments, SSE events, kanban dashboard, activity feed, sandbox output.

Gaps:
1. No GitHub issue/PR listing UI — need to browse + select issues to fix
2. No session replay — recording exists but no step-by-step replay UI
3. No sandbox terminal access — logs available but no streaming terminal view
4. Limited progress visibility — dashboard only shows coarse queued/running/completed

---

### H. ENTRY POINTS — NEEDS UNIFICATION

Current: run_job_spec (primary), run_single (direct), run_multi (multi-repo), run_resumed_job_spec (resume).

Triggers: POST /api/jobs, GitHub webhooks, chat submit_job tool.

Proposal: The /api/jobs endpoint already handles the general case. Need:
1. Repo explorer page in dashboard showing GitHub issues/PRs
2. "Fix this" button on each issue/PR creating a pre-filled job
3. Simple CLI entry point: testai run <repo_url>

---

### I. ADDITIONAL FINDINGS

Worktree isolation: per-session + per-subagent branches off repo main
Compaction: exists but may need enhancement for long sessions
Memory: cross-run memory with 3 tiers (L0 artifacts, L1 facts, L2 lessons)
Reflection: max 3 per run, 3 per tool — triggers self-correction
Recovery: configurable retry on tool failure from Role YAML
Flaky detection: auto-detects and quarantines flaky tests
PR integration: commit + PR + tier-based review flow
Hooks: pre/post tool hooks, session start (5-layer intervention)
Multi-repo: context repos cloned read-only at /workspace/context/{name}/

---

## GAP ANALYSIS & RECOMMENDATIONS

### Critical (must fix for E2E demo)

1. GitHub Issue/PR Explorer — add API + dashboard UI to browse issues/PRs and create jobs from them
2. Sandbox streaming output — wire real-time sandbox output to SSE

### High (should fix soon)

3. Dashboard progress granularity — surface Agent.get_activity_summary() data
4. Warm base images (F11) — dependency caching per language/manifest
5. Session replay — agent activity replay UI

### Medium (nice to have)

6. Unified CLI entry point — testai run <repo_url>
7. Disk quota monitoring — sandbox volume cleanup policies
8. Multi-model KG — index GitHub issues + PRs as graph nodes
9. Cost/performance dashboards — per-run cost breakdowns

---

## VERDICT: System Readiness for E2E Test

| Component | Status | Notes |
|-----------|--------|-------|
| Orchestrator <-> Subagent sync | READY | Context propagation via contextvars |
| Sandbox lifecycle | READY | Docker isolation, volume reuse, worktree branching |
| Knowledge Graph | READY | Build + query + update after edits |
| Kanban board | READY | Create + track + events |
| Artifact persistence | READY | Postgres + volume + host cache |
| Metrics/cost tracking | READY | 4-scope budgets, token ledger |
| User chat interaction | READY | API endpoints, comments, SSE events |
| Issue/PR browser | MISSING | Needs implementation |
| Sandbox terminal view | MISSING | Logs only, no streaming view |
| Session replay | MISSING | Recording exists, no replay UI |
| Warm base images | MISSING | Documented, not implemented |

Overall: System is ~80% ready for E2E test. Core orchestration, sandboxing, KG, and kanban layers are solid. Missing pieces are primarily in UI/observability layer — which is what you specifically asked about. The GitHub issue/PR explorer is the key blocker.


