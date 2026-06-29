# Agent Harness Architecture Research

**Date:** 2026-06-10  
**Goal:** Understand how production agent harnesses structure their workflows — predefined phases vs. dynamic agent-driven loops.

---

## 1. Stripe Minions

**Pattern:** Blueprint — hybrid deterministic + agentic nodes.

Minions use **blueprints**: a structured YAML-like plan that mixes fixed deterministic steps (clone repo, run linter) with LLM agent nodes (write code, fix test). The blueprint is authored per-task type, not generated dynamically. The agent executes the blueprint top-to-bottom — it doesn't decide what to do next.

**Key takeaway:** Blueprints work when tasks are repetitive (migrations, dependency updates). Stripe ships 1,300+ PRs/week with this model. But the blueprint is **authored, not generated**.

## 2. Ramp Inspect

**Pattern:** One agent, full context, autonomous loop.

Inspect runs a **single OpenCode agent** inside a Modal sandbox with the full dev environment (Postgres, Redis, Temporal, Chromium). The agent has all context upfront — it doesn't need predefined phases. It decides what tools to call, in what order. It can:
- Read code → edit code → run tests → take screenshots → commit → PR
- Spawn child sessions for parallel work across repos
- All in one autonomous loop

**Key takeaway:** No predefined phases. The agent is given a goal and full context, and it figures out the rest. "Effectively hundreds of computers that they can work on simultaneously."

## 3. OpenCode

**Pattern:** Coordinator agent + specialized subagents, dynamically chosen.

```
Build agent (primary, all tools)
  ├── @explore "find login code"    (read-only subagent)
  ├── @scout "check dependency docs" (read-only, external)
  └── @general "fix the bug"        (full tools)
```

The **Build** agent is the coordinator. It receives the user's goal, decides when to delegate to Explore, Scout, or General subagents via the `task` tool, synthesizes results, and continues its own loop. No predefined pipeline — the agent decides.

**Subagents are lazily invoked** — the coordinator calls them only when needed. Three built-in subagent types:
- **Explore:** Fast, read-only, Haiku model, for codebase navigation
- **Scout:** Read-only, for external dependency research
- **General:** Full tools, for multi-step tasks

## 4. Claude Code (Coordinator Mode)

**Pattern:** Coordinator + parallel workers, but coordinator drives decisions.

Claude Code's coordinator mode (from the system prompts):

| Phase | Who | Purpose |
|-------|-----|---------|
| Research | Workers (parallel) | Investigate codebase, find files |
| Synthesis | **Coordinator** | Read findings, understand, craft specs |
| Implementation | Workers | Make targeted changes, commit |
| Verification | Workers | Test changes work |

**Critical rule: "Never delegate understanding."** The coordinator reads worker results, synthesizes them, and produces precise specs. Workers are given file paths and line numbers — not vague instructions.

**There is no fixed pipeline.** The coordinator decides, for each task:
- Should I research first? → spawn parallel explore workers
- Do I have enough info? → synthesize → spawn implementation workers
- Did it work? → spawn verification workers
- Did the agent forget to PR? → middleware catches it

## 5. Google ADK (Agent Development Kit)

**Pattern:** Agent with tool-calling loop + artifact service.

ADK agents run in a standard tool-calling loop. They have access to:
- Tools (custom or built-in)
- Artifact service (save/load/list artifacts)
- Session service (persist state)

No predefined phases. The agent receives a user message, calls tools in its loop, saves artifacts as it goes, and returns a response.

## 6. OpenSWE

**Pattern:** Single agent + middleware safety nets.

OpenSWE runs one agent per thread. The agent has a curated set of ~6 tools (execute, fetch_url, http_request, commit_and_open_pr, linear_comment, slack_thread_reply). It runs in an autonomous tool-calling loop.

**Middleware provides deterministic safety nets** around the agentic loop:
- `open_pr_if_needed`: If agent finishes without opening a PR, middleware does it
- `check_message_queue_before_model`: Injects mid-run messages
- `ToolErrorMiddleware`: Catches tool errors

---

## 7. Hermes Agent (Nous Research)

**Pattern:** Single agent loop + subagent delegation + curated toolsets.

Hermes runs an `AIAgent` class with a synchronous `run_conversation()` loop:

```python
while (api_call_count < self.max_iterations ...):
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

**No predefined phases.** The agent receives a user message, calls tools in a loop, delegates to subagents when it needs parallel work, and returns a response. The agent decides what to do at every step.

Key architectural characteristics:
- **Toolset-based** — tools are grouped into named toolsets (`file`, `terminal`, `web`, `delegation`, `memory`, `kanban`, etc.). The agent has access to a curated set based on platform (CLI, Telegram, etc.).
- **Subagent delegation** via `delegate_task` tool — two modes: single (Sync) and batch (parallel Fan-Out). Subagents are isolated with their own terminal sessions, todo lists, and tool access.
- **Middleware hooks** — deterministic hooks around the agent loop: `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, `on_session_start`, `on_session_end`. Used for logging, safety checks, and observability — **not** for driving the agent's decisions.
- **Kanban plugin** — optional multi-agent work queue. Used for collaboration between profiles, not as the primary orchestration mechanism.
- **No fixed pipeline.** The agent drives everything. Skills, tools, and delegation are all available on-demand.

Key quote from the architecture: *"The agent loop is entirely synchronous, with interrupt checks, budget tracking, and a one-turn grace call."* — no mention of predefined phases, pipelines, or step-by-step orchestration.

## 8. OpenHands (All-Hands AI)

