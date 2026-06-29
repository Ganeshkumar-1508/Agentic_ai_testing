# Feature Gap Analysis: Wireframes → Backend → Frontend

**Date:** 2026-06-14  
**Sources:** 49 wireframes in `plans/`, 30 backend routers, 18 frontend component directories, 4 reference harnesses (Hermes, OpenClaude, OpenHands, OpenHarness), htek.dev comparison, SWE-bench 2026

---

## 1. Already Implemented

These wireframes map to features already built and deployed:

| Wireframe | Backend | Frontend | Status |
|-----------|---------|----------|--------|
| `chat-page-wireframe.html` | `chat.py`, `agent.py` | `/agent` page | ✅ Done (3-col layout, SSE, tools sidebar) |
| `sessions-wireframe.html` | `chat.py` get/list | `/sessions` | ✅ Done (list + detail with tabs) |
| `pipeline-page-wireframe.html` | `pipeline.py`, `delegate.py` | `/agent` pipeline mode | ✅ Done |
| `kanban-wireframe.html` | `kanban.py` (10.4KB) | `/kanban` page | ✅ Done |
| `testcases-page-wireframe.html` | `testcases.py` | `/test-cases` | ✅ Done (folder tree + detail) |
| `traceability-wireframe.html` | `traceability_api.py` | `/traceability` | ✅ Done (graph/matrix/table views) |
| `knowledge-graph-*.html` | `knowledge_graph_api.py` (15.7KB) | `/knowledge-graph` | ✅ Done |
| `sandbox-wireframe.html` | `sandbox.py` | `/sandbox` | ✅ Done |
| `logs-wireframe.html` | `logs.py` | Session detail → logs tab | ✅ Done |
| `project-settings-wireframe.html` | `settings.py` + `ops.py` | `/settings` + `/project` | ✅ Done |

---

## 2. Wireframes With Partial Implementation

| Wireframe | What exists | What's missing |
|-----------|-------------|----------------|
| `dashboard-wireframe-v2..v5` | Dashboard page with KPIs, quality score, pipeline feed, cost cards, coverage | **Executive layer KPIs** (WoW trends, release confidence), **role-based views** (QA Lead/Engineer/Manager), drill-down paths, quality gates config, template-as-plans |
| `daily-digest-wireframe.html` | Digest page (redirects to /dashboard) | **Full digest**: overnight activity summary, cost burn, delivery channels config, pattern insights, "What we noticed" section |
| `compare-page-wireframe.html` | No compare page exists | **Run comparison**: side-by-side diff of test results, cost, duration, tool calls between two runs |
| `failure-classification-wireframe.html` | Error state in test detail | **Error grouping** (Sentry-style): cluster failures by root cause, not test name; per-cluster stats |
| `failure-heatmap-wireframe.html` | No heatmap | **Agent activity heatmap**: 90d calendar view + 24h time series + tool usage ranking |
| `defect-triage-wireframe.html` | No defect triage | **Defect triage workflow**: assign, prioritize, track fix cycles, escalate |
| `defect-prediction-wireframe.html` | RCA card in dashboard | **Defect prediction**: heuristic risk scoring (Low/Medium/High/Flaky), prediction accuracy tracking |
| `sprint-quality-trends-wireframe.html` | Quality trend chart exists | **Sprint-level quality trends**: per-sprint pass rate, flaky rate, coverage delta |
| `test-generation-wireframe.html` | Pipeline generates tests | **Test generation UX**: NL prompt → config options → generate → preview → save workflow |
| `artifacts-wireframe.html` | Artifacts tab in session detail | **Full artifact browser**: filter by type, preview in Monaco, download, compare versions |
| `tools-wireframe.html` (plugin-manager) | Tools page shows registry | **Plugin manager**: install/uninstall, version management, MCP server config |
| `runner-proposal-wireframe.html` | No runner config | **Runner configuration**: sandbox size, timeouts, resource limits, parallel workers |
| `skills-curator.html` | No skills UI | **Skills curator UI**: browse, install, configure skills; usage stats, provenance tracking |

---

## 3. Wireframes Not Started

These wireframes have NO corresponding implementation:

