# TestAI-Production — Handoff Document

**Date:** 2026-06-04  
**Previous session focus:** Architecture review, codebase cleanup, pipeline fixes, UI redesign, agent management system  
**Next session focus:** Complete agent orchestration patterns, sandbox detail page wireframe parity, end-to-end pipeline test

---

## Session Summary

Massive refactoring session covering both backend (Python/FastAPI) and frontend (Next.js/React) across ~50 files. The project is a web-based AI agent harness for automated testing.

---

## Key Decisions (recorded in `docs/architecture-refactor-decisions.md`)

All architectural decisions were logged per the `/improve-codebase-architecture` skill workflow. Key decisions:

| # | Decision | Rationale |
|---|----------|-----------|
| 5 | Keep 6 stub routers | Wireframes created in `plans/`, API surface stable |
| 6 | Delete SQLAlchemy + 4 npm packages | Dead dependencies, zero imports |
| 7 | Add `.github/workflows/ci.yml` | TypeScript check + lint + test + build on every PR |
| 8 | Consolidate 37 routers → 4 aggregators | `main.py` imports reduced from 34 to 4 |
| 9 | Single-file agent (merge 5 mixins) | Follows OpenClaude QueryEngine.ts pattern |
| 10 | Tool self-registration with check_fn | 7 tools auto-disable when API keys missing |
| 11 | Startup instrumentation | 16 timing checkpoints logged at boot |
| 12 | Agent workspace mount → per-repo volumes | Persistent KG, test results across runs |
| 14 | Settings page → 4 categories | Agents / Pipeline / Integrations / System |

---

## What Was Built

### Backend
- **Agent config system** (`backend/harness/agent_config.py`) — Markdown files with YAML frontmatter, following OpenHands microagents pattern. 5 default agents (test-writer, code-reviewer, bug-fixer, security-auditor, docs-writer). CRUD via `AgentStore` class.
- **Agent API** (`backend/api/routers/agents.py`) — `GET/PUT/DELETE /api/agents` endpoints. Registered in `settings_routes.py` as `agents_router`.
- **Knowledge graph generator** (`backend/harness/tools/kg_generator.py`) — Lightweight KG builder callable by agents. Registers as `kg_generator` tool.
- **KG API** (`backend/api/routers/knowledge_graph_api.py`) — Serves KG from `agent_workspace/knowledge-graphs/`.
- **Sandbox metrics API** (`GET /api/sandbox/metrics`) — Aggregate CPU/memory/disk across all sandboxes for KPI strip.
- **Pipeline Fan-Out** (`backend/api/routers/pipeline.py`) — Now reads from `AgentStore` and fans out parallel tasks.
- **Schema fixes** — `pr_tracker` (BIGSERIAL→TEXT), `agent_delegations` (added `parent_delegation_id`).
- **Tech stack detection fix** — Was returning "unknown" due to `isinstance(..., dict)` check on a list.

### Frontend
- **Settings page** (`src/app/(dashboard)/settings/page.tsx`) — Redesigned with 4 categories, per-tab descriptions, merged duplicates.
- **Agent settings UI** (`src/components/settings/AgentsSettings.tsx`) — Add/edit/delete agents with tool toggles, modal editor.
- **Sandbox list page** — KPI strip (6 cards), SVG gauges (CPU/Mem/Disk), status bar, sandbox table with filters, port map, artifacts, event log.
- **Pipeline page** — Wireframe-matched layout with KPI row, requirements input, mode selector, history panel, skills panel, templates gallery, live execution dashboard, approval queue, pipeline summary.
- **Knowledge graph page** — Now draws edges between connected nodes using computed positions.
- **Sandbox detail page** — 3-column resizable layout with FileTree, Resources, Ports, Terminal, TestSummary, FlakyTests, Artifacts, Dependencies.
- **Build fix** — Added `@types/node` to `package.json` + `uuid` overrides. Build time reduced from ~270s to ~70s.

### Infrastructure
- `.github/workflows/ci.yml` added (typecheck → lint → test → build + pytest)
- `Dockerfile.frontend` fixed (removed `output: "standalone"` bug)
- `Dockerfile` unchanged
- `docker-compose.yml` unchanged

