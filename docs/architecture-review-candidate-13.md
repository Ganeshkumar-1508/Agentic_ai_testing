# Candidate 13: Extract an explicit Router concept from the scattered agent routing logic

**Strength**: Worth exploring | **Category**: missing abstraction / routing architecture

---

## Research sources (10)

### Agent harness routing patterns

1. **OpenClaude — `smartModelRouting.ts`** — Explicit pure-function router: `routeModel(RoutingInput, SmartRoutingConfig) → RoutingDecision`. Routes turns to simple or strong models based on heuristics (code fences, keywords, length, turn number). Testable, deterministic, zero side effects. https://github.com/nicepkg/openclaude (in `reference/openclaude/src/services/api/smartModelRouting.ts`)

2. **AgentKit (inngest)** — Router is a first-class concept: "A function that gets called after each agent runs, which decides whether to call another agent or stop." Three patterns: code-based (deterministic), agent-based (LLM routing), hybrid. https://agentkit.inngest.com/concepts/routers

3. **Citadel harness** — `/do` intent routing: "Describe the task once; pattern, state, and keyword tiers resolve most requests for zero tokens." Explicit routing layer between user intent and agent execution. https://github.com/SethGammon/Citadel

4. **Hermes Agent** — `/model` routing command, provider preference system, turn-based agent config resolution via `_resolve_turn_agent_config()`. Routing is explicit at the CLI and gateway level, not scattered across internals. https://github.com/NousResearch/hermes-agent

5. **SWE-agent** — Mature research harness with inspectable routing through `SWEEnv` and tool dispatch. Routing separable from agent loop. https://github.com/SWE-agent/SWE-agent

6. **OpenCode** — Modular Go harness with `internal/llm/` managing all LLM/provider/tool routing in one module. Single responsibility. https://github.com/opencode-ai/opencode

7. **htek.dev — 8 Harnesses Compared** — Every production harness (Copilot, Codex, Claude Code, Cursor, Devin, JetBrains AI, Bedrock Agents, Vertex AI) has an orchestration/routing concept. None scatter routing across 6 modules. https://htek.dev/articles/all-agent-harnesses-live-comparison

8. **Harbor** — Generalized harness for evaluating and improving agents. Routing is explicit evaluation concern. https://github.com/harbor-framework/harbor

9. **Codebase audit — routing scattered across 6+ modules** (see below)

10. **CONTEXT.md — Autonomy Model** — "Hybrid: Autonomous by default, Scoped for sensitive tasks, Guardrails always-on." The autonomy model implies routing but the routing logic is implicit, not an explicit module.

---

## Codebase evidence

### Routing logic is scattered across 6+ modules with no common interface

| Module | Routing responsibility | Interface |
|---|---|---|
| `agent/agent.py` (1,212 lines) | Main agent loop — decide to call tool, continue, or stop | Implicit in `run_stream()` generator |
| `agent/tool_dispatch.py` (54 symbols) | Route tool calls to handlers | Dict lookup + hardcoded paths |
| `services/job_control.py` (34 symbols) | Route job control actions | `JobControlAction` enum + `dispatch()` |
| `tools/orchestrator_tool.py` (3 tools) | Coordination routing | Separate tool classes |
| `orchestrator.py` (39 symbols) | Phase-based run orchestration | `OrchestratorEngine.run_job_spec()` |
| `dispatcher.py` / `dispatcher_loop.py` | Kanban dispatch | `dispatch_loop()` |

### What the harness references do differently

**OpenClaude's `smartModelRouting.ts`** defines a pure function router:
```
routeModel(RoutingInput{ userText, recentToolUses, turnNumber }, SmartRoutingConfig) 
    → RoutingDecision{ model, complexity, reason }
```
Deterministic, testable, zero side effects, no dependencies on agent internals.

**AgentKit** defines a Router as a first-class Network concept:
```
router({ network, agents, callCount, lastResult }) → Agent | undefined
```
Three patterns: code-based (deterministic), agent-based (LLM), hybrid.

**Citadel** routes `/do` commands through pattern/state/keyword tiers before they reach any agent.

**Hermes** resolves turn-specific agent config via `_resolve_turn_agent_config()` at the gateway level.

This codebase has none of these. The closest equivalent is `tool_dispatch.py`'s dict lookup — but that's inside the agent loop, after the LLM has already decided to call a tool. The question "should this turn go to a different agent or model?" has no single answer point.

### The contraction

Define a `Router` abstraction following the OpenClaude `routeModel()` pattern:
- `CodeRouter` — deterministic rules (heuristic, keyword-based, same as OpenClaude's STRONG_KEYWORDS)
- `AgentRouter` — LLM-based routing decision (same as AgentKit's Routing Agent)
- `HybridRouter` — mix of both (same as Citadel's pattern/state/keyword tiers)

Route resolution happens BEFORE the agent loop, not inside it. The router decides: which agent, which tools, which model, which tier. This makes routing explicit, testable, swappable — matching the domain model's "Autonomy Model" and following patterns proven in OpenClaude, AgentKit, and Citadel.
