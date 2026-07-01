# TestAI

**Agentic test automation platform** — autonomous agents that write tests, run pipelines, analyze failures, and surface quality signals. Engineering teams ship with confidence without manual test maintenance.

**Sharp. Intuitive. Relentless.**

---

## Overview

TestAI is a full-stack agentic testing platform that orchestrates **autonomous LLM-powered agents** across your software repositories. It combines a Python/FastAPI agent orchestration engine with a dark-native Next.js observability dashboard to create a complete test automation lifecycle:

| Phase | What happens |
|---|---|
| **Explore** | Agents clone the repo, index the knowledge graph, discover the codebase structure, tech stack, and existing tests |
| **Plan** | A coordinator agent decomposes the goal into tasks, creates a kanban board, and assigns work to subagents |
| **Execute** | Subagents write tests, run pipelines, analyze failures, and self-heal — each in an isolated Docker sandbox |
| **Verify** | Results flow back through the delegation tree; the coordinator validates output, opens PRs, or requests human review |
| **Learn** | Cross-run memory stores lessons (L2 curated facts); flaky tests are auto-detected and quarantined |

The platform targets two primary personas:
- **QA Engineers & QA Managers** — running pipelines, investigating test failures, monitoring flaky tests, tracking coverage
- **Engineering Leads & DevOps** — orchestrating agents across repos, managing infrastructure, tracking costs, configuring CI/CD integration

---

## Design Principles

1. **The tool disappears.** Every design decision reduces the distance between the user's question and the answer. If a component draws attention to itself, it is wrong.

2. **Data is the interface.** Numbers, trends, and signals are the primary content. Layout, color, and typography serve to make data legible — not to decorate.

3. **State is visible.** Loading, empty, error, success — every state is designed. An empty state teaches. A loading state sets expectation. An error state offers recovery.

4. **Precision over polish.** Sharp, correct data beats decoration but muddy hierarchy. Alignment, contrast, and density earn their place before shadows, gradients, or motion.

5. **Dark by nature, not by theme.** The dark surface is designed from the dark outward. Color choices support long reading sessions, reduce glare, and communicate state through hue, not lightness shifts.

---

## Brand Personality

- **Sharp** — precise, no fuzzy edges. Data is exact; typography is crisp; spacing is intentional.
- **Intuitive** — surfaces what matters, hides what does not. The interface disappears into the task.
- **Relentless** — the platform works while the team sleeps. Agents are active, pipelines are running, nothing is left to chance.

Inspired by Datadog and Sentry — dense but navigable dashboards where every pixel earns its place. Confident, developer-first, dark-native.

---

## Key Features

### Autonomous Test Authoring
Agents discover codebases, understand intent (from natural language goals or issue descriptions), and generate test suites across languages and frameworks. No pre-built templates — the agent reads your code and writes idiomatic tests.

- **Multi-language** — Python, TypeScript, Go, Rust, Java, C++, PHP, Kotlin, and more
- **Framework-aware** — adapts to pytest, Vitest, Jest, Go test, JUnit, PyTorch, and others
- **Codebase-aware** — reads existing tests first to match style, naming, and patterns
- **CI-ready** — generated tests run in CI before PR submission

### Multi-Repo Orchestration
Coordinate agents across repositories with a **hybrid adaptive delegation tree**. By default uses flat parent-to-worker delegation; automatically escalates to recursive trees when complexity requires it.

- **Adaptive depth triggers** — five heuristics (task breadth >5 subtasks, context pressure >70%, worker failure, repo size >100 files, disjoint tool sets) cause automatic escalation
- **Subagent lifecycle** — Sync (blocking), Fan-Out (parallel spawn + collect), Background (fire-and-steer)
- **Cross-repo context** — shared memory and knowledge graph across repositories within a run

### Tiered Autonomy
Graduated autonomy levels let teams choose how much control to delegate:

| Tier | Name | Behavior |
|---|---|---|
| **1** | Autonomous | Agent runs to completion, opens a PR, and merges on CI pass |
| **2** | Supervised | Agent runs to completion, posts diff to a kanban task, stops before `commit_and_open_pr` — a human reviews |
| **3** | Human-authored | Agent does NOT execute code. Creates a kanban proposal with spec — human reviews, edits, and resubmits |

### Flaky Test Detection & Self-Healing
Automatic identification, quarantine, and remediation of flaky tests:

- **Detection** — analyzes test run history for non-deterministic pass/fail patterns
- **Quarantine** — moves flaky tests to a separate bucket so they do not block CI
- **Self-healing** — agents analyze root cause (timing, race conditions, environment dependencies) and generate fixes
- **Dashboard** — dedicated flaky-tests view with trend charts and drill-down

### Observability Dashboard
43 route groups across a real-time dark-themed dashboard:

- **Delegation Tree** — live visualization of the agent subagent hierarchy via SSE/WebSocket
- **Session History** — replay any past agent run with full transcript
- **Token Cost Breakdown** — per-model, per-agent, per-run cost tracking with budget alerts
- **Root Cause Analysis** — from test failure to offending commit to agent decision
- **Activity Feed** — real-time SSE event stream for all agent and pipeline events
- **Quality Metrics** — coverage trends, pass rates, flake rates over time
- **Traceability** — full provenance from user goal to test file to CI result

### CI/CD Integration
Native connectors for the full development workflow:

- **GitHub** — webhook-driven PR triggers, status checks, auto-merge
- **GitLab** — webhook and MR integration
- **Slack** — delivery router for notifications, approval requests, and digests
- **Jira / Linear** — ticket creation and status sync
- **Git webhooks** — HMAC-protected endpoints for secure CI integration

### Sandboxed Execution
Every subagent runs in an isolated Docker container with:

- **Per-subagent containers** — failure isolation (one failing sandbox does not affect siblings)
- **Resource limits** — configurable CPU, memory, and timeout per sandbox
- **Credential isolation** — credentials injected per-task at spawn time; never shared
- **Shared named volumes** — sibling sandboxes share artifacts via volumes without sharing execution environments
- **Checkpoint/resume** — orchestrator respawns from last checkpoint on sandbox failure (max 2 retries)
- **Multi-runtime** — single base image (`nikolaik/python-nodejs`) with on-demand runtime install (Go, Rust, Java)

### Provider-Agnostic LLM Routing
Use any OpenAI-compatible model with automatic failover and cost controls:

- **Multi-provider** — configure providers and models through the Settings UI
- **Automatic failover** — if primary model fails, falls back to the configured secondary
- **Per-model pricing cache** — tracks token costs per model for accurate billing
- **Cost budgets** — four scopes (per-subagent, per-phase, per-run, per-user-per-day) with soft warn and hard throttle caps
- **Auto-throttle ladder** — four-step escalation: switch to HITL mode → demote parallel to sequential → switch to cheaper model → pause

### Knowledge Graph & Memory
Cross-run intelligence that improves with every session:

| Level | Type | What it stores | TTL |
|---|---|---|---|
| **L0** | Raw artifacts | LLM transcripts, tool outputs | 7 days |
| **L1** | Indexed facts | Code structure, symbols, references | 30 days |
| **L2** | Curated lessons | Cross-run learnings, fixed bugs, patterns | Permanent |

- **Curator agent** — background loop that extends L2 memory every hour
- **Knowledge graph** — SQLite-based index of code structure (imports, symbols, dependencies)
- **Memory tools** — agents can read/write cross-run facts during execution

### Kanban-Driven Job Workflow
Jobs flow through a structured lifecycle visible on the dashboard:

1. **Proposal** — a job spec is created (from chat, webhook, cron, or API)
2. **Review** — for tier 2/3, the spec lands on a kanban board for human review
3. **Execution** — agent runs in the sandbox, updates kanban tasks in real time
4. **Verification** — results are validated against acceptance criteria
5. **Completion** — PR opened, notification sent, lessons curated

### Tool Catalog (30+ primitives)
Agents compose workflows from primitive tools — no tool has baked-in knowledge of any test framework:

