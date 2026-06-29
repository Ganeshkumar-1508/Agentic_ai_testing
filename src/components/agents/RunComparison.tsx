"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, ArrowRight, ArrowUp, ArrowDown, Minus,
  CheckCircle, XCircle, AlertTriangle, Search, Clock,
  DollarSign, BarChart3, GitCompare, Share2, Download,
  Bug, RotateCcw, ChevronDown, ChevronRight, ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { api } from "@/lib/api/api-client";

interface RunSummary {
  id: string;
  status: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
  skippedCount: number;
  duration: number;
  createdAt: string;
}

interface TraceEvent {
  id: string;
  eventType: string;
  eventData: Record<string, unknown>;
  parentId: string;
  createdAt: string;
}

interface TestInfo {
  name: string;
  status: string;
  duration: number;
  error?: string;
}

type DiffCategory = "regression" | "fixed" | "new" | "removed" | "unchanged";
type ComparisonTab = "aggregate" | "tests" | "traces";

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function formatDelta(current: number, previous: number, suffix = ""): { text: string; improved: boolean } {
  const diff = current - previous;
  if (Math.abs(diff) < 0.01) return { text: "same", improved: true };
  const pct = previous !== 0 ? Math.round((diff / previous) * 100) : 0;
  const sign = diff > 0 ? "+" : "";
  const isImprovement = suffix === "cost" || suffix === "duration" ? diff < 0 : diff > 0;
  return { text: `${sign}${diff.toFixed(1)}${suffix} (${sign}${pct}%)`, improved: isImprovement };
}

async function fetchRunDetails(runId: string): Promise<RunSummary | null> {
  try {
    const json = await api.get<{ run?: RunSummary }>(`/api/runs/${runId}`);
    return json?.run ?? null;
  } catch { return null; }
}

async function fetchTraceEvents(runId: string): Promise<TraceEvent[]> {
  try {
    const json = await api.get<{ events?: TraceEvent[] }>(`/api/runs/${runId}/trace-events?limit=500`);
    return (json?.events ?? []) as TraceEvent[];
  } catch { return []; }
}

const sectionVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

function DiffValue({ current, previous, label, suffix, higherIsBetter }: {
  current: number; previous: number; label: string; suffix?: string; higherIsBetter?: boolean;
}) {
  const delta = formatDelta(current, previous, suffix || "");
  const diff = current - previous;
  const isNeutral = Math.abs(diff) < 0.01;
  const isGood = higherIsBetter ? delta.improved : !delta.improved;
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-[11px] text-neutral-500">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-neutral-300 font-mono tabular-nums">{current.toLocaleString()}{suffix || ""}</span>
        <div className="flex items-center gap-0.5">
          {isNeutral ? (
            <Minus className="w-3 h-3 text-neutral-600" strokeWidth={2} />
          ) : isGood ? (
            <ArrowDown className="w-3 h-3 text-emerald-400" strokeWidth={2} />
          ) : (
            <ArrowUp className="w-3 h-3 text-red-400" strokeWidth={2} />
          )}
          <span className={cn("text-[10px] font-mono tabular-nums", isGood ? "text-emerald-400" : "text-red-400")}>
            {delta.text}
          </span>
        </div>
        <span className="text-[11px] text-neutral-600 font-mono tabular-nums w-16 text-right">{previous.toLocaleString()}{suffix || ""}</span>
      </div>
    </div>
  );
}

