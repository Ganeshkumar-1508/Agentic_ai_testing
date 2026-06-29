"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type EventSourceState =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "error";

export interface ReconnectingEventSourceOptions {
  eventTypes?: readonly string[];
  onMessage?: (data: unknown) => void;
  onEvent?: (type: string, data: unknown) => void;
  onError?: (err: Event) => void;
  onOpen?: () => void;
  onStateChange?: (state: EventSourceState) => void;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  backoffMultiplier?: number;
  maxRetries?: number;
}

export interface ReconnectingEventSourceController {
  readonly state: EventSourceState;
  readonly retryCount: number;
  retry: () => void;
  close: () => void;
}

export function createReconnectingEventSource(
  url: string | null,
  options: ReconnectingEventSourceOptions = {},
): ReconnectingEventSourceController {
  const {
    eventTypes,
    onMessage,
    onEvent,
    onError,
    onOpen,
    onStateChange,
    initialBackoffMs = 1000,
    maxBackoffMs = 30_000,
    backoffMultiplier = 2,
    maxRetries = -1,
  } = options;

  let es: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let backoff = initialBackoffMs;
  let retryCount = 0;
  let closedByUser = false;
  let state: EventSourceState = "idle";

  const callbacks = { onMessage, onEvent, onError, onOpen, onStateChange };
  const update = (next: EventSourceState) => {
    if (state === next) return;
    state = next;
    callbacks.onStateChange?.(next);
  };

  const clearRetry = () => {
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const closeInternal = () => {
    clearRetry();
    if (es) {
      es.close();
      es = null;
    }
  };

  const connect = () => {
    if (!url) {
      update("idle");
      return;
    }
    if (es) {
      es.close();
      es = null;
    }

    let next: EventSource;
    try {
      next = new EventSource(url);
    } catch {
      update("error");
      return;
    }
    es = next;
    update("connecting");

    const namedTypes = eventTypes ?? [];
    for (const type of namedTypes) {
      next.addEventListener(type, (e: Event) => {
        const me = e as MessageEvent;
        let parsed: unknown;
        try {
          parsed = me.data ? JSON.parse(me.data) : null;
        } catch {
          parsed = me.data;
        }
        callbacks.onEvent?.(type, parsed);
      });
    }

    next.onopen = () => {
      backoff = initialBackoffMs;
      retryCount = 0;
      update("open");
      callbacks.onOpen?.();
    };

    next.onmessage = (e: MessageEvent) => {
      let parsed: unknown;
      try {
        parsed = e.data ? JSON.parse(e.data) : null;
      } catch {
        parsed = e.data;
      }
      callbacks.onMessage?.(parsed);
    };

    next.onerror = (e: Event) => {
      callbacks.onError?.(e);
      if (es) {
        es.close();
        es = null;
      }
      if (closedByUser) {
        update("closed");
        return;
      }
      if (maxRetries >= 0 && retryCount >= maxRetries) {
        update("error");
        return;
      }
      const delay = backoff;
      backoff = Math.min(backoff * backoffMultiplier, maxBackoffMs);
      retryCount += 1;
      update("reconnecting");
      retryTimer = setTimeout(connect, delay);
    };
  };

  if (url) {
    closedByUser = false;
    backoff = initialBackoffMs;
    retryCount = 0;
    connect();
  } else {
    update("idle");
  }

  return {
    get state() {
      return state;
    },
    get retryCount() {
      return retryCount;
    },
    retry() {
      closedByUser = false;
      backoff = initialBackoffMs;
      retryCount = 0;
      closeInternal();
      connect();
    },
    close() {
      closedByUser = true;
      closeInternal();
      update("closed");
    },
  };
}

export interface UseEventSourceOptions extends ReconnectingEventSourceOptions {
  url: string | null;
}

export interface UseEventSourceReturn {
  state: EventSourceState;
  retryCount: number;
  retry: () => void;
  close: () => void;
}

export function useEventSource(options: UseEventSourceOptions): UseEventSourceReturn {
  const {
    url,
    eventTypes,
    onMessage,
    onEvent,
    onError,
    onOpen,
    onStateChange,
    initialBackoffMs = 1000,
    maxBackoffMs = 30_000,
    backoffMultiplier = 2,
    maxRetries = -1,
  } = options;

  const [state, setState] = useState<EventSourceState>("idle");
  const [retryCount, setRetryCount] = useState(0);
  const controllerRef = useRef<ReconnectingEventSourceController | null>(null);

  useEffect(() => {
    if (!url) {
      setState("idle");
      setRetryCount(0);
      return;
    }
    const controllerRefLocal: { current: ReconnectingEventSourceController | null } = { current: null };
    const controller = createReconnectingEventSource(url, {
      eventTypes,
      onMessage,
      onEvent,
      onError,
      onOpen,
      onStateChange: (next) => {
        setState(next);
        setRetryCount(controllerRefLocal.current?.retryCount ?? 0);
      },
      initialBackoffMs,
      maxBackoffMs,
      backoffMultiplier,
      maxRetries,
    });
    controllerRefLocal.current = controller;
    controllerRef.current = controller;
    setState(controller.state);
    setRetryCount(0);
    return () => {
      controller.close();
      controllerRef.current = null;
    };
  }, [
    url,
    eventTypes,
    onMessage,
    onEvent,
    onError,
    onOpen,
    onStateChange,
    initialBackoffMs,
    maxBackoffMs,
    backoffMultiplier,
    maxRetries,
  ]);

  const retry = useCallback(() => controllerRef.current?.retry(), []);
  const close = useCallback(() => controllerRef.current?.close(), []);

  return { state, retryCount, retry, close };
}