| Category | Tools |
|---|---|
| **Filesystem** | bash, read, write, edit, apply_patch, glob, grep, list |
| **Code Intelligence** | ast_grep, code_search, dependency_graph, lsp |
| **Knowledge** | web_fetch, web_search, memory (L0/L1/L2), skill, tool_search |
| **Orchestration** | task (sync/fan-out/background), send_message, question, todo |
| **Specialized** | computer_use, vision_analyze, database_query, diagram, image_generate |

### Agent Roles (76 definitions)
Pre-built role configurations in `agent_workspace/agents/` covering every testing discipline: architects, coordinators, planners, explorers, code reviewers (8 language variants), subagent delegators, test planners, TDD guides, security reviewers, build-error resolvers, E2E runners, and more. Each role declares its system prompt, allowed tools, allowed skills, delegation depth, model with fallback, bash constraints, and output contract.

### Skills (75+ definitions)
Reusable instruction bundles in `.testai/skills/` covering: agent design patterns, API design, browser testing, CI/CD, code review, data science, debugging, DevOps, frontend engineering, git workflow, knowledge graph, MCP, observability, performance, security, TDD, and more. Skills are auto-discovered at startup and loaded on-demand by agents via the `skill` tool.

### User Intervention Layers
Five graduated layers of human control:

1. **Hooks** — deterministic Pre/Post tool hooks and SessionStart hooks
2. **Steer** — inject messages mid-turn without interrupting
3. **HITL** — approve, review, clarify, or edit at checkpoints
4. **Control** — interrupt, pause, cancel, or fork a running session
5. **Reliability** — checkpoint/resume survives process restarts

### PR Merge Strategy
Three modes configurable per-run:
- **Fully autonomous** — agent pushes and merges
- **PR + notify** — agent opens PR with summary; human reviews and merges
- **PR + auto-merge on CI pass** — agent opens PR; CI must pass before auto-merge

Production code changes always require human review by default.

---

## Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Dashboard (Next.js 16)                           │
│  Pipelines · Jobs · Agents · Flaky Tests · Cost · Kanban · Observability │
│  Quality · Sessions · Chat · Activity · Settings · Traceability · Admin  │
│        43 route groups · 26 component domains · 47 UI primitives          │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTP + SSE / WebSocket
                                    │
┌───────────────────────────────────▼─────────────────────────────────────┐
│                      Orchestrator Engine (Python FastAPI)                 │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                     OrchestratorEngine                            │    │
│  │  run_job_spec() → run_single() → run_multi() → run()             │    │
│  │  Bootstrap: sandbox → clone → KG index → kanban → coordinator     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                              │                                            │
│  ┌──────────┐  ┌──────────┐  │  ┌──────────┐  ┌──────────────────────┐  │
│  │ Explorer │  │Coordinator│  │  │ Subagent │  │     Tool Registry     │  │
│  │  Agents   │  │  Agent    │  │  │  Worker   │  │  ~88 tools, 9 tool   │  │
│  │ (parallel)│  │ (plans &  │  │  │ (N-way)  │  │  categories, gated    │  │
│  │          │  │ delegates)│  │  │          │  │  by role YAML         │  │
│  └──────────┘  └──────────┘  │  └──────────┘  └──────────────────────┘  │
│                              │                                            │
│  ┌──────────┐  ┌──────────┐  │  ┌──────────┐  ┌──────────────────────┐  │
│  │  Memory   │  │   MCP    │  │  │  Skills  │  │   Knowledge Graph     │  │
│  │  System   │  │  Server   │  │  │ Registry │  │   (SQLite, code       │  │
│  │ (L0/L1/L2)│  │(A2A proto)│  │  │ (75+)    │  │   symbols, imports)   │  │
│  └──────────┘  └──────────┘  │  └──────────┘  └──────────────────────┘  │
│                              │                                            │
│  ┌──────────┐  ┌──────────┐  │  ┌──────────┐  ┌──────────────────────┐  │
│  │  Kanban   │  │  Jobs    │  │  │  Events   │  │   LLM Router         │  │
│  │  Board    │  │  System  │  │  │  Bus      │  │   (multi-provider,    │  │
│  │ (Postgres)│  │(JobSpec) │  │  │(EventBus) │  │   failover, cost)     │  │
│  └──────────┘  └──────────┘  │  └──────────┘  └──────────────────────┘  │
│                              │                                            │
│  ┌──────────┐  ┌──────────┐  │  ┌──────────┐  ┌──────────────────────┐  │
│  │  A2A      │  │  Plugins  │  │  │ Scheduler│  │   Observability      │  │
│  │  Server   │  │  System  │  │  │ (cron)   │  │   (OTel export, SSE)  │  │
│  └──────────┘  └──────────┘  │  └──────────┘  └──────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
        ┌───────────▼──────────┐ ┌──────────▼──────────────────┐
        │    Docker Sandbox     │ │   PostgreSQL + External      │
        │  Per-subagent exec    │ │   Integrations               │
        │  (resource limits,    │ │                              │
        │   checkpoint/resume,  │ │  ┌────────┐ ┌─────────────┐  │
        │   credential iso.)    │ │  │ Session│ │ GitHub/GitLab│  │
        │                       │ │  │ Stores │ │ Webhooks     │  │
        │  Base: python-nodejs  │ │  ├────────┤ ├─────────────┤  │
        │  On-demand: Go, Rust, │ │  │ Kanban │ │ Slack/Jira   │  │
        │  Java, etc.           │ │  │ Tables │ │ Linear       │  │
        └───────────────────────┘ │  ├────────┤ ├─────────────┤  │
                                  │  │ Memory │ │ Cron Triggers│  │
                                  │  │ Store  │ │             │  │
                                  │  └────────┘ └─────────────┘  │
                                  └──────────────────────────────┘
```

### Layer-by-Layer Breakdown

#### 1. Dashboard Layer (Next.js 16 / TypeScript)

The web UI is organized as 43 route groups under the App Router, each corresponding to a domain concept:

| Route Group | Purpose |
|---|---|
| `/dashboard` | Summary metrics: active runs, pass/fail rates, recent activity, cost trends |
| `/pipeline` | Pipeline execution DAG with real-time status via SSE |
| `/jobs` | JobSpec list with status pills (queued/running/completed/failed/cancelled) |
| `/jobs/[spec_id]` | Full job detail: cancel, pause, resume, comment, view output |
| `/agents` | Agent registry, active agents, delegation tree viewer |
| `/chat` | Interactive chat surface for ad-hoc agent interactions |
| `/activity` | Live SSE event feed for all C01-C08 system events |
| `/flaky-tests` | Flaky test detection dashboard with trend charts |
| `/cost` | Token cost breakdown by model, agent, run |
| `/observability` | OTel status, span counts, compaction metrics |
| `/kanban` | Job proposal board with review/approve/reject workflow |
| `/sessions` | Historical session browser with replay |
| `/settings` | LLM provider config, data retention, budget thresholds |
| `/knowledge-graph` | KG browser and search |
| `/traceability` | Full provenance: goal → test file → CI result |
| `/quality` | Quality metrics: coverage trends, pass rates, flake rates |
| ... and 27 more | admin, analytics, artifacts, audit, channels, compare, cron, devtools, digest, evaluate, history, load-testing, models, notifications, project, pull-requests, requirements, sandbox, skills, terminal, test-cases, tools, visual-testing, workflows |

The frontend wraps all routes in:
- **ThemeProvider** (next-themes, fixed dark, class-based)
- **ReactQueryProvider** (TanStack Query for server state management)
- **Sonner Toaster** (notification system)
- **CommandPalette** (global Cmd+K launcher)
- **Satoshi + JetBrains Mono** fonts via Fontshare CDN

#### 2. Orchestrator Engine (Python FastAPI)

The `OrchestratorEngine` class (`backend/harness/orchestrator.py`) is the thin bootstrap that drives each run:

```
OrchestratorEngine.run(run_id, session_id, repo_url, goal)
  │
  ├─ 1. Bootstrap sandbox → clone repo → install deps
  ├─ 2. Index knowledge graph (code symbols, imports, deps)
  ├─ 3. Load cross-run memory (L1/L2 relevant facts)
  ├─ 4. Run explore agents (parallel, multi-hop code understanding)
  ├─ 5. Create kanban board (optional, for human visibility)
  ├─ 6. Spawn ONE coordinator agent (full tool surface)
  │      │
  │      └─ Coordinator.drive()
  │           ├─ Plan via todo list
  │           ├─ Delegate subagents via delegate_task
  │           │    ├─ Sync (blocking) for sequential work
  │           │    ├─ Fan-Out (parallel) for independent tasks
  │           │    └─ Background (fire-and-steer) for long-running
  │           ├─ Monitor via orchestrate_monitor
  │           └─ Complete: commit, PR, notify
  │
  └─ 7. Return results + curate L2 memory
