# Candidate 9: Complete the event emission consolidation — migrate 30+ `emit_stream_event()` call sites to typed `StreamEvent` via `EventBus`

**Strength**: Strong | **Category**: consolidation-in-progress / type safety

---

## Research sources (10)

### Agent harness event emission patterns

1. **Google ADK 2.0** — "Strict control over event emission to manage state, graph routing, and streaming." Events are typed, framework-managed, not string-based. Manual `session.events.append()` is explicitly banned. https://google.github.io/adk-docs/2.0/

2. **OpenTelemetry Semantic Conventions for GenAI** — Standard span names (`gen_ai.agent.turn`, `gen_ai.tool.call`) and attributes (`gen_ai.request.model`, `gen_ai.response.finish_reason`). One typed schema for all agent observability. https://opentelemetry.io/docs/specs/semconv/gen-ai/

3. **Langfuse OTel integration** — Typed attributes propagated via OpenTelemetry Baggage. One type-safe pipeline for all event data. No string-typed event types. https://langfuse.com/docs/opentelemetry/

4. **Microsoft Agentic Harness — OTel spans** — Typed span hierarchy: `agent.turn` (root) → `rag.retrieve`, `agent.tool_call`, `mcp.request`, `knowledge.query` (children). One typed hierarchy, not 30 string event types. https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

5. **Learn Harness Engineering — Lecture 11** — "Create a trace for each harness session, a span for each task, and sub-spans for each verification step." One trace → span hierarchy. Structured, not string-based. https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/

6. **Hermes Agent** — OpenAI-compatible `/v1/chat/completions` + `/v1/runs` endpoints. Events flow through structured API responses, not a separate `emit_stream_event` function. https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration

7. **StormHub Agent Harness** — `@ai-sdk/react` `useChat` + `DefaultChatTransport`. One typed transport layer for all streaming events. https://stormhub.github.io/stormhub/blog/2026-04-11-Agent-Coding-Harness/

8. **SSE Event Stream Format (MDN)** — Named event types (`event: userconnect`, `event: usermessage`) with JSON payload. The transport layer (SSE) uses string event names — but the application layer should use typed event objects. This codebase's old `emit_stream_event()` conflates the transport layer (SSE event names) with the application layer (event types). https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events

9. **Codebase audit — 30+ old call sites** (see below)

10. **`core/events.py` self-documentation** — "Replaces 4 fragmented event paths with a single StreamEvent type hierarchy."

---

## Codebase evidence

### Two co-existing event emission systems

| Concern | New system (typed) | Old system (string-based) |
|---|---|---|
| **Event types** | `StreamEvent` subclasses in `core/events.py` | String literals like `"subagent.spawned"` |
| **Emission** | `event_bus.emit(AgentStarted(...))` | `emit_stream_event(sid, "pipeline.started", {...})` |
| **Dispatch** | isinstance() on typed classes | String matching on event type field |
| **Sinks** | TraceCallbackSink, EventSourceSink, LogSink, StreamEventsDBSink | Single `emit_stream_event` function |
| **Consumer modules** | `agent/agent.py`, `agent/tool_dispatch.py` (2 modules) | `job_control.py`, `delegate_task.py`, `subagent.py`, `orchestrator.py`, `kanban_service.py`, `kg_refresh_tool.py`, `api/routers/pipeline.py`, `api/routers/delegate.py` (8+ modules) |

### 30+ old call sites — 8 modules still using string events

| Module | Call sites | String event types used |
|---|---|---|
| `services/job_control.py` | 4 | job.paused, job.cancelled, job.submitted, etc. |
| `api/routers/pipeline.py` | 10 | pipeline.kg_test_updated, pipeline.autoheal.*, pipeline.tool_audit |
| `tools/delegate_task.py` | 2 | subagent.spawned, subagent.heartbeat |
| `api/routers/delegate.py` | 8 | steer.injected, session.cancelled, subagent.interrupted, session.resumed, approval.resolved, session.forked |
| `agent/tool_dispatch.py` | 1 | Uses BOTH old and new |
| `orchestrator.py` | 1 | board.created |
| `tools/subagent.py` | 1 | subagent.completed |
| `services/kanban_service.py` | 1 | board.* events |
| `tools/kg_refresh_tool.py` | 1 | kg.refreshed |

### The state of the migration

`core/events.py` defines typed events. `events.py` (EventBus) consumes them. Together they form one unified typed pipeline.

But `api/state.py`'s `emit_stream_event()` — a single string+dict function — bypasses the typed pipeline entirely. It's used by 8+ modules, 30+ call sites, and some modules (tool_dispatch.py) use BOTH paths.

The typed system is richer (typed fields, structured metadata) and type-safe (isinstance dispatch). The old system is just a string echo. The migration is: define missing StreamEvent subclasses for ~15 event types, migrate 30 call sites, delete `api/state.py:emit_stream_event()`.
