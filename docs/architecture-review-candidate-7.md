# Candidate 7: Finish the stalled consolidation of 4 interception systems into one HookPipeline

**Strength**: Strong | **Category**: consolidation-in-progress / pattern duplication

---

## Research sources (10)

### Agent harness interception patterns

1. **DeerFlow (upstream)** — Single `_build_runtime_middlewares()` function returns a list of `AgentMiddleware` instances. One pipeline, one pattern. All 16 middleware classes in this codebase were ported from DeerFlow's single pipeline. https://github.com/bytedance/deer-flow

2. **Hermes Agent — `plugins.py`** — Single `PluginManager` with register/unregister/list. One plugin system, not three. All harness extensions go through one mechanism. https://github.com/NousResearch/hermes-agent

3. **a0 Agent Harness — Guardrail System** — Single safety/interception mechanism. One place for pre/post tool checks, not a middleware chain + hook system + plugin system. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

4. **Aakash Gupta — "What an Agent Harness Actually Is"** — "Human approvals, sub-agent coordination, filesystem access, prompt presets, **lifecycle hooks**, planning and execution." Lifecycle hooks are ONE item on the list, not three overlapping systems. https://aakashgupta.medium.com/2025-was-agents-2026-is-agent-harnesses-073e9877655e

5. **Microsoft Agentic Harness** — Single middleware pipeline with structured OTel spans. Each middleware emits spans (`pipeline.behavior`), one pipeline for all interception. https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

6. **OpenCode architecture** — `internal/tui` (UI), `internal/llm` (LLM), `internal/session` (sessions). Single `internal/middleware` if interception is needed, not three parallel systems. https://github.com/opencode-ai/opencode

7. **LangGraph** — Single middleware concept: `Command` + `interrupt` for human-in-the-loop. One interception primitive, not a middleware chain + hooks + plugins. https://langchain-ai.github.io/langgraph/

8. **Codebase audit — 4 interception systems, 1 incomplete consolidation** (see below)

9. **CONTEXT.md — Autonomy Model** — "Guardrails (hooks + HITL) always-on as safety net." Guardrails are ONE concept, described as "hooks + HITL" — not middleware + hooks + plugins + gates.

10. **The codebase's own `hook/__init__.py`** — "Unified hook pipeline — replaces MiddlewareChain, _hook_system, and hook_registry." The developer(s) already identified the problem and designed the solution. The migration is incomplete.

---

## Codebase evidence

### 4 interception systems doing the same thing

| System | Files | Lines | Consumers | Phase |
|---|---|---|---|---|
| **`middleware/`** | 16 middleware classes + `base.py` | ~1,500 | Agent.run_stream (directly) | Phase 1 (MIDDLEWARE) |
| **`_hook_system.py`** | 1 file at harness root | 405 | PluginManager calls from agent | Phase 2 (PLUGIN) |
| **`hook_registry.py`** | 1 file at harness root | 248 | ToolDispatcher pre-call check | Phase 0 (DETERMINISTIC_GATE) |
| **`hook/` (unified)** | `pipeline.py`, `phases.py`, `registry.py` | ~300 | None — migration not yet adopted | All 3 phases |

### The lifecycle event overlap

Each system hooks into the same agent lifecycle events, but with different interfaces:

| Lifecycle event | middleware/ method | _hook_system.py name | hook_registry.py | hook/pipeline.py name |
|---|---|---|---|---|
| Before run | `on_before_run(user_input)` | `on_session_start` | — | `BEFORE_RUN` |
| After run | `on_after_run(result, error)` | `on_session_end` | — | `AFTER_RUN` |
| Before LLM | `on_before_llm(messages, round)` | `pre_llm_call` | — | `BEFORE_LLM` / `PRE_LLM_CALL` |
| After LLM | `on_after_llm(tool_calls, round)` | `post_llm_call` | — | `AFTER_LLM` / `POST_LLM_CALL` |
| Before tool | `on_before_tool(name, args)` | `pre_tool_call` | `check_pre` | `BEFORE_TOOL` / `PRE_TOOL_CALL` |
| After tool | `on_after_tool(name, result)` | `post_tool_call` | `check_post` | `AFTER_TOOL` / `POST_TOOL_CALL` |
| End of round | `on_end_of_round(round)` | — | — | `END_OF_ROUND` |

Same 7 lifecycle events, 3 different registration APIs, 4 different invocation paths.

### The incomplete consolidation

The `hook/__init__.py` says: "Unified hook pipeline — replaces MiddlewareChain, _hook_system, and hook_registry."

The `HookPipeline` in `hook/pipeline.py` wraps all three phases. But:
- `Agent.run_stream()` still calls the old `MiddlewareChain` directly
- `ToolDispatcher` still calls `hook_registry.check_pre()` directly
- No caller has been migrated to use `HookPipeline`
- `hooks/` (plural) directory is empty — legacy spot
- `plugins/` is empty — PLUGIN phase has no implementation
- `_hook_system.py` still at root — not migrated to PLUGIN phase

### The deletion test

The unified `HookPipeline` already exists and the old systems could be deleted — if the 3 consumers (Agent, ToolDispatcher, PluginManager) are migrated. The unified pipeline has exactly the same events as the 3 legacy systems combined. This is a pure migration task, not a redesign.

### The fix

Finish the consolidation:
1. Migrate `Agent.run_stream()` from `MiddlewareChain` → `HookPipeline`
2. Migrate `ToolDispatcher` from `hook_registry.check_pre()` → `HookPipeline.on_before_tool()`
3. Migrate `_hook_system.py` callers → `HookPipeline` PLUGIN phase
4. Delete `middleware/base.py`, `_hook_system.py`, root `hook_registry.py`
5. Rename `hooks/` → old, keep `hook/` as the single pipeline