**Pattern:** Composable agent SDK + microagents (trigger-based prompt injection).

OpenHands has two layers:

**Software Agent SDK** — a composable Python library. Agents are defined in code, not through a pipeline configuration. The SDK provides the agentic engine (LLM calls, tool execution, sandbox integration) as building blocks that developers compose programmatically.

**Microagents** — specialized prompt files (Markdown with YAML frontmatter) that inject domain knowledge and task-specific workflows into the agent's context. Loaded based on trigger keywords matching the user's message:

```yaml
---
triggers:
  - keyword1
  - keyword2
---
# Microagent Content
Your specialized knowledge and instructions here...
```

Microagents are **not phases or steps** — they're contextual prompts that get loaded when the agent's task matches a trigger. The agent still decides what to do within its own loop.

Key architectural characteristics:
- **No predefined phases** — the SDK is a library of primitives, not a pipeline orchestrator
- **Agent-driven** — the agent loop (LLM → tools → LLM → tools) decides the flow
- **Microagents for context** — domain knowledge is injected on-demand based on triggers, not loaded into a fixed pipeline
- **Sandbox as tool** — the sandbox is an execution environment the agent controls, not a stage in a pipeline
- **Pluggable architecture** — the SDK composes agents in code rather than through configuration or pipeline definitions

---

## Synthesis: Common Architecture

All production agent harnesses converge on the **same pattern**:

```
User goal
  │
  ▼
┌──────────────────────────────────────────┐
│  Agent Loop (LLM + tools)                │
│  The agent decides what to do next        │
│  - Read code? → read_file tool            │
│  - Search? → grep/glob/kg_search          │
│  - Need more context? → spawn subagent    │
│  - Ready to edit? → write/edit tool       │
│  - Done? → commit_and_open_pr tool        │
│                                           │
│  Middleware (deterministic safety nets):   │
│  - open_pr_if_needed                      │
│  - ToolErrorMiddleware                    │
│  - Artifact auto-capture                  │
└──────────────────────────────────────────┘
  │
  ▼
Result (PR, artifacts, summary)
```

**What NO production harness does:**
- No hardcoded 7-phase pipeline executed sequentially
- No predefined "setup agent" that runs before "fix agent"
- No static task decomposition that runs before any agent work

**What EVERY production harness does:**
- One agent loop that decides what to do next
- Subagents spawned dynamically when the agent needs them
- Deterministic middleware as safety nets (not as primary orchestration)
- Rich context upfront so the agent doesn't waste calls discovering basics

---

---

## The Orchestration Primitive: `task` / `delegate_task` / `Agent`

Across every production harness, the core orchestration primitive is the same: **a coordinator spawns a child agent with an isolated context, gives it a goal and tools, and receives the result back.** The name varies, the pattern doesn't.

| Harness | Name | Modes | Gating |
|---------|------|-------|--------|
| Claude Code | `Agent` | Foreground, Background | `subagent_type` (Explore, code-reviewer, etc.), per-tool deny rules |
| OpenCode | `task` | Sync | Permission globs, `hidden: true` for programmatic-only |
| Hermes | `delegate_task` | Single (Sync), Batch (Fan-Out), Background | `role: leaf/orchestrator`, depth cap, budget, toolset intersection |
| OpenSWE | `task` (Deep Agents) | Single | Middleware stack per child, isolated file ops |
| Google ADK | Agent via Runner | Session-based | Artifact service isolation |
| **TestAI** | `delegate_task` | Sync, Fan-Out, Background | Depth cap (5), budget enforcement, tool intersection, MCP allow-list |

Our `delegate_task` is already on par with Hermes and ahead of Claude Code's `Agent` tool in terms of features (Fan-Out batch mode, depth caps, budget enforcement). The architecture shift was about **who calls it** — previously the kanban dispatcher called it to spawn workers. Now the coordinator agent calls it directly, which is exactly how every other harness works.

---

## What This Means for TestAI

Our current architecture has **two competing models**:

| Component | Current Pattern | Should Be |
|-----------|----------------|-----------|
| **OrchestratorEngine.run_single()** | Predefined phases: clone → KG → explore → decompose → kanban | Bootstrap only: clone → KG → hand off to agent |
| **Explore agents** | Predefined 4 parallel agents in `_explore_codebase()` | Coordinator agent decides when to explore |
| **Kanban dispatcher** | Fixed worker lifecycle: show → work → test → commit → complete | Worker agent decides its own workflow |
| **SETUP phase** | Planned as hardcoded static detection | Agent detects and installs deps if needed |

The user's intuition is correct. The **orchestrate tool** (the LLM that decomposes goals) should be replaced by a **coordinator agent** that:
1. Receives the goal + repo context
2. Spawns explore subagents when it needs more info
3. Synthesizes findings itself (never delegates understanding)
4. Spawns implementation subagents with precise specs
5. Spawns verification subagents
6. Handles edge cases (failures, mid-run changes) dynamically

The kanban board becomes an **observability layer** (tracking what happened) rather than an **orchestration layer** (driving what happens next).

### Recommended Next Steps

1. Remove the 7-phase pipeline model from `OrchestratorEngine.run_single()`
2. The engine becomes a **thin bootstrap**: sandbox → clone → KG → hand off to coordinator agent
3. The coordinator agent receives the goal and decides what to do — explore, fix, test, commit, PR
4. Kanban becomes **read-only observability** (logs what agents do) rather than **active dispatch**
5. Middleware (open_pr_if_needed, artifact capture, kg_refresh) runs as deterministic hooks
