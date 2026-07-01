"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  CheckCircle2, XCircle, AlertTriangle, BarChart3,
  TrendingUp, Target, DollarSign, Activity, Cpu, Shield,
  GitBranch, Clock, Wrench, ArrowUp, ArrowDown,
} from "lucide-react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

interface OverviewMetrics {
  outcome: { success_rate: number; total: number; completed: number; failed: number; cancelled: number; running: number };
  cost: { total_spend: number; cost_per_completed: number; avg_cost_per_session: number; by_model: { model: string; cost: number; calls: number }[] };
  safety: { error_count: number; blocked_action_count: number };
  behavior: { avg_tool_calls_per_session: number; total_tool_calls: number; sessions_trend: { day: string; count: number; cost: number }[] };
}

interface AgentBreakdown {
  role: string; total: number; completed: number; failed: number;
  tokens: number; cost: number; success_rate: number; cost_per_task: number;
}

function StatCard({ title, value, subtitle, icon: Icon, color, trend, loading }: {
  title: string; value: string; subtitle?: string; icon: React.ElementType; color: string;
  trend?: { dir: "up" | "down"; label: string }; loading?: boolean;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 120, damping: 20 }}
      className="rounded-2xl border border-zinc-800/40 bg-gradient-to-b from-zinc-900/60 to-zinc-950/40 p-5 space-y-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-[0.1em]">{title}</span>
        <Icon size={15} className={color} strokeWidth={1.5} />
      </div>
      {loading ? (
        <div className="h-8 w-28 rounded-lg shimmer-bg" />
      ) : (
        <>
          <div className="text-2xl font-semibold text-zinc-100 tracking-tight font-mono">{value}</div>
          <div className="flex items-center gap-2 text-[11px]">
            {subtitle && <span className="text-zinc-600">{subtitle}</span>}
            {trend && (
              <span className={cn("inline-flex items-center gap-0.5 font-mono",
                trend.dir === "up" ? "text-emerald-400" : "text-red-400")}>
                {trend.dir === "up" ? <ArrowUp size={10} strokeWidth={2} /> : <ArrowDown size={10} strokeWidth={2} />}
                {trend.label}
              </span>
            )}
          </div>
        </>
      )}
    </motion.div>
  );
}