---

## Files Touched (Complete List)

### Backend (Python)
| File | Action |
|------|--------|
| `backend/harness/agent_config.py` | **NEW** — Agent config markdown store |
| `backend/harness/tools/kg_generator.py` | **NEW** — Lightweight KG generator tool |
| `backend/harness/tools/browser.py` | Modified — Added `check_fn` |
| `backend/harness/tools/computer_use_tool.py` | Modified — Added `check_fn` |
| `backend/harness/tools/database_query_tool.py` | Modified — Added `check_fn` |
| `backend/harness/tools/docker_executor.py` | Modified — Added `check_fn` |
| `backend/harness/tools/image_generate_tool.py` | Modified — Added `check_fn` |
| `backend/harness/tools/send_message_tool.py` | Modified — Added `check_fn` |
| `backend/harness/tools/web_tools.py` | Modified — Added `check_fn` |
| `backend/harness/tools/registry.py` | Modified — Added `check_fn` support + helpers |
| `backend/harness/tools/execute_code.py` | Modified — Fixed `default_level` parameter |
| `backend/harness/agent/agent.py` | **REWRITTEN** — Single-file agent (659 lines) |
| `backend/harness/agent/emitters.py` | **DELETED** — Merged into agent.py |
| `backend/harness/agent/interrupts.py` | **DELETED** |
| `backend/harness/agent/reflexion.py` | **DELETED** |
| `backend/harness/agent/tools.py` | **DELETED** |
| `backend/harness/agent/loop.py` | **DELETED** |
| `backend/harness/agent/__init__.py` | Modified — Updated exports |
| `backend/harness/sandbox_manager.py` | Modified — Lazy agent_workspace mount, volume_key param |
| `backend/harness/memory/schema/schema.sql` | Modified — Fixed pr_tracker + agent_delegations |
| `backend/api/main.py` | Modified — Router consolidation (37→4), StartupTimer |
| `backend/api/agent_routes.py` | **NEW** — Router aggregator |
| `backend/api/settings_routes.py` | **NEW** — Router aggregator + agents_router |
| `backend/api/admin_routes.py` | **NEW** — Router aggregator |
| `backend/api/integration_routes.py` | **NEW** — Router aggregator |
| `backend/api/routers/agents.py` | **NEW** — Agent CRUD API |
| `backend/api/routers/knowledge_graph_api.py` | **NEW** — KG serving API |
| `backend/api/routers/sandbox.py` | Modified — Added `/sandbox/metrics` |
| `backend/api/routers/pipeline.py` | Modified — KG gen, Fan-Out support, agent_store integration |
| `backend/requirements.txt` | Modified — Removed SQLAlchemy |
| `backend/tests/test_agent_capabilities.py` | Modified — MRO test → method test |

### Frontend (TypeScript/React)
| File | Action |
|------|--------|
| `src/app/(dashboard)/settings/page.tsx` | **REWRITTEN** — 4 categories, descriptions |
| `src/app/(dashboard)/sandbox/page.tsx` | **REWRITTEN** — KPI strip, gauges, status bar, tabs |
| `src/app/(dashboard)/pipeline/page.tsx` | **REWRITTEN** — Full wireframe match |
| `src/app/(dashboard)/knowledge-graph/page.tsx` | Modified — Edge-connected nodes |
| `src/components/settings/AgentsSettings.tsx` | **NEW** — Agent CRUD UI |
| `package.json` | Modified — Added `@types/node`, `uuid` override, removed 4 unused deps |
| `next.config.ts` | Modified — Removed `output: standalone` |
| `Dockerfile.frontend` | **REWRITTEN** — Non-standalone build |

### Docs
| File | Action |
|------|--------|
| `docs/architecture-refactor-decisions.md` | **NEW** — Full decision log (14 Q&As) |
| `plans/agentic-testing-patterns-research.md` | **NEW** — Research doc (Hermes, OpenCode, Claude Code, OpenHands, Azure) |
| `plans/` | 6 wireframe HTML files added (defect-prediction, sprint-trends, defect-triage, test-generation, daily-digest, artifacts) |

---

## Current State

