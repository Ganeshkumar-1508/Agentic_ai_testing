"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface HeatmapData {
  grid: number[][];
  labels: string[];
  row_labels: string[];
  total_tokens: number;
  peak: { tokens: number; day: string; bucket: string };
  days: number;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return `${n}`;
}

function cellOpacity(tokens: number, max: number): number {
  if (max === 0 || tokens === 0) return 0.04;
  return Math.min(1, 0.15 + (tokens / max) * 0.85);
}

export function TokenUsageHeatmapCard() {
  const { data, isLoading } = useQuery<HeatmapData>({
    queryKey: ["dashboard-token-heatmap"],
    queryFn: () => api.get<HeatmapData>("/api/dashboard/widgets/token-heatmap?days=7"),
    refetchInterval: 60_000,
  });

  const grid = data?.grid ?? [];
  const labels = data?.labels ?? ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const rowLabels = data?.row_labels ?? ["AM", "PM", "Eve"];
  const total = data?.total_tokens ?? 0;
  const max = Math.max(1, ...grid.flat());
  const hasData = total > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 1.05, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="card-label">Token Usage (7 days)</div>
        <div className="text-[11px] font-mono text-neutral-400">
          {hasData ? `${formatTokens(total)} tokens` : "—"}
        </div>
      </div>

      {isLoading ? (
        <div className="h-32 rounded shimmer-bg flex-1" />
      ) : !hasData ? (
        <div className="h-32 flex items-center justify-center text-xs text-neutral-600 flex-1">
          No token usage in the last 7 days.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-[50px_repeat(7,1fr)] gap-1 text-[10px] text-neutral-500 font-mono mb-1 shrink-0">
            <span></span>
            {labels.map((d) => (
              <span key={d} className="text-center">{d.slice(0, 3)}</span>
            ))}
          </div>

          <div className="space-y-1 flex-1 min-h-0">
            {rowLabels.map((rl, rowIdx) => (
              <div key={rl} className="grid grid-cols-[50px_repeat(7,1fr)] gap-1">
                <span className="text-[10px] text-neutral-500 font-mono flex items-center">
                  {rl}
                </span>
                {grid.map((dayRow, dayIdx) => {
                  const tokens = dayRow?.[rowIdx] ?? 0;
                  const opacity = cellOpacity(tokens, max);
                  return (
                    <motion.div
                      key={`${rl}-${dayIdx}`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity }}
                      transition={{ delay: 1.1 + (rowIdx * 7 + dayIdx) * 0.01, duration: 0.3 }}
                      className={cn(
                        "h-5 rounded-sm cursor-default transition-transform hover:scale-110",
                        tokens > 0 ? "bg-emerald-400" : "bg-white/[0.04]"
                      )}
                      style={{ opacity }}
                      title={`${labels[dayIdx]} ${rl}: ${formatTokens(tokens)}`}
                    />
                  );
                })}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 mt-3 text-[10px] text-neutral-500 font-mono shrink-0">
            <span>Less</span>
            {[0.08, 0.2, 0.4, 0.7, 1.0].map((o, i) => (
              <span
                key={i}
                className="w-3 h-3 rounded-sm bg-emerald-400"
                style={{ opacity: o }}
              />
            ))}
            <span>More</span>
            {data?.peak && data.peak.tokens > 0 && (
              <span className="ml-auto text-neutral-400">
                Peak: {data.peak.day} {data.peak.bucket} ({formatTokens(data.peak.tokens)})
              </span>
            )}
          </div>
        </>
      )}
    </motion.div>
  );
}
