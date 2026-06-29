"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface PipelineSession {
  session_id: string;
  source: string;
  status: string;
  goal: string;
  model: string;
  depth: number;
  role: string;
  started_at: string;
  ended_at: string | null;
  end_reason: string | null;
  tokens: number;
  cost: number;
}

const STATUS_STYLES: Record<string, { dot: string; badge: string }> = {
  running: { dot: "bg-emerald-400 animate-pulse", badge: "bg-emerald-500/10 text-emerald-400" },
  completed: { dot: "bg-emerald-400", badge: "bg-emerald-500/10 text-emerald-400" },
  failed: { dot: "bg-red-400", badge: "bg-red-500/10 text-red-400" },
  pending: { dot: "bg-amber-400 animate-pulse", badge: "bg-amber-500/10 text-amber-400" },
  awaiting_approval: { dot: "bg-amber-400", badge: "bg-amber-500/10 text-amber-400" },
};

export function PipelineFeedCard() {
  const { data: pipelineActivity, isLoading } = useQuery<{ sessions: PipelineSession[] }>({
    queryKey: ["pipeline-activity-feed"],
    queryFn: () => api.get<{ sessions: PipelineSession[] }>("/api/pipeline-activity/recent?limit=10"),
    refetchInterval: 15_000,
  });

  const sessions = pipelineActivity?.sessions ?? [];
  const running = sessions.filter((s) => s.status === "running").length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.35, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="border border-white/[0.06] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="card-label">Active Pipelines</div>
        {running > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 relative">
              <span className="absolute inset-[-2px] rounded-full bg-emerald-400/40 animate-ping" />
            </span>
            <span className="text-[11px] text-emerald-400">{running} running</span>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2 flex-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-7 rounded shimmer-bg" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-xs text-muted-foreground text-center py-8 flex-1 flex items-center justify-center">
          No pipeline activity yet.
        </div>
      ) : (
        <div className="space-y-0 flex-1 overflow-y-auto -mr-1 pr-1">
          {Array.isArray(sessions) && sessions.slice(0, 8).map((s, i) => {
            const styles = STATUS_STYLES[s.status] || STATUS_STYLES.pending;
            return (
              <motion.div
                key={s.session_id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + i * 0.04 }}
                className="flex items-center gap-[10px] py-2 text-[11px] border-b border-white/[0.06] last:border-0"
              >
                <span className={cn("w-1.5 h-1.5 rounded-full shrink-0 relative", styles.dot === "bg-emerald-400 animate-pulse" ? "bg-emerald-400" : styles.dot)}>
                  {styles.dot.includes("animate-pulse") && <span className="absolute inset-[-2px] rounded-full bg-emerald-400/40 animate-ping" />}
                </span>
                <span className="text-muted-foreground font-mono w-[100px] truncate shrink-0">
                  {(s.session_id ?? "").slice(0, 12)}
                </span>
                <span className="text-zinc-400 flex-1 truncate">
                  {s.goal?.slice(0, 60) || "\u2014"}
                </span>
                <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-[6px] uppercase tracking-[0.3px] shrink-0", styles.badge)}>
                  {s.status}
                </span>
                {s.cost > 0 && (
                  <span className="text-zinc-600 font-mono shrink-0 w-[70px] text-right">
                    ${s.cost.toFixed(4)}
                  </span>
                )}
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
