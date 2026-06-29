"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface Module {
  module: string;
  risk_score: number;
  failure_rate: number;
  coverage_gap: number;
  test_count: number;
  fail_count: number;
  severity: "high" | "medium" | "low";
  badge: string;
}

interface DefectPredictionData {
  modules: Module[];
  high_risk_count: number;
  medium_risk_count: number;
  total_modules: number;
}

const SEVERITY_STYLES: Record<string, { bg: string; border: string; badge: string; text: string }> = {
  high: {
    bg: "bg-red-500/[0.06]",
    border: "border-red-500/15",
    badge: "bg-red-500/15 text-red-400",
    text: "text-red-400",
  },
  medium: {
    bg: "bg-amber-500/[0.06]",
    border: "border-amber-500/15",
    badge: "bg-amber-500/15 text-amber-400",
    text: "text-amber-400",
  },
  low: {
    bg: "bg-transparent",
    border: "border-white/[0.06]",
    badge: "bg-emerald-500/15 text-emerald-400",
    text: "text-emerald-400",
  },
};

export function DefectPredictionCard() {
  const { data, isLoading } = useQuery<DefectPredictionData>({
    queryKey: ["dashboard-defect-prediction"],
    queryFn: () => api.get<DefectPredictionData>("/api/dashboard/widgets/defect-prediction"),
    refetchInterval: 120_000,
  });

  const modules = data?.modules ?? [];
  const highRisk = data?.high_risk_count ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.7, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Defect Prediction</div>
        <div className="text-[11px] font-mono text-neutral-400">
          {highRisk > 0 ? `High risk: ${highRisk}` : "—"}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-1.5 flex-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-9 rounded-lg shimmer-bg" />
          ))}
        </div>
      ) : modules.length === 0 ? (
        <div className="text-xs text-neutral-600 text-center py-6 flex-1 flex items-center justify-center">No modules scored yet.</div>
      ) : (
        <div className="space-y-1.5 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
          {modules.slice(0, 5).map((m, i) => {
            const styles = SEVERITY_STYLES[m.severity] || SEVERITY_STYLES.low;
            return (
              <motion.div
                key={m.module}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.75 + i * 0.04 }}
                className={cn(
                  "flex items-center gap-2.5 px-2.5 py-2 rounded-lg border",
                  styles.bg,
                  styles.border
                )}
              >
                <span className="text-[11px] text-neutral-300 flex-1 truncate font-mono">
                  {m.module}
                </span>
                <span className={cn("text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded", styles.badge)}>
                  {m.severity}
                </span>
                <span className={cn("text-[11px] font-mono w-10 text-right shrink-0", styles.text)}>
                  {m.risk_score.toFixed(2)}
                </span>
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
