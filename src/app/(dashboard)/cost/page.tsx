"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { DollarSign, TrendingUp, BarChart3, PieChart, Wallet, CalendarDays } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { CostByModelCard } from "@/components/dashboard/CostByModelCard";
import { CostTrendCard } from "@/components/dashboard/CostTrendCard";
import { CostBreakdownCard } from "@/components/dashboard/CostBreakdownCard";

const SPRING = { type: "spring" as const, stiffness: 100, damping: 20 };

function StatCard({ title, value, subtitle, icon: Icon, loading }: { title: string; value: string; subtitle?: string; icon: any; loading?: boolean }) {
  return (
    <motion.div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-5 space-y-2" {...{initial:{opacity:0,y:12},animate:{opacity:1,y:0},transition:{type:"spring",stiffness:100,damping:20}}}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">{title}</span>
        <Icon size={16} className="text-zinc-600" strokeWidth={1.5} />
      </div>
      {loading ? (
        <div className="h-8 w-24 shimmer-bg rounded" />
      ) : (
        <>
          <div className="text-2xl font-semibold text-zinc-100 tracking-tight">{value}</div>
          {subtitle && <div className="text-[11px] text-zinc-600">{subtitle}</div>}
        </>
      )}
    </motion.div>
  );
}

export default function CostPage() {
  const { data: globalCost, isLoading: loadingGlobal } = useQuery({
    queryKey: ["cost-global"],
    queryFn: () => api.get<{ total_cost: number; session_count: number; total_input_tokens: number; total_output_tokens: number }>("/api/cost/global"),
    refetchInterval: 60_000,
  });

  const { data: budget } = useQuery({
    queryKey: ["cost-budget"],
    queryFn: () => api.get<{ default_session_budget_usd: number; warning_threshold_pct: number; global_reset_days: number }>("/api/cost/budget"),
  });

  const { data: dailyTrend } = useQuery({
    queryKey: ["cost-daily-trend"],
    queryFn: () => api.get<{ days: { date: string; cost: number }[] }>("/api/cost/daily-trend"),
  });

  const totalCost = globalCost?.total_cost ?? 0;
  const sessionCount = globalCost?.session_count ?? 0;
  const budgetUsd = budget?.default_session_budget_usd ?? 5.0;
  const avgCost = sessionCount > 0 ? totalCost / sessionCount : 0;

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
        <span className="text-xs font-mono text-zinc-600">/cost</span>
      </div>
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
          <DollarSign size={16} className="text-zinc-400" strokeWidth={1.5} />
        </div>
        <div>
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Cost & Usage</h1>
          <p className="text-sm text-zinc-600 mt-1">Track token consumption and spending across all agents</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Spend" value={`$${totalCost.toFixed(2)}`} subtitle="All time" icon={Wallet} loading={loadingGlobal} />
        <StatCard title="Sessions" value={sessionCount.toLocaleString()} subtitle="Total runs" icon={BarChart3} loading={loadingGlobal} />
        <StatCard title="Avg per Session" value={`$${avgCost.toFixed(4)}`} subtitle="Mean cost" icon={TrendingUp} loading={loadingGlobal} />
        <StatCard title="Session Budget" value={`$${budgetUsd.toFixed(2)}`} subtitle="Per-session cap" icon={PieChart} loading={!budget} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <CostTrendCard />
        <CostByModelCard />
      </div>

      <div className="grid grid-cols-1 gap-6">
        <CostBreakdownCard />
      </div>
    </div>
  );
}
