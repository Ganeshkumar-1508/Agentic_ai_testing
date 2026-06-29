"use client";

import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, GitPullRequest, Beaker, CheckCircle, XCircle, FileText } from "lucide-react";

import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface TraceItem {
  sessionId: string;
  prompt: string;
  status: string;
  runId?: string;
  runStatus?: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
}

export function TraceabilityChain() {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: runs, isLoading } = useQuery({
    queryKey: ["traceability"],
    queryFn: async () => {
      const [runsRes, sessionsRes] = await Promise.all([
        api.get<{ runs: any[] }>(`/api/runs?limit=50&offset=0`),
        api.get<{ sessions: any[] }>(`/api/sessions?limit=50`),
      ]);
      const runsList = runsRes?.runs ?? [];
      const sessionsList = sessionsRes?.sessions ?? [];

      // Build traceability chain: sessions → runs
      const traces: TraceItem[] = sessionsList.map((s: any) => {
        const relatedRuns = runsList.filter((r: any) => r.workflowId === s.id);
        return {
          sessionId: s.id ?? "",
          prompt: (s.prompt ?? "").slice(0, 120),
          status: s.status ?? "unknown",
          runId: relatedRuns[0]?.id,
          runStatus: relatedRuns[0]?.status,
          testCount: Number(relatedRuns[0]?.testCount ?? 0),
          passedCount: Number(relatedRuns[0]?.passedCount ?? 0),
          failedCount: Number(relatedRuns[0]?.failedCount ?? 0),
        };
      });

      return traces;
    },
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-6 space-y-4">
        <div className="w-48 h-4 rounded-full shimmer-bg" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  if (!runs || runs.length === 0) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-6 text-center py-12">
        <GitPullRequest className="w-8 h-8 text-neutral-600 mx-auto mb-3" strokeWidth={1.5} />
        <p className="text-sm text-neutral-500">No traceability data available yet.</p>
        <p className="text-xs text-neutral-600 mt-1">Run a pipeline to start building the traceability chain.</p>
      </div>
    );
  }

  const totalTests = runs.reduce((s, t) => s + t.testCount, 0);
  const totalPassed = runs.reduce((s, t) => s + t.passedCount, 0);
  const totalFailed = runs.reduce((s, t) => s + t.failedCount, 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-3xl p-6"
    >
      <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider mb-4">
        Traceability Chain
      </div>

      <div className="space-y-2">
        {runs.slice(0, 10).map((trace, i) => (
          <motion.div
            key={trace.sessionId}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <button
              onClick={() => setExpanded(expanded === trace.sessionId ? null : trace.sessionId)}
              className="w-full text-left bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.06] rounded-xl p-4 transition-colors"
            >
              {/* Header: Session → Run */}
              <div className="flex items-center gap-3">
                <FileText className="w-4 h-4 text-emerald-400 shrink-0" strokeWidth={1.5} />
                <span className="text-sm font-mono text-neutral-300 truncate">{trace.prompt}</span>
                <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-mono shrink-0", trace.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400")}>
                  {trace.status}
                </span>
                <ChevronDown className={cn("w-3.5 h-3.5 text-neutral-500 shrink-0 transition-transform ml-auto", expanded === trace.sessionId && "rotate-180")} strokeWidth={1.5} />
              </div>

              {/* Expanded detail */}
              <AnimatePresence>
                {expanded === trace.sessionId && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-3 pt-3 border-t border-white/[0.06] space-y-2">
                      {/* Pipeline Run */}
                      <div className="flex items-center gap-3 pl-4">
                        <Beaker className="w-3.5 h-3.5 text-neutral-500 shrink-0" strokeWidth={1.5} />
                        <span className="text-xs text-neutral-400 font-mono">Run: {trace.runId?.slice(0, 12) ?? "N/A"}</span>
                        {trace.runStatus && (
                          <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-mono", trace.runStatus === "completed" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400")}>
                            {trace.runStatus}
                          </span>
                        )}
                      </div>
                      {/* Test Results */}
                      {trace.testCount > 0 && (
                        <div className="flex items-center gap-3 pl-8">
                          <span className="text-xs text-neutral-500">{trace.testCount} tests</span>
                          <span className="text-xs text-emerald-400">{trace.passedCount} passed</span>
                          {trace.failedCount > 0 && <span className="text-xs text-red-400">{trace.failedCount} failed</span>}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </button>
          </motion.div>
        ))}
      </div>

      {/* Summary */}
      <div className="mt-4 pt-3 border-t border-white/[0.06] flex items-center gap-4 text-xs text-neutral-500">
        <span>{runs.length} sessions</span>
        <span>{totalTests} tests</span>
        <span className="text-emerald-400">{totalPassed} passed</span>
        {totalFailed > 0 && <span className="text-red-400">{totalFailed} failed</span>}
      </div>
    </motion.div>
  );
}
