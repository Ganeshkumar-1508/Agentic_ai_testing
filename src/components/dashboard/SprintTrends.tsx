"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface Sprint {
  sprint: string;
  start_date: string;
  end_date: string;
  pass_rate: number;
  total_tests: number;
  failed_tests: number;
  coverage: number | null;
  flaky_rate: number;
  quality_score: number;
  total_runs: number;
  defect_count: number;
}

interface SprintAlert {
  from_sprint: string;
  to_sprint: string;
  regressions: string[];
}

export interface SprintTrendsData {
  sprints: Sprint[];
  alerts: SprintAlert[];
  alert_count: number;
}

interface SprintTrendsProps {
  data?: SprintTrendsData;
  loading?: boolean;
}

function tone(value: number, goodDirection: "up" | "down"): "good" | "bad" | "neutral" {
  if (value === 0) return "neutral";
  return goodDirection === "up" ? "good" : "bad";
}

function fmt(n: number | null | undefined, suffix = ""): string {
  if (n == null) return "—";
  return `${n}${suffix}`;
}

function trendMeta(sprints: Sprint[]): {
  total: Sprint | null;
  hasRegression: boolean;
  totalDelta: number;
} {
  if (sprints.length < 2) return { total: sprints[0] ?? null, hasRegression: false, totalDelta: 0 };
  const first = sprints[0].quality_score;
  const last = sprints[sprints.length - 1].quality_score;
  return {
    total: sprints[sprints.length - 1],
    hasRegression: last < first,
    totalDelta: +(last - first).toFixed(1),
  };
}

export function SprintTrends({ data, loading }: SprintTrendsProps) {
  if (loading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="w-32 h-4 rounded shimmer-bg" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-8 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  const sprints = data?.sprints ?? [];
  const meta = trendMeta(sprints);
  const maxScore = Math.max(100, ...sprints.map((s) => s.quality_score || 0));

  if (sprints.length === 0) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="card-label">Sprint Trends</div>
        <div className="text-sm text-neutral-500 text-center py-6">No sprint data yet.</div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Sprint Trends</div>
        <span className="text-[10px] font-mono text-zinc-600">
          {sprints.length} sprints
        </span>
      </div>

      <div className="overflow-x-auto flex-1 min-h-0">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr>
              {["Sprint", "Pass Rate", "Tests", "Failed", "Coverage", "Flaky", "Quality", "Trend"].map((h, i) => (
                <th
                  key={h}
                  className={cn(
                    "text-[9px] font-semibold uppercase tracking-[0.1em] text-zinc-600 pb-2 border-b border-white/[0.06]",
                    i === 0 ? "text-left" : "text-right",
                    i === 0 ? "w-[80px]" : i === 7 ? "w-[100px]" : ""
                  )}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sprints.map((s, i) => {
              const isRegressing = i > 0 && s.quality_score < sprints[i - 1].quality_score - 5;
              const isLast = i === sprints.length - 1;
              const arrowUp = i === 0 || s.quality_score >= sprints[i - 1].quality_score;
              return (
                <motion.tr
                  key={s.sprint}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.05 + i * 0.04 }}
                  className={cn(
                    "transition-colors hover:bg-white/[0.02]",
                    isRegressing && "bg-red-500/[0.03]"
                  )}
                >
                  <td className="py-2.5 text-left font-mono font-semibold text-[10.5px]">
                    <span className={cn(
                      isRegressing ? "text-red-400" : isLast ? "text-emerald-400" : "text-zinc-400"
                    )}>
                      {s.sprint}
                    </span>
                    {isRegressing && (
                      <span className="ml-1.5 text-[8px] font-bold px-1.5 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/20">
                        REG
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-right font-mono text-zinc-300">
                    {fmt(s.pass_rate, "%")}
                  </td>
                  <td className="py-2.5 text-right font-mono text-zinc-400">
                    {fmt(s.total_tests)}
                  </td>
                  <td className={cn(
                    "py-2.5 text-right font-mono",
                    s.failed_tests > 0 ? "text-red-400" : "text-zinc-500"
                  )}>
                    {fmt(s.failed_tests)}
                  </td>
                  <td className="py-2.5 text-right font-mono text-zinc-400">
                    {s.coverage != null ? `${s.coverage.toFixed(1)}%` : "—"}
                  </td>
                  <td className="py-2.5 text-right font-mono text-zinc-400">
                    {fmt(s.flaky_rate, "%")}
                  </td>
                  <td className={cn(
                    "py-2.5 text-right font-mono font-semibold",
                    s.quality_score >= 80 ? "text-emerald-400"
                      : s.quality_score >= 60 ? "text-amber-400"
                      : s.quality_score > 0 ? "text-red-400"
                      : "text-zinc-500"
                  )}>
                    {fmt(s.quality_score)}
                  </td>
                  <td className="py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <div className="flex-1 h-1 rounded-full bg-white/[0.04] overflow-hidden max-w-[60px]">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all",
                            s.quality_score >= 80 ? "bg-emerald-400"
                              : s.quality_score >= 60 ? "bg-amber-400"
                              : s.quality_score > 0 ? "bg-red-400"
                              : "bg-zinc-700"
                          )}
                          style={{ width: `${Math.min(100, (s.quality_score / maxScore) * 100)}%` }}
                        />
                      </div>
                      {i > 0 && (
                        arrowUp ? (
                          <TrendingUp className="w-2.5 h-2.5 text-emerald-400 shrink-0" strokeWidth={3} />
                        ) : (
                          <TrendingDown className="w-2.5 h-2.5 text-red-400 shrink-0" strokeWidth={3} />
                        )
                      )}
                    </div>
                  </td>
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-4 mt-3 pt-3 border-t border-white/[0.06] text-[9px] font-mono text-zinc-600">
        <span className="flex items-center gap-1">
          <TrendingUp className="w-2.5 h-2.5 text-emerald-400" strokeWidth={3} />
          Improving
        </span>
        <span className="flex items-center gap-1">
          <TrendingDown className="w-2.5 h-2.5 text-red-400" strokeWidth={3} />
          Regressing
        </span>
        <span className="ml-auto text-emerald-400">
          {meta.totalDelta >= 0 ? "+" : ""}
          {meta.totalDelta.toFixed(1)} pts over {sprints.length} sprints
        </span>
      </div>
    </motion.div>
  );
}
