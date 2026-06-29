"use client";

import { useState, useEffect, useCallback } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxResources } from "@/lib/services/sandbox-client";
import type { SandboxResourceUsage } from "@/lib/types/sandbox";

export function SandboxResources() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [resources, setResources] = useState<SandboxResourceUsage | null>(null);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchSandboxResources(sessionId);
    if (data) setResources(data);
  }, [sessionId]);

  useEffect(() => {
    if (status === "running" && sessionId) {
      load();
      const interval = setInterval(load, 8000);
      return () => clearInterval(interval);
    }
  }, [status, sessionId, load]);

  const bars = resources
    ? [
        { label: "CPU", value: `${resources.cpu_percent}%`, pct: Math.min(resources.cpu_percent, 100), color: "#3b82f6" },
        { label: "MEM", value: resources.memory_total_mb ? `${resources.memory_used_mb} / ${resources.memory_total_mb} MB` : `${resources.memory_used_mb} MB`, pct: resources.memory_total_mb ? Math.round((resources.memory_used_mb / resources.memory_total_mb) * 100) : 0, color: "#34d399" },
        { label: "DSK", value: resources.disk_total_mb ? `${resources.disk_used_mb} / ${resources.disk_total_mb} MB` : `${resources.disk_used_mb} MB`, pct: resources.disk_total_mb ? Math.round((resources.disk_used_mb / resources.disk_total_mb) * 100) : 0, color: "#f59e0b" },
      ]
    : [];

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5">
      <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider mb-3">Container</div>
      {bars.length === 0 && <div className="text-[11px] text-neutral-600 text-center py-4">Waiting for data...</div>}
      {bars.map((bar) => (
        <div key={bar.label} className="flex items-center gap-2 py-1.5">
          <span className="text-[11px] text-neutral-500 w-7 shrink-0">{bar.label}</span>
          <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${bar.pct}%`, background: bar.color }} />
          </div>
          <span className="text-[10px] font-mono text-neutral-500 tabular-nums w-24 text-right">{bar.value}</span>
        </div>
      ))}
    </div>
  );
}
