"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { createReconnectingEventSource, type ReconnectingEventSourceController } from "./use-event-source";

/** Wire shape of one event frame pushed by the backend `/api/events/{session_id}` SSE route.
 *
 *  Mirrors `harness.events.Event.to_dict()`.  Kept as a separate type so
 *  the hook doesn't need a runtime import from the (huge) generated
 *  `schema.d.ts`.
 */
export interface SessionEvent {
  type: string;
  data: Record<string, unknown>;
  source: string;
  session_id: string | null;
  subagent_id: string | null;
  parent_subagent_id: string | null;
  timestamp: number;
}

export type SessionEventsState = "idle" | "connecting" | "open" | "reconnecting" | "closed" | "error";

export interface UseSessionEventsOptions {
  /** Which event types to retain.  `null` or omitted keeps **every** typed event.
   *
   *  NOTE: the browser's `EventSource` API only fires `addEventListener(type,...)`
   *  for types you explicitly subscribe to — there is no wildcard.  When
   *  `eventTypes` is null, the hook tells the underlying controller to skip
   *  per-type listeners so the generic `onmessage` channel catches the
   *  raw SSE frame (still typed by the server's `event:` field — the
   *  type lives inside `data.type`).
   */
  eventTypes?: readonly string[] | null;
  /** Optional callback fired on every retained event. */
  onEvent?: (event: SessionEvent) => void;
  /** Maximum events to retain in the local ring buffer.  Defaults to 200. */
  maxEvents?: number;
  /** Auto-connect when the component mounts.  Defaults to true. */
  autoConnect?: boolean;
}

export interface UseSessionEventsReturn {
  events: SessionEvent[];
  state: SessionEventsState;
  retryCount: number;
  error: string | null;
  clear: () => void;
  retry: () => void;
  close: () => void;
}

const DEFAULT_MAX_EVENTS = 200;

/**
 * Subscribe to the backend's `/api/events/{session_id}` SSE stream and
 * return a live, append-only list of events for the session.
 *
 * Backed by `createReconnectingEventSource` so disconnects are retried
 * with exponential backoff; the browser's `EventSource` API handles
 * `Last-Event-ID` replay automatically.
 *
 * Use this for **live, in-memory** agent activity (tool starts/stops,
 * subagent lifecycle, approval requests) — for persisted historical
 * traces use `useTraceEvents` (poll-based) instead.
 *
 * @example
 *   const { events, state } = useSessionEvents(sessionId, {
 *     eventTypes: ["ToolExecutionStarted", "ToolExecutionCompleted", "agent.completed"],
 *     onEvent: (e) => console.log("live:", e.type, e.data),
 *   });
 */
export function useSessionEvents(
  sessionId: string | null | undefined,
  options: UseSessionEventsOptions = {},
): UseSessionEventsReturn {
  const { eventTypes = null, onEvent, maxEvents = DEFAULT_MAX_EVENTS, autoConnect = true } = options;

  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [state, setState] = useState<SessionEventsState>("idle");
  const [retryCount, setRetryCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Refs to avoid re-creating the controller on every render.
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const eventTypesRef = useRef(eventTypes);
  eventTypesRef.current = eventTypes;

  const controllerRef = useRef<ReconnectingEventSourceController | null>(null);

  // Memoize the EventSource `eventTypes` option so the underlying effect
  // doesn't refire on every render (the source hook depends on it).
  const sourceEventTypes = useMemo<string[] | undefined>(() => {
    if (eventTypes === null) return undefined; // undefined → no type listeners → onmessage catches all
    return Array.from(eventTypes);
  }, [eventTypes]);

  const handleEvent = useCallback(
    (evt: SessionEvent) => {
      const allowed = eventTypesRef.current;
      if (allowed !== null && !allowed.includes(evt.type)) return;
      setEvents((prev) => {
        const next = prev.length >= maxEvents ? prev.slice(prev.length - maxEvents + 1) : prev.slice();
        next.push(evt);
        return next;
      });
      onEventRef.current?.(evt);
    },
    [maxEvents],
  );

  useEffect(() => {
    if (!autoConnect || !sessionId) {
      setState("idle");
      return;
    }

    setError(null);
    setEvents([]);

    const url = `/api/events/${encodeURIComponent(sessionId)}`;
    const controllerRefLocal: { current: ReconnectingEventSourceController | null } = { current: null };
    const controller = createReconnectingEventSource(url, {
      eventTypes: sourceEventTypes,
      // When eventTypes is null we deliberately pass `undefined` above so the
      // raw SSE frames route through onMessage — they still carry `data.type`
      // set by the server, so handleEvent's filter logic works as before.
      onMessage: (raw) => {
        if (raw && typeof raw === "object" && "type" in (raw as object)) {
          handleEvent(raw as SessionEvent);
        }
      },
      onEvent: (_type, data) => {
        if (data && typeof data === "object" && "type" in (data as object)) {
          handleEvent(data as SessionEvent);
        }
      },
      onStateChange: (s) => {
        setState(s);
        setRetryCount(controllerRefLocal.current?.retryCount ?? 0);
      },
      onOpen: () => {
        setError(null);
      },
      onError: (e) => {
        setError((e as ErrorEvent)?.message ?? "SSE connection error");
      },
    });
    controllerRefLocal.current = controller;

    controllerRef.current = controller;
    setState(controller.state);
    setRetryCount(controller.retryCount);

    return () => {
      controller.close();
      controllerRef.current = null;
    };
  }, [autoConnect, sessionId, sourceEventTypes, handleEvent]);

  const clear = useCallback(() => setEvents([]), []);
  const retry = useCallback(() => controllerRef.current?.retry(), []);
  const close = useCallback(() => controllerRef.current?.close(), []);

  return { events, state, retryCount, error, clear, retry, close };
}
