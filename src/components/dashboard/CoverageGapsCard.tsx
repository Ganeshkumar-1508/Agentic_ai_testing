"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface CoverageFile {
  file: string;
  coverage_pct: number;
  lines_covered?: number;
  lines_total?: number;
}

interface CoverageGapsData {
  files: CoverageFile[];
  threshold: number;
  total_files: number;
  below_count: number;
  report_timestamp: string | null;
}

function fileColor(pct: number): string {
  if (pct < 50) return "text-red-400";
  if (pct < 70) return "text-amber-400";
  return "text-neutral-500";
}

export function CoverageGapsCard() {
  const { data, isLoading } = useQuery<CoverageGapsData>({
    queryKey: ["dashboard-coverage-gaps"],
    queryFn: () => api.get<CoverageGapsData>("/api/dashboard/widgets/coverage-gaps?threshold=80"),
    refetchInterval: 120_000,
  });

  const files = data?.files ?? [];
  const threshold = data?.threshold ?? 80;
  const totalFiles = data?.total_files ?? 0;
  const belowCount = data?.below_count ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.75, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Coverage Gaps</div>
        <div className="text-[11px] font-mono text-neutral-500">
          Below {threshold}%
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-1.5 flex-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-4 rounded shimmer-bg" />
          ))}
        </div>
      ) : files.length === 0 ? (
        <div className="text-xs text-neutral-600 text-center py-6 flex-1 flex items-center justify-center">
          {totalFiles > 0
            ? `All ${totalFiles} files above ${threshold}% threshold.`
            : "No coverage report available."}
        </div>
      ) : (
        <>
          <div className="space-y-1.5 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
            {files.slice(0, 6).map((f, i) => (
              <motion.div
                key={f.file}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.8 + i * 0.03 }}
                className="flex items-center gap-2 text-[11px] font-mono"
              >
                <span className={cn("shrink-0 w-9 text-right tabular-nums", fileColor(f.coverage_pct))}>
                  {f.coverage_pct}%
                </span>
                <span className="flex-1 text-neutral-400 truncate">
                  {f.file}
                </span>
              </motion.div>
            ))}
          </div>
          <div className="border-t border-white/[0.04] mt-3 pt-3 text-[11px] text-neutral-500 shrink-0">
            {belowCount} of {totalFiles} files below {threshold}% threshold
          </div>
        </>
      )}
    </motion.div>
  );
}
