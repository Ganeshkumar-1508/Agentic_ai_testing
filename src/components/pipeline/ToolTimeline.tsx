"use client";

import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <span className="w-2 h-2 rounded-full bg-emerald-400" />;
  if (status === "running") return <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />;
  if (status === "failed") return <span className="w-2 h-2 rounded-full bg-red-400" />;
  return <span className="w-2 h-2 rounded-full bg-neutral-600" />;
}

export function ToolTimeline() {
  const { tools } = usePipelineStore();

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5 space-y-4">
      <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
        Tool Calls
      </div>

      <div className="space-y-2">
        <AnimatePresence>
          {tools.length === 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-neutral-600 text-sm text-center py-6"
            >
              No tool calls yet.
            </motion.div>
          )}
          {tools.map((tool, i) => {
            const duration = tool.endTime && tool.startTime
              ? ((tool.endTime - tool.startTime) / 1000).toFixed(1) + "s"
              : tool.startTime
                ? "running..."
                : "pending";

            return (
              <motion.div
                key={`${tool.name}-${i}`}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className={cn(
                  "flex items-center justify-between px-4 py-3 rounded-xl border transition-colors",
                  tool.status === "completed" && "bg-emerald-500/[0.04] border-emerald-500/10",
                  tool.status === "running" && "bg-blue-500/[0.06] border-blue-500/15",
                  tool.status === "failed" && "bg-red-500/[0.04] border-red-500/10",
                  tool.status === "pending" && "bg-white/[0.02] border-white/[0.04]",
                )}
              >
                <div className="flex items-center gap-3">
                  <StatusIcon status={tool.status} />
                  <div>
                    <div className="text-sm font-medium text-neutral-100">{tool.name}</div>
                    {tool.args && Object.keys(tool.args).length > 0 && (
                      <div className="text-[10px] text-neutral-500 font-mono truncate max-w-[400px]">
                        {(JSON.stringify(tool.args) || "").slice(0, 120)}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-[10px] text-neutral-500 font-mono tabular-nums">{duration}</span>
                    {tool.status === "running" && (
                    <span className="flex gap-0.5">
                      <span className="w-1 h-1 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "0ms" }} />
                      <span className="w-1 h-1 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "150ms" }} />
                      <span className="w-1 h-1 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "300ms" }} />
                    </span>
                  )}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}
