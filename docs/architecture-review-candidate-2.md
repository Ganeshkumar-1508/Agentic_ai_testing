# Candidate 2: Collapse 8 overlapping execution visibility pages into a unified Run viewer

**Strength**: Strong | **Category**: page architecture / modularity

---

## Research sources (10)

### Production agent harness UI patterns

1. **htek.dev — All Agent Harnesses Live Comparison** (Jun 2026)
   GitHub Copilot uses **Canvases** — one bidirectional work surface showing plans, PRs, browser sessions, terminals, deployments. No separate "Sessions" vs "Pipeline" vs "Jobs" pages.
   OpenAI Codex uses **Goals** — a single view with conversation history, file changes, tool calls, and run status.
   Anthropic Claude Code is CLI-first with session management via `/resume` and `--continue`.
   All 8 harnesses converge on 1-2 execution visibility surfaces, not 7+.
   https://htek.dev/articles/all-agent-harnesses-live-comparison

2. **Anthropic — Effective Harnesses for Long-Running Agents** (Nov 2025)
   "External artifacts become the agent's memory." Progress files, feature lists, session protocols persist across sessions.
   Session boundary is explicit: initializer agent sets up, coding agents execute one feature at a time.
   Product takeaway: "Progress tracking becomes real-time run feeds. Feature lists become spec imports and task breakdowns. Session protocols become agent orchestration."
   https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

3. **paddo.dev — Agent Harnesses: From DIY to Product** (Nov 2025)
   "What products must add: Visual progress tracking — timeline views, status indicators, screenshot captures. Structured intervention — controls for pause, resume, redirect, abort."
   The key: one unified session view with intervention controls, not split across pages.
   https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

4. **OpenHands/Agent Canvas** — One canvas per agent session. Backends, automations, integrations all accessible from the same surface. No separate "sessions" page, "pipeline" page, "jobs" page.
   https://github.com/All-Hands-AI/OpenHands

5. **r3moteBee/Pantheon** — Dashboard / Projects / Agents / Tasks / Memory / Settings. Clean separation: execution visibility is one page (Tasks), configuration is the rest. No overlapping pages.
   https://github.com/r3moteBee/pantheon

6. **Learn Harness Engineering — Lecture 11** (Observability)
   "Create a trace for each harness session, a span for each task, and sub-spans for each verification step."
   One trace = one session = one view. Not a trace for sessions, another for pipeline, another for jobs.
   https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/

7. **Microsoft Agentic Harness Architecture** (Observability)
   One observability pipeline with 2 dashboards (Azure Monitor + Grafana). Both show the same data from different angles. No overlapping pages for "activity", "observability", "cost", "sessions".
   https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

8. **dev.to — Agent Loop and Harness** (6-layer model)
   Six layers: Instruction → Context/Memory → Tool → Orchestration → Guardrails → Observability.
   Observability is one layer, not 4 pages.
   https://dev.to/mike_anderson_d01f52129fb/agent-loop-and-harness-a-practical-engineering-view-of-ai-operations-49o7

### Domain model references

9. **CONTEXT.md — Run** definition
   "Run — the unit of work. A single execution of the autonomous orchestrator. Owns a run_id, a source, a tree of subagent invocations, and a tier."
   The Run is the domain concept. Sessions, pipelines, jobs, kanban, activity, observability, cost are all facets of one Run.
   https://github.com/.../CONTEXT.md

10. **Codebase audit — 8 overlapping pages** (see below)

---

## Codebase evidence

### 8 pages, all showing agent execution data

| Page | Lines | What it shows | Overlaps with |
|---|---|---|---|
| `/sessions` | 751 | Session rows (chat/pipeline/delegation/PR sources), tabs for live/messages/delegation/PRs/artifacts/logs/timeline | **Everything** — it's already a full Run viewer |
| `/pipeline` | 567 | Pipeline runner with embedded kanban, skills, event stream, test types, history sidebar | Kanban (embedded `KanbanBoardSection`), Sessions (history list), Jobs (pipeline IS a job) |
| `/activity` | 364 | Activity feed + observability panels | Sessions (feed = sessions), Dashboard (activity widget), Observability (OTel panels) |
| `/jobs` | 294 | JobSpec list with status filters | Pipeline (creates jobs), Chat (submits jobs), Sessions (wraps jobs) |
| `/kanban` | 765 | Full kanban board with DnD, board selector, stats | Pipeline (reimplements `KanbanBoardSection`) |
| `/observability` | 35 | OTel status, compaction, provider events | Activity (also shows ProviderEventsSection/CompactionSection) |
| `/cost` | 87 | Cost dashboard with global/budget/trend data | Sessions (cost on every row), Dashboard (cost cards) |
| `/history/[runId]` | 793 | Run detail with artifacts, errors, replay, comparison | Sessions (session detail), Pipeline (run detail), Jobs (run IS a job) |

### The shallowness

The navigation interface (8 pages × 1 route each = 8 surface entries) is nearly as complex as the implementation (8 × 35-793 lines of page logic). This is a **shallow interface** — the same "what did the agent do" question routes to 8 different answers.

### The deletion test

Delete `/sessions`: complexity doesn't vanish — it reappears across Pipeline (embeds session history), Activity (reimplements feed), History (reimplements detail). Delete `/kanban`: Pipeline reimplements it inline. Delete any single page: the others already show overlapping data.

Delete them all and replace with **one Run viewer**: complexity concentrates in one deep module.

### The domain concept

CONTEXT.md defines **Run** — the unit of work. It has:
- A lifecycle (status, phases, checkpoints)
- Session data (chat messages, agent turns)
- Job data (JobSpec, tier, capabilities)
- Kanban board (if coordinator spawned tasks)
- Cost and token data
- Events and traces
- Artifacts

Currently every facet is a separate page. Deepening means **one Run viewer** with tabbed facets + a separate Configuration hub for settings that don't change per-run.
