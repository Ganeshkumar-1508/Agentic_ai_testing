"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { OwnerBadge } from "@/components/history/OwnerBadge";
import { api } from "@/lib/api/api-client";

interface FlakyTest {
  testName: string;
  branch: string;
  totalRuns: number;
  passCount: number;
  failCount: number;
  flakyScore: number;
  isQuarantined: boolean;
  lastHealed: boolean;
  updatedAt: string;
}

export function FlakySection() {
  const { data, isLoading } = useQuery({
    queryKey: ["flaky-tests-top"],
    queryFn: () => api.get<{ flaky: FlakyTest[] }>("/api/testcases/flaky", { limit: "5" }),
    refetchInterval: 60_000,
  });

  const flakyTests = data?.flaky ?? [];

  const handleQuarantine = async () => {
    await api.post("/api/dashboard/flaky/scan");
  };

  if (isLoading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-5 space-y-3">
        <div className="w-32 h-4 rounded-full bg-white/[0.03] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg bg-white/[0.02] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.03] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
        ))}
      </div>
    );
  }

  if (flakyTests.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="bg-surface border border-white/[0.06] rounded-3xl p-5"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <h2 className="text-[13px] font-semibold text-zinc-100">Flaky Tests</h2>
        </div>
        <button
          onClick={handleQuarantine}
          className="px-2.5 py-1 text-[10px] font-medium rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="inline mr-1 -mt-0.5">
            <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          Re-scan
        </button>
      </div>

      <div className="space-y-1">
        {flakyTests.map((t, i) => {
          const passRate = t.totalRuns > 0 ? Math.round((t.passCount / t.totalRuns) * 100) : 0;
          return (
            <motion.div
              key={t.testName}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.03] transition-colors group"
            >
              <span className={cn(
                "w-1.5 h-1.5 rounded-full shrink-0",
                t.isQuarantined ? "bg-amber-400" : "bg-red-400"
              )} />
              <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] text-zinc-300 truncate font-mono">{t.testName}</span>
                          <OwnerBadge testName={t.testName} />
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {t.branch && (
                            <span className="text-[9px] text-zinc-400 font-mono">{t.branch}</span>
                          )}
                          <span className="text-[9px] text-zinc-600">{t.totalRuns} runs</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                <span className={cn(
                  "text-[11px] font-semibold font-mono tabular-nums",
                  t.flakyScore > 0.6 ? "text-red-400" : "text-amber-400"
                )}>
                  {Math.round(t.flakyScore * 100)}%
                </span>
                <div className="w-12 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", passRate >= 50 ? "bg-emerald-400" : "bg-red-400")}
                    style={{ width: `${passRate}%` }}
                  />
                </div>
                {t.isQuarantined && (
                  <span className="text-[8px] px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 uppercase tracking-wider font-medium">Q</span>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