function BarChart({ data, height = 40, color = "bg-emerald-400" }: {
  data: { value: number; label?: string }[]; height?: number; color?: string;
}) {
  const max = Math.max(...data.map(d => d.value), 1);
  return (
    <div className="flex items-end gap-[2px]" style={{ height }}>
      {data.map((d, i) => (
        <div key={i} className="flex-1 min-w-[2px] flex flex-col items-center gap-1 group relative">
          <motion.div
            initial={{ height: 0 }} animate={{ height: `${(d.value / max) * 100}%` }}
            transition={{ delay: i * 0.02, duration: 0.3 }}
            className={cn("w-full rounded-sm transition-all", color)}
          />
          {d.label && (
            <span className="text-[7px] text-zinc-700 font-mono absolute -bottom-4 left-1/2 -translate-x-1/2 whitespace-nowrap">
              {d.label}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

const containerVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.04 } },
};

export default function EvaluatePage() {
  const { data: overview, isLoading } = useQuery<OverviewMetrics>({
    queryKey: ["evaluate-overview"],
    queryFn: () => api.get<OverviewMetrics>("/api/evaluate/overview"),
    refetchInterval: 60_000,
  });

  const { data: agents } = useQuery<{ agents: AgentBreakdown[] }>({
    queryKey: ["evaluate-agents"],
    queryFn: () => api.get<{ agents: AgentBreakdown[] }>("/api/evaluate/agents"),
    refetchInterval: 60_000,
  });

  const o = overview?.outcome;
  const c = overview?.cost;
  const s = overview?.safety;
  const b = overview?.behavior;
  const agentList = agents?.agents ?? [];

  const sections = [
    { key: "outcome", label: "Outcome", icon: Target, items: [
      { title: "Success Rate", value: o ? `${o.success_rate}%` : "—", subtitle: o ? `${o.completed} of ${o.total} sessions` : "", icon: CheckCircle2, color: "text-emerald-400", trend: o ? { dir: o.success_rate >= 80 ? "up" as const : "down" as const, label: `${o.failed} failed` } : undefined },
      { title: "Total Sessions", value: o?.total.toLocaleString() ?? "—", subtitle: `${o?.running ?? 0} running`, icon: BarChart3, color: "text-indigo-400" },
      { title: "Completed", value: o?.completed.toLocaleString() ?? "—", subtitle: `${((o?.completed ?? 0) / (o?.total ?? 1) * 100).toFixed(0)}% of total`, icon: CheckCircle2, color: "text-emerald-400" },
      { title: "Failed", value: o?.failed.toLocaleString() ?? "—", subtitle: `${((o?.failed ?? 0) / (o?.total ?? 1) * 100).toFixed(1)}% failure rate`, icon: XCircle, color: "text-red-400" },
    ]},
    { key: "cost", label: "Cost", icon: DollarSign, items: [
      { title: "Total Spend", value: c ? `$${c.total_spend.toFixed(2)}` : "—", subtitle: "Last 30 days", icon: DollarSign, color: "text-amber-400" },
      { title: "Cost per Task", value: c ? `$${c.cost_per_completed.toFixed(4)}` : "—", subtitle: "Per completed session", icon: TrendingUp, color: "text-emerald-400" },
      { title: "Avg per Session", value: c ? `$${c.avg_cost_per_session.toFixed(4)}` : "—", subtitle: "Across all sessions", icon: Activity, color: "text-indigo-400" },
      { title: "Top Model", value: c?.by_model?.[0]?.model?.replace(/^[^/]+\//, "") ?? "—", subtitle: c?.by_model?.[0] ? `$${c.by_model[0].cost.toFixed(2)}` : "", icon: Cpu, color: "text-zinc-400" },
    ]},
    { key: "safety", label: "Safety", icon: Shield, items: [
      { title: "Errors", value: s?.error_count.toLocaleString() ?? "—", subtitle: "error events", icon: AlertTriangle, color: "text-red-400" },
      { title: "Blocked Actions", value: s?.blocked_action_count.toLocaleString() ?? "—", subtitle: "guardrails triggered", icon: Shield, color: "text-amber-400" },
      { title: "Error Rate", value: o ? `${((s?.error_count ?? 0) / Math.max(o.total, 1) * 100).toFixed(1)}%` : "—", subtitle: "per session", icon: AlertTriangle, color: "text-red-400" },
      { title: "Block Rate", value: o ? `${((s?.blocked_action_count ?? 0) / Math.max(o.total, 1) * 100).toFixed(1)}%` : "—", subtitle: "per session", icon: Shield, color: "text-amber-400" },
    ]},
    { key: "behavior", label: "Behavior", icon: Activity, items: [
      { title: "Tool Calls", value: b?.total_tool_calls.toLocaleString() ?? "—", subtitle: "total", icon: Wrench, color: "text-emerald-400" },
      { title: "Avg Tools/Session", value: b?.avg_tool_calls_per_session.toFixed(1) ?? "—", subtitle: "average", icon: GitBranch, color: "text-indigo-400" },
      { title: "14d Trend", value: `${b?.sessions_trend?.length ?? 0} days`, subtitle: "daily session count", icon: Clock, color: "text-zinc-400" },
      { title: "Peak Day", value: (() => { const t = b?.sessions_trend; if (!t?.length) return "—"; const p = t.reduce((a, b) => a.count > b.count ? a : b); return `${p.count}` })() ?? "—", subtitle: "sessions", icon: TrendingUp, color: "text-emerald-400" },
    ]},
  ];

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400/70" />
        <span className="text-xs font-mono text-zinc-600">/evaluate</span>
      </div>
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
          <Target size={16} className="text-zinc-400" strokeWidth={1.5} />
        </div>
        <div>
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Agent Evaluation</h1>
          <p className="text-sm text-zinc-600 mt-1">Arize-style four-pillar metrics: outcome, cost, safety, behavior</p>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-28 rounded-2xl border border-zinc-800/40 bg-zinc-900/30 shimmer" />
          ))}
        </div>
      ) : (
        <motion.div variants={containerVariants} initial="hidden" animate="show" className="space-y-8">
          {/* Four pillar sections */}
          {sections.map((section) => (
            <motion.div key={section.key} variants={containerVariants} className="space-y-3">
              <div className="flex items-center gap-2 text-[11px] font-medium text-zinc-500 uppercase tracking-[0.1em]">
                <section.icon size={14} className="text-zinc-600" strokeWidth={1.5} />
                {section.label}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {section.items.map((item) => (
                  <StatCard key={item.title} {...item} loading={isLoading} />
                ))}
              </div>
            </motion.div>
          ))}

          {/* Session trend mini chart */}
          {b?.sessions_trend && b.sessions_trend.length > 1 && (
            <motion.div variants={containerVariants}
              className="rounded-2xl border border-zinc-800/40 bg-gradient-to-b from-zinc-900/60 to-zinc-950/40 p-5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-[0.1em]">Session Trend (14d)</span>
                <div className="flex items-center gap-3 text-[10px] font-mono text-zinc-600">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-400" /> count</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-amber-400" /> cost</span>
                </div>
              </div>
              <div className="flex items-end gap-[2px] h-12">
                {b.sessions_trend.map((d, i) => {
                  const allCounts = b.sessions_trend.map(x => x.count);
                  const maxCount = Math.max(...allCounts, 1);
                  const allCosts = b.sessions_trend.map(x => x.cost);
                  const maxCost = Math.max(...allCosts, 0.01);
                  return (
                    <div key={d.day} className="flex-1 min-w-[3px] flex flex-col items-center gap-px relative group">
                      <motion.div
                        initial={{ height: 0 }} animate={{ height: `${(d.cost / maxCost) * 100}%` }}
                        transition={{ delay: i * 0.02 }}
                        className="w-full bg-amber-500/20 rounded-sm"
                      />
                      <motion.div
                        initial={{ height: 0 }} animate={{ height: `${(d.count / maxCount) * 100}%` }}
                        transition={{ delay: i * 0.02 }}
                        className="w-full bg-emerald-500/30 rounded-sm"
                      />
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* Cost by model */}
          {c?.by_model && c.by_model.length > 0 && (
            <motion.div variants={containerVariants}
              className="rounded-2xl border border-zinc-800/40 bg-gradient-to-b from-zinc-900/60 to-zinc-950/40 p-5 space-y-3">
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-[0.1em]">Cost by Model</span>
              <div className="space-y-2">
                {c.by_model.slice(0, 6).map((m, i) => {
                  const pct = c.total_spend > 0 ? (m.cost / c.total_spend) * 100 : 0;
                  return (
                    <div key={m.model} className="flex items-center gap-3">
                      <span className="text-[11px] text-zinc-400 font-mono min-w-[120px] truncate">{m.model.replace(/^[^/]+\//, "")}</span>
                      <div className="flex-1 h-2 rounded-full bg-zinc-800/50 overflow-hidden">
                        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }}
                          transition={{ delay: 0.3 + i * 0.05, duration: 0.5 }}
                          className="h-full rounded-full bg-emerald-400/60" />
                      </div>
                      <span className="text-[10px] text-zinc-500 font-mono w-16 text-right">${m.cost.toFixed(2)}</span>
                      <span className="text-[9px] text-zinc-700 font-mono w-12 text-right">{m.calls} calls</span>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* Per-agent breakdown */}
          {agentList.length > 0 && (
            <motion.div variants={containerVariants}
              className="rounded-2xl border border-zinc-800/40 bg-gradient-to-b from-zinc-900/60 to-zinc-950/40 p-5 space-y-3">
              <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-[0.1em]">Per-Agent Breakdown</span>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b border-zinc-800/30 text-zinc-600 font-mono">
                      <th className="text-left py-2 pr-4">Role</th>
                      <th className="text-right py-2 pr-4">Sessions</th>
                      <th className="text-right py-2 pr-4">Success</th>
                      <th className="text-right py-2 pr-4">Tokens</th>
                      <th className="text-right py-2 pr-4">Cost</th>
                      <th className="text-right py-2 pr-4">Cost/Task</th>
                      <th className="text-right py-2">Success Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentList.map((a) => (
                      <tr key={a.role} className="border-b border-zinc-800/15 hover:bg-zinc-800/10 transition-colors">
                        <td className="py-2 pr-4 text-zinc-300 font-mono">{a.role}</td>
                        <td className="py-2 pr-4 text-right text-zinc-400 font-mono">{a.total}</td>
                        <td className="py-2 pr-4 text-right text-zinc-400 font-mono">{a.completed}</td>
                        <td className="py-2 pr-4 text-right text-zinc-500 font-mono">{a.tokens.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-right text-zinc-500 font-mono">${a.cost.toFixed(4)}</td>
                        <td className="py-2 pr-4 text-right text-zinc-500 font-mono">${a.cost_per_task.toFixed(4)}</td>
                        <td className="py-2 text-right">
                          <span className={cn("font-mono",
                            a.success_rate >= 80 ? "text-emerald-400" : a.success_rate >= 50 ? "text-amber-400" : "text-red-400")}>
                            {a.success_rate}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          {!o?.total && (
            <div className="flex flex-col items-center py-16 text-zinc-600 gap-3">
              <BarChart3 size={24} strokeWidth={1} className="text-zinc-700" />
              <p className="text-sm">No evaluation data yet</p>
              <p className="text-xs text-zinc-700">Run some agents to see evaluation metrics here</p>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
