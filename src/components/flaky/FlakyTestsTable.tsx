"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { Search, ChevronDown, Shield, ShieldOff, Bug, HeartPulse } from "lucide-react";

import { toast } from "sonner";
import { api } from "@/lib/api/api-client";

interface FlakyTest {
  testName: string;
  flakyScore: number;
  isQuarantined: boolean;
  totalRuns: number;
  passCount: number;
  failCount: number;
  branch?: string;
  lastHealed?: string;
}

const FILTERS = ["All", "Active", "Quarantined"] as const;
const SORTS = ["Score", "Name", "Pass %", "Runs"] as const;

export function FlakyTestsTable() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("All");
  const [sort, setSort] = useState<string>("Score");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["flaky-tests"],
    queryFn: async () => {
      const json = await api.get<{ flaky: any[] }>(`/api/tests/flaky?limit=50`);
      return (json?.flaky ?? []).map((t: any) => ({
        testName: t.testName ?? "",
        flakyScore: Number(t.flakyScore ?? 0),
        isQuarantined: Boolean(t.isQuarantined),
        totalRuns: Number(t.totalRuns ?? 0),
        passCount: Number(t.passCount ?? 0),
        failCount: Number(t.failCount ?? 0),
        branch: t.branch ?? "main",
        lastHealed: t.lastHealed ?? null,
      })) as FlakyTest[];
    },
    staleTime: 15_000,
  });

  const quarantineMutation = useMutation({
    mutationFn: async ({ testName, quarantine, branch }: { testName: string; quarantine: boolean; branch: string }) => {
      await api.post(`/api/tests/flaky/${testName}/quarantine`, { quarantine, branch });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["flaky-tests"] }),
  });

  const healMutation = useMutation({
    mutationFn: async (testName: string) => {
      await api.post(`/api/tests/heal`, { test_name: testName, language: "python", framework: "pytest" });
    },
  });

  const filtered = useMemo(() => {
    let items = data ?? [];
    if (filter === "Active") items = items.filter((t) => !t.isQuarantined);
    if (filter === "Quarantined") items = items.filter((t) => t.isQuarantined);
    if (search) items = items.filter((t) => t.testName.toLowerCase().includes(search.toLowerCase()));
    items.sort((a, b) => {
      if (sort === "Score") return b.flakyScore - a.flakyScore;
      if (sort === "Name") return a.testName.localeCompare(b.testName);
      if (sort === "Pass %") return (a.passCount / a.totalRuns) - (b.passCount / b.totalRuns);
      if (sort === "Runs") return b.totalRuns - a.totalRuns;
      return 0;
    });
    return items;
  }, [data, filter, search, sort]);

  if (isLoading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-6 space-y-3">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-3xl p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
          Flaky Tests {data ? `(${data.length})` : ""}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" strokeWidth={1.5} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tests..."
              className="w-40 pl-8 pr-3 py-1.5 text-xs rounded-lg bg-white/[0.04] border border-white/[0.06] text-neutral-300 placeholder:text-neutral-600 focus:outline-none focus:border-emerald-500/30"
            />
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="px-2 py-1.5 text-xs rounded-lg bg-white/[0.04] border border-white/[0.06] text-neutral-300 focus:outline-none"
          >
            {SORTS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div className="flex gap-1 mb-4">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn("px-3 py-1.5 text-xs rounded-lg transition-colors", filter === f ? "bg-emerald-500/15 text-emerald-400" : "text-neutral-500 hover:text-neutral-300")}
          >
            {f}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="text-sm text-neutral-500 text-center py-8">
          {search ? "No tests match your search." : "No flaky tests detected. Quality looks good."}
        </div>
      ) : (
        <div className="space-y-1">
          <AnimatePresence>
            {filtered.map((test, i) => {
              const passRate = test.totalRuns > 0 ? Math.round((test.passCount / test.totalRuns) * 100) : 0;
              return (
                <motion.div key={test.testName} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}>
                  <div
                    onClick={() => setExpanded(expanded === test.testName ? null : test.testName)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/[0.04] transition-colors cursor-pointer"
                  >
                    <span className="flex-1 text-sm text-neutral-300 font-mono truncate min-w-0">{test.testName}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="w-16 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                        <div className={cn("h-full rounded-full transition-all", test.flakyScore > 50 ? "bg-red-400" : test.flakyScore > 20 ? "bg-amber-400" : "bg-emerald-400")} style={{ width: `${Math.min(test.flakyScore * 100, 100)}%` }} />
                      </div>
                      <span className={cn("text-xs font-mono w-8 text-right", test.flakyScore > 0.5 ? "text-red-400" : test.flakyScore > 0.2 ? "text-amber-400" : "text-emerald-400")}>
                        {(test.flakyScore * 100).toFixed(0)}
                      </span>
                    </div>
                    <span className="text-xs text-neutral-500 font-mono w-12 text-right shrink-0">{passRate}%</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); quarantineMutation.mutate({ testName: test.testName, quarantine: !test.isQuarantined, branch: test.branch ?? "main" }); }}
                      className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-colors shrink-0", test.isQuarantined ? "bg-amber-500/10 text-amber-400" : "bg-white/[0.04] text-neutral-500 hover:text-neutral-300")}
                    >
                      {test.isQuarantined ? <ShieldOff className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Shield className="w-3.5 h-3.5" strokeWidth={1.5} />}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); healMutation.mutate(test.testName); }}
                      className="w-7 h-7 rounded-lg bg-white/[0.04] hover:bg-emerald-500/10 flex items-center justify-center text-neutral-500 hover:text-emerald-400 transition-colors shrink-0"
                    >
                      <Bug className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </button>
                    <ChevronDown className={cn("w-3.5 h-3.5 text-neutral-500 transition-transform shrink-0", expanded === test.testName && "rotate-180")} strokeWidth={1.5} />
                  </div>

                  <AnimatePresence>
                    {expanded === test.testName && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="mx-3 mb-2 p-4 rounded-xl bg-zinc-950/20 border border-white/[0.06] space-y-2">
                          {test.lastHealed && (
                            <div className="text-xs text-emerald-400/80">
                              Last healed: {test.lastHealed}
                            </div>
                          )}
                          <div className="flex items-center gap-4 text-xs text-neutral-500">
                            <span>{test.totalRuns} total runs</span>
                            <span className="text-emerald-400">{test.passCount} passed</span>
                            {test.failCount > 0 && <span className="text-red-400">{test.failCount} failed</span>}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}