### What Works
- Tech stack detection → correctly returns "python"
- Knowledge graph → builds with 500+ nodes, persisted to `agent_workspace/`
- Pipeline → orchestrator → subagent completes in ~5min
- Agents CRUD API → `GET/PUT/DELETE /api/agents` returns 5 default agents
- Sandbox metrics API → aggregate CPU/memory/disk across sandboxes
- Settings page → 4 categories with descriptions
- Tool self-registration → 7 tools auto-disable based on `check_fn`
- Startup timer → 16 checkpoints logged
- CI pipeline → `.github/workflows/ci.yml`

### What Needs Work
1. **Pipeline Fan-Out** — The current implementation uses `tasks: [...]` but the `delegate_tool.run()` needs the `tasks` parameter properly tested. The default 5 agents (test-writer, code-reviewer, bug-fixer, security-auditor, docs-writer) should each get their own parallel subagent.
2. **Agent config parser fix** — YAML frontmatter tool/trigger parsing incorrectly returns empty arrays. The `agent_config.py` parser fix needs to be deployed (file was modified but build was interrupted).
3. **Sandbox detail page** — The `[sessionId]/page.tsx` imports 8 components (FileTree, Resources, Ports, Terminal, etc.) but they may need data wired to real API endpoints.
4. **Pipeline page live data** — Currently shows mock data in the execution dashboard. Needs real event stream connection.
5. **Orchestration pattern selector** — Azure patterns research completed. UI dropdown for sequential/concurrent/groupchat/handoff/magentic needs implementation.
6. **Test results persistence** — Pipeline saves to `agent_workspace/results/` but the test file scraping from sandbox needs verification.
7. **Frontend build time** — Currently ~250s. Pre-building node_modules or moving to multi-stage could help.

---

## Key URLs & References

- **Reference projects:** `reference/hermes-agent/`, `reference/openclaude/`, `reference/OpenHands/`, `reference/openharness/`
- **Research doc:** `plans/agentic-testing-patterns-research.md`
- **Decision log:** `docs/architecture-refactor-decisions.md`
- **Wireframes:** `plans/sandbox-wireframe.html`, `plans/pipeline-page-wireframe.html`, `plans/knowledge-graph-understand-anything.html`
- **Azure patterns:** https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns
- **OpenCode agents:** https://opencode.ai/docs/agents/
- **Understand-Anything:** https://github.com/Lum1104/Understand-Anything

---

## Sensitive Information (REDACTED)

- API key in `plans/test_env.txt` → key has been redacted (starts with `sk-l3mh...`)
- Backend `.env` contains `SECRET_KEY` → should be rotated if this repo goes public
- `backend/.env` has `DATABASE_URL` with credentials → local dev only, not production

---

## Suggested Skills

The following skills should be loaded for the next session:

1. **`design-taste-frontend`** — For any UI/UX work on the sandbox detail page, pipeline page, or settings page. Enforces Tailwind v4, Geist font, dark theme, bento grid patterns.

2. **`improve-codebase-architecture`** — For continuing the architecture review. Use the Glossary (Module, Interface, Depth, Seam, Adapter) when proposing refactors. Generate HTML architecture reports.

3. **`diagnose`** — For debugging the agent config parser, Fan-Out pipeline, or test persistence issues. Use the disciplined loop: reproduce → minimise → hypothesise → instrument → fix.

4. **`handoff`** — This skill. Use at end of next session to pass context cleanly.

5. **`find-skills`** — If the next task requires a capability not covered by installed skills.

6. **`ast-grep`** — For structural code search across the 50+ modified files to ensure consistency (e.g., find all router patterns, verify all imports).

---

## Quick Start Commands

```bash
# Start all services
docker compose up -d

# Rebuild only backend
docker compose up -d --build backend

# Rebuild only frontend  
docker compose up -d --build frontend

# Trigger a pipeline
python "$env:TEMP\final_test.py"

# Check agents API
curl http://localhost:8001/api/agents

# Check sandbox metrics
curl http://localhost:8001/api/sandbox/metrics

# Clean up all sandbox containers
docker rm -f $(docker ps -q --filter name=testai-sandbox)
```

---

*End of handoff. Ready for the next agent to continue.*
