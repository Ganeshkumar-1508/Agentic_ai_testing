# Candidate 27: Module system — extensible sub-packages with full-stack registration

**Strength**: Strong | **Category**: extensibility architecture / plugin system

---

## Research sources (10)

### Agent harness extensibility patterns

1. **Hermes Agent — plugins/ + PluginContext** — `register_tool()`, `register_hook()`, `register_cli_command()`. Third-party plugins discoverable from `~/.hermes/plugins/`, pip entry points, and repo `plugins/`. No core edits needed. https://github.com/NousResearch/hermes-agent

2. **Hermes — per-platform toolset config** — `tools.telegram.enabled: true/false` per platform. Config-driven feature toggling with zero code changes. https://github.com/NousResearch/hermes-agent

3. **Hermes — memory provider plugins** — `plugins/memory/<name>/` implements `MemoryProvider` ABC. New backends install as standalone repos without landing in core tree. https://github.com/NousResearch/hermes-agent (AGENTS.md)

4. **OpenCode** — Single `opencode.json` config. Provider/tool configuration is data-driven, not code-driven. Adding a provider = adding config. https://github.com/opencode-ai/opencode

5. **AgentKit (inngest)** — Agent + Network + Router + State + Tracing. Each concept is composable. No core modification needed to add new behavior. https://github.com/inngest/agent-kit

6. **Deep Agents (LangChain)** — "Extensible — override or replace any piece without forking." Opinionated defaults but every component can be swapped. https://github.com/langchain-ai/deepagents

7. **This project's existing plugin system** — `backend/harness/plugins/__init__.py` already has `PluginContext` with `register_tool()`, `register_hook()`, `register_command()`. Auto-discovers from `~/.testai/plugins/`, `.testai/plugins/`, and pip entry points. https://github.com/... (in `backend/harness/plugins/__init__.py`)

8. **This project's existing provider registry** — `backend/harness/providers/__init__.py` auto-discovers providers from `$TESTAI_HOME/providers/<name>.py`. Already extensible via filesystem. https://github.com/... (in `backend/harness/providers/__init__.py`)

9. **Frontend Harness Engineering (ChristoSmuts)** — AGENTS.md + SKILL.md as portable primitives. Modules are declarative, not imperative. https://github.com/ChristoSmuts/frontend-harness-engineering

10. **Codebase audit — existing extensibility infrastructure exists but only covers tools/hooks/commands** (see below)

---

## Codebase evidence

### What the existing plugin system supports vs what's missing

The existing `backend/harness/plugins/__init__.py` provides:

```python
class PluginContext:
    def register_tool(self, tool_cls)      # ✅ Works
    def register_hook(self, event, handler) # ✅ Works
    def register_command(self, name, handler) # ✅ Works
```

But a full-stack module needs these additional capabilities:

| Capability | Current plugins | Module system |
|---|---|---|
| Tools | ✅ `register_tool()` | ✅ Same |
| Lifecycle hooks | ✅ `register_hook()` | ✅ Same |
| CLI commands | ✅ `register_command()` | ✅ Same |
| **API routes** | ❌ Not supported | ✅ `register_router()` |
| **DB tables** | ❌ Not supported | ✅ `register_migration()` |
| **UI pages** | ❌ Not supported | ✅ `register_route()` |
| **Config** | ❌ Env vars only | ✅ Scoped config in `modules.yaml` |
| **Module dependencies** | ❌ Not tracked | ✅ `dependencies: ["db", "events"]` |

### The module discovery and loading sequence

```
1. Read .testai/modules.yaml
2. Scan ~/.testai/modules/*/ and .testai/modules/*/
3. For each enabled module:
   a. Import __init__.py → find HarnessModule subclass
   b. Check dependencies are met
   c. Apply DB migrations from migrations/
   d. Register tools into tool registry
   e. Register FastAPI routers
   f. Register lifecycle hooks into HookPipeline
   g. Submit UI manifest (nav entries, pages, components)
4. Start serving
```

### How it connects to existing systems

```
Module registry ──→ tool_registry.register()
                ──→ app.include_router(router, prefix="/api/<module>")
                ──→ HookPipeline.add_plugin(event, handler)
                ──→ alembic.run_migrations("modules/<name>/migrations/")
                ──→ frontend nav registry (adds sidebar entry)
```

### End-to-end example: a user adding a "Jira Integration" module

```yaml
# .testai/modules.yaml
modules:
  jira:
    enabled: true
    config:
      url: "https://mycompany.atlassian.net"
      email: "${JIRA_EMAIL}"
      token: "${JIRA_API_TOKEN}"
```

```python
# ~/.testai/modules/jira/__init__.py
class JiraModule(HarnessModule):
    name = "jira"
    dependencies = ["db", "events"]

    def register_tools(self):
        from .tools import JiraSearchTool, JiraCreateTool
        for t in [JiraSearchTool, JiraCreateTool]:
            registry.register(t())

    def register_routers(self):
        from .routes import router
        return [("/api/jira", router)]

    def register_hooks(self):
        from .hooks import link_pr_to_jira
        return [("post_tool_call", link_pr_to_jira)]

    def register_ui(self):
        return [{
            "path": "/jira",
            "label": "Jira",
            "icon": "GitBranch",
            "component": "JiraDashboard",
        }]

module = JiraModule()
```

Result: agent gets `jira_search` + `jira_create` tools, `/api/jira/*` endpoints, auto-link PRs to tickets, and a "Jira" page in the sidebar. Zero core edits.
