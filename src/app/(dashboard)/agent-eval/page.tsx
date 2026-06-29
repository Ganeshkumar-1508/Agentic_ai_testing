"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  ShieldCheck,
  ShieldAlert,
  TrendingUp,
  AlertTriangle,
  Gauge,
  Activity,
  Layers,
  FileText,
  FlaskConical,
  Bug,
  Zap,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/PageHeader";
import { api } from "@/lib/api/api-client";

const QualityTrendChart = dynamic(
  () => import("./_eval/QualityTrendChart").then((m) => m.QualityTrendChart),
  { ssr: false, loading: () => <div className="h-[260px] rounded-xl shimmer-bg" /> }
);

type QualityScore = {
  score: number | null;
  verdict: "go" | "caution" | "blocked" | "no-data";
  thresholds?: { go: number; caution: number };
  components?: Record<string, {
    raw: number;
    weighted: number;
    weight: number;
    details: Record<string, unknown>;
  }>;
  weakest_area?: string;
  blocker?: string;
  period_days: number;
};

type QualityTrend = {
  trend: Array<{
    date: string;
    score: number;
    verdict: string;
  }>;
};

type QualityMetrics = {
  period: string;
  metrics: Record<string, Array<{ value: number; date: string }>>;
  available: string[];
};

const springHover = { type: "spring" as const, stiffness: 100, damping: 20 };
const cubicEnter = { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const };

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.08 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: cubicEnter },
};

const COMPONENT_META: Record<string, { label: string; icon: typeof Gauge; color: string }> = {
  pass_rate: { label: "Pass Rate", icon: ShieldCheck, color: "text-emerald-400" },
  coverage: { label: "Coverage", icon: FlaskConical, color: "text-zinc-400" },
  flaky_rate: { label: "Flaky Rate", icon: AlertTriangle, color: "text-amber-400" },
  defect_density: { label: "Defect Density", icon: Bug, color: "text-rose-400" },
  automation_coverage: { label: "Automation", icon: Zap, color: "text-zinc-400" },
};

