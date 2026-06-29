"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface ModelCost {
  model: string;
  session_count: number;
  total_cost: number;
  pct: number;
}

interface CostByModelData {
  models: ModelCost[];
  total_cost: number;
  budget_total: number;
  budget_remaining: number;
  budget_pct_used: number;
  days: number;
}

const MODEL_COLORS = ["bg-emerald-400", "bg-zinc-400", "bg-blue-400", "bg-amber-400", "bg-rose-400", "bg-zinc-400"];

function stripProvider(name: string): string {
  return name.replace(/^(openai|anthropic|google|opencode|deepseek|meta|mistral)\//i, "");
}

export function CostByModelCard() {
  const { data, isLoading } = useQuery<CostByModelData>({
    queryKey: ["dashboard-cost-by-model"],
    queryFn: () => api.get<CostByModelData>("/api/dashboard/widgets/cost-by-model"),
    refetchInterval: 60_000,
  });

  const models = data?.models ?? [];
  const hasData = models.length > 0;
  const budgetPct = data?.budget_pct_used ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.65, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="card-label">Cost by Model</div>
        <div className="text-[11px] font-mono text-neutral-600">{data?.days ?? 30}d</div>
      </div>

      {isLoading ? (
        <div className="space-y-2.5 flex-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-5 rounded shimmer-bg" />
          ))}
        </div>
      ) : !hasData ? (
        <div className="text-xs text-neutral-600 text-center py-6 flex-1 flex items-center justify-center">No model cost data yet.</div>
      ) : (
        <>
          <div className="space-y-2.5 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
            {models.slice(0, 5).map((m, i) => (
              <motion.div
                key={m.model}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.7 + i * 0.04 }}
                className="flex items-center gap-2 text-[11px]"
              >
                <span className="text-neutral-400 min-w-[100px] truncate font-mono text-[10.5px]">
                  {stripProvider(m.model)}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${m.pct}%` }}
                    transition={{ delay: 0.8 + i * 0.05, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                    className={cn("h-full rounded-full", MODEL_COLORS[i % MODEL_COLORS.length])}
                  />
                </div>
                <span className="text-neutral-500 font-mono shrink-0 w-12 text-right">
                  ${m.total_cost.toFixed(2)}
                </span>
              </motion.div>
            ))}
          </div>

          <div className="border-t border-white/[0.04] mt-4 pt-3 shrink-0">
            <div className="flex justify-between text-[11px] mb-1.5">
              <span className="text-neutral-500">Budget remaining</span>
              <span className="text-emerald-400 font-mono">
                ${data?.budget_remaining.toFixed(2)} / ${data?.budget_total.toFixed(2)}
              </span>
            </div>
            <div className="h-1 rounded-full bg-white/[0.04] overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(budgetPct, 100)}%` }}
                transition={{ delay: 1.0, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="h-full rounded-full bg-emerald-400"
              />
            </div>
          </div>
        </>
      )}
    </motion.div>
  );
}
