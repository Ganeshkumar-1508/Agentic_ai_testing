"use client";

import { usePipelineStore } from "@/stores/pipeline-store";

export function MetricsBar() {
  const { totalTokens, estimatedCost, status, connected } = usePipelineStore();

  return (
    <div className="flex items-center gap-3">
      {connected && status === "running" && (
        <>
          <div className="flex items-center gap-1.5 text-[10px] text-neutral-500 font-mono tabular-nums px-2 py-1 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            live
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-neutral-500 font-mono tabular-nums px-2 py-1 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            {totalTokens.toLocaleString()}t
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-neutral-500 font-mono tabular-nums px-2 py-1 rounded-lg bg-white/[0.03] border border-white/[0.06]">
            ${estimatedCost.toFixed(4)}
          </div>
        </>
      )}
      <div className="flex items-center gap-1.5 text-[10px] text-neutral-500 font-mono tabular-nums">
        read · write · analyze · delegate
      </div>
    </div>
  );
}