export default function AgentEvalPage() {
  const scoreQ = useQuery({
    queryKey: ["quality-score"],
    queryFn: () => api.get<QualityScore>("/api/quality/score?days=14"),
    refetchInterval: 60_000,
  });

  const trendQ = useQuery({
    queryKey: ["quality-trend"],
    queryFn: () => api.get<QualityTrend>("/api/quality/trend?days=90"),
    refetchInterval: 120_000,
  });

  const metricsQ = useQuery({
    queryKey: ["quality-metrics"],
    queryFn: () => api.get<QualityMetrics>("/api/quality/metrics?period=30d"),
    refetchInterval: 60_000,
  });

  const data = scoreQ.data;
  const trend = trendQ.data?.trend ?? [];
  const metricsData = metricsQ.data;

  const verdictTone = data?.verdict === "go"
    ? { bg: "bg-emerald-500/10", border: "border-emerald-400/20", text: "text-emerald-300", dot: "bg-emerald-400" }
    : data?.verdict === "caution"
    ? { bg: "bg-amber-500/10", border: "border-amber-400/20", text: "text-amber-300", dot: "bg-amber-400" }
    : { bg: "bg-rose-500/10", border: "border-rose-400/20", text: "text-rose-300", dot: "bg-rose-400" };

  const components = useMemo(() => {
    if (!data || !data.components || typeof data.components !== "object") return [];
    return Object.entries(data.components)
      .map(([key, c]) => ({
        key,
        ...c,
        meta: COMPONENT_META[key] ?? { label: key, icon: Gauge, color: "text-neutral-400" },
      }))
      .sort((a, b) => b.weight - a.weight);
  }, [data]);

  const weakestLabel = COMPONENT_META[data?.weakest_area ?? ""]?.label ?? data?.weakest_area;

  return (
    <div className="space-y-6">
      <PageHeader
        route="/agent-eval"
        title="Agent Evaluation"
        label="BENCHMARKS"
        description="Release readiness scored across pass rate, coverage, flakiness, and automation."
      />

      {scoreQ.isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-[2.5fr_1fr] gap-3">
          <div className="h-48 rounded-xl shimmer-bg" />
          <div className="h-48 rounded-xl shimmer-bg" />
        </div>
      ) : !data || data.score === null || data.verdict === "no-data" ? (
        <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-12 flex flex-col items-center justify-center text-center">
          <Bot className="w-8 h-8 text-neutral-700 mb-3" strokeWidth={1.2} />
          <h3 className="text-[15px] font-medium text-neutral-200 mb-1">No eval data yet</h3>
          <p className="text-[12px] text-neutral-500 max-w-sm">
            Run a pipeline to generate quality scores and evaluation metrics.
          </p>
        </div>
      ) : (
        <>
          <motion.section
            initial="hidden"
            animate="show"
            variants={containerVariants}
            className="grid grid-cols-1 lg:grid-cols-[2.5fr_1fr] gap-3"
          >
            <motion.div variants={itemVariants} className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-6 flex items-center gap-6">
              <div className="shrink-0 relative">
                <ScoreRing score={data.score} verdict={data.verdict} />
              </div>
              <div>
                <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider mb-1.5">
                  Overall Quality Score
                </div>
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn("px-2 py-0.5 rounded text-[10.5px] font-mono uppercase tracking-wider", verdictTone.bg, verdictTone.border, verdictTone.text)}>
                    {data.verdict}
                  </span>
                  <span className="text-[11px] font-mono text-neutral-600">
                    pass ≥{data.thresholds?.go ?? 80} · warn ≥{data.thresholds?.caution ?? 60}
                  </span>
                </div>
                <div className="text-[12px] text-neutral-400 leading-relaxed max-w-md">
                  {data.verdict === "go"
                    ? "All quality gates pass. Release ready."
                    : data.verdict === "caution"
                    ? `Weakest area: ${weakestLabel}. Address before release for confidence.`
                    : `Blocked by: ${data.blocker || "critical metric below threshold"}.`
                  }
                </div>
              </div>
            </motion.div>

            <motion.div variants={itemVariants} className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-5 flex flex-col justify-center">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-neutral-500" strokeWidth={1.5} />
                <span className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
                  {data.period_days}d snapshot
                </span>
              </div>
              <div className="space-y-2.5">
                <MetricRow label="Pass rate" value={data?.components?.pass_rate?.raw ?? 0} suffix="%" />
                <MetricRow label="Coverage" value={data?.components?.coverage?.raw ?? 0} suffix="%" />
                <MetricRow label="Flaky rate" value={data?.components?.flaky_rate?.raw ?? 0} suffix="%" />
                <MetricRow label="Automation" value={data?.components?.automation_coverage?.raw ?? 0} suffix="%" />
              </div>
            </motion.div>
          </motion.section>

          <motion.section
            initial="hidden"
            animate="show"
            variants={containerVariants}
            className="grid grid-cols-1 md:grid-cols-2 gap-3"
          >
            {components.map((c) => (
              <motion.div
                key={c.key}
                variants={itemVariants}
                whileHover={{ scale: 1.012, transition: springHover }}
                className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-5 active:scale-[0.99] transition-transform"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <c.meta.icon className={cn("w-4 h-4", c.meta.color)} strokeWidth={1.5} />
                    <span className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
                      {c.meta.label}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-neutral-600">
                    weight {Math.round(c.weight * 100)}%
                  </span>
                </div>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-2xl font-semibold tracking-tight text-zinc-100 leading-none">
                    {Math.round(c.raw)}
                  </span>
                  <span className="text-[13px] font-mono text-neutral-500">/ 100</span>
                  <span className={cn(
                    "ml-auto text-[13px] font-mono tabular-nums",
                    c.weighted >= c.weight * 80 ? "text-emerald-400" : c.weighted >= c.weight * 60 ? "text-amber-400" : "text-rose-400"
                  )}>
                    +{c.weighted.toFixed(1)}
                  </span>
                </div>
                <ScoreBar value={c.raw} />
                <div className="mt-2 text-[10.5px] font-mono text-neutral-600">
                  {getComponentDetail(c)}
                </div>
              </motion.div>
            ))}
          </motion.section>

          <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-3">
            <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-5">
              <div className="flex items-center gap-2 mb-1">
                <Activity className="w-4 h-4 text-neutral-500" strokeWidth={1.5} />
                <span className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
                  Score trend
                </span>
              </div>
              <div className="text-[10.5px] font-mono text-neutral-600 mt-0.5 mb-4">
                90-day quality trajectory
              </div>
              <QualityTrendChart data={trend} isLoading={trendQ.isLoading} />
            </div>

            <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-5">
              <div className="flex items-center gap-2 mb-3">
                <RefreshCw className="w-4 h-4 text-neutral-500" strokeWidth={1.5} />
                <span className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
                  Pipeline metrics
                </span>
              </div>
              <div className="text-[10.5px] font-mono text-neutral-600 mb-4">
                Last 30 days of run data
              </div>
              {metricsQ.isLoading ? (
                <div className="space-y-3">
                  <div className="h-4 rounded shimmer-bg" />
                  <div className="h-4 rounded shimmer-bg w-2/3" />
                  <div className="h-4 rounded shimmer-bg w-1/2" />
                </div>
              ) : metricsData ? (
                <div className="space-y-3">
                  {metricsData.available.map((name) => {
                    const points = metricsData.metrics[name] ?? [];
                    const latest = points[points.length - 1];
                    return (
                      <div key={name} className="flex items-center justify-between text-[12px]">
                        <span className="text-neutral-500 capitalize font-mono">
                          {name.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono text-neutral-200 tabular-nums">
                          {name === "pipeline_status"
                            ? latest ? "active" : "inactive"
                            : latest ? Number(latest.value).toFixed(1) : "\u2014"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[12px] text-neutral-600">No pipeline metrics recorded.</p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MetricRow({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-neutral-500">{label}</span>
      <span className="font-mono text-neutral-200 tabular-nums">
        {Math.round(value)}{suffix}
      </span>
    </div>
  );
}

function ScoreBar({ value }: { value: number }) {
  const hue = value >= 80 ? "bg-emerald-400" : value >= 60 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(value, 100)}%` }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className={cn("h-full rounded-full", hue)}
      />
    </div>
  );
}

function ScoreRing({ score, verdict }: { score: number; verdict: string }) {
  const r = 44;
  const circ = 2 * Math.PI * r;
  const offset = circ - (Math.min(score, 100) / 100) * circ;
  const color = verdict === "go" ? "#34d399" : verdict === "caution" ? "#fbbf24" : "#fb7185";
  return (
    <div className="relative w-[72px] h-[72px]">
      <svg width="72" height="72" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
        <motion.circle
          cx="60" cy="60" r={r}
          fill="none" stroke={color} strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[18px] font-semibold text-zinc-100 tabular-nums">
          {Math.round(score)}
        </span>
      </div>
    </div>
  );
}

function getComponentDetail(c: { key: string; raw: number; details: Record<string, unknown> }): string {
  const d = c.details;
  if (d.note) return String(d.note);
  if (d.total !== undefined && d.passed !== undefined) {
    return `${d.passed}/${d.total} tests passing`;
  }
  if (d.total_runs !== undefined) {
    return `${d.total_runs} pipeline runs`;
  }
  return "";
}
