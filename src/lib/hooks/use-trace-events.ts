"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { api } from "@/lib/api/api-client";

export interface TraceEvent {
  id: string;
  eventType: string;
  eventData: Record<string, unknown>;
  parentId: string;
  createdAt: string;
}

export interface TraceTreeNode {
  event: TraceEvent;
  children: TraceTreeNode[];
}

export type RunStatus = "idle" | "loading" | "streaming" | "completed" | "failed";

export interface UseTraceEventsReturn {
  events: TraceEvent[];
  tree: TraceTreeNode[];
  status: RunStatus;
  error: string | null;
  refetch: () => void;
}

function buildTree(events: TraceEvent[]): TraceTreeNode[] {
  const map = new Map<string, TraceTreeNode>();
  const roots: TraceTreeNode[] = [];

  for (const e of events) {
    map.set(e.id, { event: e, children: [] });
  }

  for (const e of events) {
    const node = map.get(e.id);
    if (!node) continue;
    if (e.parentId && map.has(e.parentId)) {
      map.get(e.parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  return roots;
}

export function useTraceEvents(runId: string, live = false): UseTraceEventsReturn {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const seenRef = useRef<Set<string>>(new Set());

  const fetchEvents = useCallback(async () => {
    if (!runId) return;
    try {
      const raw = await api.get<any>(
        `/api/runs/${runId}/trace-events`,
        { limit: "500" },
      ).then((d) => (d?.events ?? []) as TraceEvent[]).catch(() => {
        throw new Error("Failed to fetch trace events");
      });

      setEvents((prev) => {
        const existing = new Set(prev.map((e) => e.id));
        const newEvents = raw.filter((e) => !existing.has(e.id));
        if (newEvents.length === 0 && prev.length > 0) return prev;
        return [...prev, ...newEvents];
      });

      const hasAgentEnd = raw.some((e: TraceEvent) => e.eventType === "agent.completed");
      if (hasAgentEnd) {
        setStatus("completed");
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } else if (live) {
        setStatus("streaming");
      } else {
        setStatus("completed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setStatus("failed");
    }
  }, [runId, live]);

  useEffect(() => {
    if (!runId) {
      setEvents([]);
      setStatus("idle");
      return;
    }

    setEvents([]);
    setError(null);
    seenRef.current = new Set();
    setStatus("loading");

    if (live) {
      fetchEvents();
      pollRef.current = setInterval(fetchEvents, 2000);
      return () => {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      };
    } else {
      fetchEvents();
    }
  }, [runId, live, fetchEvents]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  const tree = useMemo(() => buildTree(events), [events]);

  return { events, tree, status, error, refetch: fetchEvents };
}
