"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { Search, ExternalLink } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface RunRecord {
  id: string;
  status: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
  duration: number;
  createdAt: string;
}

const FILTERS = ["All", "Passed", "Failed"] as const;

export function RecentRunsTable() {
  const router = useRouter();
  const [filter, setFilter] = useState<string>("All");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["recent-runs"],
    queryFn: async () => {
      const json = await api.get<{ runs: RunRecord[] }>("/api/runs?limit=50&offset=0");
      return json?.runs ?? [];
    },
    staleTime: 30_000,
  });

  const filtered = useMemo(() => {
    let items = data ?? [];
    if (filter === "Passed") items = items.filter((r) => r.status === "completed");
    if (filter === "Failed") items = items.filter((r) => r.status === "failed");
    if (search) items = items.filter((r) => r.id?.toLowerCase().includes(search.toLowerCase()));
    return items.slice(0, 10);
  }, [data, filter, search]);

  if (isLoading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="w-24 h-4 rounded shimmer-bg" />
        {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 rounded-lg shimmer-bg" />)}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="card-label">Recent Runs</div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-500" strokeWidth={1.5} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..." className="w-32 pl-7 pr-2 py-1 text-[11px] rounded-lg bg-white/[0.04] border border-white/[0.06] text-neutral-300 placeholder:text-neutral-600 focus:outline-none focus:border-emerald-500/30" />
          </div>
          {FILTERS.map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={cn("px-2.5 py-1 text-[11px] rounded-lg transition-colors", filter === f ? "bg-emerald-500/15 text-emerald-400" : "text-neutral-500 hover:text-neutral-300")}>
              {f}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="text-sm text-neutral-500 text-center py-8 flex-1 flex items-center justify-center">No runs found.</div>
      ) : (
        <div className="space-y-1 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
          <AnimatePresence>
            {filtered.map((run, i) => {
              const passRate = run.testCount > 0 ? Math.round((run.passedCount / run.testCount) * 100) : 0;
              const isRunning = run.status === "running" || run.status === "pending";
              return (
                <motion.div
                  key={run.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  onClick={() => router.push(`/pipeline/${run.id}`)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/[0.04] transition-colors cursor-pointer group"
                >
                  <span className={cn("w-2 h-2 rounded-full shrink-0", run.status === "completed" ? "bg-emerald-400" : run.status === "failed" ? "bg-red-400" : "bg-amber-400 animate-pulse")} />
                  <span className="flex-1 text-sm font-mono text-neutral-300 truncate min-w-0">{run.id?.slice(0, 8)}</span>
                  <span className="text-xs text-neutral-500 font-mono">{run.duration ?? 0}s</span>
                  <span className={cn("text-xs font-mono w-12 text-right", passRate >= 80 ? "text-emerald-400" : passRate >= 50 ? "text-amber-400" : "text-red-400")}>{passRate}%</span>
                  <ExternalLink className="w-3 h-3 text-neutral-600 opacity-0 group-hover:opacity-100 transition-opacity" strokeWidth={1.5} />
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
      {data && data.length > 10 && (
        <button onClick={() => router.push("/history")} className="w-full mt-3 text-xs text-neutral-500 hover:text-neutral-300 transition-colors text-center py-2 shrink-0">
          View all {data.length} runs
        </button>
      )}
    </motion.div>
  );
}
