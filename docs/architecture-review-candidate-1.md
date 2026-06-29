# Candidate 1: Full-stack rebrand and reorganise around agent-harness primitives

**Strength**: Strong | **Category**: brand identity / information architecture / full-stack naming

---

## Research sources (12)

### Agent harness industry context

1. **Epsilla — The Third Evolution** (Mar 2026)
   Three eras: Prompt Engineering (2022-2024) → Context Engineering (2025) → **Harness Engineering (2026)**.
   "The harness defines the agent's workflow, constraints, feedback loops, toolchain, and lifecycle."
   https://www.epsilla.com/blogs/harness-engineering-evolution-prompt-context-autonomous-agents

2. **Aakash Gupta — 2025 Was Agents, 2026 Is Agent Harnesses** (Jan 2026)
   "New moat: harness quality. Building reliable harnesses requires thousands of engineering hours."
   Old moat = model quality. New moat = harness infrastructure.
   https://aakashgupta.medium.com/2025-was-agents-2026-is-agent-harnesses-heres-why-that-changes-everything-073e9877655e

3. **Phil Schmid — The importance of Agent Harness in 2026** (Jan 2026)
   "The Harness is the Dataset." Competitive advantage is the trajectories your harness captures.
   Start simple, build to delete, think in terms of agent infrastructure layer.
   https://www.philschmid.de/agent-harness-2026

4. **paddo.dev — Agent Harnesses: From DIY to Product** (Nov 2025)
   Anthropic's harness patterns (progress files, feature lists, session protocols) become product surfaces.
   "Progress tracking becomes real-time run feeds. Session protocols become agent orchestration."
   https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

### Production harness architecture patterns

5. **htek.dev — All Agent Harnesses Live Comparison** (Jun 2026)
   ~98.4% of a production agent is harness infrastructure, ~1.6% is AI decision logic.
   8 harnesses compared: all organise around Runs/Sessions, Agents/Tools, Observability, Governance, Cost.
   No production harness uses "Test Cases" or "Flaky Tests" as primary navigation concepts.
   https://htek.dev/articles/all-agent-harnesses-live-comparison

6. **Microsoft Agentic Harness Architecture Guide — Observability**
   Span naming: `agent.turn`, `agent.tool_call`, `mcp.request`, `rag.retrieve`, `knowledge.query`.
   Metrics: `harness.agent.turns`, `harness.agent.tokens`, `harness.tools.invocations`.
   Navigation organised around harness primitives — not testing concepts.
   https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

7. **dev.to — Agent Loop and Harness: A Practical Engineering View**
   Six layers: Instruction → Context/Memory → Tool → Orchestration → Guardrails → Observability.
   "The model reasons, the agent loop decides and acts, the harness controls."
   https://dev.to/mike_anderson_d01f52129fb/agent-loop-and-harness-a-practical-engineering-view-of-ai-operations-49o7

### Harness engineering discipline

8. **Awesome Harness Engineering (walkinglabs)** — 250+ curated resources
   Organises the field: Foundations → Context/Memory → Guardrails/Safety → Specs/Workflow → Evals/Observability → Runtimes/Harnesses → MCP
   This taxonomy IS the domain model for harness engineering.
   https://github.com/walkinglabs/awesome-harness-engineering

9. **Awesome Harness Engineering (Jiaaqiliu)** — 883 entities, 1590 relationships
   Knowledge graph of agent infrastructure: frameworks, patterns, tools, organisations.
   https://github.com/Jiaaqiliu/Awesome-Harness-Engineering

10. **Learn Harness Engineering — Lecture 11: Making the Agent's Runtime Observable**
    "Create a trace for each harness session, a span for each task."
    Runtime signals: lifecycle, feature path execution, data flow, resource utilisation, errors.
    https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/

### Reference implementations

11. **r3moteBee/agent-harness (Pantheon)** — Self-hosted production web UI
    5-tier memory, project isolation, autonomous task scheduling, polished web UI.
    Navigation: Dashboard / Projects / Agents / Tasks / Memory / Settings.
    https://github.com/r3moteBee/agent-harness

