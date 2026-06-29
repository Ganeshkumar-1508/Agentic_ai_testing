"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  LineChart, Line, XAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { TrendingUp, Play, Clock, Layers } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function PipelineMetricsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["pipeline-metrics"],
    queryFn: async () => {
      return api.get<{ metrics: Array<{
        session_id: string; repo_url: string; total_tests: number;
        passed_tests: number; failed_tests: number; pass_rate: number;
        total_tokens: number; total_cost: number; subagent_count: number;
        duration_seconds: number; created_at: string;
      }> }>(`/api/ops/pipeline-metrics?limit=20`);
    },
    refetchInterval: 30_000,
  });

  const metrics = data?.metrics ?? [];
  const total = metrics.length;
  const avgPassRate = total > 0 ? metrics.reduce((s, m) => s + (m.pass_rate || 0), 0) / total : 0;
  const avgDuration = total > 0 ? metrics.reduce((s, m) => s + (m.duration_seconds || 0), 0) / total : 0;
  const totalSubagents = metrics.reduce((s, m) => s + (m.subagent_count || 0), 0);
  const totalRuns = total;

  if (isLoading) {
    return (
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4">
        <div className="w-36 h-4 rounded-full shimmer-bg" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-20 bg-white/[0.02] rounded-xl animate-pulse" />)}
        </div>
      </div>
    );
  }

  if (total === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 80, damping: 18 }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-5"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-zinc-500" strokeWidth={1.5} />
          <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Coordinator Metrics</span>
        </div>
        {total > 0 && <span className="text-[10px] text-zinc-600 font-mono">{total} runs</span>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Avg Pass Rate", value: `${avgPassRate.toFixed(1)}%`, sub: `across ${totalRuns} runs`, icon: TrendingUp, color: "text-emerald-400" },
          { label: "Avg Duration", value: formatDuration(avgDuration), sub: "per run", icon: Clock, color: "text-blue-400" },
          { label: "Total Runs", value: String(totalRuns), sub: "all time", icon: Play, color: "text-amber-400" },
          { label: "Subagents", value: String(totalSubagents), sub: "total spawned", icon: Layers, color: "text-zinc-400" },
        ].map((kpi, i) => {
          const Icon = kpi.icon;
          return (
            <motion.div
              key={kpi.label}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, type: "spring", stiffness: 100, damping: 20 }}
              className="bg-white/[0.01] border border-white/[0.04] rounded-xl p-3.5 space-y-2"
            >
              <div className="flex items-center gap-1.5">
                <Icon className="w-3 h-3" strokeWidth={1.5} />
                <span className="text-[10px] text-zinc-600 font-medium">{kpi.label}</span>
              </div>
              <div className={`text-xl font-semibold tracking-tight tabular-nums ${kpi.color}`}>{kpi.value}</div>
              <div className="text-[10px] text-zinc-700">{kpi.sub}</div>
            </motion.div>
          );
        })}
      </div>

      {metrics.length > 1 && (
        <div className="h-32 min-h-[128px]">
          <ResponsiveContainer width="100%" height={128} debounce={50}>
            <LineChart data={[...metrics].reverse().map(m => ({ ...m, label: (m.created_at || "").slice(5, 10) }))}>
              <XAxis dataKey="label" tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} interval={4} />
              <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 11 }} />
              <Line type="monotone" dataKey="pass_rate" stroke="#34d399" strokeWidth={1.5} dot={false} name="Pass Rate" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </motion.div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}
