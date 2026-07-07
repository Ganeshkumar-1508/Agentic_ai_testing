"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api/api-client";

function Skeleton() {
  return (
    <div className="border border-white/[0.06] p-6 card-wireframe space-y-3">
      <div className="w-28 h-4 rounded shimmer-bg" />
      <div className="flex gap-[3px] items-end h-[60px]">
        {Array.from({ length: 30 }).map((_, i) => (
          <div key={i} className="flex-1 rounded-sm shimmer-bg" style={{ height: `${20 + ((i * 17 + 7) % 50)}%` }} />
        ))}
      </div>
    </div>
  );
}

export function FlakyScoreTrend() {
  const analyticsQ = useQuery<{ spark_flaky?: number[] }>({
    queryKey: ["analytics-30d"],
    queryFn: () => api.get<{ spark_flaky?: number[] }>(`/api/dashboard/widgets/analytics-30d`),
    staleTime: 60_000,
  });

  const rawData = useMemo(() => {
    const spark = (analyticsQ.data?.spark_flaky as number[] | undefined) ?? [];
    return spark.length >= 2 ? spark : null;
  }, [analyticsQ.data]);

  const isLoading = analyticsQ.isLoading;

  if (isLoading) return <Skeleton />;

  const bars = rawData ?? [];
  const maxVal = Math.max(...bars, 1);
  const current = bars[bars.length - 1] ?? 0;
  const previous = bars.length >= 2 ? bars[bars.length - 2] : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="border border-white/[0.06] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-[0.6px]">Flaky Score Trend</div>
        {previous != null && (
          <span className="text-[11px] text-amber-400 font-mono">
            {current >= previous ? "+" : ""}{Math.round(current - previous)} this week
          </span>
        )}
      </div>

      {bars.length === 0 ? (
        <div className="text-xs text-muted-foreground text-center py-8 flex-1 flex items-center justify-center">No flaky test data available.</div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col justify-end">
          <div className="flex gap-[3px] items-end h-[60px]">
            {bars.map((v, i) => {
              const h = Math.max(4, (v / maxVal) * 100);
              const opacity = 0.15 + (v / maxVal) * 0.6;
              return (
                <motion.div
                  key={i}
                  initial={{ height: 0 }}
                  animate={{ height: `${h}%` }}
                  transition={{ delay: i * 0.01, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  className="flex-1 rounded-sm transition-all hover:opacity-100 cursor-pointer"
                  style={{ background: `rgba(245,158,11,${opacity})` }}
                  title={`${v} flaky tests`}
                />
              );
            })}
          </div>
          <div className="flex justify-between mt-2 text-[10px] font-mono text-zinc-600 shrink-0">
            <span>30 days</span>
            <span>{current} current</span>
          </div>
        </div>
      )}
    </motion.div>
  );
}
