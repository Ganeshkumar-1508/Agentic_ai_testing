# E2E Pipeline Architecture Interview — Findings Log

> Created: 2026-06-15
> Purpose: Capture decisions, gaps, and recommendations from the design interview for the end-to-end autonomous testing pipeline.

---

## Branch 1: Architecture Coherence — Tools, Skills, Knowledge Graph Access

**Status:** ✅ Explored (2026-06-15)

### Key Findings

| Component | Status | Details |
|---|---|---|
| CodeGraph Tools | ✅ Working | `CodeGraphExploreTool`, `CodeGraphNodeTool`, `CodeGraphSearchTool`, `CodeGraphCallersTool` — all registered in tool registry, call `query_symbols()`/`get_callers()`/`get_callees()` via sandbox |
| Skills Tools | ✅ Working | `SkillsListTool`, `SkillViewTool`, `SkillManageTool` — list, load, create, edit, install skills at runtime |
| Memory Tool | ✅ Working | `MemoryTool` registered; coordinator prompt explicitly says "use memory to save lessons learned" |
| Project Isolation for KG | ❌ Gap | CodeGraph indexes at `/workspace/repo/.codegraph/`. Sandbox uses `volume_key=repo_url` for Docker volume — **Key fix: need per-repo isolated KG volumes** |

### Decision

- **Per-repo isolated KG** is required. Each repo needs its own `.codegraph/` directory on its own Docker volume.

---

## Branch 2: Sandbox Lifecycle & Isolation

**Status:** ✅ Explored + Industry research complete (2026-06-15)

### Current State

| Aspect | Status |
|---|---|
| Container creation | `SandboxManager.get_or_create()` — Docker with `sleep infinity` |
| Reuse model | `volume_key=repo_url` decouples volume from session |
| TTL / Auto-cleanup | ❌ `reap_stale()` defined but **never scheduled**. `POST /sandbox/exec-containers/reap` endpoint is **broken** |
| Pre-destroy data export | ❌ `copy_db_to_host()` called during setup only, not before destroy |
| Frontend monitoring | ❌ Wireframe exists (`plans/sandbox-wireframe.html`), **not implemented** |
| Container recovery | ⚠️ Recovers primary workspace only, not workers/sidecars |

### Industry Comparison

| Framework | Container Tech | Lifecycle Model | TTL |
|---|---|---|---|
| OpenHands | Docker | Per-conversation, context manager | No TTL |
| Greptile | Rootless Podman + pivot_root | Per-repo persistent | Agent loop bound |
| K8s Agent Sandbox | gVisor/Kata | Sandbox CRD, warm pools | Scale-to-zero |
| Docker Sandboxes (new) | Container → microVM | Per-agent, bind mount | Session bound |
| LangChain Deep Agents | Modal/Runloop/Daytona | `create()` → use → `stop()` | Explicit |
| TestSprite | Ephemeral cloud | Per-run | Run bound |

### Decision

- **Single reusable container per repo**, keyed by `sha256(repo_url)`
- **TTL = 30m inactivity**, `reap_stale` scheduled as background loop in `api/main.py`
- **KG lives on Docker volume** at `/workspace/repo/.codegraph/` — CodeGraph auto-sync updates graph on file changes. No explicit lifecycle stages — one container per repo, agent handles the full pipeline.
- Per-repo Docker volume means `codegraph init` runs once per repo and persists across container destroy/recreate.

---

## Branch 3: Knowledge Graph Mutation

**Status:** ✅ Explored (2026-06-15)

### Key Findings

- CodeGraph auto-sync (enabled by default) watches for file changes and updates the graph in real-time
- When an agent edits a file to fix a bug, CodeGraph automatically re-indexes affected symbols
- KG lives at `/workspace/repo/.codegraph/` — on the Docker volume, persists across container restarts
- CodeGraph is a **code-level KG** (functions, classes, imports, call graphs)

### Decision

Two-tier persistence model:
- **L0 — CodeGraph** (auto-synced on Docker volume): function-level symbols, call graphs, file structure. Updated automatically by CodeGraph's file watcher.
- **L1 — Cross-run Memory** (`memory` tool): stores task-level facts ("session_xyz fixed the login redirect bug in auth.py:42")

---

## Branch 4: Metrics, Artifacts, Observability & Dashboard

**Status:** ⏳ In Progress — questions pending user input (2026-06-15)

### Current State

