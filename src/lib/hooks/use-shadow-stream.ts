"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface ShadowEvent {
  type: string;
  data: Record<string, unknown>;
  id: number;
  ts: string | null;
}

export interface ShadowAgentState {
  currentTool: { name: string; input: string; elapsed: number } | null;
  reasoning: string;
  tokenBurn: { tokens: number; cost: number; model: string }[];
  recentToolResults: { tool: string; result: string; duration: number }[];
  status: "idle" | "connecting" | "live" | "error";
  elapsed: number;
}

const SHADOW_EVENT_TYPES = [
  "shadow.ready",
  "token",
  "reasoning",
  "tool_calls",
  "tool_result",
  "cost.tick",
  "budget.tick",
  "shadow.ended",
] as const;

export function useShadowStream(sessionId: string | null) {
  const [state, setState] = useState<ShadowAgentState>({
    currentTool: null,
    reasoning: "",
    tokenBurn: [],
    recentToolResults: [],
    status: "idle",
    elapsed: 0,
  });
  const [connectionState, setConnectionState] = useState<"idle" | "connecting" | "live" | "error">("idle");
  const esRef = useRef<EventSource | null>(null);
  const startTimeRef = useRef<number>(0);
  const elapsedIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reasoningBufferRef = useRef("");

  const close = useCallback(() => {
    if (elapsedIntervalRef.current) {
      clearInterval(elapsedIntervalRef.current);
      elapsedIntervalRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setConnectionState("idle");
    setState({
      currentTool: null,
      reasoning: "",
      tokenBurn: [],
      recentToolResults: [],
      status: "idle",
      elapsed: 0,
    });
    reasoningBufferRef.current = "";
  }, []);

  useEffect(() => {
    if (!sessionId) {
      close();
      return;
    }

    const url = `/api/delegate/${sessionId}/shadow/stream`;
    setConnectionState("connecting");
    reasoningBufferRef.current = "";
    startTimeRef.current = Date.now();

    const es = new EventSource(url);
    esRef.current = es;

    elapsedIntervalRef.current = setInterval(() => {
      setState((prev) => ({
        ...prev,
        elapsed: Math.floor((Date.now() - startTimeRef.current) / 1000),
      }));
    }, 1000);

    es.addEventListener("shadow.ready", (e: MessageEvent) => {
      setConnectionState("live");
      startTimeRef.current = Date.now();
    });

    es.addEventListener("reasoning", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const text = d?.data?.text || "";
        if (text) {
          reasoningBufferRef.current += text;
          setState((prev) => ({ ...prev, reasoning: reasoningBufferRef.current }));
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("token", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const text = d?.data?.text || d?.text || "";
        if (text) {
          setState((prev) => ({ ...prev, reasoning: prev.reasoning + text }));
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("tool_calls", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const toolCalls = d?.data?.tool_calls || d?.data?.toolCalls || [];
        if (toolCalls.length > 0) {
          const tc = toolCalls[0];
          setState((prev) => ({
            ...prev,
            currentTool: {
              name: tc.name || tc.function?.name || "unknown",
              input: JSON.stringify(tc.arguments || tc.input || tc.function?.arguments || "").slice(0, 200),
              elapsed: 0,
            },
          }));
          reasoningBufferRef.current = "";
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("tool_result", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const toolName = d?.data?.tool_name || d?.data?.name || "";
        const result = d?.data?.output_preview || d?.data?.result || d?.data?.content || "";
        const duration = d?.data?.duration_ms || 0;
        if (toolName) {
          setState((prev) => ({
            ...prev,
            currentTool: null,
            recentToolResults: [
              { tool: toolName, result: String(result).slice(0, 300), duration },
              ...prev.recentToolResults,
            ].slice(0, 20),
          }));
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("cost.tick", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        const tokens = d?.data?.tokens || d?.tokens || 0;
        const cost = d?.data?.cost || d?.cost || 0;
        const model = d?.data?.model || d?.model || "";
        if (tokens || cost) {
          setState((prev) => ({
            ...prev,
            tokenBurn: [
              ...prev.tokenBurn,
              { tokens, cost, model },
            ].slice(-60),
          }));
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("shadow.ended", () => {
      close();
    });

    es.onerror = () => {
      setConnectionState("error");
    };

    return () => {
      close();
    };
  }, [sessionId, close]);

  return { state, connectionState, close };
}
