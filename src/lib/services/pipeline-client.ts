"use client";

import { useCallback, useRef } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import type { PipelineEvent } from "@/lib/types/pipeline";
import { BACKEND_URL } from "@/lib/api/api-client";

export function usePipelineStream() {
  const abortRef = useRef<AbortController | null>(null);
  const { addEvent, setConnected, setStatus, setRunId, setRequirements, startRun, reset } = usePipelineStore();

  const startStream = useCallback(async (requirements: string, mode = "auto") => {
    reset();
    startRun();
    setRequirements(requirements);
    setConnected(true);

    abortRef.current = new AbortController();

    try {
      const res = await fetch(`${BACKEND_URL}/pipeline/test/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirements, mode }),
        signal: abortRef.current.signal,
      });

      if (!res.ok) throw new Error(`Pipeline stream failed: ${res.status}`);
      const reader = res.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const parsed = JSON.parse(line.slice(6));
              const event = parsed.data || parsed;
              const typedEvent: PipelineEvent = { type: event.type, ...event };
              addEvent(typedEvent);
              if (event.type === "done") {
                setConnected(false);
                if (event.run_id) {
                  setRunId(event.run_id);
                  try { sessionStorage.setItem("pipeline_run_id", event.run_id); } catch {}
                }
                return;
              }
              if (event.type === "error") {
                setConnected(false);
                return;
              }
            } catch {
              // Skip unparseable events
            }
          }
        }
      }
    } catch (error) {
      if (abortRef.current?.signal.aborted) return;
      console.error("Pipeline stream error:", error);
      addEvent({ type: "error", message: error instanceof Error ? error.message : "Stream failed" });
      setConnected(false);
      setStatus("failed");
    }
  }, [addEvent, setConnected, setStatus, setRunId, startRun, reset]);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    setConnected(false);
    setStatus("idle");
  }, [setConnected, setStatus]);

  return { startStream, stopStream };
}
