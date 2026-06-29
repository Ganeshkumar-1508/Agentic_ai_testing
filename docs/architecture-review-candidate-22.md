# Candidate 22: Clarify the service layer boundary — what belongs in services/ vs tools/ vs middleware/

**Strength**: Worth exploring | **Category**: layering architecture / unclear boundaries

---

## Research sources (10)

### Agent harness layering patterns

1. **Hermes Agent** — Three clear layers: `tools/` (tool implementations), `gateway/` (platform adapters), `agent/` (agent core + memory). Tools are auto-discovered, gateway platforms are independent, agent is the core loop. No ambiguous "services" layer. https://github.com/NousResearch/hermes-agent

2. **OpenCode** — Clear modules: `cmd/` (CLI), `internal/llm/` (LLM + tools), `internal/session/` (session management), `internal/tui/` (UI). Single responsibility per module. https://github.com/opencode-ai/opencode

3. **OpenHands** — `agent/` (agent core), `backend/` (services), `frontend/` (UI). Backend services have clear boundaries. https://github.com/All-Hands-AI/OpenHands

4. **Pantheon** — `agent/` (agent logic), `api/` (endpoints), `sources/` (ingestion), `memory/` (storage). Each directory has a clear domain. https://github.com/r3moteBee/pantheon

5. **Microsoft Agentic Harness** — Clean Architecture with domain/application/infrastructure layers. Clear separation of concerns. https://github.com/mckruz/microsoft-agentic-harness

6. **Deep Agents (LangChain)** — "The batteries-included agent harness" with opinionated defaults and clear module boundaries. https://github.com/langchain-ai/deepagents

7. **AgentKit (inngest)** — Agent + Network + State + Router + Tracing. Five clear concepts, each with a single module. https://github.com/inngest/agent-kit

8. **12 Factor App — "Services are processes"** — Each service owns a single concern. Unclear boundaries create confusion about where to add new capabilities. https://12factor.net/processes

9. **Codebase audit — services/ vs tools/ vs middleware/ boundary** (see below)

10. **CONTEXT.md — Tool Catalog** — Defines tools as primitive capabilities. Nothing equivalent exists for services — no definition of what makes something a "service."

---

## Codebase evidence

### The ambiguous layering

This project has 4 directories where business logic lives, with no clear boundary rules:

| Directory | Count | Examples that fit | Examples that blur the boundary |
|---|---|---|---|
| **`services/`** | 30 files | `team_service.py`, `kanban_service.py` | `memory_monitor.py` (should be in `memory/`), `github_service.py` (could be `tools/github_tools.py`) |
| **`tools/`** | 90+ files | `file_tools.py`, `web_tools.py` | `kg_refresh_tool.py` (is this a tool or a service?), `session_search_tool.py` (could be a service) |
| **`middleware/`** | 16 classes | `InputSanitizeMiddleware`, `TokenBudgetMiddleware` | `SkillActivationMiddleware` (is middleware the right place for skill activation?) |
| **Root level** | 30+ files | `orchestrator.py`, `events.py` | `compaction.py` (should this be in context_compressor/?), `l2_reflection.py` (should this be in memory/?) |

### The decision problem

When adding a new capability, a developer has to choose from 4+ directories with no convention:

```
Should I add my new capability to...
├── services/    (business logic, data access)
├── tools/       (model-callable functions)
├── middleware/  (pre/post hooks for agent loop)
├── root level   (??? everything else)
└── ???          (there's no clear answer)
```

This is exactly the problem identified in Candidates 4, 6, 7, and 15 — modules end up in the wrong directory and never get moved. The root cause is not the individual modules — it's the lack of clear boundary rules for the layering itself.

### The contraction

Define a clear layering convention:
- **`tools/`** — Model-callable functions. One tool = one JSON schema. No internal business logic.
- **`services/`** — Business logic that coordinates multiple tools or data sources. Cannot be called directly by the model.
- **`middleware/`** — Agent loop lifecycle hooks. Cannot do I/O on its own (delegates to services).
- **Root level** — Cross-cutting infrastructure (`events.py`, `orchestrator.py`). Every root-level file should justify its position.

Then audit and move modules that violate the convention:
- `memory_monitor.py` → `memory/_monitor.py`
- `compaction.py` → `context_compressor/`
- `l2_reflection.py` → `memory/l2_lessons/`
- Tool-adjacent files that are not model-callable → `services/`