**Backend Metrics (working):**
| Component | Details |
|---|---|
| `token_usage` table | Per-call: model, provider, input/output/cache tokens, cost, session_id, task_id |
| `trace_events` table | `llm:start/end`, `tool:start/end`, `agent:start/end` with span data + OTel compatibility |
| `pipeline_runs` table | Run status, repo_url, branch, inputs, timestamps |
| `CostTracker` | Per-session budget ($5 default), SSE alert on exceed |
| `GlobalBudgetTracker` | 30d rolling aggregate by session |
| `AnalyticsService` | Daily usage + per-model breakdown (30d) |
| `CostService` | Session/global/per-model/daily-trend/per-role endpoints |

**Frontend Dashboard (37 components, mostly built):**
- Cost monitoring: CostTrendCard, CostBreakdownCard, CostByModelCard, TokenUsageHeatmapCard
- Quality: QualityScoreGauge, QualityTrendChart, CoverageChart, CoverageGapsCard
- Failures: FailureCategories, RCACard, DefectPredictionCard
- Pipeline: PipelineFeedCard, RecentRunsTable, ActiveOrchestrationsCard, BlockedTasksCard
- Other: SelfHealingCard, LogsCard, ProviderFailoverCard, TraceabilityCard, ActivityHeatmap, Analytics30dCard

**Hermes Reference Patterns (gaps in TestAI):**
- `SubagentProgress` model with `costUsd`, `inputTokens`, `outputTokens`, `toolCount`, `filesRead`, `filesWritten`, stream events
- Kanban event stream via WebSocket (`/events` endpoint)
- OTel span hierarchy: agent→round→llm/tool (TestAI has flat spans)

### Gaps for E2E Pipeline

| Metric | Status | Priority |
|---|---|---|
| Token cost per model/session | ✅ | Core |
| Pipeline run status | ✅ | Core |
| Per-subagent cost/time/tools | ❌ | TBD |
| Per-pipeline-stage timing | ❌ | TBD |
| Kanban task metrics (blocked time, fix cycles) | ❌ | TBD |
| KG health (nodes/edges per repo) | ❌ | TBD |
| Sandbox resource usage (CPU/mem) | ⚠️ endpoints exist, UI missing | TBD |
| Agent tool-call count per stage | ❌ | TBD |
| Test pass/fail per fix attempt | ❌ | TBD |
| Real-time pipeline progress (SSE) | ❌ | TBD |
| E2E run cost (explore+triage+fix+verify) | ❌ | TBD |

### Decision: Metric Priorities

> Decided 2026-06-15 — accepted recommendations

1. **Per-subagent cost breakdown** ✅ P0 — use `task_id` field in `token_usage` to tag per-subagent costs (`$run_id:explore`, `$run_id:fix:task`, etc.). Stage-level cost aggregation via `root_run_id` rollup.
2. **Real-time SSE push** ✅ P1 — polling (30s) for MVP dashboard, WebSocket event stream for kanban board added post-MVP.

---

## Branch 5: Artifact Persistence & Configuration

**Status:** ⏳ In progress (2026-06-15)

### Current State

**Artifacts (`PostgresArtifactStore`):**
- `store(session_id, path, content, mime_type, description, subagent_id)` → writes to `artifacts` table
- `get(artifact_id)`, `list_by_session(session_id)`, `delete(artifact_id)`
- No automatic capture — agents must explicitly call store

**Repository Configuration:**
- `.testai/agents/` — Role definitions (YAML)
- `.testai/skills/` — Skills (SKILL.md)
- `.testai/prompts/agents/coordinator.txt` — Coordinator prompt template
- `.testai/mcp.json` — MCP server definitions
- Settings page in frontend (`src/app/(dashboard)/settings/page.tsx`) with tabs

