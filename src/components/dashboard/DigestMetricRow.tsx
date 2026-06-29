"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { CheckCircle2, AlertOctagon, GitPullRequest, Activity, Timer } from "lucide-react";
import { cn } from "@/lib/utils";

interface Session {
  session_id: string;
  status: string;
}

interface DigestMetricRowProps {
  overview: any;
  loading: boolean;
  sessions: Session[];
}

const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 110, damping: 22 } },
};

function PassRateBlock({
  passRate,
  failed,
  total,
  sessions,
}: {
  passRate: number;
  failed: number;
  total: number;
  sessions: Session[];
}) {
  const sparkData = useMemo(() => {
    const buckets = 14;
    const order = Array.isArray(sessions) ? sessions.slice(0, 70) : [];
    if (order.length === 0) {
      return Array.from({ length: buckets }, (_, i) => ({ i, v: 0 }));
    }
    const size = Math.max(1, Math.ceil(order.length / buckets));
    return Array.from({ length: buckets }, (_, i) => {
      const slice = order.slice(i * size, (i + 1) * size);
      if (slice.length === 0) return { i, v: 0 };
      const passed = slice.filter((s) => s.status === "ok" || s.status === "completed").length;
      return { i, v: Math.round((passed / slice.length) * 100) };
    });
  }, [sessions]);

  return (
    <div className="relative p-5 lg:p-6 rounded-[2rem] overflow-hidden card-wireframe flex flex-col h-full min-h-[140px]">
      <div className="flex items-start justify-between shrink-0">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600">Pass rate · 24h</div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="text-4xl lg:text-5xl font-semibold tracking-tighter text-zinc-50 font-mono leading-none">
              {passRate.toFixed(1)}
              <span className="text-xl lg:text-2xl text-zinc-500 ml-0.5">%</span>
            </span>
          </div>
        </div>
        <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/15 flex items-center justify-center text-emerald-400 shrink-0">
          <CheckCircle2 className="w-4 h-4" strokeWidth={1.5} />
        </div>
      </div>

      <div className="flex-1 min-h-0 -mx-2 mt-3 opacity-70">
        <ResponsiveContainer width="100%" height="100%" debounce={50}>
          <AreaChart data={sparkData}>
            <defs>
              <linearGradient id="passGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area type="monotone" dataKey="v" stroke="#34d399" strokeWidth={1.5} fill="url(#passGrad)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-2 gap-3 pt-3 mt-1 border-t border-white/[0.05] shrink-0">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-700">Tests run</div>
          <div className="text-sm font-mono text-zinc-200 mt-0.5">{total.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-700">Failures</div>
          <div className={cn("text-sm font-mono mt-0.5", failed > 0 ? "text-amber-400" : "text-zinc-500")}>
            {failed.toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniMetric({
  label,
  value,
  sub,
  icon: Icon,
  tone = "neutral",
  loading,
  index = 0,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  tone?: "neutral" | "warn" | "good";
  loading?: boolean;
  index?: number;
}) {
  return (
    <motion.div
      variants={item}
      className="p-5 lg:p-6 rounded-[2rem] card-wireframe flex flex-col justify-between min-h-[120px]"
    >
      {loading ? (
        <div className="space-y-2.5">
          <div className="h-3 w-20 rounded-full shimmer-bg" />
          <div className="h-7 w-16 rounded-lg shimmer-bg" />
          <div className="h-2.5 w-24 rounded-full shimmer-bg" />
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-[0.15em] text-zinc-600">{label}</span>
            <Icon
              className={cn(
                "w-3.5 h-3.5",
                tone === "warn" && "text-amber-400",
                tone === "good" && "text-emerald-400",
                tone === "neutral" && "text-zinc-600"
              )}
              strokeWidth={1.5}
            />
          </div>
          <div>
            <div className="text-3xl font-semibold tracking-tight text-zinc-100 font-mono leading-none">
              {value}
            </div>
            {sub && <div className="text-[11px] text-zinc-600 mt-1.5 font-mono">{sub}</div>}
          </div>
        </>
      )}
    </motion.div>
  );
}

export function DigestMetricRow({ overview, loading, sessions }: DigestMetricRowProps) {
  const tests = overview?.tests_24h ?? { total: 0, passed: 0, failed: 0 };
  const passRate = overview?.pass_rate_24h ?? 0;
  const failed = tests.failed;
  const total = tests.total;
  const pipelineRuns = overview?.pipeline_runs_24h ?? 0;
  const repoCount = useMemo(
    () => new Set(sessions.map((s: any) => s.source).filter(Boolean)).size,
    [sessions]
  );
  const pipelineSub = repoCount > 0 ? `across ${repoCount} source${repoCount === 1 ? "" : "s"}` : "no source data yet";

  return (
    <section className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr_1fr] gap-4 items-stretch">
      <PassRateBlock passRate={passRate} failed={failed} total={total} sessions={sessions} />
      <div className="grid grid-cols-1 gap-4 h-full">
        <MiniMetric
          label="Pipeline runs"
          value={pipelineRuns}
          sub={pipelineSub}
          icon={Activity}
          loading={loading}
          index={1}
        />
        <MiniMetric
          label="Flaky tests"
          value={overview?.flaky_tests ?? 0}
          sub={`${overview?.quarantined_tests ?? 0} quarantined`}
          icon={Timer}
          tone={(overview?.flaky_tests ?? 0) > 5 ? "warn" : "neutral"}
          loading={loading}
          index={2}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 h-full">
        <MiniMetric
          label="PRs attention"
          value={overview?.prs_needing_attention ?? 0}
          sub="awaiting test signal"
          icon={GitPullRequest}
          tone={(overview?.prs_needing_attention ?? 0) > 0 ? "warn" : "good"}
          loading={loading}
          index={3}
        />
        <MiniMetric
          label="Active agents"
          value={overview?.active_agents ?? 0}
          sub="delegated tasks"
          icon={AlertOctagon}
          tone={(overview?.active_agents ?? 0) > 0 ? "good" : "neutral"}
          loading={loading}
          index={4}
        />
      </div>
    </section>
  );
}