```

#### 3. Agent Layer

The `Agent` class (`backend/harness/agent/agent.py`) is a 1310-line unified LLM tool-calling loop:

- **run(user_input)** — blocking call, returns final response
- **run_stream(user_input)** — async generator for SSE streaming
- **interrupt()** — cooperative cancel signal
- **ReflexionMemory** — automatic reflection injection at configurable intervals
- **ToolDispatcher** — routes tool calls to the tool registry with access control
- **Event emitters** — AgentStarted, AgentCompleted, LLMCallStarted/Completed, ToolExecutionStarted/Completed, ReflexionInjected

Key owned components:
- `AgentDependencies` — configurable deps injection
- `DelegationContext` — tree tracking of subagent relationships
- `ValidationSystem` — validates subagent output against contracts

#### 4. LLM Router

The `LLMRouter` (`backend/harness/llm.py`) provides provider-agnostic model access:

- **Provider profiles** — configured via UI (Settings → Backend Providers), stored in Postgres
- **Automatic failover** — sequential retry across configured providers
- **Known context lengths** — model-specific context window tracking (including Grok-4.3 at 1M tokens)
- **Pricing cache** — per-model cost lookup with TTL-based refresh
- **DeepSeek v4 thinking mode** — special handling for reasoning_content on assistant tool-call messages

#### 5. Tool Registry (~88 tools)

`backend/harness/tools/registry.py` + `toolsets.py` compose tool sets per role. Each tool is a standalone class with input schema, output schema, and `run()` method:

| Category | Key Tools |
|---|---|
| **Filesystem** | `file_tools`, `grep_tool`, `glob_tool`, `execute_code`, `apply_patch_tool`, `command_blocklist` |
| **Code Intelligence** | `lsp_tool`, `codegraph_tools`, `semantic_search_tool`, `dependency_graph_tool`, `ast_grep` (via tree-sitter) |
| **Web** | `web_tools`, `web_extract_tool`, `browser` (playwright-based), `url_safety` |
| **Subagent** | `delegate_task`, `subagent`, `orchestrator_tool`, `team_tools`, `fan_out_tool` |
| **Memory** | `memory_tool`, `memory_search`, `checkpoint`, `todo_tool`, `todo_store` |
| **Git** | `github_tools`, `commit_and_open_pr_tool` |
| **Security** | `credential_scanner`, `osv_check`, `path_security`, `binary_extensions` |
| **Specialized** | `computer_use_tool`, `database_query_tool`, `diagram_tool`, `image_generate_tool`, `vision_analyze_tool`, `visual_diff_tool` |
| **Skills** | `skill_tools`, `skill_evolution_tools`, `skills_guard`, `skills_ast_audit` |
| **Utility** | `circuit_breaker`, `retry_utils`, `env_passthrough`, `coverage_analyzer`, `coverage_intelligence`, `error_classifier` |

#### 6. Memory & Knowledge Systems

| System | Storage | Key Component |
|---|---|---|
| **L0 Raw Artifacts** | Postgres (JSONB) | `session` + `messages` tables, 7-day TTL |
| **L1 Indexed Facts** | Postgres + SQLite | `memory/store.py`, `harness/memory/` |
| **L2 Curated Lessons** | Postgres | `curator.py` — background loop (hourly), permanent |
| **Knowledge Graph** | SQLite | `codegraph.py` — code symbols, imports, dependency analysis |
| **Settings Store** | Postgres | `settings_store.py` — LLM provider config, budgets, schedules |

#### 7. Job System

Units of work flow through a canonical pipeline:

```
JobSpec (Pydantic model)
  ├─ prompt: str
  ├─ repo_url: str
  ├─ branch: str
  ├─ tier: 1 | 2 | 3
  ├─ capabilities: [write_test_files, open_pr, ...]
  ├─ approval: review_queue routing
  ├─ context: {session_id, agent_id}
  │
  └─ POST /api/jobs → submit_job_to_orchestrator()
       ├─ chat tools: submit, list, get, cancel, pause, resume, comment, get_output
       ├─ real pause (PauseSignal + job checkpoint, not cancel)
       ├─ auto-resume from checkpoint (fresh run_id, same spec_id)
       └─ DB-backed checkpoint in production
