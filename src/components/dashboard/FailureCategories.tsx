"use client";

import { motion } from "framer-motion";

export interface CategoryData {
  count: number;
  pct: number;
  topTests: string[];
}

export interface FailureCategoriesData {
  defects: CategoryData;
  flakes: CategoryData;
  environment: CategoryData;
  unknown: CategoryData;
  total: number;
}

interface FailureCategoriesProps {
  data?: FailureCategoriesData;
  loading?: boolean;
}

const CATEGORY_CONFIG: Array<{
  key: keyof Omit<FailureCategoriesData, "total">;
  label: string;
  borderClass: string;
  countClass: string;
}> = [
  { key: "defects",     label: "Defects",     borderClass: "border-red-500/15",    countClass: "text-red-400" },
  { key: "flakes",      label: "Flakes",      borderClass: "border-amber-500/15",  countClass: "text-amber-400" },
  { key: "environment", label: "Environment", borderClass: "border-blue-500/15",   countClass: "text-blue-400" },
  { key: "unknown",     label: "Unknown",     borderClass: "border-white/[0.06]",  countClass: "text-zinc-500" },
];

export function FailureCategories({ data, loading }: FailureCategoriesProps) {
  if (loading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="w-28 h-4 rounded shimmer-bg" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 rounded-lg shimmer-bg" />
          ))}
        </div>
      </div>
    );
  }

  const hasData = data && data.total > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="card-label">Failure Categories</div>
        {data && (
          <span className="text-[10px] font-mono text-zinc-600">
            {data.total} total
          </span>
        )}
      </div>

      {!hasData ? (
        <div className="text-sm text-neutral-500 text-center py-6 flex-1 flex items-center justify-center">
          No failures yet.
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 flex-1 min-h-0">
          {CATEGORY_CONFIG.map(({ key, label, borderClass, countClass }) => {
            const cat = data![key];
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className={`p-3 rounded-lg border ${borderClass} flex flex-col gap-1.5 min-h-0`}
              >
                <div className={`text-2xl font-bold font-mono tabular-nums ${countClass}`}>
                  {cat.count}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                  {label}
                </div>
                <div className="text-[9px] font-mono text-zinc-600">
                  {cat.pct.toFixed(1)}%
                </div>
                {cat.topTests.length > 0 && (
                  <div className="mt-1 text-[10px] text-zinc-500 space-y-0.5 overflow-hidden">
                    {cat.topTests.slice(0, 3).map((t, i) => (
                      <div key={i} className="truncate font-mono">
                        {t}
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
