# Candidate 5: Unify 5 competing data-fetching patterns behind a consistent frontend data layer

**Strength**: Worth exploring | **Category**: data architecture / pattern duplication

---

## Research sources (10)

### Frontend data layer patterns

1. **Tkdodo — Practical React Query** — React Query best practices: one `QueryClient` with global defaults, standardised error handling via `QueryCache.onError`, consistent stale times per data type (session vs settings vs real-time). The pattern: declare data dependencies declaratively, let the cache handle deduplication. https://tkdodo.eu/blog/practical-react-query

2. **Wolf Tech — SSE vs WebSockets vs Polling Decision Matrix (2026)** — Rule of thumb: unidirectional server→client = SSE, bidirectional = WebSocket, infrequent (<30s) = polling with cache semantics. Each has a place — the problem is mixing them inconsistently. https://wolf-tech.io/blog/nextjs-15-sse-vs-websockets-vs-polling-real-time-decision-matrix-2026

3. **OpenHands — useWebSocket hook** — Single custom hook for all real-time data. One interface, one reconnect strategy, one cleanup pattern. Compare to this codebase: SSE in Chat (inline 125 lines), SSE in Pipeline (zustand store), SSE in Activity (custom useActivityFeed). https://github.com/All-Hands-AI/OpenHands

4. **a0 Agent Harness Web UI** — Single `agentHarness` global store (Alpine.js). One state store, one polling mechanism, one API client. All surfaces read from the same store. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

5. **StormHub Agent Harness** — `@ai-sdk/react` `useChat` + `DefaultChatTransport` as the single chat/streaming primitive. One pattern for all server→client streaming. https://stormhub.github.io/stormhub/blog/2026-04-11-Agent-Coding-Harness/

6. **Vite SSR Guide** — Server data fetching patterns for Next.js/SSR. Consistent pattern for initial data load vs client-side fetch. https://vite.dev/guide/ssr

7. **React Query + SSE pattern (industry consensus)** — React Query for query data (declarative, cached, refetchable), SSE for streaming data (real-time events), zustand for client-only UI state. Three primitives with clear boundaries.

8. **Martin Fowler — CQRS** — Command/Query separation: writes go through the SSE stream (commands), reads go through React Query (queries). Mixing them creates tangled state.

9. **Codebase audit — 5 competing patterns** (see below)

10. **CONTEXT.md — Observability** — "Stream events + checkpoints" (durability), "SSE/WebSocket" (real-time). The backend has one event stream pattern; the frontend consumes it 3 different ways.

---

## Codebase evidence

### 5 competing data-fetching patterns

| Pattern | Pages | Count | What's wrong |
|---|---|---|---|
| **useQuery** (+ react-query) | Dashboard, Sessions, Jobs, Agents, AI Ops, Settings, Skills, Cost, Kanban, Knowledge Graph | ~15 | Most pages do this right. But refetchInterval values are arbitrary (5s, 15s, 30s, 60s) with no central config. Some pages set it, some don't. |
| **useEffect + api.get() + setState** | Flaky Tests, Test Cases, Chat (msg load), Chat (session list), Visual Testing | ~5 | Classic manual pattern. No cache deduplication, no retry, no shared loading state. Error handling varies: some show errors, some `.catch(() => {})` silently. Example: `flaky-tests/page.tsx:31 — .catch(() => {})` |
| **SSE EventSource (inline)** | Chat (`page.tsx:242-367`) | 1 | 125 lines of inline EventSource wiring with 26 event listeners. No reuse — the SSE logic is trapped inside the page component. |
| **SSE via Zustand store** | Pipeline (`pipeline-store.ts`) | 1 | Zustand store wraps SSE connection + derives state. Better than inline, but the store couples streaming, derivation, and UI state in one file. |
| **SSE via custom hook** | Activity (`useActivityFeed`, `useEventSource`) | 2 | Best pattern — reusable hook with reconnect, ring buffer, pause/resume. But only 2 hooks use it. |

### The real problem: no data-fetching contract

Each pattern handles these questions differently:

| Concern | useQuery pattern | useEffect pattern | SSE pattern |
|---|---|---|---|
| **Loading state** | `isLoading` from hook | Manual `loading` useState | Connection state from hook |
| **Error state** | `error` from hook | `.catch(() => {})` — swallowed | Error event listener + fallback |
| **Retry** | Built-in (3 retries default) | None | Manual reconnect |
| **Cache** | Automatic deduplication | None — re-fetches on every mount | N/A (streaming) |
| **Refetch** | `refetchInterval` per query | Re-run on mount | SSE stays open |
| **Stale-while-revalidate** | Built-in | Not used | N/A |

### The contraction

Declare a frontend data layer contract:

- **Queries** (data that changes infrequently) → useQuery with global defaults (`staleTime: 30s`, `retry: 3`, `refetchOnWindowFocus: true`)
- **Streams** (real-time events) → one `useEventSource` hook with standard reconnect, ring buffer, pause/resume. No inline EventSource wiring.
- **UI state** (client-only state) → Zustand stores without API calls mixed in
- **No more** `useEffect + api.get() + setState` anywhere