```

#### 8. Event Bus

`EventBus` provides a pub/sub system for internal and external observability:

- **Typed events** — AgentStarted, ToolExecStarted, KanbanTransition, BudgetThrottle, etc.
- **SSE streaming** — real-time feed to the dashboard activity page
- **Postgres persistence** — durable event log for replay
- **Hermes scheduling** — configurable intervals for heartbeat events (5s heartbeat, 30s idle fuse, 5min in-tool fuse)

#### 9. Sandbox Layer

Per-subagent Docker containers managed by `SandboxManager`:

- **Base image**: `nikolaik/python-nodejs` (Python 3.x + Node.js 22.x)
- **On-demand runtimes**: agents install Go, Rust, Java, etc. via bash
- **Resource limits**: 512MB RAM, 1 CPU, 300s timeout (configurable via `sandbox.toml`)
- **Network isolation**: limited by default, configurable per-run
- **Workspace layout**: `/workspace/repo/` (writable) + `/workspace/context/{name}/` (read-only context repos)
- **Docker executor**: manages container lifecycle, exec commands, capture output

#### 10. C0-C8 Implemented Features

The latest architecture sprint (C0-series) added:

| Feature | Design Doc | Status |
|---|---|---|
| **C01 — Worktree Isolation** | `2026-06-21-c01-design.md` | Implemented |
| **C02 — Agent Teams** | `2026-06-21-c02-design.md` | Implemented (MVP) |
| **C03 — Push-Based Board Completion** | `2026-06-21-c03-design.md` | Implemented |
| **C04 — KG Refresh Tool** | `2026-06-21-c04-design.md` | Implemented |
| **C05 — A2A Wire Protocol** | `2026-06-21-c05-design.md` | Implemented |
| **C06 — Subagent Heartbeat + Stale Detection** | `2026-06-21-c06-design.md` | Implemented |
| **C07 — Budget Auto-Throttle Ladder** | `2026-06-22-c07-design.md` | Implemented |
| **C08 — JobSpec Canonicalisation** | `2026-06-21-c08-*.md` (6 sub-docs) | Implemented |
| **F02 — 1M-Context Model Support** | `2026-06-22-f02-design.md` | Implemented |
| **F04 — OpenTelemetry Spans** | `2026-06-22-f04-design.md` | Implemented |

---

## Tech Stack

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| **Next.js** | 16.1.1 | React framework with App Router, server components, API routes |
| **React** | 19.2.7 | UI component library |
| **TypeScript** | 5.x | Type safety across the frontend |
| **Tailwind CSS** | 4.x | Utility-first CSS with CSS variable design tokens |
| **shadcn/ui** | (via Radix primitives) | 47 accessible component primitives (dialog, dropdown, popover, table, tabs, toast, tooltip, etc.) |
| **Framer Motion** | 12.23.2 | Declarative animations for UI state transitions |
| **TanStack React Query** | 5.82.0 | Server state management, caching, and background refetching |
| **TanStack React Table** | 8.21.3 | Data table with sorting, filtering, pagination |
| **Recharts** | 3.8.1 | Chart and graph rendering (cost trends, pass rates, etc.) |
| **Zustand** | 5.0.6 | Lightweight client state management (pipeline-store) |
| **React Hook Form** | 7.60.0 | Performant form validation and handling |
| **Zod** | 4.0.2 | Schema validation for forms and API contracts |
| **@xyflow/react** | 12.11.0 | Node-based UI rendering (pipeline DAGs, delegation trees) |
| **Mermaid** | 11.16.0 | Diagram rendering for documentation and reports |
| **next-auth** | 4.24.11 | Authentication (session management, providers) |
| **next-intl** | 4.3.4 | Internationalization framework |
| **@dnd-kit** | 6.x / 10.x | Drag-and-drop for kanban boards and reorderable lists |
| **Lucide React** | 0.525.0 | Icon library |
| **OpenAI SDK** | 6.38.0 | LLM API client for server-side route calls |
| **Sonner** | 2.0.6 | Toast notification system |
| **Vauli** | 1.1.2 | Drawer/Sheet component |
| **CMDK** | 1.1.1 | Command palette (Cmd+K) |
| **React Markdown** | 10.1.0 | Markdown rendering in chat and documentation |
| **Shiki** | 4.3.0 | Code syntax highlighting |
| **MDXEditor** | 3.39.1 | Rich text editing for kanban descriptions and comments |
| **date-fns** | 4.1.0 | Date formatting and manipulation |
| **clsx + tailwind-merge** | — | `cn()` utility for conditional class merging |
| **Embla Carousel** | 8.6.0 | Carousel/slider component |

### Backend

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.11 | Runtime |
| **FastAPI** | >=0.115.0 | Async web framework with automatic OpenAPI docs |
| **Uvicorn** | >=0.32.0 | ASGI server |
| **Pydantic** | >=2.10.0 | Data validation, settings management, schema generation |
| **asyncpg** | >=0.30.0 | Async PostgreSQL driver |
| **OpenAI SDK** | >=1.55.0 | LLM provider API calls |
| **httpx** | >=0.28.0 | Async HTTP client for web tools and provider calls |
| **MCP** | >=1.26.0 | Model Context Protocol client for external tool discovery |
| **Jinja2** | >=3.1.0 | Template engine for prompt rendering |
| **Pillow** | >=11.0.0 | Image processing (screenshot analysis, visual diff prep) |
| **pixelmatch** | >=0.2.0 | Visual diff comparison |
| **crawl4ai** | >=0.8.7 | Web crawling for content extraction |
| **markitdown** | >=0.1.6 | File-to-markdown conversion |
| **agent-browser-cli** | >=0.20.0 | Browser automation (Playwright-based) |
| **OpenTelemetry** | (optional) | Distributed tracing export for enterprise observability |
| **Pytest** | >=8.3.0 | Test framework |
| **httpx** | — | Also used in tests for async HTTP client against the API |

### Infrastructure

| Technology | Purpose |
|---|---|
| **Docker** | Containerization of all services |
| **Docker Compose** | Multi-service orchestration for dev and production |
| **PostgreSQL 16 (Alpine)** | Primary database: sessions, messages, tasks, kanban, artifacts, token_usage |
| **Nginx** | Reverse proxy (production profile routes frontend at `/`, API at `/api/`) |
| **GitHub Actions** | CI/CD: typecheck, lint, vitest, Next.js build, pytest, E2E |
| **sandbox.toml** | Sandbox runtime configuration (Docker type, image, resource limits) |
| **design docs** | `.drawio` architecture diagrams in `docs/` |

### Agent System

| Component | Description |
|---|---|
| **LLM Router** | Multi-provider router with automatic failover, cost tracking, and context-length awareness |
| **Tool Registry** | ~88 tools across 9 categories, gated by role YAML declarations |
| **Skill Registry** | 75+ reusable instruction bundles auto-discovered from `.testai/skills/` |
| **MCP Client** | Model Context Protocol client for external tool servers (configurable via `.testai/mcp.json`) |
| **Knowledge Graph** | SQLite-based code symbol index for intelligent code navigation |
| **Memory System** | Three-tier: L0 raw (7d TTL), L1 indexed (30d), L2 curated (permanent) |
| **Curator** | Background agent that extends L2 memory every hour |
| **Event Bus** | Typed pub/sub for observability, SSE streaming, and inter-component communication |
| **A2A Server** | Agent-to-Agent protocol (JSON-RPC 2.0) exposing orchestrator as a standards-compliant endpoint |
| **Sandbox Manager** | Per-subagent Docker container lifecycle management |
| **Scheduler** | Cron-based job scheduling for recurring runs |
| **Plugin System** | Extensible hook-based plugin architecture with `_hook_system.py` and `plugins/` |

---

## Getting Started

### Prerequisites

| Dependency | Version | Required for |
|---|---|---|
| **Docker & Docker Compose** | Latest | Running all services (recommended path) |
| **Node.js** | 20+ | Local frontend development |
| **Python** | 3.11+ | Local backend development |
| **OpenAI-compatible API key** | — | LLM provider access (OpenCode, OpenAI, etc.) |
| **Make** | — | Using convenience commands (optional) |

### Quick Start (Docker — Recommended)

```bash
# 1. Clone the repository
git clone <repo-url> && cd testai

# 2. Create environment files from templates
cp .env.example .env
cp backend/.env.example backend/.env

# 3. Edit .env with your API key
#    OPENAI_API_KEY=sk-your-api-key-here

# 4. Start all services (first run will build images)
make up
#    Or manually: docker compose up -d

# 5. Verify everything is healthy
make health
#    Or manually check:
#    - Backend:  http://localhost:8001/health
#    - Frontend: http://localhost:3001
#    - API Docs: http://localhost:8001/openapi.json
#    - DB:       docker compose exec db pg_isready -U postgres
```

Open **http://localhost:3001** to access the TestAI dashboard.

### What the Docker Compose Environment Provides

| Service | Port | Description |
|---|---|---|
| **Postgres** | 5432 | Database for sessions, messages, kanban, artifacts, jobs |
| **Backend (FastAPI)** | 8000 | Agent orchestration engine + REST API |
| **Frontend (Next.js)** | 3000 | Dashboard UI |
| **Nginx** (production only) | 80 | Reverse proxy routing `/api/` to backend, everything else to frontend |

### Local Development Setup

For active development on frontend or backend independently:

```bash
# ── Frontend (port 3000) ──
npm install
npm run dev

# ── Backend (port 8000) ──
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
# Copy env and set your API key in the UI at Settings → Backend Providers
cp .env.example .env
uvicorn api.main:app --reload --port 8000

