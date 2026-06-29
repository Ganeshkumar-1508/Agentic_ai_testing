"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { OwnerBadge } from "@/components/history/OwnerBadge";
import { api } from "@/lib/api/api-client";

interface SlowTest {
  testName: string;
  runCount: number;
  avgDurationMs: number;
  maxDurationMs: number;
  passRate: number;
  totalPassed: number;
  totalFailed: number;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

export function SlowestTests() {
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["slowest-tests"],
    queryFn: async () => {
      const json = await api.get<{ tests: SlowTest[] }>(`/api/tests/slowest?limit=10&days=30`);
      return json?.tests ?? [];
    },
    staleTime: 60_000,
  });

  const tests = data ?? [];
  const maxAvg = Math.max(...tests.map((t) => t.avgDurationMs), 1);

  return (
    <div className="bg-surface border border-white/[0.06] rounded-3xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500">
            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
          </svg>
          <span className="text-[13px] font-semibold text-zinc-100">Slowest Tests</span>
          {!isLoading && tests.length > 0 && (
            <span className="text-[10px] text-zinc-600 font-mono">Top {tests.length}</span>
          )}
        </div>
        <svg
          className={cn("w-3.5 h-3.5 text-zinc-600 transition-transform duration-300", open && "rotate-180")}
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-4 space-y-1">
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-9 rounded-lg bg-white/[0.02] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.03] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
                ))
              ) : tests.length === 0 ? (
                <div className="text-[11px] text-zinc-600 text-center py-6">No test data available yet.</div>
              ) : (
                tests.map((t, i) => (
                  <motion.div
                    key={t.testName}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03 }}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.03] transition-colors"
                  >
                    <span className="text-[10px] text-zinc-700 font-mono w-4 shrink-0 text-right">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] text-zinc-300 truncate font-mono">{t.testName}</span>
                        <OwnerBadge testName={t.testName} />
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[9px] text-zinc-600">{t.runCount} runs</span>
                        <span className={cn("text-[9px] font-medium", t.passRate >= 80 ? "text-emerald-500" : t.passRate >= 50 ? "text-amber-500" : "text-red-500")}>
                          {t.passRate}% pass
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="w-20 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-amber-400"
                          style={{ width: `${(t.avgDurationMs / maxAvg) * 100}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-mono text-zinc-300 tabular-nums w-14 text-right">
                        {formatMs(t.avgDurationMs)}
                      </span>
                    </div>
                  </motion.div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
