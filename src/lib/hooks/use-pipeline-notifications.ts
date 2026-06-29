"use client";

import { useEffect } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";

export function usePipelineNotifications() {
  const addEvent = usePipelineStore((s) => s.addEvent);

  useEffect(() => {
    const unsub = usePipelineStore.subscribe((state, prev) => {
      const lastEvent = state.events[state.events.length - 1];
      const prevLen = prev.events.length;

      if (state.events.length > prevLen && lastEvent) {
        // Could trigger toast for done/error events
        if (lastEvent.type === "done" && typeof window !== "undefined") {
          // In production, dispatch a custom event that a toast component listens to
          window.dispatchEvent(new CustomEvent("pipeline:done", { detail: lastEvent }));
        }
        if (lastEvent.type === "error") {
          window.dispatchEvent(new CustomEvent("pipeline:error", { detail: lastEvent }));
        }
      }
    });

    return () => unsub();
  }, []);
}
