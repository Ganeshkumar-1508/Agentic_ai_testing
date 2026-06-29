"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, Bot, Shield, DollarSign, CheckCircle2, Timer } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

type PipelineStats = {
  active_sessions: number;
  recent_24h: { total: number; passed: number; failed: number; pass_rate: number };
};

type SwarmSummary = {
  sessions_total: number;
  total_tool_calls: number;
};

type Governance = {
  pending_approvals: number;
  high_risk_flaky: number;
};

type CostTrend = {
  days: Array<{ day: string; cost: number; total_tokens: number }>;
};

function useOpsQueries() {
  const pipeline = useQuery<PipelineStats>({
    queryKey: ["aiops-pipeline-stats"],
    queryFn: () => api.get<PipelineStats>("/api/pipeline-activity/stats"),
    refetchInterval: 15_000,
  });
  const swarm = useQuery<SwarmSummary>({
    queryKey: ["aiops-swarm-summary"],
    queryFn: () => api.get<SwarmSummary>("/api/ops/swarm/summary"),
    refetchInterval: 30_000,
  });
  const governance = useQuery<Governance>({
    queryKey: ["aiops-governance"],
    queryFn: () => api.get<Governance>("/api/ops/governance/config"),
    refetchInterval: 60_000,
  });
  const costTrend = useQuery<CostTrend>({
    queryKey: ["aiops-cost-trend"],
    queryFn: () => api.get<CostTrend>("/api/cost/daily-trend", { days: "7" }),
    refetchInterval: 60_000,
  });
  return { pipeline, swarm, governance, costTrend };
}

function KpiShell({
  index, label, sub, icon, accent = "emerald", children,
}: {
  index: number;
  label: string;
  sub?: string;
  icon?: React.ReactNode;
  accent?: "emerald" | "sky" | "amber" | "neutral";
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      whileHover={{ scale: 1.02, transition: { type: "spring", stiffness: 100, damping: 20 } }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6 cursor-default card-glow h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
          {label}
        </span>
        {icon && (
          <span
            className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center",
              accent === "emerald" && "bg-emerald-500/10 text-emerald-400",
              accent === "sky" && "bg-zinc-500/10 text-zinc-400",
              accent === "amber" && "bg-amber-500/10 text-amber-400",
              accent === "neutral" && "bg-white/[0.04] text-neutral-400",
            )}
          >
            {icon}
          </span>
        )}
      </div>
      {children}
      {sub && <div className="text-[10.5px] text-neutral-500 mt-1.5 font-mono">{sub}</div>}
    </motion.div>
  );
}

export default function AiOpsOverviewPage() {
  const { pipeline, swarm, governance, costTrend } = useOpsQueries();

  const recent = pipeline.data?.recent_24h ?? { total: 0, passed: 0, failed: 0, pass_rate: 0 };
  const active = pipeline.data?.active_sessions ?? 0;
  const passRate = Number(recent.pass_rate || 0);
  const approvals = governance.data?.pending_approvals ?? 0;
  const totalCost7d = (costTrend.data?.days ?? []).reduce((s, d) => s + Number(d.cost || 0), 0);
  const toolCalls = swarm.data?.total_tool_calls ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr] gap-4">
        <KpiShell
          index={0}
          label="Pipeline Health"
          sub={`${recent.total} runs · 24h`}
          icon={<Activity className="w-3.5 h-3.5" strokeWidth={1.5} />}
          accent="emerald"
        >
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-medium text-zinc-100 tracking-tighter tabular-nums leading-none">
              {recent.passed}
              <span className="text-zinc-600 text-xl"> / {recent.total}</span>
            </span>
            <span className="text-[10.5px] font-mono text-neutral-500 ml-auto">
              passed
            </span>
          </div>
          <div className="mt-3 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, passRate)}%` }}
              transition={{ delay: 0.35, duration: 0.7, ease: [0.16, 1, 0.3, 1] as const }}
              className="h-full rounded-full bg-emerald-500"
            />
          </div>
          <div className="flex items-center justify-between mt-2.5 text-[10.5px] font-mono">
            <span className="text-neutral-500">{passRate.toFixed(1)}% pass rate</span>
            <span className="flex items-center gap-2">
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle2 className="w-3 h-3" strokeWidth={1.5} />
                {recent.passed}
              </span>
              <span className="text-rose-400/80">{recent.failed}</span>
              <span className="flex items-center gap-1 text-zinc-400">
                <Timer className="w-3 h-3" strokeWidth={1.5} />
                {active}
              </span>
            </span>
          </div>
        </KpiShell>

        <KpiShell
          index={1}
          label="Active Subagents"
          sub={`${toolCalls.toLocaleString()} tool calls`}
          icon={<Bot className="w-3.5 h-3.5" strokeWidth={1.5} />}
          accent="sky"
        >
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-medium text-zinc-100 tracking-tighter tabular-nums leading-none">
              {active}
            </span>
            <span className="text-[10.5px] font-mono text-neutral-500 ml-auto">
              live
            </span>
          </div>
          <div className="mt-3 flex items-center gap-1">
            {Array.from({ length: 12 }).map((_, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, scaleY: 0.4 }}
                animate={{ opacity: 1, scaleY: 1 }}
                transition={{ delay: 0.2 + i * 0.02, duration: 0.4 }}
                className={cn(
                  "h-6 flex-1 rounded-sm origin-bottom",
                  i < active ? "bg-zinc-400/70" : "bg-white/[0.04]",
                )}
              />
            ))}
          </div>
        </KpiShell>

        <KpiShell
          index={2}
          label="Approvals"
          sub="awaiting human review"
          icon={<Shield className="w-3.5 h-3.5" strokeWidth={1.5} />}
          accent={approvals > 0 ? "amber" : "neutral"}
        >
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-medium text-zinc-100 tracking-tighter tabular-nums leading-none">
              {approvals}
            </span>
            <span className="text-[10.5px] font-mono text-neutral-500 ml-auto">
              pending
            </span>
          </div>
          <div className="mt-3 text-[10.5px] font-mono">
            <a
              href="/sessions"
              className="inline-flex items-center gap-1 text-neutral-500 hover:text-emerald-400 transition-colors"
            >
              {approvals > 0 ? "Open review queue" : "Queue empty"}
              <span aria-hidden>→</span>
            </a>
          </div>
        </KpiShell>

        <KpiShell
          index={3}
          label="Cost · 7d"
          sub="model spend"
          icon={<DollarSign className="w-3.5 h-3.5" strokeWidth={1.5} />}
          accent="neutral"
        >
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-medium text-zinc-100 tracking-tighter tabular-nums leading-none">
              ${totalCost7d.toFixed(3)}
            </span>
            <span className="text-[10.5px] font-mono text-neutral-500 ml-auto">
              USD
            </span>
          </div>
          <div className="mt-3 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, (totalCost7d / 1) * 100)}%` }}
              transition={{ delay: 0.35, duration: 0.7, ease: [0.16, 1, 0.3, 1] as const }}
              className="h-full rounded-full bg-emerald-400/70"
            />
          </div>
        </KpiShell>
      </div>
    </div>
  );
}
