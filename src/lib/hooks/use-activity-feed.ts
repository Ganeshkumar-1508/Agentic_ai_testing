"use client";

/**
 * useActivityFeed — live SSE activity stream for the C01-C08 events.
 *
 * Connects to `GET /api/events/{session_id}` and surfaces a
 * filtered, in-memory activity log. Powers:
 *   - `/activity` — the global activity feed page
 *   - `/jobs/[spec_id]` — the per-job activity timeline
 *
 * Design notes:
 *   - We ring-buffer the last N events (default 500) so long
 *     runs don't blow up memory.
 *   - Filters are a `Set<string>` of event_type substrings; the
 *     default is the union of all C01-C08 event types.
 *   - The hook uses the existing `useEventSource` reconnect
 *     wrapper so a transient backend drop doesn't lose the
 *     feed — we get a "reconnecting" badge instead.
 *   - `pause`/`resume` toggles whether we ACCEPT new events from
 *     the SSE stream; the connection stays open so the user can
 *     resume without a reconnect storm.
 *
 * C01-C08 events surfaced:
 *   subagent.heartbeat      — every 5s per active subagent
 *   subagent.spawned        — coordinator started a subagent
 *   subagent.completed      — subagent finished (ok/failed)
 *   kg.refreshed            — knowledge graph sync completed
 *   kg.refreshed.failed     — KG sync failed
 *   board.completed         — kanban board finished
 *   board.failed            — kanban board failed
 *   team.created            — agent team created
 *   team.dissolved          — agent team dissolved
 *   job.cancelled           — JobSpec was cancelled
 *   job.paused              — JobSpec was paused
 *
 * Refs:
 *   backend/harness/api/state.py:94-103  emit_stream_event
 *   backend/api/routers/events.py:76-122 SSE endpoint
 *   src/lib/hooks/use-event-source.ts    reconnecting client
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BACKEND_URL } from "@/lib/api/api-client";
import {
  createReconnectingEventSource,
  type EventSourceState,
} from "@/lib/hooks/use-event-source";

export const ACTIVITY_EVENT_TYPES = [
  "subagent.heartbeat",
  "subagent.spawned",
  "subagent.completed",
  "subagent.text",
  "subagent.start",
  "subagent.complete",
  "kg.refreshed",
  "kg.refreshed.failed",
  "board.completed",
  "board.failed",
  "team.created",
  "team.dissolved",
  "job.cancelled",
  "job.paused",
  "budget.throttled",
  "agent.started",
  "agent.completed",
  "round.started",
  "round.completed",
  "llmcall.started",
  "llmcall.completed",
  "toolprogress",
  "tool.execution.started",
  "tool.execution.completed",
  "token.generated",
  "reasoning.generated",
  "approval.required",
  "reflexion.injected",
  "error",
  "status",
] as const;

export type ActivityEventType = (typeof ACTIVITY_EVENT_TYPES)[number] | string;

export interface ActivityEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  /** ISO timestamp from the backend `GenericStreamEvent.timestamp`. */
  timestamp: string;
  /** When we accepted the event on the client (for fallback). */
  receivedAt: number;
}

export interface UseActivityFeedOptions {
  sessionId: string | null;
  /** Substring filters; an event passes if `type.includes(filter)`. */
  filters?: ReadonlySet<string>;
  /** Ring-buffer cap. Default 500. */
  maxEvents?: number;
  /** Auto-scroll target (parent can call this on a ref). */
  onAppend?: () => void;
}

export interface UseActivityFeedReturn {
  events: ActivityEvent[];
  state: EventSourceState;
  paused: boolean;
  clear: () => void;
  pause: () => void;
  resume: () => void;
  togglePause: () => void;
  counts: Record<string, number>;
  total: number;
}

const DEFAULT_MAX_EVENTS = 500;

function toIsoTimestamp(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (typeof raw === "number") return new Date(raw * 1000).toISOString();
  return new Date().toISOString();
}

function normalize(
  type: string,
  data: unknown,
  eventId: string | undefined,
): ActivityEvent {
  const payload =
    data && typeof data === "object" && !Array.isArray(data)
      ? (data as Record<string, unknown>)
      : {};
  return {
    id: eventId || `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    payload,
    timestamp: toIsoTimestamp(payload.timestamp),
    receivedAt: Date.now(),
  };
}

export function useActivityFeed({
  sessionId,
  filters,
  maxEvents = DEFAULT_MAX_EVENTS,
  onAppend,
}: UseActivityFeedOptions): UseActivityFeedReturn {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [state, setState] = useState<EventSourceState>("idle");
  const [paused, setPaused] = useState(false);

  // Keep the latest filter set in a ref so the SSE callback can
  // read it without resubscribing.
  const filtersRef = useRef<ReadonlySet<string> | undefined>(filters);
  filtersRef.current = filters;

  // Pause state ref so the SSE callback can short-circuit
  // appending without re-subscribing.
  const pausedRef = useRef<boolean>(false);
  pausedRef.current = paused;

  // onAppend ref for stable callback identity.
  const onAppendRef = useRef<(() => void) | undefined>(onAppend);
  onAppendRef.current = onAppend;

  const clear = useCallback(() => setEvents([]), []);

  const pause = useCallback(() => setPaused(true), []);
  const resume = useCallback(() => setPaused(false), []);
  const togglePause = useCallback(() => setPaused((p) => !p), []);

  // Build the SSE URL. We pass a session_id — the backend filters
  // by it. The events.py router subscribes that session to its
  // EventSourceSink and forwards every event for that session.
  // Empty sessionId routes to the global stream which forwards
  // every event from every session (the Claude HUD "follow live"
  // pattern).
  const url = useMemo(() => {
    if (!sessionId) return `${BACKEND_URL}/api/events/_global`;
    return `${BACKEND_URL}/api/events/${encodeURIComponent(sessionId)}`;
  }, [sessionId]);

  useEffect(() => {
    if (!url) {
      setState("idle");
      return;
    }

    const controller = createReconnectingEventSource(url, {
      eventTypes: [...ACTIVITY_EVENT_TYPES, "connected"],
      onEvent: (type, data) => {
        if (type === "connected") {
          setState("open");
          return;
        }
        // Short-circuit if paused — but we still want the
        // connection to stay open, so we just skip the append.
        if (pausedRef.current) return;
        const filters = filtersRef.current;
        if (filters && filters.size > 0) {
          let match = false;
          for (const f of filters) {
            if (type.includes(f)) {
              match = true;
              break;
            }
          }
          if (!match) return;
        }
        setEvents((prev) => {
          const next = [...prev, normalize(type, data, undefined)];
          if (next.length > maxEvents) {
            next.splice(0, next.length - maxEvents);
          }
          return next;
        });
        onAppendRef.current?.();
      },
      onOpen: () => setState("open"),
      onError: () => setState("reconnecting"),
      onStateChange: (s) => setState(s),
      initialBackoffMs: 1000,
      maxBackoffMs: 10_000,
    });

    setState(controller.state);
    return () => {
      controller.close();
    };
  }, [url, maxEvents]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const e of events) c[e.type] = (c[e.type] ?? 0) + 1;
    return c;
  }, [events]);

  return {
    events,
    state,
    paused,
    clear,
    pause,
    resume,
    togglePause,
    counts,
    total: events.length,
  };
}
