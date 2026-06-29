"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCw, Loader2, AlertCircle, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

interface RecentFailure {
  test_name: string;
  error: string;
  created_at: string;
}

interface RecentFailuresProps {
  failures: RecentFailure[];
  loading?: boolean;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

export function RecentFailures({ failures, loading }: RecentFailuresProps) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const rerunAll = useMutation({
    mutationFn: async () => {
      return api.post<{ status: string; rerun: number }>("/api/dashboard/rerun-failed", { run_id: "" });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
      qc.invalidateQueries({ queryKey: ["dashboard-rca-clusters"] });
    },
  });

  if (loading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="flex items-center justify-between">
          <div className="w-32 h-4 rounded shimmer-bg" />
          <div className="w-28 h-6 rounded-full shimmer-bg" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  const items = failures ?? [];
  const hasFailures = items.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />
          <span className="card-label">Recent Failures</span>
          {hasFailures && (
            <span className="px-1.5 py-0.5 rounded-full text-[9px] font-mono bg-red-500/10 text-red-400 border border-red-500/20">
              {items.length}
            </span>
          )}
        </div>
        <button
          onClick={() => rerunAll.mutate()}
          disabled={!hasFailures || rerunAll.isPending}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-semibold uppercase tracking-wider transition-colors",
            "bg-red-500/10 text-red-400 border border-red-500/20",
            "hover:bg-red-500/20 active:scale-[0.97]",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {rerunAll.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />
          ) : (
            <RotateCw className="w-3 h-3" strokeWidth={2} />
          )}
          Re-run all failed
        </button>
      </div>

      {!hasFailures ? (
        <div className="flex-1 flex flex-col items-center justify-center py-8 text-center">
          <AlertTriangle className="w-5 h-5 mb-2 text-zinc-700" strokeWidth={1.5} />
          <p className="text-[12px] text-zinc-600">No recent failures</p>
          <p className="text-[10px] text-zinc-700 mt-1">All test runs are passing</p>
        </div>
      ) : (
        <div className="space-y-2 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
          {items.slice(0, 6).map((f, i) => {
            const isExpanded = !!expanded[i];
            return (
              <motion.button
                key={i}
                type="button"
                onClick={() => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 + i * 0.04 }}
                className={cn(
                  "w-full text-left p-3 rounded-lg border transition-colors",
                  "bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.1]"
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                  <span className="text-[12px] text-zinc-200 truncate flex-1 font-medium">
                    {f.test_name}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-600 shrink-0">
                    {timeAgo(f.created_at)}
                  </span>
                  {isExpanded ? (
                    <ChevronDown className="w-3 h-3 text-zinc-600 shrink-0" strokeWidth={2} />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-zinc-600 shrink-0" strokeWidth={2} />
                  )}
                </div>
                <AnimatePresence>
                  {f.error && (
                    <motion.pre
                      initial={false}
                      animate={{
                        height: isExpanded ? "auto" : 0,
                        opacity: isExpanded ? 1 : 0,
                        marginTop: isExpanded ? 8 : 0,
                      }}
                      transition={{ duration: 0.2 }}
                      className={cn(
                        "text-[10px] font-mono text-red-300/80 overflow-hidden whitespace-pre-wrap",
                        "bg-red-500/[0.04] border border-red-500/10 rounded p-2"
                      )}
                    >
                      {isExpanded ? f.error : f.error.slice(0, 140) + (f.error.length > 140 ? "…" : "")}
                    </motion.pre>
                  )}
                </AnimatePresence>
              </motion.button>
            );
          })}
        </div>
      )}

      {rerunAll.isSuccess && (
        <p className="mt-3 text-[10px] font-mono text-emerald-400">
          Re-run queued · {rerunAll.data?.rerun ?? 0} tests
        </p>
      )}
      {rerunAll.isError && (
        <p className="mt-3 text-[10px] font-mono text-red-400">
          Re-run failed to queue
        </p>
      )}
    </motion.div>
  );
}
