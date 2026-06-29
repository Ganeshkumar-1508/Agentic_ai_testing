"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BarChart3, Calendar, Loader2, Sparkles, TrendingUp, AlertCircle, CheckCircle2, Timer, Zap } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import { DigestHero } from "@/components/dashboard/DigestHero";
import { DigestMetricRow } from "@/components/dashboard/DigestMetricRow";
import { DigestAttention } from "@/components/dashboard/DigestAttention";
import { DigestInsights } from "@/components/dashboard/DigestInsights";

const stagger = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

function useLiveClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function greetingFor(hour: number): string {
  if (hour < 5) return "Burning the midnight oil";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 21) return "Good evening";
  return "Late night";
}

interface QuickStat {
  label: string;
  value: string;
  sub?: string;
  tone: "good" | "warn" | "bad" | "neutral";
  icon: React.ReactNode;
}

function QuickStats({ overview, loading }: { overview: any; loading: boolean }) {
  const tests = overview?.tests_24h?.total ?? 0;
  const passed = overview?.tests_24h?.passed ?? 0;
  const failed = overview?.tests_24h?.failed ?? 0;
  const passRate = overview?.pass_rate_24h ?? 0;
  const runs = overview?.pipeline_runs_24h ?? 0;
  const cost = overview?.tests_24h ? null : null;
  const prs = overview?.prs_needing_attention ?? 0;

  const stats: QuickStat[] = [
    {
      label: "Pipeline runs (24h)",
      value: runs > 0 ? String(runs) : "—",
      sub: runs > 0 ? `${overview?.pipeline_status?.completed ?? 0} completed` : "no runs yet",
      tone: runs > 0 ? "good" : "neutral",
      icon: <BarChart3 className="w-3.5 h-3.5" strokeWidth={1.5} />,
    },
    {
      label: "Pass rate",
      value: tests > 0 ? `${Math.round(passRate)}%` : "—",
      sub: tests > 0 ? `${passed} passed · ${failed} failed` : "no tests yet",
      tone: tests === 0 ? "neutral" : passRate >= 80 ? "good" : passRate >= 60 ? "warn" : "bad",
      icon: <CheckCircle2 className="w-3.5 h-3.5" strokeWidth={1.5} />,
    },
    {
      label: "Quarantined tests",
      value: overview?.quarantined_tests != null ? String(overview.quarantined_tests) : "—",
      sub: "auto-quarantined by flaky detection",
      tone: (overview?.quarantined_tests ?? 0) > 0 ? "warn" : "neutral",
      icon: <AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />,
    },
    {
      label: "PRs needing attention",
      value: prs > 0 ? String(prs) : "0",
      sub: prs > 0 ? "ready to merge or fix" : "all PRs passing",
      tone: prs > 0 ? "warn" : "good",
      icon: <TrendingUp className="w-3.5 h-3.5" strokeWidth={1.5} />,
    },
  ];

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="grid grid-cols-2 md:grid-cols-4 gap-3"
    >
      {stats.map((s) => {
        const toneRing = {
          good: "border-emerald-500/20 bg-emerald-500/[0.03]",
          warn: "border-amber-500/20 bg-amber-500/[0.03]",
          bad: "border-red-500/20 bg-red-500/[0.03]",
          neutral: "border-white/[0.06] bg-white/[0.02]",
        }[s.tone];
        const toneText = {
          good: "text-emerald-400",
          warn: "text-amber-400",
          bad: "text-red-400",
          neutral: "text-zinc-500",
        }[s.tone];
        return (
          <motion.div
            key={s.label}
            variants={item}
            className={cn(
              "p-4 rounded-[1.5rem] border backdrop-blur-sm transition-colors",
              toneRing
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-zinc-500">
                {s.label}
              </span>
              <span className={toneText}>{s.icon}</span>
            </div>
            <div className="text-2xl font-semibold font-mono tracking-tight text-zinc-100">
              {loading ? (
                <span className="inline-block w-12 h-6 rounded shimmer-bg align-middle" />
              ) : (
                s.value
              )}
            </div>
            <div className="text-[10px] font-mono text-zinc-600 mt-1 truncate">
              {s.sub}
            </div>
          </motion.div>
        );
      })}
    </motion.div>
  );
}

export default function HomePage() {
  const now = useLiveClock();
  const hour = now?.getHours() ?? 9;

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => api.get<any>("/api/dashboard/overview"),
    refetchInterval: 30_000,
    retry: 2,
  });

  const { data: dailyData } = useQuery({
    queryKey: ["daily-stats"],
    queryFn: () => api.get<any>("/api/dashboard/daily-stats?days=30"),
    staleTime: 60_000,
  });

  const { data: activityData } = useQuery({
    queryKey: ["pipeline-activity"],
    queryFn: () => api.get<any>("/api/pipeline-activity/recent", { limit: "14" }),
    staleTime: 30_000,
  });

  const { data: digestConfigs } = useQuery({
    queryKey: ["digest-configs"],
    queryFn: () => api.get<any>("/api/digest/configs"),
    staleTime: 120_000,
  });

  const days = dailyData?.days ?? [];
  const yesterday = days.length >= 2 ? days[days.length - 2] : null;
  const sessions = activityData?.sessions ?? [];
  const configs = digestConfigs?.configs ?? [];

  const dateLabel = now
    ? now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
    : "—";

  return (
    <div className="relative min-h-[100dvh]">
      {/* Ambient background (subtle, from the wireframe) */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div
          className="absolute -top-32 -right-32 w-[600px] h-[600px] rounded-full blur-[140px] opacity-40"
          style={{ background: "radial-gradient(circle, rgba(52,211,153,0.10), transparent 70%)" }}
        />
        <div
          className="absolute top-1/3 left-1/4 w-[420px] h-[420px] rounded-full blur-[120px] opacity-30"
          style={{ background: "radial-gradient(circle, rgba(96,165,250,0.07), transparent 70%)" }}
        />
      </div>

      <motion.div
        initial="hidden"
        animate="show"
        variants={stagger}
        className="relative z-10 space-y-10"
      >
        {/* Hero — premium, homepage-wireframe-inspired */}
        <motion.section variants={item} className="relative">
          <div className="flex items-start justify-between gap-6 flex-wrap">
            <div className="space-y-5 max-w-2xl">
              <div className="inline-flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.22em] text-emerald-400 border border-emerald-500/15 rounded-full px-3 py-1 bg-emerald-500/[0.04]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>Today · {dateLabel}</span>
                <span className="text-emerald-500/40">·</span>
                <Timer className="w-3 h-3" strokeWidth={1.5} />
                <span>24h window</span>
              </div>

              <h1 className="text-[2.75rem] md:text-[3.75rem] font-semibold tracking-tighter leading-[0.95] text-zinc-50">
                {greetingFor(hour)}.
              </h1>

              <p className="text-base text-zinc-400 leading-relaxed max-w-[60ch]">
                Your agents worked through the night. Here&apos;s what changed, what broke,
                and what needs you — distilled into a 30-second read.
              </p>
            </div>

            {/* CTA cluster — the "go to dashboard" button + secondary */}
            <div className="flex flex-col items-end gap-3 shrink-0">
              <Link
                href="/dashboard"
                className="group inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full bg-emerald-500 text-zinc-950 font-semibold text-sm shadow-[0_8px_32px_-8px_rgba(52,211,153,0.45)] hover:shadow-[0_12px_40px_-8px_rgba(52,211,153,0.55)] hover:scale-[1.02] active:scale-[0.98] transition-all"
              >
                <Zap className="w-4 h-4" strokeWidth={2.5} />
                Go to dashboard
                <span className="ml-1 w-5 h-5 rounded-full bg-zinc-950/15 flex items-center justify-center transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5">
                  <ArrowUpRight className="w-3 h-3" strokeWidth={2.5} />
                </span>
              </Link>
              <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-500">
                <Link href="/digest" className="hover:text-emerald-400 transition-colors">
                  View full digest →
                </Link>
                <span className="text-zinc-800">·</span>
                <Link href="/pipeline" className="hover:text-emerald-400 transition-colors">
                  Open pipeline →
                </Link>
              </div>
            </div>
          </div>
        </motion.section>

        {/* Loading skeleton (whole page) */}
        {overviewLoading && !overview && (
          <div className="flex items-center gap-3 text-zinc-500 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
            <span>Compiling your morning briefing…</span>
          </div>
        )}

        {/* Quick stats row */}
        {overview && <QuickStats overview={overview} loading={overviewLoading} />}

        {/* Two-column: insights + attention (the briefing content) */}
        {overview && (
          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-6">
            <motion.section variants={item} className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
                  <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-400">
                    Insights
                  </span>
                </div>
                <Link
                  href="/dashboard?tab=digest"
                  className="text-[10px] font-mono uppercase tracking-[0.15em] text-zinc-600 hover:text-emerald-400 transition-colors"
                >
                  See in digest →
                </Link>
              </div>
              <DigestInsights overview={overview} loading={overviewLoading} />
            </motion.section>

            <motion.section variants={item} className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />
                  <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-400">
                    Needs your attention
                  </span>
                </div>
                <Link
                  href="/dashboard?tab=failures"
                  className="text-[10px] font-mono uppercase tracking-[0.15em] text-zinc-600 hover:text-emerald-400 transition-colors"
                >
                  Open failures →
                </Link>
              </div>
              <DigestAttention overview={overview} loading={overviewLoading} />
            </motion.section>
          </div>
        )}

        {/* Hero greeting re-stated with the digest flavor (keeps the brand voice) */}
        {overview && (
          <motion.section variants={item}>
            <DigestHero overview={overview} loading={overviewLoading} yesterday={yesterday} digestConfigs={configs} />
          </motion.section>
        )}

        {/* Compact metric strip — gives a spark of the day visually */}
        {overview && (
          <motion.section variants={item}>
            <DigestMetricRow overview={overview} loading={overviewLoading} sessions={sessions} />
          </motion.section>
        )}

        {/* Bottom CTA — gives the "go to dashboard" button a second placement */}
        <motion.section
          variants={item}
          className="flex flex-col items-center text-center gap-4 pt-6 border-t border-white/[0.06]"
        >
          <p className="text-xs text-zinc-500 max-w-md">
            That&apos;s the morning briefing. For full pipelines, sessions, and live test runs, head to the dashboard.
          </p>
          <Link
            href="/dashboard"
            className="group inline-flex items-center gap-2.5 px-5 py-2.5 rounded-full border border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04] hover:border-emerald-500/30 text-zinc-200 font-medium text-sm transition-all"
          >
            <BarChart3 className="w-4 h-4 text-zinc-400 group-hover:text-emerald-400 transition-colors" strokeWidth={1.5} />
            Open full dashboard
            <ArrowUpRight className="w-3.5 h-3.5 text-zinc-500 group-hover:text-emerald-400 transition-colors" strokeWidth={1.5} />
          </Link>
        </motion.section>
      </motion.div>
    </div>
  );
}
