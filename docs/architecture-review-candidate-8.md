# Candidate 8: Unify 6+ trace visualization components behind a shared trace event data model

**Strength**: Worth exploring | **Category**: component architecture / data model duplication

---

## Research sources (10)

### Agent trace visualization patterns

1. **OpenTelemetry Trace Model** — Single span data model (trace_id, span_id, parent_span_id, name, kind, start_time, end_time, attributes, events). One model → multiple views (waterfall, graph, flame chart, list). No component duplicates the data model. https://opentelemetry.io/docs/specs/semconv/gen-ai/

2. **Microsoft Agentic Harness — OTel spans** — Single set of structured spans: `agent.turn`, `agent.tool_call`, `rag.retrieve`, `knowledge.query`, `mcp.request`. One span type set, consumed by one dashboard (Grafana or Azure Monitor). https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

3. **a0 Agent Harness Web UI** — Single Dashboard component for "run progress, task graphs, and memory candidates." One component, one data source (the global `agentHarness` store). Not 6 separate visualization components. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

4. **OpenHands Agent Canvas** — Single unified view per session with conversation + tools + files. One component tree, one data model. https://github.com/All-Hands-AI/OpenHands

5. **OTel Agent Tracing (Nitin K Singh)** — "Trace waterfall in Aspire showing nested spans from HTTP through LLM to database." One trace viewer, one span model, multiple views derived from it. https://nitinksingh.com/posts/observability--tracing-multi-agent-workflows-with-opentelemetry/

6. **Azure Monitor / Grafana** — Standard observability dashboards. One trace data model → multiple dashboard panels. The trace model is shared; the views are different renderings of the same spans.

7. **GitHub Copilot Canvases** — One bidirectional work surface showing "plans, PRs, browser sessions, terminals, deployments, dashboards, or workflow states." One surface, many views. https://htek.dev/articles/all-agent-harnesses-live-comparison

8. **Learn Harness Engineering — Lecture 11** — "Create a trace for each harness session, a span for each task." One trace data model: session → task → verification step. Not multiple models per visualization. https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/

9. **Codebase audit — 6+ trace visualization components** (see below)

10. **CONTEXT.md — Observability** — "Delegation tree via SSE/WebSocket, session history, token cost breakdown, root cause diagnosis." One set of observability data, rendered in different views.

---

## Codebase evidence

### 6+ trace visualization components with different data models

| Component | Lines | Source of data | Its data model | Renders as |
|---|---|---|---|---|
| **DelegationTreeView** | 619 | Own EventSource + api.get | `TreeNode` (sessionId, parentId, goal, depth, role, status, toolCalls, costUsd) | Collapsible tree of agent delegations |
| **TraceGraph** | 170 | `use-trace-events` hook | `TraceEvent` (eventType, eventData, timestamp) + `TraceTreeNode` | Graph/tree of trace events |
| **TraceWaterfall** | 453 | `use-trace-events` hook (SAME) | `TraceEvent` (SAME) + `DisplayRow` (duration, tokens, cost, pipelineStep) | Horizontal waterfall timeline |
| **AgentExecutionFlow** | 303 | pipeline types | `AgentExecutionDetail` + `ToolState` (agentName, status, toolCalls, output) | Vertical agent step flow |
| **PipelineDag** | ~200 | pipeline events | DAG-specific node/edge types | Directed acyclic graph |
| **ToolCallTimeline** | ~150 | tool events | Tool-specific event data | Chronological tool call list |
| **AgentPipeline** | ~200 | pipeline store | `AgentState` (type, status, progress) | Pipeline stage visualization |
| **TraceDetailPanel** | ~300 | user selection of any above | Generic `TraceEvent` | Detail tabs: input/output/meta/raw |

### The overlap

All 8 components visualize **the same thing**: "what the agent did and in what order." But they:
- Import from **5 different data sources** (use-trace-events, useEventSource, pipeline-store, pipeline types, api.get)
- Define **6 different data models** (TreeNode, TraceEvent, DisplayRow, AgentExecutionDetail, ToolState, AgentState) for the same conceptual data
- Duplicate **color mapping** logic (emerald=running, red=failed, amber=warning — defined in 5 places)
- Duplicate **event type → icon** mapping (Bot→agent, Terminal→tool — defined in 4 places)
- Duplicate **timestamp formatting**, **duration calculation**, **token formatting**

### The contraction

Define one shared trace event data model (`TraceSpan { id, parentId, type, name, status, startTime, endTime, metadata, children }`) and derive all 6 component views from it. The `use-trace-events` hook already exists and is used by TraceGraph + TraceWaterfall — extend it to replace the 4 other data sources.

OpenTelemetry uses ONE span model → multiple visualizers. MS Agentic Harness uses ONE span set → one dashboard. This codebase defines the data model 6 times and the color mapping 5 times.
