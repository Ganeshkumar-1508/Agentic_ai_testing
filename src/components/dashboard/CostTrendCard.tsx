"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface DailyCost {
  day: string;
  cost: number;
  total_tokens: number;
}

interface CostTrendData {
  days: DailyCost[];
}

export function CostTrendCard() {
  const { data, isLoading } = useQuery<CostTrendData>({
    queryKey: ["dashboard-cost-trend"],
    queryFn: () => api.get<CostTrendData>("/api/cost/daily-trend"),
    refetchInterval: 60_000,
  });

  const days = data?.days ?? [];
  const total = days.reduce((s, d) => Number(s) + Number(d.cost || 0), 0);
  const avg = days.length > 0 ? total / days.length : 0;

  let peak = { cost: 0, label: "—" };
  if (days.length > 0) {
    const maxDay = days.reduce((a, b) => (Number(b.cost) > Number(a.cost) ? b : a));
    peak = {
      cost: Number(maxDay.cost || 0),
      label: maxDay.day
        ? new Date(maxDay.day).toLocaleDateString("en-US", { weekday: "short" })
        : "—",
    };
  }

  const maxCost = Math.max(0.01, ...days.map((d) => Number(d.cost || 0)));
  const hasData = days.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.6, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="card-label">Cost Trend (30d)</div>
        <div className="text-[11px] font-mono text-neutral-400">
          {hasData ? `$${total.toFixed(2)} total` : "—"}
        </div>
      </div>

      <div className="flex items-baseline justify-between mb-3 shrink-0">
        <div>
          <div className="text-2xl font-semibold font-mono text-neutral-100">
            ${avg.toFixed(2)}
          </div>
          <div className="text-[10px] text-neutral-500 mt-0.5">avg daily</div>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold font-mono text-emerald-400">
            ${peak.cost.toFixed(2)}
          </div>
          <div className="text-[10px] text-neutral-500 mt-0.5">peak ({peak.label})</div>
        </div>
      </div>

      {isLoading ? (
        <div className="h-12 rounded shimmer-bg flex-1" />
      ) : !hasData ? (
        <div className="h-12 flex items-center justify-center text-xs text-neutral-600 flex-1">
          No cost data in the last 30 days.
        </div>
      ) : (
        <div className="flex items-end gap-[2px] h-12 flex-1">
          {days.map((d, i) => {
            const h = (Number(d.cost || 0) / maxCost) * 100;
            const isPeak = Number(d.cost) === peak.cost && peak.cost > 0;
            return (
              <motion.div
                key={`${d.day}-${i}`}
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: `${Math.max(h, 4)}%`, opacity: 1 }}
                transition={{ delay: 0.7 + i * 0.015, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className={cn(
                  "flex-1 min-w-[2px] rounded-sm",
                  isPeak ? "bg-emerald-400" : "bg-emerald-500/15"
                )}
                title={`${d.day}: $${Number(d.cost || 0).toFixed(4)}`}
              />
            );
          })}
        </div>
      )}

      <div className="flex justify-between mt-2 text-[10px] font-mono text-neutral-600 shrink-0">
        <span>30d ago</span>
        <span>Today</span>
      </div>
    </motion.div>
  );
}