# ── Database ──
# Either run Postgres locally or via Docker:
docker compose up -d db
```

## Project Structure

```
testai/
│
├── src/                                          # Next.js 16 frontend
│   ├── app/                                      # App Router
│   │   ├── layout.tsx                            # Root layout: ThemeProvider, ReactQuery, CommandPalette
│   │   ├── page.tsx                              # Redirects to /dashboard
│   │   ├── globals.css                           # Design tokens + Tailwind CSS v4
│   │   ├── (dashboard)/                          # Route group (41 sub-routes)
│   │   │   ├── activity/                         # Live SSE event feed
│   │   │   ├── admin/                            # Admin panel
│   │   │   ├── agent-eval/                       # Agent evaluation
│   │   │   ├── agents/                           # Agent registry & active agents
│   │   │   ├── ai-ops/                           # AI operations dash
│   │   │   ├── analytics/                        # Usage analytics
│   │   │   ├── artifacts/                        # Artifact browser
│   │   │   ├── audit/                            # Audit log
│   │   │   ├── channels/                         # Communication channels
│   │   │   ├── chat/                             # Interactive agent chat
│   │   │   ├── compare/                          # Run comparison
│   │   │   ├── cost/                             # Token cost breakdown
│   │   │   ├── cron/                             # Cron job management
│   │   │   ├── dashboard/                        # Main summary dashboard
│   │   │   ├── devtools/                         # Developer tools
│   │   │   ├── digest/                           # Daily/Weekly digests
│   │   │   ├── evaluate/                         # Test evaluation
│   │   │   ├── flaky-tests/                      # Flaky test detection
│   │   │   ├── history/                          # Session history
│   │   │   ├── jobs/                             # JobSpec list + detail
│   │   │   ├── kanban/                           # Kanban board workflow
│   │   │   ├── knowledge-graph/                  # KG browser
│   │   │   ├── load-testing/                     # Load test runs
│   │   │   ├── models/                           # Model registry
│   │   │   ├── notifications/                    # Notification center
│   │   │   ├── observability/                    # OTel status, compaction
│   │   │   ├── pipeline/                         # Pipeline DAG viewer
│   │   │   ├── project/                          # Project settings
│   │   │   ├── pull-requests/                    # PR management
│   │   │   ├── quality/                          # Quality metrics
│   │   │   ├── requirements/                     # Requirements tracking
│   │   │   ├── sandbox/                          # Sandbox configuration
│   │   │   ├── sessions/                         # Session browser
│   │   │   ├── settings/                         # Global settings
│   │   │   ├── skills/                           # Skill registry
│   │   │   ├── terminal/                         # Web terminal
│   │   │   ├── test-cases/                       # Test case management
│   │   │   ├── tools/                            # Tool registry
│   │   │   ├── traceability/                     # Full provenance view
│   │   │   ├── visual-testing/                   # Visual diff viewer
│   │   │   └── workflows/                        # Workflow definitions
│   │   └── api/                                  # Server-side API routes
│   │       ├── agents/[name]/route.ts            # Agent CRUD
│   │       ├── agents/active/route.ts            # Active agents
│   │       └── runs/[id]/logs/route.ts           # Run log streaming
│   ├── components/                               # React components
│   │   ├── ui/                                   # 47 shadcn/ui primitives
│   │   ├── layout/                               # Shell, sidebar, navbar
│   │   ├── shared/                               # Shared components (ReactQueryProvider, CommandPalette)
│   │   ├── dashboard/                            # Dashboard-specific components
│   │   ├── pipeline/                             # Pipeline DAG components
│   │   ├── jobs/                                 # Job list, detail, controls
│   │   ├── agents/                               # Agent cards, delegation tree
│   │   ├── chat/                                 # Chat interface
│   │   ├── kanban/                               # Kanban board components
│   │   ├── observability/                        # OTel status, metrics
│   │   ├── flaky/                                # Flaky test components
│   │   ├── session/                              # Session replay components
│   │   ├── activity/                             # Activity feed components
│   │   ├── settings/                             # Settings forms
│   │   ├── skills/                               # Skill browser components
│   │   ├── test-cases/                           # Test case components
│   │   ├── traceability/                         # Traceability tree
│   │   ├── cron/                                 # Cron job components
│   │   ├── history/                              # History components
│   │   ├── logs/                                 # Log viewer
│   │   ├── notifications/                        # Notification components
│   │   ├── project/                              # Project components
│   │   ├── sandbox/                              # Sandbox config components
│   │   ├── workflow/                             # Workflow editor components
│   │   ├── ai-ops/                               # AI ops components
│   │   └── test-plans/                           # Test plan components
│   ├── hooks/
│   │   └── use-mobile.ts                         # Mobile detection hook
│   ├── stores/
│   │   └── pipeline-store.ts                     # Zustand pipeline state
│   ├── lib/
│   │   ├── api/                                  # API client + generated types
│   │   ├── types/                                # TypeScript type definitions
│   │   └── utils.ts                              # cn() utility
│   └── __tests__/                                # Vitest test files
│       ├── utils.test.ts
│       ├── jobs-types.test.ts
│       ├── job-spec-adapters.test.ts
│       ├── compaction-section.test.tsx
│       ├── cost-dashboard.test.tsx
│       ├── observability-status.test.tsx
│       ├── session-health.test.tsx
│       ├── session-timeline.test.tsx
│       ├── status-footer.test.tsx
│       ├── throttle-indicator.test.tsx
│       ├── tier-badge.test.tsx
│       └── use-activity-feed.test.ts
│
├── backend/                                      # Python agent orchestration engine
│   ├── api/                                      # FastAPI application
│   │   ├── main.py                               # App factory, lifespan, router mounting
│   │   ├── deps.py                               # Dependency injection
│   │   ├── state.py                              # Shared application state
│   │   ├── admin_routes.py                       # Admin API endpoints
│   │   ├── agent_routes.py                       # Agent lifecycle endpoints
│   │   ├── settings_routes.py                    # Settings CRUD endpoints
│   │   ├── integration_routes.py                 # External integration endpoints
│   │   └── routers/                              # 63 route modules
│   │       ├── agents.py, chat.py, jobs.py, kanban.py, ...
│   │       ├── observability/, sessions/, settings/, ...
│   │       └── a2a/ (A2A protocol JSON-RPC routes)
│   ├── harness/                                  # Core agent orchestration (100+ modules)
│   │   ├── orchestrator.py                       # OrchestratorEngine class
│   │   ├── agent/                                # Agent class + deps + dispatch
│   │   │   ├── agent.py                          # 1310-line unified Agent class
│   │   │   ├── deps.py                           # AgentDependencies
│   │   │   └── tool_dispatch.py                  # ToolDispatcher
│   │   ├── a2a/                                  # A2A protocol server
│   │   ├── backends/                             # Execution backends (local, docker, ssh)
│   │   ├── channels/                             # Communication channels
│   │   ├── chat/                                 # Chat surface logic
│   │   ├── ci/                                   # CI integration (Git providers)
│   │   ├── context_compressor/                   # Context window management
│   │   ├── core/                                 # Core abstractions (events, base classes)
│   │   ├── cron/                                 # Cron/scheduled job support
│   │   ├── delivery/                             # Delivery router (Slack, Jira, Linear, email)
│   │   ├── jobs/                                 # Job system (JobSpec, dispatcher)
│   │   ├── hooks/ + hook_registry.py             # Hook system for user intervention
│   │   ├── integrations/                         # Third-party integrations
│   │   ├── kanban/                               # Kanban board management
│   │   ├── llm.py                                # LLM Router + ChatMessage
│   │   ├── mcp/                                  # MCP client
│   │   ├── memory/                               # Memory stores (L0/L1/L2)
│   │   ├── observability/                        # Telemetry, OTel export
│   │   ├── permissions/                          # Permission manager
│   │   ├── phases/                               # Orchestration phases
│   │   ├── plugins/                              # Plugin system
│   │   ├── providers/                            # LLM provider implementations
│   │   ├── sandbox/                              # Docker sandbox management
│   │   ├── scheduler/                            # Cron-based job scheduler
│   │   ├── search/                               # Search providers
│   │   ├── services/                             # Background services (janitor, sweeper, memory monitor)
│   │   ├── skills/                               # Skill system
│   │   ├── store/                                # Persistence adapters (Postgres, in-memory)
│   │   ├── subagents/                            # Subagent definitions
│   │   ├── tools/                                # ~88 tool implementations
│   │   ├── webhooks/                             # Webhook support
│   │   ├── workflow/                             # Workflow engine
│   │   └── ... (60+ additional modules)
│   ├── tests/                                    # 130+ test files
│   │   ├── conftest.py                           # Shared fixtures
│   │   ├── fake_llm.py                           # Mock LLM for tests
│   │   ├── test_*.py                             # ~100 automated tests
│   │   ├── manual_*.py                           # ~15 manual smoke tests
│   │   ├── phases/                               # Phase-specific tests
│   │   └── blocking_io/                          # Blocking IO detection tests
│   ├── requirements.txt                          # Python dependencies
│   ├── test.txt                                  # Test dependencies
│   ├── Dockerfile                                # Python 3.11-slim container
│   ├── check_db.py, check_routes.py              # Health checks
│   └── e2e_check.py, e2e_smoke.py                # E2E verification scripts
│
├── .testai/                                      # TestAI runtime configuration
│   ├── mcp.json                                  # MCP server config
│   ├── memories/                                 # Cross-run memory storage
│   ├── prompts/                                  # System prompt templates
│   ├── skills/                                   # 75+ skill definitions (subdirectories)
│   └── verification/                             # E2E verification artifacts
│
├── agent_workspace/
│   └── agents/                                   # 76 agent role definitions (.md)
│       ├── architect.md, coordinator.md
│       ├── planner.md, explore.md
│       ├── code-reviewer.md (8 parts)
│       ├── subagent-delegator.md
│       ├── test-planner.md, tdd-guide.md
│       ├── e2e-runner.md, security-reviewer.md
│       ├── build-error-resolver.md
│       └── language-specific: python, java, go, rust, c++, php, kotlin, database
│
├── docs/                                         # 97 architecture & design documents
│   ├── PRODUCT.md                                # Product description, brand, design principles
│   ├── CONTEXT.md                                # Domain glossary (injected as system context)
│   ├── research/                                 # Harness comparison, gap analysis
│   ├── 2026-06-21-c0*-design.md                  # C01-C08 feature designs
│   ├── 2026-06-22-f0*-design.md                  # F02, F04 feature designs
│   ├── stabilization-sprint-1.md                 # Stabilization plans
│   ├── gaps-and-missing-features-*.md            # Gap analysis reports
│   ├── E2E_*_TEST_*.md                           # E2E test reports
│   └── *.drawio                                  # Architecture diagrams
│
├── scripts/                                      # 23 utility scripts
│   ├── submit_f3_smoke.py, submit_job.py
│   ├── check_tools.py, check_session.py
│   ├── check_events.py, check_orch.py
│   ├── test_frontend_api.py, test_lifespan.py
│   ├── test_providers.py, test_tool_calling.py
│   ├── refresh_pricing.py, list_mcp_tools.py
│   ├── health-check.sh
│   ├── analyze_hooks.js, analyze_hooks.ps1
│   └── _check_settings.js, _check_settings_imports.js
│
├── docker-compose.yml                             # 4 services: postgres, backend, frontend, nginx
├── Dockerfile.frontend                            # Node 20-alpine multi-stage build
├── nginx.conf                                     # Production reverse proxy config
├── sandbox.toml                                   # Sandbox resource limits
├── components.json                                # shadcn/ui configuration
├── tsconfig.json                                  # TypeScript configuration
├── next.config.ts                                 # Next.js configuration
├── vitest.config.ts                               # Vitest configuration
├── postcss.config.mjs                             # PostCSS + Tailwind CSS
├── Makefile                                       # Developer convenience commands
├── .env.example                                   # Frontend environment template
├── .github/workflows/                             # CI/CD pipelines
│   ├── ci.yml                                     # PR/push: typecheck, lint, vitest, build, pytest
│   ├── e2e.yml                                    # Weekly E2E + on PR touching backend/src
│   └── testai-pr.yml                              # TestAI auto-test on PR via webhook
└── package.json                                   # NPM project manifest