| Wireframe | Backend needed | Frontend needed | Priority |
|-----------|---------------|-----------------|----------|
| `daily-digest-wireframe.html` | `digest_api.py` (exists, 1.7KB — sparse) | Dedicated daily digest page or dashboard tab | Medium |
| `compare-page-wireframe.html` | New: run comparison endpoint | Compare page with diff view | Low |
| `homepage-wireframe.html` / v2 | None (static marketing) | Homepage for non-authenticated users | Low |
| `project-isolation-ui.html` | Project scoping middleware | Project switcher + isolation settings | Medium |
| `project-switcher-dashboard-wireframe.html` | Project API + per-project data | Dashboard scoped to active project | Medium |
| `agent-swarm-wireframe.html` | `swarm/` in ops.py exists | Swarm dashboard page | Low |
| `swarm-dashboard.html` | Same as above | Alternative swarm view | Low |
| `agent-pr-tooling-wireframe.html` | `pr_manager.py` (20KB) exists | PR tooling interface | Low (PR page merged into sessions) |

---

## 4. Backend Features That Exist But Have No UI

These backend modules have NO frontend counterpart:

| Module | Size | What it does | Missing UI |
|--------|------|-------------|------------|
| `backend/harness/hooks/` | - | Hook system (10 lifecycle events) | Hook config UI, hook logs |
| `backend/harness/plugins/` | - | Plugin system | Plugin manager in Tools page |
| `backend/harness/jobs/` | - | Cron job scheduler | Cron job management UI |
| `backend/harness/scheduler/` | - | Task scheduler | Schedule config UI |
| `backend/harness/ci/` | - | CI integration | CI config UI |
| `backend/harness/delivery/` | - | Delivery router (Slack/Teams/email) | Channel config in Settings |
| `backend/harness/integrations/` | - | External integrations | Integration config UI |
| `backend/harness/services/` | - | Service layer | Admin services UI |
| `backend/harness/permissions/` | - | Permission system | Permission config UI |
| `backend/harness/context_compressor/` | - | Context compression | Compaction stats/metrics UI |
| `backend/harness/environments/` | - | Environment management | Environment config UI |

---

## 5. High-Value Features From Other Harnesses (Not In Wireframes)

From the comparative research (Claude Code, OpenCode, Pi, OpenHands, Hermes):

| Feature | Source | What it does | Effort |
|---------|--------|-------------|--------|
| **Command palette (Cmd+K)** | Claude Code, VS Code | Universal search: runs, sessions, tests, files, settings | 2h |
| **Live sandbox terminal (xterm.js)** | Claude Code | SSH into running sandbox from browser | 4h |
| **Reactive compaction** | OpenHarness, Claude Code | Auto-detect context overflow → compact → retry | 3h |
| **JSONL session recording** | Hermes, Claude Code | Record all sessions as JSONL for replay/debug | 2h |
| **Provider descriptor model** | Hermes, OpenClaude | Declarative provider config (no code changes for new providers) | 4h |
| **Permission modes** | OpenHarness | FULL_AUTO / DEFAULT / PLAN permission presets | 3h |
| **Error classification** | Hermes (12+ failure types) | Classify errors → map to recovery strategies | 3h |
| **FakeApiClient testing pattern** | OpenHarness | Deterministic fake streaming for test reliability | 2h |
| **Iteration budget** | Hermes | Shared token/cost budget trackable by parent+child | 2h |
| **Session forking** | OpenClaude | Branch conversation for experiments | 1h |

---

## 6. Recommended Build Order

Based on effort + value + wireframe completeness:

| Phase | Features | Wireframes | Total effort |
|-------|----------|------------|-------------|
| **P1: Dashboard polish** | Digest tab, error grouping, heatmap | `daily-digest`, `failure-heatmap`, `failure-classification` | ~8h |
| **P2: Quality gates** | Quality config, sprint trends, defect triage | `sprint-quality-trends`, `defect-triage`, `defect-prediction` | ~8h |
| **P3: Compare + run detail** | Run comparison, session replay, batch re-run | `compare-page`, `runs-wireframe` | ~6h |
| **P4: Project isolation** | Project switcher, per-project data, isolation UI | `project-switcher`, `project-isolation`, `projects-wireframe` | ~6h |
| **P5: Backend depth** | Provider descriptors, compaction, JSONL recording | No wireframe — backend infra | ~9h |
| **P6: QoL** | Command palette, terminal, saved filters, notifications | No wireframe — UX infra | ~8h |
| **P7: Admin** | Hook config, plugin manager, cron UI, permissions | `plugin-manager`, `skills-curator` | ~10h |
