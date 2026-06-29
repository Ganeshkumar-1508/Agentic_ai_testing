"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface Cluster {
  error_pattern: string;
  count: number;
  tests: string[];
  verdict: "defect" | "flake";
  severity: string;
}

interface RCAData {
  total_failures: number;
  defect_count: number;
  flake_count: number;
  cluster_count: number;
  top_defects: Cluster[];
  top_flakes: Cluster[];
  days: number;
}

const VERDICT_STYLES: Record<string, string> = {
  defect: "bg-red-500/15 text-red-400",
  flake: "bg-amber-500/15 text-amber-400",
};

export function RCACard() {
  const { data, isLoading } = useQuery<RCAData>({
    queryKey: ["dashboard-rca-clusters"],
    queryFn: () => api.get<RCAData>("/api/dashboard/widgets/rca-clusters?days=30"),
    refetchInterval: 60_000,
  });

  const defectCount = data?.defect_count ?? 0;
  const flakeCount = data?.flake_count ?? 0;
  const clusterCount = data?.cluster_count ?? 0;
  const topDefects = data?.top_defects ?? [];
  const topFlakes = data?.top_flakes ?? [];
  const topClusters = [...topDefects, ...topFlakes].slice(0, 4);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.8, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Root Cause Analysis</div>
        <div className="text-[11px] font-mono text-neutral-500">
          {data?.days ?? 30}d
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-4 shrink-0">
        {[
          { label: "Defects", value: defectCount, color: "text-red-400", bg: "bg-red-500/[0.06]", border: "border-red-500/15" },
          { label: "Flakes", value: flakeCount, color: "text-amber-400", bg: "bg-amber-500/[0.06]", border: "border-amber-500/15" },
          { label: "Clusters", value: clusterCount, color: "text-emerald-400", bg: "bg-emerald-500/[0.06]", border: "border-emerald-500/15" },
        ].map((s) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.85, duration: 0.3 }}
            className={cn("text-center py-2 rounded-lg border", s.bg, s.border)}
          >
            <div className={cn("text-lg font-semibold font-mono", s.color)}>{s.value}</div>
            <div className="text-[9px] text-neutral-500 uppercase tracking-wider mt-0.5">{s.label}</div>
          </motion.div>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-1.5 flex-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-5 rounded shimmer-bg" />
          ))}
        </div>
      ) : topClusters.length === 0 ? (
        <div className="text-xs text-neutral-600 text-center py-4 flex-1 flex items-center justify-center">No failure clusters in this window.</div>
      ) : (
        <>
          <div className="text-[10px] font-semibold text-neutral-600 uppercase tracking-wider mb-2 shrink-0">
            Top Clusters
          </div>
          <div className="space-y-1.5 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
            {topClusters.map((c, i) => (
              <motion.div
                key={`${c.error_pattern}-${i}`}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.9 + i * 0.04 }}
                className="flex items-center gap-2 text-[11px]"
              >
                <span className={cn("text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0", VERDICT_STYLES[c.verdict] || VERDICT_STYLES.flake)}>
                  {c.verdict}
                </span>
                <span className="flex-1 text-neutral-400 truncate font-mono text-[10.5px]">
                  {c.error_pattern}
                </span>
                <span className="text-neutral-600 font-mono shrink-0">
                  {c.count} {c.count === 1 ? "hit" : "hits"}
                </span>
              </motion.div>
            ))}
          </div>
        </>
      )}
    </motion.div>
  );
}
