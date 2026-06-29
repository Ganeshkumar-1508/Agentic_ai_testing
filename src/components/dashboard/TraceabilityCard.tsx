"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface TypeStats {
  total: number;
  passed: number;
  failed: number;
  pending: number;
}

interface TraceabilityData {
  by_type: Record<string, TypeStats>;
  total_requirements: number;
  linked_pct: number;
}

const TYPE_ORDER = ["unit", "integration", "e2e", "contract"];

export function TraceabilityCard() {
  const { data, isLoading } = useQuery<TraceabilityData>({
    queryKey: ["dashboard-traceability"],
    queryFn: () => api.get<TraceabilityData>("/api/dashboard/widgets/traceability"),
    refetchInterval: 120_000,
  });

  const byType = data?.by_type ?? {};
  const linkedPct = data?.linked_pct ?? 0;
  const totalReqs = data?.total_requirements ?? 0;

  const types = TYPE_ORDER.filter((t) => byType[t]).slice(0, 4);
  const hasData = types.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.85, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Traceability</div>
        <div className="text-[11px] font-mono text-emerald-400">
          {linkedPct > 0 ? `${linkedPct}% linked` : "—"}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2.5 flex-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-5 rounded shimmer-bg" />
          ))}
        </div>
      ) : !hasData ? (
        <div className="text-xs text-neutral-600 text-center py-6 flex-1 flex items-center justify-center">
          {totalReqs > 0
            ? `${totalReqs} requirements, no tests linked yet.`
            : "No requirements or test cases yet."}
        </div>
      ) : (
        <>
          <div className="text-[10px] font-semibold text-neutral-600 uppercase tracking-wider mb-2.5 shrink-0">
            By Test Type
          </div>
          <div className="space-y-2.5 flex-1 min-h-0">
            {types.map((ttype, i) => {
              const stats = byType[ttype];
              const total = Math.max(stats.total, 1);
              const passedPct = (stats.passed / total) * 100;
              const failedPct = (stats.failed / total) * 100;
              const pendingPct = (stats.pending / total) * 100;
              return (
                <motion.div
                  key={ttype}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.9 + i * 0.04 }}
                  className="flex items-center gap-2 text-[11px]"
                >
                  <span className="text-neutral-400 capitalize min-w-[70px]">
                    {ttype}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden flex">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${passedPct}%` }}
                      transition={{ delay: 1.0 + i * 0.05, duration: 0.5 }}
                      className="h-full bg-emerald-400"
                    />
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${failedPct}%` }}
                      transition={{ delay: 1.05 + i * 0.05, duration: 0.5 }}
                      className="h-full bg-red-400"
                    />
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${pendingPct}%` }}
                      transition={{ delay: 1.1 + i * 0.05, duration: 0.5 }}
                      className="h-full bg-neutral-700"
                    />
                  </div>
                  <span className="text-neutral-500 font-mono shrink-0 w-8 text-right">
                    {stats.total}
                  </span>
                </motion.div>
              );
            })}
          </div>
          <div className="border-t border-white/[0.04] mt-3 pt-3 flex items-center gap-3 text-[10px] shrink-0">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm bg-emerald-400" />
              <span className="text-neutral-500">Passed</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm bg-red-400" />
              <span className="text-neutral-500">Failed</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm bg-neutral-700" />
              <span className="text-neutral-500">Pending</span>
            </span>
          </div>
        </>
      )}
    </motion.div>
  );
}