export function RunComparison({ runId, compareId, onClose }: { runId: string; compareId: string | null; onClose: () => void }) {
  const router = useRouter();
  const [tab, setTab] = useState<ComparisonTab>("aggregate");
  const [search, setSearch] = useState("");
  const [diffFilter, setDiffFilter] = useState<DiffCategory | "all">("all");
  const [currentRun, setCurrentRun] = useState<RunSummary | null>(null);
  const [compareRun, setCompareRun] = useState<RunSummary | null>(null);
  const [currentEvents, setCurrentEvents] = useState<TraceEvent[]>([]);
  const [compareEvents, setCompareEvents] = useState<TraceEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!compareId) { setIsLoading(false); return; }
    setIsLoading(true); setLoadError(null);
    Promise.all([
      fetchRunDetails(runId), fetchRunDetails(compareId),
      fetchTraceEvents(runId), fetchTraceEvents(compareId),
    ]).then(([r1, r2, e1, e2]) => {
      setCurrentRun(r1); setCompareRun(r2);
      setCurrentEvents(e1); setCompareEvents(e2);
      setIsLoading(false);
    }).catch(() => { setLoadError("Failed to load comparison data"); setIsLoading(false); });
  }, [runId, compareId]);

  const diffTests = useMemo(() => {
    if (!compareRun) return [];
    const currentTests: TestInfo[] = [];
    const compareTests: TestInfo[] = [];
    const currentNames = new Set(currentTests.map((t) => t.name));
    const compareNames = new Set(compareTests.map((t) => t.name));
    const allNames = new Set([...currentNames, ...compareNames]);
    const result: Array<{ name: string; category: DiffCategory; current?: TestInfo; previous?: TestInfo }> = [];

    for (const name of allNames) {
      const c = currentTests.find((t) => t.name === name);
      const p = compareTests.find((t) => t.name === name);
      let category: DiffCategory = "unchanged";
      if (c && !p) category = "new";
      else if (!c && p) category = "removed";
      else if (c && p && c.status === "failed" && p.status !== "failed") category = "regression";
      else if (c && p && c.status !== "failed" && p.status === "failed") category = "fixed";
      result.push({ name, category, current: c, previous: p });
    }

    return result.filter((t) => {
      if (diffFilter !== "all" && t.category !== diffFilter) return false;
      if (search && !t.name.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    }).sort((a, b) => {
      const order: Record<DiffCategory, number> = { regression: 0, fixed: 1, new: 2, removed: 3, unchanged: 4 };
      return (order[a.category] ?? 5) - (order[b.category] ?? 5);
    });
  }, [currentRun, compareRun, search, diffFilter]);

  const aggregated = useMemo(() => {
    const c = currentRun; const p = compareRun;
    if (!c || !p) return null;
    return {
      tests: { current: c.testCount, previous: p.testCount, higherIsBetter: true },
      passed: { current: c.passedCount, previous: p.passedCount, higherIsBetter: true },
      failed: { current: c.failedCount, previous: p.failedCount, higherIsBetter: false },
      duration: { current: c.duration, previous: p.duration, higherIsBetter: false },
    };
  }, [currentRun, compareRun]);

  // ── No comparison selected ─────────────────────────────────────

  if (!compareId) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center border border-dashed border-white/[0.08] rounded-3xl">
        <GitCompare className="w-10 h-10 text-neutral-600 mb-3" strokeWidth={1.2} />
        <p className="text-sm text-neutral-500 mb-1">Select a run to compare</p>
        <p className="text-xs text-neutral-600">Choose a second run from the history page to see a diff</p>
      </div>
    );
  }

  if (isLoading) return (
    <div className="space-y-4">
      <SkeletonBlock className="h-8 w-64" />
      <div className="grid grid-cols-2 gap-4">
        <SkeletonBlock className="h-48 rounded-3xl" />
        <SkeletonBlock className="h-48 rounded-3xl" />
      </div>
    </div>
  );

  if (loadError) return <ErrorState message={loadError} onRetry={() => window.location.reload()} />;

  const tabs: Array<{ id: ComparisonTab; label: string }> = [
    { id: "aggregate", label: "Aggregate" },
    { id: "tests", label: "Tests" },
    { id: "traces", label: "Traces" },
  ];

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.06 } } }}
      className="space-y-5"
    >
      {/* Header */}
      <motion.div variants={sectionVariants} className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button type="button" onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.06] flex items-center justify-center text-neutral-500 hover:text-neutral-300 transition-all active:scale-[0.95]">
            <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
          </button>
          <div>
            <h2 className="text-sm font-semibold text-neutral-100 tracking-tight">Run Comparison</h2>
            <p className="text-[11px] text-neutral-600 font-mono">{runId.slice(0, 8)} vs {compareId.slice(0, 8)}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" className="px-2.5 py-1.5 rounded-lg text-[10px] text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all flex items-center gap-1">
            <Share2 className="w-3 h-3" strokeWidth={1.5} />Share
          </button>
          <button type="button" className="px-2.5 py-1.5 rounded-lg text-[10px] text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all flex items-center gap-1">
            <Download className="w-3 h-3" strokeWidth={1.5} />Export
          </button>
        </div>
      </motion.div>

      {/* Run headers */}
      <motion.div variants={sectionVariants} className="grid grid-cols-2 gap-4">
        {[currentRun, compareRun].map((run, i) => run ? (
          <div key={i} className={cn("border rounded-3xl bg-surface p-4", i === 0 ? "border-emerald-500/20" : "border-white/[0.06]")}>
            <div className="flex items-center gap-2 mb-1">
              {i === 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono border border-emerald-500/20">current</span>}
              <span className="text-xs font-mono font-medium text-neutral-200">{run.id.slice(0, 8)}</span>
              <span className={cn("text-[10px] font-mono", run.status === "completed" ? "text-emerald-400" : "text-red-400")}>{run.status}</span>
            </div>
            <p className="text-[10px] text-neutral-600 font-mono">{new Date(run.createdAt).toLocaleString()}</p>
          </div>
        ) : null)}
      </motion.div>

      {/* Tabs */}
      <motion.div variants={sectionVariants} className="flex items-center gap-0.5 border-b border-white/[0.06]">
        {tabs.map((t) => (
          <button key={t.id} type="button" onClick={() => setTab(t.id)}
            className={cn("px-4 py-2 rounded-t-lg text-[11px] font-medium transition-all", tab === t.id ? "bg-white/[0.04] text-neutral-200 border border-white/[0.06] border-b-transparent -mb-px" : "text-neutral-500 hover:text-neutral-400")}>
            {t.label}
          </button>
        ))}
      </motion.div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] as const }}>

          {tab === "aggregate" && aggregated && (
            <div className="border border-white/[0.06] rounded-3xl bg-surface p-4 divide-y divide-white/[0.06]">
              {Object.entries(aggregated).map(([key, val]) => (
                <DiffValue key={key} label={key.charAt(0).toUpperCase() + key.slice(1)}
                  current={val.current} previous={val.previous}
                  higherIsBetter={val.higherIsBetter} />
              ))}
            </div>
          )}

          {tab === "tests" && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-600" strokeWidth={1.5} />
                  <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tests..."
                    className="w-full h-8 pl-8 pr-3 rounded-lg bg-white/[0.02] border border-white/[0.06] text-xs text-neutral-300 placeholder:text-neutral-600 outline-none focus:border-white/[0.12] transition-colors" />
                </div>
                {(["all", "regression", "fixed", "new", "removed"] as const).map((f) => (
                  <button key={f} type="button" onClick={() => setDiffFilter(f)}
                    className={cn("px-2 py-1 rounded-md text-[10px] font-medium transition-all capitalize", diffFilter === f ? "bg-white/[0.08] text-neutral-200" : "text-neutral-500 hover:text-neutral-400")}>{f}</button>
                ))}
              </div>

              {diffTests.length === 0 ? (
                <div className="flex flex-col items-center py-10 text-center">
                  <GitCompare className="w-8 h-8 text-neutral-600 mb-2" strokeWidth={1.2} />
                  <p className="text-xs text-neutral-500">No test diffs match your filter</p>
                </div>
              ) : (
                <div className="border border-white/[0.06] rounded-3xl bg-surface divide-y divide-white/[0.06]">
                  {diffTests.map((test) => {
                    const catColors: Record<DiffCategory, string> = {
                      regression: "border-l-red-400/40 bg-red-500/[0.02]",
                      fixed: "border-l-emerald-400/40 bg-emerald-500/[0.02]",
                      new: "border-l-zinc-400/40 bg-zinc-500/[0.02]",
                      removed: "border-l-neutral-500/40 bg-white/[0.01]",
                      unchanged: "border-l-transparent",
                    };
                    const catLabels: Record<DiffCategory, string> = {
                      regression: "regression", fixed: "fixed", new: "new", removed: "removed", unchanged: "",
                    };
                    return (
                      <div key={test.name} className={cn("px-4 py-2.5 border-l-2", catColors[test.category])}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 min-w-0">
                            {test.category === "regression" ? <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" strokeWidth={1.5} />
                              : test.category === "fixed" ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" strokeWidth={1.5} />
                              : test.category === "new" ? <ArrowUp className="w-3.5 h-3.5 text-zinc-400 shrink-0" strokeWidth={2} />
                              : <Minus className="w-3.5 h-3.5 text-neutral-500 shrink-0" strokeWidth={2} />}
                            <span className="text-xs text-neutral-200 truncate font-medium">{test.name}</span>
                            {catLabels[test.category] && (
                              <span className={cn("text-[9px] px-1.5 py-0.5 rounded font-mono font-medium",
                                test.category === "regression" ? "bg-red-500/10 text-red-400" :
                                test.category === "fixed" ? "bg-emerald-500/10 text-emerald-400" :
                                test.category === "new" ? "bg-zinc-500/10 text-zinc-400" :
                                "bg-neutral-500/10 text-neutral-500")}>{catLabels[test.category]}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 shrink-0 text-[10px] text-neutral-600 font-mono tabular-nums">
                            {test.previous && <span>{formatDuration(test.previous.duration)}</span>}
                            {test.current && <span>{formatDuration(test.current.duration)}</span>}
                          </div>
                        </div>
                        {test.current?.error && (
                          <p className="text-[10px] text-red-300 font-mono mt-1 ml-6 line-clamp-1">{test.current.error}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {tab === "traces" && (
            <div className="grid grid-cols-2 gap-4">
              {[
                { label: `${runId.slice(0, 8)} (current)`, events: currentEvents },
                { label: `${compareId.slice(0, 8)} (previous)`, events: compareEvents },
              ].map((side, i) => (
                <div key={i} className="border border-white/[0.06] rounded-3xl bg-surface p-3">
                  <p className="text-[10px] text-neutral-500 font-mono mb-3">{side.label}</p>
                  <div className="space-y-1 max-h-[300px] overflow-y-auto">
                    {side.events.slice(0, 30).map((e) => (
                      <div key={e.id} className="flex items-center gap-2 text-[10px] text-neutral-500 font-mono">
                        <span className="w-2 h-2 rounded-full bg-neutral-600 shrink-0" />
                        <span className="truncate">{e.eventType.replace(":start", "").replace(":end", "")}</span>
                      </div>
                    ))}
                    {side.events.length === 0 && <p className="text-[10px] text-neutral-600 text-center py-4">No trace events</p>}
                  </div>
                </div>
              ))}
            </div>
          )}

        </motion.div>
      </AnimatePresence>

      {/* Footer */}
      <motion.div variants={sectionVariants}
        className="border-t border-white/[0.06] pt-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button type="button" className="px-3 py-1.5 rounded-lg text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium hover:bg-amber-500/20 transition-all active:scale-[0.95] flex items-center gap-1">
            <Bug className="w-3 h-3" strokeWidth={1.5} />Create issue from regressions
          </button>
            <button type="button" onClick={() => router.push(`/history/${runId}`)} className="px-3 py-1.5 rounded-lg text-[10px] text-neutral-500 hover:text-neutral-300 border border-white/[0.06] transition-all flex items-center gap-1">
            <ExternalLink className="w-3 h-3" strokeWidth={1.5} />Open current run
          </button>
        </div>
        <span className="text-[10px] text-neutral-600 font-mono">{diffTests.filter((t) => t.category === "regression").length} regressions</span>
      </motion.div>
    </motion.div>
  );
}
