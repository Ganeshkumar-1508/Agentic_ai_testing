"use client";

import { Suspense, useState, useMemo, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { DashboardProvider, useDashboard } from "@/components/dashboard/DashboardProvider";
import { KpiCardSparkline } from "@/components/dashboard/KpiCardSparkline";
import { Beaker, CheckCircle2, XCircle, TrendingUp, TriangleAlert, Newspaper, LayoutDashboard, Activity, Bug, ShieldCheck, LayoutGrid, User2 } from "lucide-react";
import { QualityScoreGauge } from "@/components/dashboard/QualityScoreGauge";
import { PipelineFeedCard } from "@/components/dashboard/PipelineFeedCard";
import { RecentFailures } from "@/components/dashboard/RecentFailures";
import { RecentRunsTable } from "@/components/dashboard/RecentRunsTable";
import { FailureCategories } from "@/components/dashboard/FailureCategories";
import { CoverageChart } from "@/components/dashboard/CoverageChart";
import { FlakyScoreTrend } from "@/components/flaky/FlakyScoreTrend";
import { SelfHealingCard } from "@/components/dashboard/SelfHealingCard";
import { LogsCard } from "@/components/dashboard/LogsCard";
import { ProviderFailoverCard } from "@/components/dashboard/ProviderFailoverCard";
import { CostByModelCard } from "@/components/dashboard/CostByModelCard";
import { CostTrendCard } from "@/components/dashboard/CostTrendCard";
import { CostBreakdownCard } from "@/components/dashboard/CostBreakdownCard";
import { DonutChart } from "@/components/dashboard/DonutChart";
import { Analytics30dCard } from "@/components/dashboard/Analytics30dCard";
import { QuickActionsCard } from "@/components/dashboard/QuickActionsCard";
import { CoverageGapsCard } from "@/components/dashboard/CoverageGapsCard";
import { RCACard } from "@/components/dashboard/RCACard";
import { DefectPredictionCard } from "@/components/dashboard/DefectPredictionCard";
import { TraceabilityCard } from "@/components/dashboard/TraceabilityCard";
import { QualityTrendChart } from "@/components/dashboard/QualityTrendChart";
import { SprintTrends } from "@/components/dashboard/SprintTrends";
import { TokenUsageHeatmapCard } from "@/components/dashboard/TokenUsageHeatmapCard";
import { UsageStream } from "@/components/dashboard/UsageStream";
import { ActiveOrchestrationsCard } from "@/components/dashboard/ActiveOrchestrationsCard";
import { BlockedTasksCard } from "@/components/dashboard/BlockedTasksCard";
import { SystemHealthBar } from "@/components/dashboard/SystemHealthBar";
import { NotificationBell } from "@/components/dashboard/NotificationBell";
import { DashboardSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { DashboardEmptyState } from "@/components/dashboard/DashboardEmptyState";
import { DigestHero } from "@/components/dashboard/DigestHero";
import { DigestMetricRow } from "@/components/dashboard/DigestMetricRow";
import { DigestTimeline } from "@/components/dashboard/DigestTimeline";
import { DigestFailures } from "@/components/dashboard/DigestFailures";
import { DigestInsights } from "@/components/dashboard/DigestInsights";
import { DigestCostBar } from "@/components/dashboard/DigestCostBar";
import { DigestChannels } from "@/components/dashboard/DigestChannels";
import { DigestAttention } from "@/components/dashboard/DigestAttention";
import { DigestTab } from "./DigestTab";
import { ActivityHeatmap } from "@/components/dashboard/ActivityHeatmap";

const rowVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

function DashboardContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeTab = searchParams?.get("tab") || "overview";
  const [role, setRole] = useState("qa-engineer");
  const {
    overview,
    analytics,
    coverage,
    failureCategories,
    systemHealth,
    sprintTrends,
    isLoading,
    isInitialLoading,
    isOverviewLoading,
    isAnalyticsLoading,
    isCoverageLoading,
    isFailureCategoriesLoading,
    isSystemHealthLoading,
    isSprintTrendsLoading,
    error,
  } = useDashboard();

  const recentFailures = useMemo<Array<{ test_name: string; error: string; created_at: string }>>(
    () =>
      (overview?.recent_failures ?? []).map((f: any) => ({
        test_name: f.test_name || f.name || "unknown",
        error: f.error || "",
        created_at: f.created_at || "",
      })),
    [overview?.recent_failures]
  );

  const releaseScore = Number(overview?.quality_score ?? overview?.pass_rate_24h ?? 0);
  const releaseVerdict = releaseScore >= 80 ? "go" : releaseScore >= 60 ? "caution" : "no-go";
  const verdictColor = releaseVerdict === "go" ? "text-emerald-400" : releaseVerdict === "caution" ? "text-amber-400" : "text-red-400";

  const sparklines = useMemo(() => {
    const a = analytics;
    return {
      tests: (a?.spark_tests as number[]) ?? [],
      passRate: (a?.spark_pass_rate as number[]) ?? [],
      flaky: (a?.spark_flaky as number[]) ?? [],
      coverage: (coverage?.sparkline ?? []).map((p) => Number(p.line_pct) || 0),
    };
  }, [analytics, coverage]);

  const kpiColor = (i: number) => {
    const colors = ["default", "accent", "danger", "blue", "warning", "purple"] as const;
    return colors[i] ?? "default";
  };

  const DIGEST_TABS = [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "quality", label: "Quality", icon: ShieldCheck },
    { id: "cost", label: "Cost", icon: Newspaper },
    { id: "activity", label: "Activity", icon: Activity },
    { id: "digest", label: "Digest", icon: Newspaper },
  ] as const;

  const ROLE_LABEL: Record<string, string> = {
    "qa-engineer": "QA Engineer",
    "qa-manager": "QA Manager",
    "admin": "Admin",
    executive: "Executive",
  };

  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const updatedAt = (overview as any)?.timestamp ? new Date((overview as any).timestamp) : null;
  const updatedAgo = (() => {
    if (!updatedAt || !now || isNaN(updatedAt.getTime())) return null;
    const sec = Math.max(0, Math.floor((now.getTime() - updatedAt.getTime()) / 1000));
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    return `${Math.floor(hr / 24)}d ago`;
  })();

  const isOverviewEmpty = useMemo(() => {
    if (!overview) return false;
    const tests = (overview as any).tests_24h?.total ?? 0;
    const runs = (overview as any).pipeline_runs_24h ?? 0;
    const failures = Array.isArray((overview as any).recent_failures) ? (overview as any).recent_failures.length : 0;
    return tests === 0 && runs === 0 && failures === 0;
  }, [overview]);
  const showEmptyState = !isLoading && isOverviewEmpty;

  return (
    <div className="space-y-4">
      {/* Header + Tab bar */}
      <div className="flex items-start justify-between mb-2 flex-wrap gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">
              {activeTab === "digest" ? "Daily Digest" : activeTab === "quality" ? "Quality Signals" : activeTab === "cost" ? "Cost & Spend" : activeTab === "activity" ? "Activity" : "Overview"}
            </h1>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/15">
              <User2 className="w-3 h-3" strokeWidth={1.5} />
              {ROLE_LABEL[role] ?? role}
            </span>
            {updatedAgo && (
              <span className="text-[10px] font-mono text-zinc-600">
                Updated {updatedAgo}
              </span>
            )}
          </div>
          <p className="text-[13px] text-zinc-500">
            {activeTab === "digest"
              ? "Overnight summary of agent activity, costs, and quality signals"
              : activeTab === "quality"
                ? "Pass rates, failure clusters, flakiness, and traceability signals"
                : activeTab === "cost"
                  ? "Token spend, model breakdown, sprint trends, and provider health"
                  : activeTab === "activity"
                    ? "Pipeline feed, recent failures, and usage heatmaps"
                    : "Snapshot of active runs, blocked work, and recent agent activity"}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex bg-card border border-white/[0.06] rounded-full p-0.5 gap-0.5">
            {DIGEST_TABS.map((t) => {
              const TabIcon = t.icon;
              return (
                <button key={t.id} onClick={() => router.push(`/dashboard?tab=${t.id}`)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium transition-all ${
                    activeTab === t.id ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-500 hover:text-zinc-300"
                  }`}>
                  <TabIcon className="w-3 h-3" strokeWidth={1.5} />
                  {t.label}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            {(activeTab === "overview" || activeTab === "cost") && (
              <select value={role} onChange={(e) => setRole(e.target.value)}
                className="bg-card border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-[11px] text-zinc-400 outline-none focus:border-emerald-500/30">
                <option value="qa-engineer">QA Engineer</option>
                <option value="qa-manager">QA Manager</option>
                <option value="admin">Admin</option>
                <option value="executive">Executive</option>
              </select>
            )}
            <NotificationBell />
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg bg-white/[0.03] border border-white/[0.06] text-zinc-500 hover:text-zinc-300 transition-colors">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Export
            </motion.button>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-[1.5rem] bg-red-500/10 border border-red-500/15 text-red-400 text-sm">
          <XCircle className="w-4 h-4 shrink-0" strokeWidth={1.5} />
          <span className="flex-1">{error instanceof Error ? error.message : "Dashboard data unavailable"}</span>
          <button onClick={() => window.location.reload()} className="text-[11px] px-2.5 py-1 rounded-lg bg-red-500/15 hover:bg-red-500/25 text-red-300 transition-colors active:scale-[0.97]">
            Retry
          </button>
        </div>
      )}

      {/* Tab Content */}
      {showEmptyState && activeTab === "overview" ? (
        <DashboardEmptyState hasOverview={!!overview} />
      ) : activeTab === "digest" ? (
        <DigestTab overview={overview} isLoading={isLoading} />
      ) : activeTab === "quality" ? (
        <>
          {/* Row 1: Quality Score | Test Distribution */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full">
              <QualityScoreGauge
                passRate={overview?.pass_rate_24h ?? 0}
                flakyRate={overview?.flaky_tests ?? 0}
                score={overview?.quality_score}
                components={overview?.quality_components}
                loading={isLoading}
              />
            </motion.div>
            <motion.div variants={cardVariants} className="h-full"><DonutChart passed={overview?.tests_24h?.passed ?? 0} failed={overview?.tests_24h?.failed ?? 0} loading={isLoading} /></motion.div>
          </motion.div>
          {/* Row 2: Failure Categories | RCA Clusters */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr] gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><FailureCategories data={failureCategories} loading={isFailureCategoriesLoading} /></motion.div>
            <motion.div variants={cardVariants} className="h-full"><RCACard /></motion.div>
          </motion.div>
          {/* Row 3: Flaky Trend | Quality Trend (30d) */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><FlakyScoreTrend /></motion.div>
            <motion.div variants={cardVariants} className="h-full"><QualityTrendChart /></motion.div>
          </motion.div>
        </>
      ) : activeTab === "cost" ? (
        <>
          {/* Row 1: Cost Trend | Cost by Role | Cost by Model */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_1.5fr] gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><CostTrendCard /></motion.div>
            <motion.div variants={cardVariants} className="h-full"><CostBreakdownCard /></motion.div>
            <motion.div variants={cardVariants} className="h-full"><CostByModelCard /></motion.div>
          </motion.div>
          {/* Row 2: Token Usage (full-width) */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><TokenUsageHeatmapCard /></motion.div>
          </motion.div>
          {/* Row 3: Provider Failover */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><ProviderFailoverCard /></motion.div>
            <motion.div variants={cardVariants} className="h-full"><UsageStream /></motion.div>
          </motion.div>
        </>
      ) : activeTab === "activity" ? (
        <>
          {/* Row 1: Active Pipelines | Recent Failures */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><PipelineFeedCard /></motion.div>
            <motion.div variants={cardVariants} className="h-full"><RecentFailures failures={recentFailures} loading={isLoading} /></motion.div>
          </motion.div>
          {/* Row 2: Heatmap (full-width) */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><ActivityHeatmap /></motion.div>
          </motion.div>
          {/* Row 3: Token Usage (full-width) */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><TokenUsageHeatmapCard /></motion.div>
          </motion.div>
          {/* Row 4: Usage Stream (live event log) */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 gap-4 items-stretch">
            <motion.div variants={cardVariants} className="h-full"><UsageStream /></motion.div>
          </motion.div>
        </>
      ) : role === "admin" ? (
        <>
          {/* ADMIN OVERVIEW — cost, sessions, health, runs — no testing */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <motion.div variants={cardVariants}>
              <div className="rounded-[2rem] p-5 card-wireframe h-full flex flex-col">
                <span className="card-label">Agent Runs</span>
                <div className="text-2xl font-semibold font-mono text-zinc-100 mt-2">{overview?.pipeline_runs_24h ?? 0}</div>
                <span className="text-[10px] text-zinc-600 mt-1">Last 24h</span>
              </div>
            </motion.div>
            <motion.div variants={cardVariants}>
              <div className="rounded-[2rem] p-5 card-wireframe h-full flex flex-col">
                <span className="card-label">Active Agents</span>
                <div className="text-2xl font-semibold font-mono text-zinc-100 mt-2">{overview?.active_agents ?? 0}</div>
                <span className="text-[10px] text-zinc-600 mt-1">Currently running</span>
              </div>
            </motion.div>
            <motion.div variants={cardVariants}>
              <div className="rounded-[2rem] p-5 card-wireframe h-full flex flex-col">
                <span className="card-label">Quality Score</span>
                <div className="text-2xl font-semibold font-mono text-zinc-100 mt-2">{overview?.quality_score != null ? `${Math.round(overview.quality_score)}` : "--"}</div>
                <span className="text-[10px] text-zinc-600 mt-1">{overview?.pass_rate_24h != null ? `${Math.round(overview.pass_rate_24h)}% pass` : "No data"}</span>
              </div>
            </motion.div>
            <motion.div variants={cardVariants}>
              <div className="rounded-[2rem] p-5 card-wireframe h-full flex flex-col">
                <span className="card-label">Updated</span>
                <div className="text-2xl font-semibold font-mono text-zinc-100 mt-2 text-base">{updatedAgo || "--"}</div>
                <span className="text-[10px] text-zinc-600 mt-1">Last refresh</span>
              </div>
            </motion.div>
          </motion.div>

          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants}><CostTrendCard /></motion.div>
            <motion.div variants={cardVariants}><CostByModelCard /></motion.div>
          </motion.div>

          <SystemHealthBar data={systemHealth} loading={isSystemHealthLoading} />

          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants}><RecentRunsTable /></motion.div>
            <motion.div variants={cardVariants}><ProviderFailoverCard /></motion.div>
          </motion.div>
        </>
      ) : (
        <>
          {/* QA ENGINEER / EXECUTIVE OVERVIEW — full testing view */}
          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <motion.div variants={cardVariants}>
              <KpiCardSparkline label="Tests (24h)" value={overview?.tests_24h?.total ?? 0} sparklineData={sparklines.tests}
                icon={<Beaker className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />} color={kpiColor(0)} loading={isLoading} index={0}
                trend={analytics?.change_tests_pct != null ? { value: `${analytics.change_tests_pct > 0 ? "+" : ""}${(analytics.change_tests_pct).toFixed(1)}%`, positive: (analytics.change_tests_pct ?? 0) >= 0 } : undefined} />
            </motion.div>
            <motion.div variants={cardVariants}>
              <KpiCardSparkline label="Pass Rate" value={overview?.pass_rate_24h != null ? `${Math.round(overview.pass_rate_24h)}%` : "--"} sparklineData={sparklines.passRate}
                icon={<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />} color={kpiColor(1)} loading={isLoading} index={1}
                trend={analytics?.change_pass_pct != null ? { value: `${analytics.change_pass_pct > 0 ? "+" : ""}${(analytics.change_pass_pct).toFixed(1)}%`, positive: (analytics.change_pass_pct ?? 0) >= 0 } : undefined} />
            </motion.div>
            <motion.div variants={cardVariants}>
              <KpiCardSparkline label="Failed" value={overview?.tests_24h?.failed ?? 0}
                icon={<XCircle className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />} color={kpiColor(2)} loading={isLoading} index={2} />
            </motion.div>
            <motion.div variants={cardVariants}>
              <KpiCardSparkline label="Agent Runs" value={overview?.pipeline_runs_24h ?? 0}
                icon={<TrendingUp className="w-3.5 h-3.5 text-blue-400" strokeWidth={1.5} />} color={kpiColor(3)} loading={isLoading} index={3} />
            </motion.div>
            <motion.div variants={cardVariants}>
              <KpiCardSparkline label="Flaky Tests" value={overview?.flaky_tests ?? 0} sparklineData={sparklines.flaky}
                icon={<TriangleAlert className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />} color={kpiColor(4)} loading={isLoading} index={4}
                trend={analytics?.change_flaky_pct != null ? { value: `${analytics.change_flaky_pct > 0 ? "+" : ""}${(analytics.change_flaky_pct).toFixed(1)}%`, positive: (analytics.change_flaky_pct ?? 0) <= 0 } : undefined} />
            </motion.div>
            {role === "executive" ? (
              <motion.div variants={cardVariants}>
                <div className="border border-white/[0.06] rounded-[2rem] p-5 space-y-4 h-full">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono text-zinc-600 uppercase tracking-[0.06em]">Release Confidence</span>
                    <ShieldCheck className={cn("w-4 h-4", verdictColor)} strokeWidth={1.5} />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className={cn("text-2xl font-medium font-mono tracking-tighter leading-none", verdictColor)}>{releaseScore.toFixed(0)}</span>
                    <span className="text-[10px] font-mono uppercase text-zinc-600">/ 100</span>
                  </div>
                  <div className="h-2 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className={cn("h-full rounded-full transition-all", releaseScore >= 80 ? "bg-emerald-400" : releaseScore >= 60 ? "bg-amber-400" : "bg-red-400")} style={{ width: `${releaseScore}%` }} />
                  </div>
                  <div className={cn("text-[10px] font-semibold uppercase tracking-wider", verdictColor)}>{releaseVerdict}</div>
                </div>
              </motion.div>
            ) : (
              <motion.div variants={cardVariants}>
                <KpiCardSparkline
                  label="Coverage"
                  value={coverage ? `${coverage.line_pct.toFixed(1)}%` : "--"}
                  sparklineData={sparklines.coverage}
                  icon={<LayoutGrid className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />}
                  color="default"
                  loading={isLoading}
                  index={5}
                  trend={coverage?.change_pct != null ? {
                    value: `${coverage.change_pct > 0 ? "+" : ""}${coverage.change_pct.toFixed(1)}%`,
                    positive: coverage.change_pct >= 0,
                  } : undefined}
                  subtitle={coverage
                    ? (coverage.untested_requirements > 0
                        ? `${coverage.untested_requirements} untested requirements`
                        : "all requirements covered")
                    : undefined}
                />
              </motion.div>
            )}
          </motion.div>

          <SystemHealthBar data={systemHealth} loading={isSystemHealthLoading} />

          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants}><ActiveOrchestrationsCard /></motion.div>
            <motion.div variants={cardVariants}><BlockedTasksCard /></motion.div>
          </motion.div>

          <motion.div initial="hidden" animate="show" variants={rowVariants} className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4 items-stretch">
            <motion.div variants={cardVariants}><RecentRunsTable /></motion.div>
            <motion.div variants={cardVariants}><QuickActionsCard /></motion.div>
          </motion.div>
        </>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardProvider>
        <DashboardContent />
      </DashboardProvider>
    </Suspense>
  );
}
