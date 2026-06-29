"use client";

import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

export function SubAgentPanel() {
  const { events } = usePipelineStore();

  const delegateEvents = events.filter(
    (e) => e.type === "tool_calls" || e.type === "tool_result" || e.type === "ToolExecutionStarted" || e.type === "ToolExecutionCompleted"
  );

  const subAgents = delegateEvents
    .filter((e) => e.type === "tool_calls")
    .flatMap((e) => e.calls.filter((c) => c.function.name === "delegate_task"));

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] p-5 space-y-4">
      <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
        Sub-Agents
      </div>

      <AnimatePresence mode="wait">
        {subAgents.length === 0 ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-neutral-600 text-sm text-center py-6"
          >
            No sub-agent delegations yet.
          </motion.div>
        ) : (
          <motion.div key="list" className="space-y-2">
            {subAgents.map((sa, i) => {
              let goal = "";
              try {
                goal = JSON.parse(sa.function.arguments || "{}").goal || "";
              } catch {
                goal = sa.function.arguments?.slice(0, 100) || "";
              }

              return (
                <motion.div
                  key={`${sa.id}-${i}`}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-neutral-100">delegate_task</span>
                    <span className="text-[10px] text-neutral-500 font-mono">{sa.id.slice(0, 8)}</span>
                  </div>
                  <div className="text-[10px] text-neutral-400">Goal: {goal}</div>
                  <div className="text-[10px] text-neutral-500">
                    Sub-agent runs in isolated context. Final result returned to parent.
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
