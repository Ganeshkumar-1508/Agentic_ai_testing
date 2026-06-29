"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { BarChart3, TrendingUp, DollarSign, Cpu, Activity, MousePointerClick } from "lucide-react";

interface DailyUsage {
  day: string; input_tokens: number; output_tokens: number; estimated_cost: number; sessions: number;
}

interface ModelBreakdown {
  model: string; input_tokens: number; output_tokens: number; estimated_cost: number; api_calls: number;
}

function containerVariants(delay: number) {
  return {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const, delay } },
  };
}

function MetricCard({ label, value, sub, icon, color }: { label: string; value: string; sub: string; icon: React.ReactNode; color: string }) {
  return (
    <motion.div variants={containerVariants(0.1)} initial="hidden" animate="show"
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px]">{label}</span>
        <span className={cn("w-7 h-7 rounded-lg flex items-center justify-center", color)}>{icon}</span>
      </div>
      <span className="text-2xl font-semibold font-mono tracking-tight text-zinc-100">{value}</span>
      <span className="text-[11px] text-zinc-600">{sub}</span>
    </motion.div>
  );
}

function DailyUsageChart({ data }: { data: DailyUsage[] }) {
  const maxCost = Math.max(0.01, ...data.map(d => d.estimated_cost));
  return (
    <motion.div variants={containerVariants(0.2)} initial="hidden" animate="show"
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5">
      <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px] mb-4">Daily Cost (30d)</div>
      <div className="flex items-end gap-[2px] h-20">
        {data.map((d, i) => (
          <motion.div key={d.day} initial={{ height: 0 }} animate={{ height: `${Math.max((d.estimated_cost / maxCost) * 100, 3)}%` }}
            transition={{ delay: 0.3 + i * 0.008, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="flex-1 min-w-[2px] rounded-sm bg-emerald-500/30 hover:bg-emerald-400/50 transition-colors cursor-pointer"
            title={`${d.day}: $${d.estimated_cost.toFixed(4)}`} />
        ))}
      </div>
      <div className="flex justify-between mt-2 text-[10px] font-mono text-zinc-700">
        <span>{data[0]?.day?.slice(5) ?? "—"}</span>
        <span>{data[data.length - 1]?.day?.slice(5) ?? "—"}</span>
      </div>
    </motion.div>
  );
}

function ModelBreakdownTable({ data }: { data: ModelBreakdown[] }) {
  return (
    <motion.div variants={containerVariants(0.3)} initial="hidden" animate="show"
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5">
      <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px] mb-3">Per-Model Breakdown</div>
      <div className="space-y-1.5">
        {data.slice(0, 8).map((m, i) => {
          const pct = data.length > 0 ? (m.estimated_cost / data[0].estimated_cost) * 100 : 0;
          return (
            <div key={m.model} className="flex items-center gap-3">
              <span className="w-24 text-[11px] font-mono text-zinc-400 truncate">{m.model.split("/").pop()}</span>
              <div className="flex-1 h-5 rounded-md bg-white/[0.04] overflow-hidden">
                <motion.div initial={{ width: 0 }} animate={{ width: `${Math.max(pct, 2)}%` }}
                  transition={{ delay: 0.4 + i * 0.04, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  className="h-full rounded-md bg-emerald-500/30" />
              </div>
              <span className="w-16 text-right text-[10px] font-mono text-zinc-500">{((m.input_tokens + m.output_tokens) / 1000).toFixed(0)}k tok</span>
              <span className="w-12 text-right text-[10px] font-mono text-zinc-600">{m.api_calls} calls</span>
              <span className="w-20 text-right text-[11px] font-mono text-zinc-300">${m.estimated_cost.toFixed(2)}</span>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

export default function AnalyticsPage() {
  const { data: usageRaw, isLoading: ul } = useQuery<{ daily: DailyUsage[]; totals: Record<string, number> }>({
    queryKey: ["analytics-usage"], queryFn: () => api.get("/api/analytics/usage?days=30"),
  });
  const { data: modelsRaw, isLoading: ml } = useQuery<{ models: ModelBreakdown[]; period_days: number }>({
    queryKey: ["analytics-models"], queryFn: () => api.get("/api/analytics/models?days=30"),
  });

  const daily = usageRaw?.daily ?? [];
  const totals = usageRaw?.totals ?? {};
  const models = modelsRaw?.models ?? [];
  const isLoading = ul || ml;

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-8 pt-6 pb-12">
        <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">Analytics</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[...Array(4)].map((_, i) => <div key={i} className="h-28 rounded-[1.5rem] shimmer-bg" />)}
        </div>
        <div className="h-48 rounded-[1.5rem] shimmer-bg" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-8 pt-6 pb-12">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">Analytics</div>
        <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Usage Overview</h1>
        <p className="text-[13px] text-zinc-500 mt-0.5">Token consumption, cost trends, and model breakdown for the last 30 days</p>
      </motion.div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricCard label="Total Cost" value={`$${(totals.total_estimated_cost ?? 0).toFixed(2)}`} sub="Last 30 days" icon={<DollarSign className="w-3.5 h-3.5" strokeWidth={1.5} />} color="bg-emerald-500/15 text-emerald-400" />
        <MetricCard label="Input Tokens" value={((totals.total_input ?? 0) / 1_000_000).toFixed(1) + "M"} sub="Total prompt tokens" icon={<TrendingUp className="w-3.5 h-3.5" strokeWidth={1.5} />} color="bg-blue-500/15 text-blue-400" />
        <MetricCard label="Output Tokens" value={((totals.total_output ?? 0) / 1_000_000).toFixed(1) + "M"} sub="Total completion tokens" icon={<Activity className="w-3.5 h-3.5" strokeWidth={1.5} />} color="bg-zinc-500/15 text-zinc-400" />
        <MetricCard label="Sessions" value={String(totals.total_sessions ?? 0)} sub="Agent runs" icon={<MousePointerClick className="w-3.5 h-3.5" strokeWidth={1.5} />} color="bg-amber-500/15 text-amber-400" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-4 mb-6">
        <DailyUsageChart data={daily} />
        <ModelBreakdownTable data={models} />
      </div>

      {daily.length > 0 && (
        <motion.div variants={containerVariants(0.4)} initial="hidden" animate="show"
          className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px] mb-3">Daily Breakdown</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-zinc-600 border-b border-white/[0.06]">
                  <th className="text-left py-2 font-medium">Date</th>
                  <th className="text-right py-2 font-medium">Input Tokens</th>
                  <th className="text-right py-2 font-medium">Output Tokens</th>
                  <th className="text-right py-2 font-medium">Cost</th>
                  <th className="text-right py-2 font-medium">Sessions</th>
                </tr>
              </thead>
              <tbody>
                {daily.slice(-20).reverse().map((d) => (
                  <tr key={d.day} className="border-b border-white/[0.03] text-zinc-400 hover:text-zinc-200 transition-colors">
                    <td className="py-2 text-zinc-500">{d.day}</td>
                    <td className="py-2 text-right font-mono">{(d.input_tokens / 1000).toFixed(0)}k</td>
                    <td className="py-2 text-right font-mono">{(d.output_tokens / 1000).toFixed(0)}k</td>
                    <td className="py-2 text-right font-mono text-emerald-400">${d.estimated_cost.toFixed(4)}</td>
                    <td className="py-2 text-right font-mono">{d.sessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}

      {daily.length === 0 && (
        <motion.div variants={containerVariants(0.4)} initial="hidden" animate="show"
          className="text-center py-20 border border-dashed border-white/[0.06] rounded-[1.5rem]">
          <BarChart3 className="w-10 h-10 text-zinc-700 mx-auto mb-3" strokeWidth={1} />
          <p className="text-sm text-zinc-600">No usage data yet. Run the pipeline to see analytics.</p>
        </motion.div>
      )}
    </div>
  );
}
