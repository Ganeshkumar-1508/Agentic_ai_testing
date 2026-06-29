"use client";

import { useState, useEffect, useCallback } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxPorts } from "@/lib/services/sandbox-client";
import type { SandboxPort } from "@/lib/types/sandbox";
import { Monitor, Globe } from "lucide-react";

export function SandboxPorts() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [ports, setPorts] = useState<SandboxPort[]>([]);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchSandboxPorts(sessionId);
    setPorts(data);
  }, [sessionId]);

  useEffect(() => {
    if (status === "running" && sessionId) {
      load();
      const interval = setInterval(load, 10000);
      return () => clearInterval(interval);
    }
  }, [status, sessionId, load]);

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5">
      <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider mb-3">Ports</div>
      {ports.length === 0 && <div className="text-[11px] text-neutral-600 text-center py-4">No exposed ports</div>}
      <div className="flex flex-wrap gap-2">
        {ports.map((p) => (
          <div key={p.container_port} className="flex items-center gap-1.5 text-[10px] font-mono text-blue-400 bg-blue-500/6 border border-blue-500/10 rounded-lg px-2.5 py-1.5">
            {p.label ? <Globe className="w-3 h-3" strokeWidth={1.5} /> : <Monitor className="w-3 h-3" strokeWidth={1.5} />}
            <span>{p.container_port}</span>
            {p.label && <span className="text-neutral-500">/{p.label}</span>}
            <span className="text-neutral-600">→</span>
            <span className="text-neutral-400">localhost:{p.host_port}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
