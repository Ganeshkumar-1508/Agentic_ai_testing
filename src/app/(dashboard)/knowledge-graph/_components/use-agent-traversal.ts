"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import type { KGNode, KnowledgeGraph } from "./types";
import { useEventSource } from "@/lib/hooks/use-event-source";
import { api, BASE_URL } from "@/lib/api/api-client";

// C3.1: CodeGraph MCP tools (replaced the old kg_search / kg_callers /
// kg_callees names in the 5→4 consolidation). The traversal panel
// highlights the nodes/edges the agent is currently exploring, so it
// MUST keep this set in sync with the tool names registered by
// `harness/tools/codegraph_tools.py`.
const KG_TOOL_NAMES = new Set([
  "codegraph_explore",
  "codegraph_node",
  "codegraph_search",
  "codegraph_callers",
]);
const SSE_EVENT_TYPES = [
  "subagent.tool_start",
  "subagent.tool_completed",
  "session.completed",
  "session.failed",
] as const;

export interface TraversalEvent {
  id: string;
  nodeId: string;
  nodeName: string;
  agentId: string;
  tool: string;
  query: string;
  timestamp: number;
}

export interface AgentTraversalState {
  traversedNodeIds: ReadonlySet<string>;
  traversedEdgeIds: ReadonlySet<string>;
  events: TraversalEvent[];
  isConnected: boolean;
  sessionId: string | null;
  sessionStatus: string | null;
  isRunning: boolean;
  clearTraversal: () => void;
}

function parseToolInput(input: string): Record<string, string> {
  if (!input || input === "{}") return {};
  try {
    return JSON.parse(input) as Record<string, string>;
  } catch {
    try {
      return JSON.parse(input.replace(/'/g, '"')) as Record<string, string>;
    } catch {
      return { raw: input };
    }
  }
}

function findMatchingNodeIds(graph: KnowledgeGraph, query: string): Set<string> {
  const matched = new Set<string>();
  const lower = query.toLowerCase().trim();
  if (!lower) return matched;

  for (const node of graph.nodes) {
    if (
      node.id.toLowerCase() === lower ||
      node.name.toLowerCase() === lower ||
      node.name.toLowerCase().includes(lower) ||
      (node.file ?? "").toLowerCase().includes(lower) ||
      (node.filePath ?? "").toLowerCase().includes(lower) ||
      node.tags.some((t) => t.toLowerCase().includes(lower)) ||
      (node.summary ?? "").toLowerCase().includes(lower)
    ) {
      matched.add(node.id);
    }
  }

  return matched;
}

export function useAgentTraversal(graph: KnowledgeGraph | null): AgentTraversalState {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [rawEvents, setRawEvents] = useState<TraversalEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const graphRef = useRef(graph);
  graphRef.current = graph;

  const seenKeysRef = useRef(new Set<string>());

  const sseUrl = sessionId && sessionStatus === "running" ? `${BASE_URL}/api/delegate/${sessionId}/stream` : null;

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.get<{ active_session?: { id?: string; status?: string } | null }>("/api/ops/swarm/active");
        if (cancelled) return;
        const session = data?.active_session;
        if (session?.id && (session.status === "running" || session.status === "completed")) {
          setSessionId(session.id);
          setSessionStatus(session.status);
        } else {
          setSessionId(null);
          setSessionStatus(null);
        }
      } catch {
        if (!cancelled) {
          setSessionId(null);
          setSessionStatus(null);
        }
      }
    };
    poll();
    const interval = setInterval(poll, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const nodeMap = useMemo(() => {
    const map = new Map<string, KGNode>();
    if (!graph) return map;
    for (const node of graph.nodes) {
      map.set(node.id, node);
      map.set(node.name.toLowerCase(), node);
      if (node.file) map.set(node.file.toLowerCase(), node);
      if (node.filePath) map.set(node.filePath.toLowerCase(), node);
    }
    return map;
  }, [graph]);

  const onEventRef = useRef<(type: string, data: unknown) => void>(undefined!);
  onEventRef.current = (type, rawData) => {
    const currentGraph = graphRef.current;
    if (!currentGraph || type !== "subagent.tool_start") return;

    const data = rawData as Record<string, unknown>;
    const toolName = (data.tool_name as string) ?? "";
    if (!KG_TOOL_NAMES.has(toolName)) return;

    const toolInput = (data.tool_input as string) ?? "{}";
    const agentId = (data.agent_id as string) ?? "agent";
    const params = parseToolInput(toolInput);
    const query = (params.query ?? params.symbol_id ?? params.raw ?? toolInput).slice(0, 200);
    const matchedIds = findMatchingNodeIds(currentGraph, query);

    if (matchedIds.size === 0) return;

    const ts = Date.now();
    const newEvents: TraversalEvent[] = [];

    for (const nodeId of matchedIds) {
      const key = `${ts}-${nodeId}-${toolName}`;
      if (seenKeysRef.current.has(key)) continue;
      seenKeysRef.current.add(key);
      if (seenKeysRef.current.size > 500) {
        const arr = Array.from(seenKeysRef.current);
        seenKeysRef.current = new Set(arr.slice(-300));
      }
      const node = nodeMap.get(nodeId) ?? nodeMap.get(nodeId.toLowerCase());
      newEvents.push({
        id: key,
        nodeId,
        nodeName: node?.name ?? nodeId,
        agentId,
        tool: toolName,
        query,
        timestamp: ts,
      });
    }

    if (newEvents.length > 0) {
      setRawEvents((prev) => [...newEvents, ...prev].slice(0, 150));
    }
  };

  const onOpenRef = useRef<() => void>(undefined!);
  onOpenRef.current = () => setIsConnected(true);

  const onStateChangeRef = useRef<(state: string) => void>(undefined!);
  onStateChangeRef.current = (state) => {
    setIsConnected(state === "open" || state === "reconnecting");
  };

  useEventSource({
    url: sseUrl,
    eventTypes: SSE_EVENT_TYPES,
    onEvent: useCallback((type, data) => onEventRef.current?.(type, data), []),
    onOpen: useCallback(() => onOpenRef.current?.(), []),
    onStateChange: useCallback((state) => onStateChangeRef.current?.(state), []),
  });

  const traversedNodeIds = useMemo(() => {
    const set = new Set<string>();
    for (const ev of rawEvents) set.add(ev.nodeId);
    return set as ReadonlySet<string>;
  }, [rawEvents]);

  const traversedEdgeIds = useMemo(() => {
    const set = new Set<string>();
    if (!graph) return set as ReadonlySet<string>;
    for (const edge of graph.edges) {
      if (traversedNodeIds.has(edge.source) && traversedNodeIds.has(edge.target)) {
        set.add(`${edge.source}→${edge.target}`);
      }
    }
    return set as ReadonlySet<string>;
  }, [traversedNodeIds, graph]);

  const clearTraversal = useCallback(() => {
    setRawEvents([]);
    seenKeysRef.current = new Set();
  }, []);

  return {
    traversedNodeIds,
    traversedEdgeIds,
    events: rawEvents,
    isConnected,
    sessionId,
    sessionStatus,
    isRunning: sessionStatus === "running",
    clearTraversal,
  };
}

export interface TraversalTimelineProps {
  events: TraversalEvent[];
  onFocusNode: (nodeId: string) => void;
  onClear: () => void;
}
