"use client";

import { useState, useEffect, useCallback } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxDependencies } from "@/lib/services/sandbox-client";
import type { SandboxDependency } from "@/lib/types/sandbox";
import { ScrollArea } from "@/components/ui/scroll-area";

export function SandboxDependencies() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [deps, setDeps] = useState<SandboxDependency[]>([]);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchSandboxDependencies(sessionId);
    setDeps(data.dependencies);
    setTotal(data.total_count);
  }, [sessionId]);

  useEffect(() => {
    if (status === "completed" && sessionId) load();
  }, [status, sessionId, load]);

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">Dependencies</div>
        <span className="text-[10px] font-mono text-neutral-600">{total} total</span>
      </div>
      <ScrollArea className="max-h-[160px]">
        {deps.length === 0 && <div className="text-[11px] text-neutral-600 text-center py-4">No dependencies detected</div>}
        {deps.map((d) => (
          <div key={d.name} className="flex items-center justify-between py-1 text-xs">
            <span className="text-neutral-400 truncate mr-2">{d.name}</span>
            <span className="text-neutral-600 font-mono text-[10px] shrink-0">v{d.version}</span>
          </div>
        ))}
      </ScrollArea>
    </div>
  );
}
