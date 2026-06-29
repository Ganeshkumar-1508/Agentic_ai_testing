# Unified Agent Surface: Consolidating Chat, Pipeline, Requirements, and PRs

**Date:** 2026-06-14  
**Sources:** Anthropic engineering blog, htek.dev harness comparison, MindStudio agent harness guide, OpenHarness, OpenHands, Claude Code source, GitHub Copilot architecture

---

## Current Problem: Fragmented Entry Points

TestAI has **4+ separate UI surfaces** that all lead to agent execution:

| Surface | Route | Backend | What it does |
|---------|-------|---------|-------------|
| **Chat** | `/chat` | `POST /api/chat` | Conversational agent with `CHAT_READONLY_TOOLSET`, can call `submit_job` |
| **Pipeline** | `/pipeline` | `POST /api/pipeline/from-requirements` | Autonomous test-generation workflow with orchestrator |
| **Requirements** | `/traceability` | `POST /api/traceability/requirements` | Structured QA metadata CRUD (passive data store) |
| **Pull Requests** | `/pull-requests` | `GET/POST /api/prs/*` | PR tracking, manual test triggers, auto-fix |

These share the same underlying engine (orchestrator + agents + sandbox) but expose it through different UIs with different mental models.

---

## How Other Harnesses Handle This

### 1. Claude Code: Single Entry Point, Multiple Modes

Claude Code has **one** entry point (the CLI), but supports different interaction modes:

- **Default mode** (`claude`): Interactive chat with full tool access — user types prompts, agent responds, calls tools
- **Print mode** (`claude -p "fix this bug"`): Non-interactive, single-shot execution, streams output to stdout
- **Coordinator mode** (`claude --agent coordinator`): Spawns subagents for complex tasks
- **Slash commands** (`/explore`, `/review`): Mode switches within the same session

**Key insight:** No separate "pipeline" page. Every interaction starts from the same input. Mode selection (interactive vs. batch) is a **runtime choice**, not a separate surface. The agent decides whether to delegate, explore, or execute based on the prompt.

**Relevant source files in reference/openclaude:**
- `src/main.tsx` — single `run()` function, all modes branch from Commander options
- `src/cli/transports/` — different output transports but shared execution core

### 2. GitHub Copilot: Issue → PR Pipeline, No Separate UI

GitHub Copilot's **Cloud Coding Agent** has:

- **Entry point:** A GitHub Issue comment or the `POST /agents/repos/{owner}/{repo}/tasks` API
- **Workflow:** Agent researches → plans → implements → opens PR — all in one flow
- **Surface:** Lives inside the existing GitHub UI (issue comments, PR tabs)
- **Monitoring:** Remote control from GitHub Mobile or web UI

**Key insight:** Copilot doesn't have a separate "pipeline page." The pipeline IS the agent run. Everything is a task that starts from an intent (issue/comment/API call) and ends with a PR. The user monitors through the same GitHub interface they already use.

### 3. OpenAI Codex (Responses API): One API, Multiple Outputs

Codex uses a **single Responses API** with built-in tools:
- One endpoint handles both chat and task execution
- The toolset (code interpreter, web search, file access) is consistent across modes
- Multi-turn conversations AND single-shot tasks use the same infrastructure

**Key insight:** No mode distinction at the infrastructure level. The difference between "chat" and "task" is just whether you continue the conversation or not.

### 4. OpenHands: Conversation-Centric

OpenHands models everything as a **conversation**:
- `POST /api/v1/conversations` — creates a conversation (long-running agent session)
- Settings, sandbox, and tools are configured per-conversation
- The web client is one of many possible interfaces into the conversation
- No separate "pipeline" surface — complex tasks are just longer conversations

**Key insight:** The conversation is the universal primitive. Short chat = short conversation. Complex pipeline = long conversation with tool calls. They're the same thing.

---

## Pattern Convergence: What Every Harness Agrees On

Across Claude Code, GitHub Copilot, OpenHands, and Codex:

| Concept | Common Name | TestAI Equivalent | Problem |
|---------|------------|-------------------|---------|
| User intent | **Prompt** or **Message** | Chat message / Pipeline requirements | Two different input formats for the same thing |
| Execution session | **Session** or **Conversation** | Chat session / Pipeline run | Two different session models |
| Long-running work | **Task** or **Run** | Pipeline run / Orchestration | The orchestrator is the chat agent's `submit_job` output — same engine |
| Structured data | **Artifact** or **Attachment** | Requirements / Test cases / PRs | Separate CRUD pages for what's really just labeled data |
| PR output | **Delivery** | Pipeline output / PR page | The pipeline produces PRs, PR page tracks them — should be the same view |

---

## Recommended Architecture: Unified Agent Surface

### Replace 4 surfaces → 1 surface with modes

```
┌──────────────────────────────────────────────┐
│              Agent Workspace                  │
│  /agent                                      │
│                                               │
│  ┌─────────────────────────────────────┐      │
│  │  Prompt Input                        │      │
│  │  [What do you want to do?_________] │      │
│  │  [Submit] [Schedule] [As PR]        │      │
│  └─────────────────────────────────────┘      │
│                                               │
│  ┌──────────────┐  ┌────────────────────┐     │
│  │  Sessions    │  │  Artifacts         │     │
│  │  (chat/job)  │  │  (tests / PRs)    │     │
│  └──────────────┘  └────────────────────┘     │
│                                               │
│  ┌─────────────────────────────────────┐      │
│  │  Traceability (read-only view)      │      │
│  │  [graph showing req⇄test links]     │      │
│  └─────────────────────────────────────┘      │
└──────────────────────────────────────────────┘
```

### Principles

1. **One input, any intent.** The prompt is always free-form text. The system detects whether it's a question (chat), a test-generation request (pipeline), or a fix-this-bug command (orchestration). Slash commands (`/test`, `/fix`, `/explore`) disambiguate.

2. **Session is the universal primitive.** Every interaction creates a session. Chat messages, pipeline runs, orchestration jobs — all share `sessions` table, `messages` table, same streaming protocol. Source tag (`chat`/`pipeline`/`delegation`) is metadata, not a different UI.

3. **Requirements → structured artifacts.** Requirements aren't a separate execution surface. They're labels attached to test artifacts within a session. The traceability page becomes a **read-only dashboard** that queries artifact links, not a CRUD UI.

4. **PRs → delivery channel, not a separate surface.** The PR page merges into the session detail view. Every session that produced code shows PR status inline. The "Run Tests" and "Auto-Fix" buttons are on the session, not a separate PR manager.

5. **Modes, not pages.** Instead of chat vs. pipeline mode toggles, use:
   - Interactive: streaming chat with immediate response
   - Batch: submit and get notified when done
   - Scheduled: fire-and-forget with cron trigger
   These are delivery modes, not different tools.

### Implementation Sketch

**Backend changes:**
- Single `POST /api/agent/run` endpoint replacing `/api/chat` and `/api/pipeline/from-requirements`
- Accepts `{ prompt, mode: "chat" | "batch", source: "user" | "webhook" | "cron" }`
- Returns a session_id immediately (for batch) or streams SSE (for chat)
- Session service detects intent (via LLM classification or slash command) and routes to appropriate agent config

**Frontend changes:**
- Single `/agent` page replacing `/chat`, `/pipeline`, `/pull-requests`
- `/sessions` becomes the history browser for all runs
- `/traceability` becomes a read-only graph dashboard
- Remove `/requirements` (inline form on session start)
- Remove `/pull-requests` (inline on session detail)

**Database (already unified):**
- `sessions` table already has `source` field — just use it consistently
- `pipeline_runs` table already shares session_id — merge PR artifacts into sessions view
- `requirements` table stays as data layer, accessed through session/artifact links

### Migration Path

1. **Phase 1:** Add `POST /api/agent/run` alongside existing endpoints. Frontend routes `/agent` as the new default. Old routes redirect.
2. **Phase 2:** Migrate PR tracking into session detail view. Remove `/pull-requests` page.
3. **Phase 3:** Make traceability read-only. Remove requirement CRUD from the UI (keep API).
4. **Phase 4:** Remove old routes.

---

## Summary

The industry consensus is clear: **one prompt input, one session model, one execution engine.** The separation between "chat" and "pipeline" is an artifact of incremental development, not a meaningful architectural distinction. Claude Code, GitHub Copilot, OpenHands, and Codex all converge on a single-entry-point model where mode and scope are runtime parameters, not separate pages.
