# Candidate 21: Introduce a toolset abstraction — conditional tool loading per role/platform

**Strength**: Worth exploring | **Category**: tool architecture / missing abstraction

---

## Research sources (10)

### Tool organization patterns in agent harnesses

1. **Hermes Agent** — First-class **toolset** system. `toolsets.py` defines `_HERMES_CORE_TOOLS` (base set for all platforms) + named toolsets (kanban, delegation, file, web, browser, etc.). Toolsets are conditionally loaded: kanban tools only appear when `HERMES_KANBAN_TASK` is set. Per-platform enable/disable via `config.yaml`. https://github.com/NousResearch/hermes-agent (in `reference/hermes-agent/toolsets.py`)

2. **Hermes AGENTS.md — "The core is a narrow waist"** — "Every model tool we add is sent on every API call, so the bar for a new core tool is high. Most new capability should arrive as a service-gated tool (`check_fn`), a plugin, or an MCP server." Toolsets with `check_fn` enable conditional loading. This project has no equivalent. https://github.com/NousResearch/hermes-agent (in `reference/hermes-agent/AGENTS.md`)

3. **Hermes Kanban implementation** — Kanban tools are in `tools/kanban_tools.py` with `check_fn` gating. They are registered in `_HERMES_CORE_TOOLS` but only appear in the schema when conditions are met. The kanban dashboard is a **plugin** (`plugins/kanban/dashboard/`), not a core page. This project's kanban is a core page and always-loaded tools. https://github.com/NousResearch/hermes-agent (in `reference/hermes-agent/tools/kanban_tools.py`)

4. **OpenCode** — Tool routing is in `internal/llm` with tools grouped by capability. No flat tool list — tools are methods on typed structs. https://github.com/opencode-ai/opencode

5. **OpenHands** — Tools are grouped by capability in the backend. Frontend has no concept of individual tools — it renders agent actions generically. https://github.com/All-Hands-AI/OpenHands

6. **a0 Agent Harness** — Tool system with `harness_run`, `harness_checkpoint`, `harness_memory_propose` as named capabilities. Grouped by domain. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

7. **htek.dev — 8 harnesses compared** — Every harness groups tools by capability. None has a flat unconditional tool list like this project. Copilot has extensions, Codex has skills, Claude Code has MCP. https://htek.dev/articles/all-agent-harnesses-live-comparison

8. **CONTEXT.md — Tool Catalog** — Tools are listed by category (FILESYSTEM, CODE INTELLIGENCE, KNOWLEDGE, ORCHESTRATION, SPECIALIZED). The domain model already defines categories — but the code has no toolset implementation.

9. **Codebase audit — flat tool registry, no conditional loading** (see below)

10. **CONTEXT.md — Role** — "allowed_tools is a flat list." No named toolset composition. Adding a tool to a role requires editing the role YAML instead of composing named toolsets.

---

## Codebase evidence

### Current: flat tool loading

```
tools/registry.py — registry.register(name, ...) for every tool
tools/*.py — 90+ tool files, all registered unconditionally
agent/tool_dispatch.py — Role-based gating via allowed_tools set
```

Every tool is loaded on every API call. The tool registry has no concept of named groups (toolsets). The `allowed_tools` in roles is a flat string list:

```yaml
# Current: flat list of individual tools (from Role YAML)
allowed_tools:
  - read
  - write
  - bash
  - web_search
```

### Hermes: conditional toolset loading

```python
# Hermes: named toolsets with conditional loading
_HERMES_CORE_TOOLS = ["web_search", "terminal", "read_file", ...]  # base set

# Toolsets are groups that can be enabled/disabled
# Kanban tools only appear when env var is set
# check_fn gates individual tools
registry.register(name="kanban_show", toolset="kanban", check_fn=_profile_has_kanban_toolset, ...)
```

### The gap

| Concern | Hermes (toolset) | This project (flat) |
|---|---|---|
| Tool grouping | Named toolsets (kanban, delegation, file, web) | Flat list in allowed_tools |
| Conditional loading | check_fn per tool, toolset-gated | Always loaded |
| Per-platform config | tools.cli.enabled, tools.telegram.enabled | Single role config |
| Adding new tool | Register + toolset + check_fn | Register + add to role |
| Schema overhead | Minimal — only active tools in schema | All tools always in schema |

### The contraction

Introduce a `Toolset` abstraction:
- Named toolsets: `file` (read, write, edit, glob, grep), `web` (web_search, web_fetch), `code` (ast_grep, code_search, lsp), `orchestration` (task, send_message, question), `delegation` (delegate_task, collect_results)
- Roles compose toolsets: `allowed_toolsets: [file, web]` instead of `allowed_tools: [read, write, edit, glob, grep, web_search, web_fetch]`
- Conditional loading via `check_fn` per toolset (Hermes pattern)
- API schema only includes tools from active toolsets

This reduces the API schema size, makes role definitions composable, and matches the domain model's Tool Catalog categories.
