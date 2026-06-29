"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Archive, RotateCcw, CheckCircle, Clock } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface Checkpoint {
  phase: string;
  eventCursor: number;
  createdAt: string;
}

interface CheckpointTimelineProps {
  runId: string;
  currentPhase?: string;
}

const PHASE_ORDER = ["enter", "analyze", "setup", "work", "review", "publish", "persist"];
const PHASE_LABELS: Record<string, string> = {
  enter: "ENTER", analyze: "ANALYZE", setup: "SETUP", work: "WORK",
  review: "REVIEW", publish: "PUBLISH", persist: "PERSIST",
};

export function CheckpointTimeline({ runId, currentPhase }: CheckpointTimelineProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["checkpoints", runId],
    queryFn: async () => {
      const json = await api.get<{ checkpoints: Checkpoint[] }>(`/api/runs/${runId}/checkpoints`);
      return json?.checkpoints ?? [];
    },
    enabled: !!runId,
  });

  if (isLoading) {
    return <div className="h-12 rounded-xl shimmer-bg" />;
  }

  if (!data || data.length === 0) return null;

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Archive className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
        <span className="text-[10px] font-semibold text-zinc-100 uppercase tracking-wider">Checkpoints</span>
        <span className="text-[9px] font-mono text-zinc-600">{data.length} saved</span>
      </div>
      <div className="flex items-center gap-1.5">
        {PHASE_ORDER.map((phase) => {
          const cp = data.find((c) => c.phase === phase);
          const isCurrent = phase === currentPhase;
          return (
            <div key={phase} className="flex items-center gap-0">
              <div className={cn(
                "flex flex-col items-center gap-0.5 px-1.5 py-1 rounded-lg transition-colors",
                cp ? "bg-emerald-500/8" : isCurrent ? "bg-amber-500/8" : "opacity-30",
              )}>
                {cp ? (
                  <CheckCircle className="w-3 h-3 text-emerald-400" strokeWidth={1.5} />
                ) : isCurrent ? (
                  <Clock className="w-3 h-3 text-amber-400" strokeWidth={1.5} />
                ) : (
                  <div className="w-3 h-3 rounded-full bg-zinc-700" />
                )}
                <span className={cn("text-[7px] font-mono", cp ? "text-emerald-400/60" : "text-zinc-600")}>
                  {PHASE_LABELS[phase] ?? phase}
                </span>
              </div>
              {phase !== "persist" && (
                <div className={cn("w-3 h-px", cp ? "bg-emerald-400/20" : "bg-zinc-800")} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
