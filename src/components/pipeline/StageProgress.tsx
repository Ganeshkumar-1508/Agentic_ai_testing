"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2, Circle, ArrowRight } from "lucide-react";

export interface StageInfo {
  name: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  description: string;
}

const STAGES: StageInfo[] = [
  { name: "setup", label: "Setup", status: "pending", description: "Clone repo, build KG, create board" },
  { name: "execute", label: "Execute", status: "pending", description: "Fix issues, run tests, heal failures" },
  { name: "finalize", label: "Finalize", status: "pending", description: "Review, publish, persist results" },
];

export function StageProgress({ stages = STAGES, className = "" }: { stages?: StageInfo[]; className?: string }) {
  const timelineItems = stages.map((s, i) => ({
    ...s,
    icon: s.status === "completed" ? CheckCircle2 : s.status === "running" ? Loader2 : s.status === "failed" ? Circle : Circle,
    color: s.status === "completed" ? "text-emerald-400" : s.status === "running" ? "text-emerald-400" : s.status === "failed" ? "text-red-400" : "text-zinc-600",
    line: i < stages.length - 1,
  }));

  return (
    <div className={`bg-card border border-white/[0.06] rounded-xl p-5 ${className}`}>
      <div className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-4 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        Pipeline Stages
      </div>
      <div className="space-y-0">
        {timelineItems.map((stage, i) => {
          const Icon = stage.icon;
          return (
            <motion.div
              key={stage.name}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, type: "spring", stiffness: 100, damping: 20 }}
              className="relative flex items-start gap-4 pb-6 last:pb-0"
            >
              {/* Connector line */}
              {stage.line && (
                <div className={`absolute left-[11px] top-7 w-px h-8 ${stage.status === "completed" ? "bg-emerald-500/40" : "bg-zinc-800"}`} />
              )}

              {/* Icon */}
              <div className={`relative mt-0.5 ${stage.color}`}>
                <Icon
                  className={`w-5 h-5 ${stage.status === "running" ? "animate-spin" : ""}`}
                  strokeWidth={1.5}
                />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-[13px] font-medium ${stage.status === "completed" ? "text-emerald-400" : stage.status === "running" ? "text-zinc-100" : stage.status === "failed" ? "text-red-400" : "text-zinc-500"}`}>
                    {stage.label}
                  </span>
                  {stage.status === "running" && (
                    <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-500">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      In progress
                    </span>
                  )}
                  {stage.status === "completed" && (
                    <span className="text-[10px] font-mono text-zinc-600">Done</span>
                  )}
                </div>
                <div className="text-[11px] text-zinc-600 mt-0.5">{stage.description}</div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
