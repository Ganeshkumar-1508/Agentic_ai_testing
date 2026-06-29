# Candidate 14: Unify 4 uncoordinated resource management systems into a shared budget/compaction coordinator

**Strength**: Worth exploring | **Category**: resource management / cross-cutting concern

---

## Research sources (10)

### Agent harness resource management patterns

1. **MS Agentic Harness** — "The context budget that decides how much it can hold in its head at once" is a unified concept. Token budget, compression, and cost are coordinated. https://github.com/mckruz/microsoft-agentic-harness

2. **OpenCode** — Single `autoCompact: true/false` config. Compact triggers at 95% of context window. One config, one behavior. Token limits and compression are coordinated through one module (`internal/session`). https://github.com/opencode-ai/opencode

3. **Anthropic — Effective Harnesses** — Initializer + coding agent pattern with progress files. Context budget is managed through external artifacts (feature lists, progress files), not through separate uncoordinated subsystems. Session startup protocol reconstructs state before any work. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

4. **Citadel** — Campaigns with persistent `.planning/` files. Token spend is tracked via `/cost` and `/dashboard` from "runtime-native telemetry." One telemetry pipeline for all resource tracking. https://github.com/SethGammon/Citadel

5. **Hermes Agent** — Single `hermes_state.py` manages session state, model config, and message history. Token tracking, context budget, and session management are in one module. https://github.com/NousResearch/hermes-agent

6. **a0 Agent Harness** — Single `harness-store.js` that polls `/run` and `/state`. One store for all resource state (run progress, task graphs, memory candidates). https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

7. **OpenHands** — WebSocket hook for all real-time data. One stream for token usage, agent state, tool execution. https://github.com/All-Hands-AI/OpenHands

8. **CONTEXT.md — Cost Budgets** — "Four scopes (per-subagent, per-phase, per-run, per-user-per-day)" with soft/hard caps. The domain model defines a unified budget concept, but the implementation splits it across 4 modules.

9. **Codebase audit — 4 uncoordinated resource management systems** (see below)

10. **CONTEXT.md — Workspace Container** — "Per-run persistent Docker container, dependencies pre-installed." The resource management should coordinate what the container can use (budget), what the agent can process (compression), and what it costs.

---

## Codebase evidence

### 4 resource management systems that should be one

| System | File | What it tracks | How it triggers |
|---|---|---|---|
| **Token budget** | `middleware/token_budget.py` | Per-run token soft/hard limits | Before LLM call, checks budget |
| **Tool budget** | `middleware/tool_budget.py` | Oversized tool results → disk | After tool result, checks size |
| **Context compression** | `context_compressor/compressor.py` + `compaction.py` | Context window usage | `should_compress()` heuristic |
| **Cost tracking** | `budget_tracker.py` + `cost_tracker.py` | Per-run/per-user USD cost | After LLM call, records tokens |

### The coordination gap

| Scenario | What should happen | What actually happens |
|---|---|---|
| Context approaching window limit | Compress before next turn AND throttle tool use | Compressor fires independently; tool budget doesn't know |
| Token hard limit hit | Stop agent AND finalize cost record | Token middleware blocks the call; cost tracker doesn't know |
| Cost budget exceeded | Pause agent AND compress aggressively to save tokens | Budget tracker pauses; compressor doesn't know |
| Tool returns oversized result | Truncate AND count against token budget | Tool middleware truncates; token budget doesn't know |

Each system makes decisions independently. The domain model (CONTEXT.md) defines "4 scopes" for budgets but the implementation scatters them across middleware, compressor, and tracker modules with no shared coordinator.

### The contraction

Define a `ResourceManager` that coordinates:
- **Budget** — token/cost/tool limits from `middleware/token_budget.py` + `budget_tracker.py`
- **Compression** — compression triggers from `context_compressor/` + `compaction.py`
- **Telemetry** — usage recording from `cost_tracker.py` + `events.py`

The `ResourceManager` sits in the agent loop as a single seam. Before each turn, it checks: "Do we have budget? Should we compress? Record cost." After each turn, it updates: "Tokens consumed, cost accrued, should we compress for next turn?" This matches the MS Agentic Harness's "context budget" concept and the domain model's unified budget vocabulary.
