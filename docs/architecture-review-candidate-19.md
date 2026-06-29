# Candidate 19: Standardize the web API route registration — 64 flat router files, manual main.py wiring

**Strength**: Worth exploring | **Category**: web API architecture / route organization

---

## Research sources (10)

### Web-based agent harness API patterns

1. **OpenHands (web-based)** — REST API server with autodiscovered routes via FastAPI's `routers/` pattern. Router registration uses a single `include_router` call per domain, with `prefix` and `tags` for OpenAPI grouping. No inline imports in main.py. https://github.com/All-Hands-AI/OpenHands

2. **Pantheon (web-based)** — Single `backend/api/` with 19 endpoints in one router file. No 64-file flat directory. Routes are method-based not file-based. https://github.com/r3moteBee/pantheon

3. **OpenCode (web-based TUI)** — Go-based with `cmd/` + `internal/` structure. Not directly applicable (TUI not HTTP API), but its `internal/` modules are organized by domain, not by file-per-endpoint. https://github.com/opencode-ai/opencode

4. **Hermes Agent (web-based gateway)** — Single `gateway/platforms/api_server.py` with OpenAI-compatible endpoints. All routes in one file, organized by method, not by file-per-endpoint. https://github.com/NousResearch/hermes-agent

5. **Harbor (web-based harness)** — FastAPI with auto-discovered routes. One `api/` directory with grouped routers. No manual wiring of each router in main.py. https://github.com/harbor-framework/harbor

6. **FastAPI best practices** — "Include routers by prefix, not by individual import." Use `prefix` and `tags` for organization. Avoid inline imports in the main app file. https://fastapi.tiangolo.com/tutorial/bigger-applications/

7. **htek.dev — 8 harnesses compared** — Every web-based harness (Copilot Cloud, Codex, Claude Code web, Cursor, Devin) uses either a single API surface or grouped domain routers. None require editing main.py to add a new route. https://htek.dev/articles/all-agent-harnesses-live-comparison

8. **Microsoft Agentic Harness (web-based)** — .NET Minimal API with endpoints grouped by feature in separate files, auto-registered via reflection. No manual registration. https://github.com/mckruz/microsoft-agentic-harness

9. **Codebase audit — 64 flat router files, manual main.py wiring** (see below)

10. **FastAPI APIRouter best practices** — "One router file per domain module. Use `prefix` and `tags` at router creation time. Import routers at module level, not inside the application factory." This codebase mixes inline imports, loop imports, and direct imports.

---

## Codebase evidence

### 3 inconsistent router registration patterns in main.py

| Pattern | Example | Count |
|---|---|---|
| **Loop import** (top-level) | `for r in agent_routers: app.include_router(r)` | 4 groups |
| **Inline import** (inside main()) | `from .routers.observability import router as observability_router; app.include_router(observability_router)` | 15+ |
| **Mixed** | Some routers imported at top, some inline, some with prefix, some without | All |

### 64 flat router files — no subdirectories, no grouping

```
backend/api/routers/
├── admin.py
├── admin_api.py
├── agent.py
├── agents.py
├── analytics.py
├── artifacts_api.py
├── audit.py
├── blueprints.py
├── chat.py
├── cost.py
├── coverage_api.py
├── cross_repo.py
├── curator_api.py
├── dashboard_api.py
├── dashboard_widgets.py
├── defect_api.py
├── delegate.py
├── digest_api.py
├── evaluate_api.py
├── events.py
├── generate_api.py
├── healing_api.py
├── health.py
├── impact_api.py
├── integrations.py
├── jobs.py
├── kanban.py
├── knowledge_graph_api.py
├── logs.py
├── memory.py
├── notifications.py
├── notify_api.py
├── observability.py
├── ops.py
├── permissions.py
├── pipeline.py
├── pr_manager.py
├── pr_webhook.py
├── projects_api.py
├── provider_defs.py
├── quality_api.py
├── rca_api.py
├── recordings.py
├── repos.py
├── runs.py
├── sandbox.py
├── sandbox_config.py
├── saved_filters.py
├── search_providers.py
├── settings.py
├── slack_webhooks.py
├── slash_commands.py
├── sprint_api.py
├── stakeholder_api.py
├── test_plans.py
├── testcases.py
├── testing_features_api.py
├── tools_management.py
├── traceability_api.py
├── triage_api.py
├── webhooks.py
├── workflows.py
```
64 files, one directory, no versioning prefix, no sub-directories.

### The contraction

- Group routers by domain into subdirectories (`routers/agent/`, `routers/pipeline/`, `routers/settings/`, `routers/observability/`)
- Single router registration convention: one `include_router` call per group with `prefix`
- No inline imports in main.py — all routers imported at module level
- Add API versioning prefix (`/api/v1/`) for future-proofing