**Gaps:**
- No per-repo configuration (what if repo A needs different tools/tier than repo B?)
- No pipeline-specific settings (timeout per stage, retry count, model selection per stage)
- No webhook-based job triggers wired to the kanban pipeline (the webhook endpoint exists but doesn't push to kanban)

### Decision: Configuration Model

> Decided 2026-06-15 — all config through dashboard UI

**No `testai.yaml` in repos.** All configuration centralized in dashboard UI (DB-backed). Framework auto-detection (scan repo for lockfiles, config files, directory conventions) happens at runtime — coordinator detects test runner, language, and build tools from repo contents using `codegraph_explore` + `bash`.

Config stored in DB tables:
- `providers` — LLM provider configs (model, base_url, api_key)
- `mcp_configs` — MCP server definitions
- `budgets` — per-scope soft/hard caps
- `pipeline_configs` — per-pipeline settings (model per stage, timeout, max cycles)

---

## Branch 6: What Else to Refine/Fix/Include

**Status:** ⏳ Open question (2026-06-15)

### Key Gaps Identified During Interview

| # | Gap | Area | Priority |
|---|---|---|---|
| 1 | Per-repo isolated KG volumes | Sandbox/KG | P0 — confirmed |
| 2 | TTL auto-cleanup (`reap_stale` not scheduled) | Sandbox | P0 — confirmed |
| 3 | Broken `POST /sandbox/exec-containers/reap` endpoint | Sandbox | P1 — fix dead code |
| 4 | Pre-destroy KG/artifact export missing | Sandbox | P1 — need `copy_db_to_host` on destroy |
| 5 | Per-subagent cost breakdown (via `task_id`) | Metrics | P0 — confirmed |
| 6 | Pipeline stage timing | Metrics | P0 |
| 7 | Kanban task event stream / WebSocket | Metrics | P1 |
| 8 | Dashboard sandbox monitoring (wireframe only, no UI) | Frontend | P2 |
| 9 | Incomplete container recovery (workers/sidecars orphaned) | Sandbox | P2 |
| 10 | Webhook endpoint exists but doesn't push to kanban | Pipeline | P1 |
| 11 | Auto-detect test framework at pipeline start | Pipeline | P0 |
| 12 | SSE for real-time pipeline progress | Dashboard | P1 |

### Verified State of Each Option

**Integrations (Slack, Jira, Linear, Webhook)**
| Aspect | Status |
|---|---|
| `SendMessageTool` | ✅ Exists — supports inter-agent, Slack, and generic webhook delivery |
| Slack bot token config | ✅ Stored in `integration_configs` table, fetched via `_get_integration_config("slack")` |
| Webhook delivery | ✅ `_deliver_webhook()` — POST to any URL with JSON payload |
| Jira/Linear | ❌ Not implemented in harness — only in `reference/OpenHands/enterprise/` |
| Notification persistence | ✅ `notifications` table — `id, channel, recipient, subject, body, status, error, run_id, delivered_at` |
| Pipeline completion push | ❌ No hook currently calls `SendMessageTool` on pipeline finish |

**Security Controls**
| Aspect | Status |
|---|---|
| SSRF guard (`url_safety.py`) | ✅ Full — blocks cloud metadata IPs (169.254.169.254), private networks, CGNAT, always-blocked floor |
| Skills security scan (`skills_guard.py`) | ✅ Static analysis guard for community-sourced skills |
| Path-traversal guard | ✅ `skill_manage` resolves path, verifies within skills dir |
| Secret injection into sandbox | ❌ No mechanism to inject repo-specific secrets |
| Network egress for sandbox | ❌ Full network by default, no Docker network policy |
| Sandbox runs as root | ❌ No user namespace remapping |

**Decision:** Skip integrations and security for MVP. Focus only on skills.

---

### Pre-existing Prompts & Skills Available

**Harness Prompts (`backend/harness/prompts/` — 100+ files):**

| Prompt | Relevance to E2E Pipeline |
|---|---|
| `agent-prompt-explore.md` | ✅ **Ready to use** — read-only codebase search agent (disallowed: Edit, Write). Perfect for Explore phase. Model: haiku (cheap). |
| `agent-prompt-general-purpose.md` | ✅ **Ready to use** — searches, analyzes, and edits. Full tool access. Perfect for Fix/Verify agents. |
| `agent-prompt-review-pr-slash-command.md` | ✅ **Ready to use** — `gh pr view/diff` + code analysis workflow. Triaging PR issues. |
| `agent-prompt-code-review-part-1-8.md` | ✅ **8-part code review suite** — line-by-line diff scan, removed-behavior auditor, cross-file tracer, 3-state verification. Triaging + reviewing fixes. |
| `agent-prompt-security-review-slash-command.md` | ✅ Security audit prompt for vulnerability detection. |
| `skill-verify-skill.md` | ✅ **Runtime verification workflow** — build the app, drive it, capture evidence. "Don't run tests. Don't typecheck." For Verify phase. |
| `skill-debugging.md` | ✅ Debug logging and issue diagnosis workflow. For Fix phase. |
| `skill-run-skill-template.md` | ✅ **Template** for creating new run skills with YAML frontmatter + sections (Prerequisites, Setup, Run). |
| `skill-run-app.md` | ✅ Template for app-running skills. |
| `skill-run-cli-tool-example.md` / `skill-run-browser-driven-web-app-example.md` | ✅ Example run skills for different app types. |

**ECC (`docs/ECC/` — 181 skills, 64 agents, 79 commands):**
- 64 specialized agents (planner, tdd-guide, code-reviewer, e2e-runner, refactor-cleaner, etc.)
- 262 skills across domains
- `orchestration-status.js` — script for checking orchestration status
- `orchestrate-worktrees.js` — worktree orchestration
- `skills-health.js` — skill health monitoring

**Key ECC agents relevant to pipeline:**
| Agent | Purpose |
|---|---|
| `planner` | Implementation planning, breaking work into phases |
| `tdd-guide` | Test-driven development — write tests first |
| `code-reviewer` | Code quality and maintainability review |
| `e2e-runner` | End-to-end Playwright testing |
| `build-error-resolver` | Fix build/type errors |
| `refactor-cleaner` | Dead code cleanup |
| `loop-operator` | Autonomous loop execution, stall monitoring |
| `harness-optimizer` | Reliability, cost, throughput tuning |

### Decision: Adopted Hermes Autonomous Agent Pattern

**Created `backend/harness/agent_discovery.py`** — filesystem-driven agent discovery:
- Scans 3 directories in override chain: built-in (`harness/agents/`) → user (`~/.testai/agents/`) → project (`.testai/agents/`)
- `get_agent(name)` returns parsed `AgentConfig` from frontmatter + body
- `get_subagent_prompt()` builds subagent prompt from agent file

**Created 6 Hermes-style agent `.md` files in `backend/harness/agents/`:**

| File | Phase | Frontmatter | Model |
|---|---|---|---|
| `explore.md` | Explore | read-only tools, disallowed edit/write | haiku |
| `triage.md` | Triage | code review angles, codegraph_callers for impact | haiku |
| `fix.md` | Fix | full tool access, self-heal (max 3 cycles) | sonnet |
| `verify.md` | Verify | runtime observation only, no test re-run | haiku |
| `planner.md` | Plan | read-only, dependency ordering | haiku |
| `orchestrator.md` | **Coordinator** | delegate_task + kanban + all codegraph | sonnet |

Each file = YAML frontmatter (config) + battle-tested prompt body (from `backend/harness/prompts/`).

**What makes this Hermes-autonomous:**
- No hardcoded mode dict — agents are discovered by scanning filesystem
- Anyone can drop a new `.md` file in `harness/agents/`, `~/.testai/agents/`, or `.testai/agents/` and it's automatically available
- The coordinator (`orchestrator.md`) delegates by agent name: `delegate_task(agent="explore", goal=...)`
- Override chain: built-in → user → project (project wins on name conflict)

---

## Proposed Pipeline Workflow (2026-06-15)

```
JobSpec → OrchestratorEngine (sandbox, clone, codegraph init)
  → Coordinator (orchestrator.md) creates kanban board
    → Phase 1: Parallel Analysis
        ├─ agent: explore      — read-only codebase search
        ├─ agent: triage       — issue/PR analysis + impact tracing
        └─ agent: web-researcher — research docs, known fixes, APIs
              ↓
        agent: planner — fix plan with dependency ordering
    → Decision gate (coordinator reviews plan, questions user if needed)
    → Batch fan-out if large change
    → Phase 2: Fix-Verify Loop (max 3 cycles)
        └─ loop: agent: fix → agent: verify → (back to fix if failed)
    → Phase 3: Parallel Review Suite
        ├─ agent: code-reviewer    — 5-axis code review
        ├─ agent: security-auditor — OWASP vulnerability scan
        └─ agent: test-engineer    — coverage + Prove-It pattern
    → Quality gate (Critical/High findings → back to fix)
    → Save summary → Open PR / Queue for review / Await human
```

### Key Improvements over Original
1. **Parallel triage**: triage + web-researcher run simultaneously
2. **Fix-Verify loop**: verify failure loops back to fix (max 3 cycles)
3. **Quality gate**: review suite findings block merge if Critical/High remain
4. **Early exit**: explore finds nothing → done immediately
5. **Batch early**: large changes detected at triage, not as afterthought
6. **Tier awareness**: Tier 1=auto-PR, Tier 2=review queue, Tier 3=await human


