# Candidate 3: Extract 10 concerns from the overloaded Chat page into composable hooks

**Strength**: Strong | **Category**: component architecture / hook extraction

---

## Research sources (10)

### Agent harness chat surface architecture patterns

1. **a0 Agent Harness Web UI** — 3 surfaces: Dashboard (runs), Config Panel (settings), State Store (Alpine.js store polled from backend). The chat surface is 1 of 3 distinct surfaces, not a monolith containing all concerns. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

2. **Hermes Agent API Server** — Separate endpoints: `POST /v1/chat/completions` (streaming chat), `POST /v1/runs` (start run), `GET /v1/runs/{id}/events` (SSE lifecycle events). Chat and Run are different surfaces with different data models. https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration

3. **OpenCode architecture** — `cmd/` (CLI), `internal/session/` (session management), `internal/app/` (core services), `internal/message/` (message handling). Each concern is a separate module. https://github.com/opencode-ai/opencode

4. **StormHub Agent Harness** — Schema-driven UI rendering separates the chat composer from the run lifecycle. Tool outputs become structured UI spec trees, not inline mutation of chat state. https://stormhub.github.io/stormhub/blog/2026-04-11-Agent-Coding-Harness/

5. **Microsoft Agentic Harness** — Agent turn (`agent.turn` span), tool call (`agent.tool_call` span), and RAG retrieval (`rag.retrieve` span) are separate instrumentation points. The agent turn (chat) is one span type among many. https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

6. **Frontend Harness Engineering (ChristoSmuts)** — AGENTS.md + SKILL.md as bootstrap toolkit. Separates agent configuration (AGENTS.md) from run orchestration (skills). https://github.com/ChristoSmuts/frontend-harness-engineering

7. **htek.dev — All Agent Harnesses Compared** — GitHub Copilot separates Chat (IDE/CLI) from Cloud Agent (autonomous runs). Claude Code separates CLI chat from managed agents platform. Surface separation is universal. https://htek.dev/articles/all-agent-harnesses-live-comparison

8. **paddo.dev — Agent Harnesses: DIY to Product** — "Progress tracking becomes real-time run feeds." The run feed (SSE stream of lifecycle events) is separate from the chat composer that submitted the job. https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

9. **Codebase evidence — Chat page analysis** (see below)

10. **CONTEXT.md — Run** definition — "Run is the unit of work. Owns a run_id, source, subagent tree, tier." Chat is the input surface; Run is the execution surface. Different modules. https://github.com/.../CONTEXT.md

---

## Codebase evidence

### The Chat page does 10 things

| # | Concern | Lines | What it does |
|---|---|---|---|
| 1 | **Message state** | 61, 144-163 | Load, render, stream messages; message data model |
| 2 | **SSE connection** | 242-367 | 26 event listeners, cleanup, reconnect logic |
| 3 | **Job submission** | 370-417 | Input→JobSpec conversion, POST /api/jobs, error handling |
| 4 | **Session management** | 134-197, 464-488 | Load sessions, CRUD, localStorage persistence |
| 5 | **Approval handling** | 420-449 | Approve/deny API calls, state management |
| 6 | **Slash commands** | 119-131, 491-516 | Detection, backend routing, local fallback |
| 7 | **Composer state** | 109-111, 631-666 | File mgmt, drag/drop, voice, model picker |
| 8 | **Timer/elapsed** | 205-211 | interval-based elapsed time counter |
| 9 | **Reactions** | 452-461 | Up/down vote API calls |
| 10 | **Stop/cancel** | 234-239 | Cancel API call, stream cleanup |

### The shallowness

The page component's interface (props, state, callbacks passed to child components) is nearly as complex as the implementation (709 lines of inline logic mixing 10 concerns). Every concern has its own state variables, its own API calls, its own cleanup logic — all in one file.

### The deletion test

Delete the Chat page. Complexity doesn't vanish — it reappears across the child components (Composer, MessageBubble, SessionSidebar, RightRail, StatusFooter) which now have no coordinator, and across any other page that needs to submit a job (Pipeline reimplements parts of this, Jobs page reimplements others). The Chat page IS the coordinator; it's just doing too much coordination inline.

Extract three hooks and a coordinator:

- `useChatSession(sessionId)` → manages SSE connection, session loading, message streaming
- `useJobRunner()` → manages input→JobSpec conversion, submission, cancel
- `useChatUI()` → manages drag/drop, slash commands, files, approvals, reactions

The page becomes a slim coordinator (50 lines) that composes three deep hooks. Testing moves from "mock the entire page" to "unit-test each hook in isolation."
