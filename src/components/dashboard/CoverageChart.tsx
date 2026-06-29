"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api/api-client";

const CATEGORIES = [
  { key: "line", label: "Line Coverage", color: "#34d399" },
  { key: "branch", label: "Branch Coverage", color: "#60a5fa" },
  { key: "function", label: "Function Coverage", color: "#a78bfa" },
  { key: "statement", label: "Statement Coverage", color: "#fb923c" },
];

function Skeleton() {
  return (
    <div className="border border-white/[0.06] p-6 card-wireframe space-y-4">
      <div className="w-28 h-4 rounded shimmer-bg" />
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="w-28 h-3 rounded shimmer-bg" />
          <div className="flex-1 h-3 rounded-full shimmer-bg" />
          <div className="w-10 h-3 rounded shimmer-bg" />
        </div>
      ))}
    </div>
  );
}

type CoverageData = {
  line: number; branch: number; func: number; stmt: number;
  linePrev: number | null; branchPrev: number | null;
};

export function CoverageChart() {
  const { data, isLoading } = useQuery<CoverageData | null>({
    queryKey: ["coverage-history"],
    queryFn: async () => {
      const json = await api.get<{ reports: any[] }>("/api/coverage/history?limit=30");
      const reports: any[] = json?.reports ?? [];
      if (reports.length === 0) return null;
      const latest = reports[reports.length - 1];
      const prev = reports[reports.length - 2] || null;
      return {
        line: Number(latest.lineCoverage ?? 0),
        branch: Number(latest.branchCoverage ?? 0),
        func: Number(latest.functionCoverage ?? latest.funcCoverage ?? 0),
        stmt: Number(latest.statementCoverage ?? latest.stmtCoverage ?? 0),
        linePrev: prev ? Number(prev.lineCoverage ?? 0) : null,
        branchPrev: prev ? Number(prev.branchCoverage ?? 0) : null,
      };
    },
    staleTime: 30_000,
  });

  const bars = useMemo(() => {
    if (!data) return [];
    const items: Array<{ key: string; label: string; color: string; value: number; prev: number | null }> = [];
    for (const c of CATEGORIES) {
      let value = 0;
      let prev: number | null = null;
      if (c.key === "line") { value = data.line; prev = data.linePrev; }
      else if (c.key === "branch") { value = data.branch; prev = data.branchPrev; }
      else if (c.key === "function") { value = data.func; }
      else if (c.key === "statement") { value = data.stmt; }
      if (value > 0) items.push({ ...c, value, prev });
    }
    return items;
  }, [data]);

  if (isLoading) return <Skeleton />;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="border border-white/[0.06] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Coverage</div>
        {bars.length > 0 && (
          <span className="text-[11px] text-emerald-400">{Math.round(bars.reduce((s, b) => s + b.value, 0) / bars.length)}% avg</span>
        )}
      </div>

      {bars.length === 0 ? (
        <div className="text-xs text-muted-foreground text-center py-8 flex-1 flex items-center justify-center">No coverage data yet. Run a pipeline to see trends.</div>
      ) : (
        <div className="space-y-3 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
          {bars.map((b, i) => (
            <motion.div
              key={b.key}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-center gap-2.5"
            >
              <span className="text-xs text-zinc-400 min-w-[100px]">{b.label}</span>
              <div className="flex-1 h-2 bg-white/[0.04] rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${b.value}%` }}
                  transition={{ delay: i * 0.06 + 0.1, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                  className="h-full rounded-full"
                  style={{ background: b.color }}
                />
              </div>
              <span className="font-mono text-xs text-muted-foreground min-w-[36px] text-right">{b.value}%</span>
            </motion.div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
