"use client";

import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

export function TestResults() {
  const { status, tools } = usePipelineStore();

  const completed = tools.filter((t) => t.status === "completed").length;
  const failed = tools.filter((t) => t.status === "failed").length;
  const total = tools.length;
  const progress = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5 space-y-4">
      <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
        Test Results
      </div>

      {/* Progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-neutral-300">{completed} of {total} tools</span>
          <span className="text-neutral-500 font-mono">{progress.toFixed(0)}%</span>
        </div>
        <div className="h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-emerald-400 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
          />
        </div>
      </div>

      {/* Tool list */}
      <div className="space-y-1">
        {tools.length === 0 && status !== "running" && (
          <div className="text-neutral-600 text-sm text-center py-4">
            No results yet.
          </div>
        )}
        {tools.map((tool, i) => (
          <div
            key={`${tool.name}-${i}`}
            className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.02]"
          >
            <div className="flex items-center gap-2">
              <span className={cn(
                "w-1.5 h-1.5 rounded-full",
                tool.status === "completed" && "bg-emerald-400",
                tool.status === "failed" && "bg-red-400",
                tool.status === "running" && "bg-blue-400 animate-pulse",
                tool.status === "pending" && "bg-neutral-600",
              )} />
              <span className="text-xs text-neutral-300">{tool.name}</span>
            </div>
            <span className={cn(
              "text-[10px] font-medium",
              tool.status === "completed" && "text-emerald-400",
              tool.status === "failed" && "text-red-400",
              tool.status === "running" && "text-blue-400",
              tool.status === "pending" && "text-neutral-500",
            )}>
              {tool.status}
            </span>
          </div>
        ))}
      </div>

      {/* Summary */}
      {total > 0 && (
        <div className="flex items-center gap-4 pt-2 border-t border-white/[0.05]">
          <div className="flex items-center gap-1.5 text-[10px] text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            pass: {completed}
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-red-400">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
            fail: {failed}
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-neutral-500">
            <span className="w-1.5 h-1.5 rounded-full bg-neutral-600" />
            pending: {total - completed - failed}
          </div>
        </div>
      )}
    </div>
  );
}
