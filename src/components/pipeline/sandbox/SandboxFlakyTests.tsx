"use client";

import { useState, useEffect, useCallback } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchFlakyTests } from "@/lib/services/sandbox-client";
import type { SandboxFlakyTest } from "@/lib/types/sandbox";
import { AlertTriangle } from "lucide-react";

export function SandboxFlakyTests() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [flaky, setFlaky] = useState<SandboxFlakyTest[]>([]);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchFlakyTests(sessionId);
    setFlaky(data);
  }, [sessionId]);

  useEffect(() => {
    if (status === "completed" && sessionId) load();
  }, [status, sessionId, load]);

  if (flaky.length === 0) return null;

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-zinc-400" strokeWidth={1.5} />
          <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">Flaky</span>
        </div>
        <span className="text-[10px] font-medium text-zinc-400 bg-zinc-500/10 border border-zinc-500/15 rounded-md px-2 py-0.5">{flaky.length} detected</span>
      </div>
      <div className="space-y-1">
        {flaky.slice(0, 5).map((f) => (
          <div key={f.test_name} className="flex items-center justify-between py-1 text-xs">
            <span className="text-neutral-400 truncate mr-2">{f.test_name}</span>
            <div className="flex items-center gap-2 shrink-0">
              <span className="font-mono text-[10px] text-neutral-600">
                <span className="text-emerald-400">{f.pass_count}</span>
                /<span className="text-red-400">{f.fail_count}</span>
              </span>
              <span className="font-mono text-[10px] text-zinc-400">{f.flaky_score}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
