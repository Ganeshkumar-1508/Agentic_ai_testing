"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface RoutingEntry {
  model: string;
  calls: number;
  pct: number;
  cost: number;
}

interface ProviderFailoverData {
  circuit_state: "closed" | "open";
  open_providers: string[];
  open_count: number;
  last_failover: { provider: string; message: string; at: string } | null;
  routing: RoutingEntry[];
  total_calls: number;
  days: number;
}

const MODEL_COLORS = ["bg-emerald-400", "bg-zinc-400", "bg-blue-400", "bg-amber-400", "bg-rose-400", "bg-zinc-400"];

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "never";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

export function ProviderFailoverCard() {
  const { data, isLoading } = useQuery<ProviderFailoverData>({
    queryKey: ["dashboard-provider-failover"],
    queryFn: () => api.get<ProviderFailoverData>("/api/dashboard/widgets/provider-failover"),
    refetchInterval: 30_000,
  });

  const isHealthy = data?.circuit_state !== "open";
  const routing = data?.routing ?? [];
  const totalCalls = data?.total_calls ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.55, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Provider Failover</div>
        <div className={cn(
          "text-[11px] font-mono",
          isHealthy ? "text-emerald-400" : "text-amber-400"
        )}>
          {isLoading ? "—" : isHealthy ? "Healthy" : "Degraded"}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2 flex-1">
          <div className="h-4 rounded shimmer-bg w-1/2" />
          <div className="h-3 rounded shimmer-bg w-2/3" />
          <div className="h-3 rounded shimmer-bg w-1/2 mt-4" />
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 mb-2 shrink-0">
            <span className={cn(
              "w-2 h-2 rounded-full",
              isHealthy ? "bg-emerald-400 animate-pulse" : "bg-red-400"
            )} />
            <span className="text-xs text-neutral-300">Circuit {data?.circuit_state ?? "closed"}</span>
            <span className="ml-auto text-[10px] font-mono text-neutral-600">
              {data?.open_count ?? 0} open
            </span>
          </div>

          <div className="text-[10px] text-neutral-500 mb-4 shrink-0">
            {data?.last_failover
              ? `Last failover: ${formatRelative(data.last_failover.at)} (${data.last_failover.provider})`
              : "No failovers in this window"}
          </div>

          <div className="border-t border-white/[0.04] pt-3 flex-1 min-h-0 overflow-y-auto -mr-1 pr-1">
            <div className="text-[10px] font-semibold text-neutral-600 uppercase tracking-wider mb-2.5">
              Model Routing
              <span className="ml-2 text-neutral-700 normal-case font-mono">
                {totalCalls > 0 ? `${totalCalls} calls / ${data?.days ?? 7}d` : "—"}
              </span>
            </div>

            {routing.length === 0 ? (
              <div className="text-xs text-neutral-600 text-center py-4">No routing data yet.</div>
            ) : (
              <div className="space-y-2">
                {routing.slice(0, 5).map((r, i) => (
                  <motion.div
                    key={r.model}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.6 + i * 0.04 }}
                    className="flex items-center gap-2 text-[11px]"
                  >
                    <span className="text-neutral-400 min-w-[90px] truncate font-mono text-[10.5px]">
                      {r.model.replace(/^(openai|anthropic|google|opencode|deepseek)\//i, "")}
                    </span>
                    <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${r.pct}%` }}
                        transition={{ delay: 0.7 + i * 0.05, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                        className={cn("h-full rounded-full", MODEL_COLORS[i % MODEL_COLORS.length])}
                      />
                    </div>
                    <span className="text-neutral-500 font-mono shrink-0 w-10 text-right">
                      {r.pct}%
                    </span>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </motion.div>
  );
}