## Configuration

### Frontend Environment Variables (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | Yes | `http://localhost:8001` | Backend API base URL for client-side requests |
| `BACKEND_URL` | Yes | `http://localhost:8001` | Backend API base URL for server-side requests |
| `OPENAI_API_KEY` | Yes | — | LLM provider API key for server-side API routes |
| `OPENAI_BASE_URL` | No | `https://opencode.ai/zen/go/v1` | LLM provider base URL |
| `NEXT_PUBLIC_DEFAULT_MODEL` | No | `deepseek-v4-flash` | Default model ID shown in the UI |
| `DEFAULT_MODEL` | No | `deepseek-v4-flash` | Default model ID for server-side calls |

### Backend Environment Variables (`backend/.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8000` | Server port |

> **Note:** LLM provider API keys, endpoints, and models are configured through the dashboard at **Settings → Backend Providers**, not environment variables. This allows runtime configuration without server restarts.

### Sandbox Configuration (`sandbox.toml`)

| Setting | Default | Description |
|---|---|---|
| `type` | `docker` | Sandbox execution type |
| `image` | `opensandbox/execd:latest` | Container image |
| `sandbox_image` | `ubuntu` | Base OS image |
| `memory` | `512MB` | RAM limit per sandbox |
| `cpu` | `1` | CPU cores per sandbox |
| `timeout` | `300s` | Maximum execution timeout |

### MCP Server Configuration (`.testai/mcp.json`)

JSON configuration file for Model Context Protocol servers. Each entry specifies the server name, command, arguments, and environment variables. Agents discover MCP tools at runtime via this configuration.

## Development Guide

### Available Commands

#### Makefile Targets

| Command | Description |
|---|---|
| `make up` | Start all services via Docker Compose |
| `make down` | Stop all services |
| `make build` | Build all Docker images |
| `make backend` | Hot-reload Python changes (copy files + restart container) |
| `make frontend` | Rebuild and restart frontend container |
| `make logs` | Tail logs from all services |
| `make health` | Check health of all services (backend, frontend, database, API docs) |
| `make test` | Run full Python integration test suite |
| `make test-quick` | Run quick health/endpoint test subset |
| `make db-shell` | Open interactive psql shell |
| `make db-reset` | Reset database (drop all data, recreate on next backend start) |
| `make clean` | Remove all stopped containers and unused Docker images |
| `make setup` | First-time setup — copy .env.example files if they do not exist |

#### NPM Scripts

| Script | Command | Description |
|---|---|---|
| `npm run dev` | `next dev -p 3000` | Start Next.js dev server on port 3000 |
| `npm run build` | `next build` | Production build |
| `npm run start` | `cross-env NODE_ENV=production node .next/standalone/server.js` | Production server start |
| `npm run lint` | `eslint .` | Run ESLint across all frontend files |
| `npm run generate:api` | `openapi-typescript http://localhost:8001/openapi.json -o src/lib/api/schema.d.ts` | Generate TypeScript types from OpenAPI spec |
| `npm run test:ts` | `tsc --noEmit` | TypeScript type checking |
| `npm run test` | `vitest run` | Run Vitest unit tests |
| `npm run test:watch` | `vitest` | Run Vitest in watch mode |

### Workflow: Adding a New Route

1. Create the route directory in `src/app/(dashboard)/<name>/`
2. Add a `page.tsx` with the dashboard layout
3. Import and compose components from `src/components/<name>/`
4. Add API client methods in `src/lib/api/`
5. Add types in `src/lib/types/`
6. Add tests in `src/__tests__/`
7. Run `npm run test:ts && npm run lint && npm run test` to verify

### Workflow: Adding a New Tool

1. Create the tool class in `backend/harness/tools/<name>_tool.py`
2. Extend the base tool class with input/output schemas
3. Register the tool in `backend/harness/tools/registry.py`
4. Add the tool to the appropriate toolset in `backend/harness/tools/toolsets.py`
5. Gate the tool behind role declarations in `agent_workspace/agents/*.md`
6. Run `make test` to verify

### Code Conventions

- **Frontend**: TypeScript strict mode, shadcn/ui component patterns, Tailwind CSS v4 utility classes, CSS variable design tokens in `globals.css`
- **Backend**: Python 3.11 type hints, Pydantic models for all schemas, async/await throughout, FastAPI dependency injection
- **Agent roles**: Markdown files with YAML front matter declaring system_prompt, allowed_tools, allowed_skills, model, delegation_depth, bash_constraints, output_contract
- **Skills**: `SKILL.md` files in `.testai/skills/<name>/` with structured instructions

## Testing

### Frontend Tests (Vitest)

12 test files in `src/__tests__/` covering:

- **Utilities**: `utils.test.ts`, `jobs-types.test.ts`, `job-spec-adapters.test.ts`
- **Components**: `compaction-section.test.tsx`, `cost-dashboard.test.tsx`, `observability-status.test.tsx`, `session-health.test.tsx`, `session-timeline.test.tsx`, `status-footer.test.tsx`, `throttle-indicator.test.tsx`, `tier-badge.test.tsx`
- **Hooks**: `use-activity-feed.test.ts`

```bash
# TypeScript type checking
npm run test:ts

# Run all frontend tests
npm run test

# Watch mode
npm run test:watch
```

### Backend Tests (pytest)

130+ test files in `backend/tests/`:

- ~100 automated `test_*.py` files covering: agents, backends, chat, checkpoints, codegraph, compaction, context compression, deliveries, events, hooks, jobs, kanban, knowledge graph, MCP, memory, observability, orchestrator, pipelines, sandbox, tools, worktrees, and more
- ~15 manual smoke test scripts (`manual_*_smoke.py`)
- ~15 audit/check utility scripts (`_*.py`)
- Test fixtures: `conftest.py`, `fake_llm.py` (mock LLM responses)

```bash
# Full test suite
make test

# Quick subset (health, runs, sessions, export)
make test-quick

# Direct pytest invocation
python -m pytest backend/tests/ -v --timeout=30
```

### E2E Tests

GitHub Actions workflows:

| Workflow | Trigger | What it runs |
|---|---|---|
| **CI** (`ci.yml`) | PR/push to main | TypeScript typecheck, ESLint, Vitest, Next.js build, Python pytest |
| **E2E** (`e2e.yml`) | Weekly (Mon 06:00 UTC) + on PRs touching `backend/` or `src/` | Full-stack end-to-end test |
| **TestAI PR** (`testai-pr.yml`) | On PR via webhook to backend | Auto-trigger TestAI pipeline against the PR |

### Test Verification Reports

Recent E2E verification runs are documented in `docs/`:

- `E2E_AGENTIC_TEST_2026-06-16.md`
- `E2E_LIVE_TEST_2026-06-16.md`
- `E2E_AGENTIC_FULL_TEST_2026-06-17.md`
- `E2E_AGENT_HARNESS_TEST_2026-06-18.md`
- `E2E_SYSTEM_AUDIT_2026-06-18.md`
- `comprehensive-system-analysis-2026-06-25.md`

---

## In Progress & Roadmap

### Current Phase Status

The platform is being developed across five phases. The latest Gap Verification Report (2026-06-25) assesses readiness:

| Phase | Focus | Readiness | Status |
|---|---|---|---|
| **Phase 1: Reliability** | Fix immediate bugs, stuck detection, timeouts | **~100%** | Complete (7/7 gaps fixed) |
| **Phase 2: Isolation** | Per-subagent sandbox, circuit breaker, network isolation | **~90%** | Complete (5/7 fixed, 2 partial) |
| **Phase 3: Observability** | OTel export, latency metrics, tool health | **~40%** | In progress (5/12 fixed, 7 missing) |
| **Phase 4: Intelligence** | Compaction, context modes, skill versioning, flaky detection | **~65%** | In progress (6/11 fixed, 5 partial) |
| **Phase 5: User Facing** | GitHub integration, chat agent, sandbox config, multi-repo | **~50%** | In progress (2/6 fixed, 2 partial, 2 missing) |

### Recently Completed (C0-C8 Sprint)

| Feature | Description |
|---|---|
| **C01 — Worktree Isolation** | Per-session + per-subagent git worktree isolation using contextvar-based git runner propagation. Auto-cleanup on completion. |
| **C02 — Agent Teams** | Dynamic team creation via `team_create` tool. Lead gets full tool surface; members get read+reply. Auto-dissolve with TeamSweeper. |
| **C03 — Push-Based Board Completion** | `BoardWaiter` replaces 15s polling with push-based completion via EventBus. Zero DB polls in happy path. |
| **C04 — KG Refresh Tool** | Coordinator-only tool for mid-run incremental KG sync with 60s debounce and force-escape. |
| **C05 — A2A Wire Protocol** | Exposes orchestrator as standards-compliant A2A Server (JSON-RPC 2.0) with Agent Card at `/.well-known/agent.json`. |
| **C06 — Subagent Heartbeat** | `SubagentHeartbeat` with 5s interval, 30s idle fuse, 5min in-tool fuse. Raises `SubagentStuckError`. |
| **C07 — Budget Auto-Throttle** | 4-step ladder: HITL → sequential → cheaper model → pause. Sticky de-escalation. UI: ThrottleIndicator with 5-pip ladder. |
| **C08 — JobSpec Canonicalisation** | Single `POST /api/jobs` entry point. 8 chat tools. Real pause (not cancel). Auto-resume from checkpoint. DB-backed checkpoints. |
| **F02 — 1M-Context Support** | Compaction threshold 85%. `TESTAI_COMPACTION_THRESHOLD` env var. Grok-4.3 (1M) support. |
| **F04 — OpenTelemetry Spans** | 4 new span types. Opt-in via `OTEL_ENABLED`. Status endpoint + UI with live span counts. |

### Pending Bugs (P2)

Important issues identified post-Phase-8 verification, tracked in `backend/.pending-bugs.md`:

| # | Bug | Location | Impact |
|---|---|---|---|
| 10 | Legacy `HookRegistry` used in plugins | `harness/plugins/__init__.py:165` | Plugin hooks route through deprecated registry; modern pipeline never fires them |
| 11 | `json` re-imported inside loop | `harness/tools/code_search_tool.py:31,40,48` | Three `import json` calls inside per-iteration branch instead of top-level |
| 12 | Dependency graph only analyses `import_map` | `harness/tools/dependency_graph_tool.py:80-100` | "Incoming" branch falls back to substring search with false positives |
| 13 | Knowledge graph tool does not cache `_find_json_graph` | `harness/tools/knowledge_graph_tool.py:50-130` | Every `kg_search` call re-walks the disk probe list |
| 14 | Curator ignores its `db` argument | `harness/curator.py:80,145,170` | `run_curator`, `should_run`, `mark_run_completed` accept but never use `db` parameter |
| 15 | Curator "first run seeds last_run_at" is fragile | `harness/curator.py:148` | On fresh install, `should_run()` returns False forever |
| 16 | Pricing cache TTL hours is the only matching constant | `harness/pricing_cache.py:21` | Unit (hours) is hidden; callers do not know to multiply by 3600 |
| 17 | `discover_plugins` swallows FS errors | `harness/_hook_system.py:380-403` | `except Exception` masks obvious config errors |
| 18 | MCPClient constructor takes no config | `harness/mcp/client.py:687` | All config lives on `SamplingHandler`; outer client should expose config |
| 19 | `_read_curator_state` import mismatch | `api/routers/curator_api.py:25` | Resolved by Phase 8 alias; recorded for documentation |
| 20 | Lifespan swallows SandboxManager construction errors | `api/main.py:196-198` | Missing Docker daemon will abort startup instead of degrading |

### Pending Improvements (P3)

| # | Bug | Location | Impact |
|---|---|---|---|
| 21 | `_skills_cache_path` writes to home but reads from const | `harness/prompt_builder.py:28,~250` | Writer and reader use slightly different paths |
| 22 | `_adapt_skill` hard-codes replacements | `harness/tools/skill_tools.py:67-86` | Anthropic-to-TestAI tool-name mapping is a hand-rolled list |
| 23 | `INSTALL_POLICY["community"]` too strict | `harness/tools/skills_guard.py:45` | ~80% of community skills caught by caution-level findings |
| 24 | `SamplingHandler.metrics` is a plain dict | `harness/mcp/client.py:605` | Mutated from sampling coroutine without a lock |
| 25 | `get_hook_registry()` mutates a global | `harness/_hook_system.py:151` | In multi-tenant, leaks hook registrations across requests |

### Deferred Features (v1.1+ Candidates)

From `docs/TODO-v1.1.md` — features deferred with explicit re-introduction criteria:

| Feature | Re-introduce when |
|---|---|
| **Skill-evolution PRs** | Version history, human-review-before-use, cross-machine sync, or skills library >50 skills is needed |
| **Per-feature test tracker** | Anyone asks "did the last run cover feature X?" |
| **Workspace PR** (job-to-branch PR) | Users want the agent to push branches and open PRs on remote repos |
| **AST-based code index** | Context compression needs improvement beyond heuristic truncation |
| **Auth (HTTP basic env-var)** | External access beyond localhost is required |
| **Multi-tenant user_id (Path B)** | Multiple teams need isolated workspaces |

### Key Remaining Gaps (Unaddressed in Current Phase)

From `docs/gaps-and-missing-features-2026-06-25.md`:

| Gap | Area | Notes |
|---|---|---|
| G24 | No orchestrator integration tests | Planned for Phase 3 |
| G30 | Per-subagent memory isolation | Deferred to later phase |
| G32 | Per-tool cost tracking | Deferred |
| G36 | No codegraph tool tests | Deferred |
| G42 | Cross-session chat context | Deferred |
| G44 | User-configurable artifact lifecycle | Deferred |
| G48 | CI/CD e2e pipeline test | Deferred |
| G49 | GPU support | Future phase |

### Upcoming Projects (Adoption Queue)

From `docs/upcoming-projects-research-2026-06-24.md` — external projects evaluated for adoption:

#### Tier 1 — High Impact

| Project | Pattern | Effort | Priority |
|---|---|---|---|
| **Sponsio** | Deterministic policy enforcement (0.01ms, zero LLM) | 3 sprints | P1 |
| **TokenTamer** | AST-based context compression (50-80% savings) | 2 sprints | P2 |
| **Scenario** | Simulation-based agent testing (agents test agents) | 2 sprints | P3 |
| **Chorus** | AI-DLC workflow, Agent Connections dashboard | 2 sprints | P4 |
| **Mirage** | Unified VFS — replace 10-15 API tools with filesystem ops | 3 sprints | P5 |
| **Nono** | Zero-latency sandbox (alternative to Docker) | 2 sprints | P6 |
| **Cognee** | Memory platform with knowledge graph (replace memory_tool) | 2 sprints | P7 |
| **oh-my-pi** | Hash-anchored edits, LSP pre-flight, DAP | 4 sprints | P8 |
| **Logfire** | Agent observability dashboard (Pydantic/OTel) | 1 sprint | P9 |

#### Tier 2 — Medium Impact

| Project | Description | Effort |
|---|---|---|
| **abtop** | Agent process monitor widget | 1 sprint |
| **claude-tap** | Agent API traffic inspector | 1 day |
| **TrustGraph** | Holonic context graphs for L2 memory | 3 sprints |
| **BitRouter** | Cost-optimizing LLM router | 2 sprints |
| **oh-my-agent** | Domain-specialized agent roles | 2 sprints |
| **thClaws** | OpenRouter Fusion for multi-model deliberation | 3 sprints |
| **Replayd** | Replayable agent regression tests | 1 sprint |
| **Memori** | Agent-native memory infrastructure | 2 sprints |
| **agentverify** | Deterministic agent testing via pytest plugin | 1 sprint |

### Deferred C05-b Features

The A2A protocol implementation defers to a follow-up sprint (C05-b):

- `tasks/resubscribe` — push notification re-subscription
- Push notifications — server-initiated event delivery
- `FilePart` ingestion — file content handling in A2A messages
- A2A client tool — tool for coordinator to call external A2A agents

### Deferred C07 Features

The budget auto-throttle system defers:

- Per-user-per-day budget caps
- Custom threshold configuration per agent type
- Auto-resume after step 4 pause

---

## Deployment

### Production Profile

The production deployment uses Docker Compose with four services behind Nginx:

```bash
docker compose --profile production up -d
```

This starts:

| Service | Image | Role |
|---|---|---|
| **Postgres** | `postgres:16-alpine` | Persistent database for sessions, messages, jobs, kanban, artifacts |
| **Backend** | Custom (`backend/Dockerfile`) | Python 3.11-slim, single-worker Uvicorn, FastAPI agent engine |
| **Frontend** | Custom (`Dockerfile.frontend`) | Node 20-alpine, Next.js standalone build (multi-stage, minimal image) |
| **Nginx** | `nginx:alpine` | Reverse proxy: serves frontend at `/`, proxies `/api/*` to backend |

### Production Architecture

```
                          Internet
                             │
                        ┌────▼────┐
                        │  Nginx   │  Port 80
                        │ (reverse │
                        │  proxy)  │
                        └────┬────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
         │ Frontend│   │ Backend │   │Postgres │
         │ Next.js │   │ FastAPI │   │   16    │
         │  :3000  │   │  :8000  │   │  :5432  │
         └─────────┘   └─────────┘   └─────────┘
```

### Frontend Build (Multi-Stage)

`Dockerfile.frontend` uses a multi-stage build:
1. **Deps stage** — `npm ci` with frozen lockfile
2. **Build stage** — `npm run build` generates standalone output
3. **Production stage** — `node .next/standalone/server.js` with public assets copied

### Backend Container

`backend/Dockerfile` is a single-stage Python 3.11-slim build:
- Installs system dependencies (git, build-essential, postgresql-client)
- Installs Python packages from `requirements.txt`
- Runs `uvicorn api.main:app --host 0.0.0.0 --port 8000` (single worker)

### Nginx Configuration

`nginx.conf` routes:
- `/` → Frontend (Next.js standalone on port 3000)
- `/api/*` → Backend (FastAPI on port 8000)
- WebSocket upgrades for real-time SSE streaming

### Environment Variables for Production

In addition to dev variables, production requires:

| Variable | Service | Description |
|---|---|---|
| `POSTGRES_SERVER` | Backend | PostgreSQL hostname (default: `db`) |
| `POSTGRES_USER` | Backend | Database user (default: `postgres`) |
| `POSTGRES_PASSWORD` | Backend | Database password |
| `POSTGRES_DB` | Backend | Database name (default: `testai`) |
| `OTEL_ENABLED` | Backend | Set to `true` to enable OpenTelemetry export |

### Docker Compose Configuration

The `docker-compose.yml` defines four services with:
- Named volumes for Postgres data persistence
- Health checks on all services
- Dependency ordering (backend waits for db, frontend waits for backend)
- Production profile flag to include Nginx
- Backend environment variables for database connection

---

## Contributing

### Getting Started

1. Read the domain glossary in [`docs/CONTEXT.md`](docs/CONTEXT.md) — this is injected as system context for agents and covers all domain concepts
2. Read [`docs/PRODUCT.md`](docs/PRODUCT.md) for brand, design principles, and persona definitions
3. Explore the agent role definitions in `agent_workspace/agents/` for role conventions
4. Review the skill definitions in `.testai/skills/` for reusable instruction patterns
5. Check the feature designs in `docs/2026-06-21-c0*-design.md` for implemented architecture decisions

### PR Requirements

All pull requests must pass:

| Check | Command | Scope |
|---|---|---|
| TypeScript type check | `npm run test:ts` | Frontend |
| ESLint | `npm run lint` | Frontend |
| Vitest | `npm run test` | Frontend |
| Next.js build | `npm run build` | Frontend |
| Pytest | `make test` | Backend |

These checks run automatically via GitHub Actions CI (`.github/workflows/ci.yml`) on every PR/push to main.

### Code Conventions

- **Frontend**: TypeScript strict mode, shadcn/ui component patterns, Tailwind CSS v4 utility classes, CSS variable design tokens in `globals.css`
- **Backend**: Python 3.11 type hints, Pydantic models for all schemas, async/await, FastAPI dependency injection
- **Agent roles**: Markdown with YAML front matter (`system_prompt`, `allowed_tools`, `allowed_skills`, `model`, `delegation_depth`, `bash_constraints`, `output_contract`)
- **Skills**: `SKILL.md` files with structured, progressively-disclosed instructions
- **Design docs**: Markdown in `docs/` following the `YYYY-MM-DD-<feature>-design.md` naming convention

### Architecture Decision Records

Architecture decisions are documented in `docs/` with filenames following the convention `architecture-<topic>-<date>.md`. Key documents:

- `architecture-refactor-decisions.md` — Major refactoring decisions
- `architecture-review-*.md` — Architecture review notes
- `architecture-decision-tree.md` — Decision tree for architecture choices

### Reporting Issues

Bug reports should include:
- Component/area (frontend, backend, agent, skills, etc.)
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or screenshots
- Environment details (deployment mode, versions)

Feature requests should reference the relevant persona (QA Engineer, DevOps, etc.) and describe the use case.

---

## License

Private — internal use. All rights reserved.

---

*TestAI: Sharp. Intuitive. Relentless.*