12. **StormHub — Building Autonomous Agent Coding Harness** (Apr 2026)
    Multi-agent harness architecture from POC to production.
    Navigation around: agent lifecycle, task management, observability, sandboxes.
    https://stormhub.github.io/stormhub/blog/2026-04-11-Agent-Coding-Harness/

---

## Codebase evidence

### Quantity: 1674 references to "testai" across the entire stack

```
Frontend:   ~100+   brand name, localStorage keys, sidebar header, route paths, breadcrumbs
Backend:    ~520    Docker labels, container names, dir paths, env vars, git branches, fn names
Infra:      ~670    DB names, CI vars, Docker Compose services, network names, .testai/ dir
```

### Frontend — brand name and navigation anchor

| Location | What | Layer |
|---|---|---|
| `src/components/layout/AppSidebar.tsx:274` | Brand "TestAI" in sidebar | User-facing |
| `src/components/layout/AppSidebar.tsx:51-90` | NAV_CATEGORIES: "Analyze" section with Test Cases, Flaky Tests, Traceability | Architecture |
| `src/components/layout/AppHeader.tsx:9-26` | BREADCRUMB_LABELS maps `/test-cases`, `/flaky-tests` | User-facing |
| `src/app/(dashboard)/chat/page.tsx:22` | localStorage key `testai_chat_thread` | Internal |
| `src/app/(dashboard)/flaky-tests/page.tsx` | Route `/flaky-tests` | User-facing |
| `src/app/(dashboard)/visual-testing/page.tsx` | Route `/visual-testing` | User-facing |

### Backend — Docker, infra, naming conventions

| Location | What | Layer |
|---|---|---|
| `backend/harness/backends/docker.py:360` | Docker label `testai-managed=1` | Infrastructure |
| `backend/harness/backends/docker.py:313` | Container name `testai-{uuid}` | Infrastructure |
| `backend/harness/backends/docker.py:360-363` | Labels: `testai-agent=1`, `testai-session-id` | Infrastructure |
| `backend/harness/backends/credential_files.py:43-44` | Function `_testai_home()` → `~/.testai/` | Internal |
| `backend/harness/services/worktree_manager.py:294-305` | Git branch naming `testai/session-<id>` | Infrastructure |
| `backend/harness/services/worktree_manager.py:474` | Worktree dir `.testai-worktrees` | Infrastructure |
| `backend/harness/webhooks/github_pr_feedback.py:18` | GitHub mention pattern `@testai` | User-facing |
| `backend/harness/services/job_control.py:52` | DB column `testai_user_tier_override` | Database |
| `backend/api/routers/sandbox.py:123` | Volume prefix `testai-ws-` | Infrastructure |

### Infrastructure — Docker Compose, CI, database

| Location | What |
|---|---|
| `docker-compose.yml:7,27,59,74` | Container names: `testai-db`, `testai-backend`, `testai-frontend`, `testai-nginx` |
| `docker-compose.yml:10-12` | DB user/password/database all `testai` |
| `docker-compose.yml:33` | ENV `TESTAI_HOME=/app/.testai` |
| `docker-compose.yml:93` | Network name: `testai-network` |
| `.github/workflows/e2e.yml:29-31` | CI vars: POSTGRES_DB=testai_test, USER=testai, PASS=testai |
| `backend/.env:10` | `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/testai` |
| `.env:21` | `DATABASE_URL=postgresql://testai:testai@postgres:5432/testai` |

### The full-stack identity gap

Every other production agent harness organises its entire stack around **agent-harness primitives**:
- Runs/Sessions, Agents, Tools, Observability, Governance, Cost as navigation categories
- Docker labels reflecting the product identity (e.g. `copilot-`, `codex-`, `claude-`)
- Database names and users matching the product
- Git branch conventions using the product prefix

This project's backend already implements those primitives (CONTEXT.md, `backend/harness/` with 40+ sub-modules). But the full stack — from Docker labels to the frontend brand — still says **"TestAI"**. The frontend navigation module is just the most visible symptom of a system-wide identity that no longer matches what the system does.
