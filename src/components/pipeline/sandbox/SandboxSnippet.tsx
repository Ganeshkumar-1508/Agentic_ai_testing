"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxResources, fetchSandboxInfo } from "@/lib/services/sandbox-client";
import type { SandboxResourceUsage, SandboxInfo } from "@/lib/types/sandbox";
import { Container, ExternalLink, Wifi } from "lucide-react";

export function SandboxSnippet() {
  const { sessionId, status, connected } = usePipelineStore();
  const [info, setInfo] = useState<SandboxInfo | null>(null);
  const [resources, setResources] = useState<SandboxResourceUsage | null>(null);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const [infoData, resData] = await Promise.all([
      fetchSandboxInfo(sessionId),
      fetchSandboxResources(sessionId),
    ]);
    if (infoData) setInfo(infoData);
    if (resData) setResources(resData);
  }, [sessionId]);

  useEffect(() => {
    if ((status === "running" || status === "completed") && sessionId) {
      load();
      const interval = setInterval(load, 5000);
      return () => clearInterval(interval);
    }
  }, [status, sessionId, load]);

  if (!sessionId || (status !== "running" && status !== "completed")) return null;

  return (
    <div className="bg-surface border border-emerald-500/10 rounded-[1.5rem] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-emerald-500/6">
        <div className="flex items-center gap-3">
          <Container className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          <span className="text-sm font-medium text-emerald-400">Sandbox</span>
          <span className="text-[11px] font-mono text-neutral-500">{sessionId.slice(0, 12)}</span>
          <span className="text-[11px] text-neutral-600">·</span>
          <span className="flex items-center gap-1.5 text-[11px] text-neutral-500">
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-neutral-600"}`} />
            {connected ? "running" : "idle"}
          </span>
        </div>
        <Link
          href={`/sandbox/${sessionId}`}
          className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/6 border border-emerald-500/10 rounded-lg px-3 py-1.5 hover:bg-emerald-500/10 transition-colors"
        >
          Open Sandbox
          <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
        </Link>
      </div>

      <div className="flex items-center gap-6 px-5 py-3 flex-wrap">
        <div className="flex items-center gap-2 flex-1 min-w-[140px]">
          <span className="text-[11px] text-neutral-500 w-7 shrink-0">CPU</span>
          <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${Math.min(resources?.cpu_percent ?? 0, 100)}%`, background: "#3b82f6" }} />
          </div>
          <span className="text-[10px] font-mono text-neutral-500 tabular-nums w-12 text-right">{resources?.cpu_percent ?? "—"}%</span>
        </div>

        <div className="flex items-center gap-2 flex-1 min-w-[140px]">
          <span className="text-[11px] text-neutral-500 w-7 shrink-0">MEM</span>
          <div className="flex-1 h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all duration-1000" style={{ width: resources?.memory_total_mb ? `${Math.min(Math.round((resources.memory_used_mb / resources.memory_total_mb) * 100), 100)}%` : "0%", background: "#34d399" }} />
          </div>
          <span className="text-[10px] font-mono text-neutral-500 tabular-nums w-20 text-right">
            {resources ? `${Math.round(resources.memory_used_mb / 1024 * 10) / 10} GB` : "—"}
          </span>
        </div>

        <div className="flex items-center gap-3 text-[10px] text-neutral-500 shrink-0 ml-auto">
          {info && (
            <>
              <span className="flex items-center gap-1">
                <Wifi className="w-3 h-3" strokeWidth={1.5} />
                {Math.round(info.uptime_seconds / 60)}m
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
