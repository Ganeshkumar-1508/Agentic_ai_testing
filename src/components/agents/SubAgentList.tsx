"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Bot, ChevronDown, ChevronRight, Clock, CheckCircle, XCircle, RotateCw, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TraceEvent } from "@/lib/hooks/use-trace-events";

interface SubAgentListProps {
  events: TraceEvent[];
  onSelect: (eventId: string) => void;
  className?: string;
}

interface SubAgentEntry {
  id: string;
  task: string;
  result: string;
  mode: string;
  status: string;
  createdAt: string;
}

function extractSubAgents(events: TraceEvent[]): SubAgentEntry[] {
  const entries: SubAgentEntry[] = [];
  for (const e of events) {
    if (e.eventType === "ToolExecutionStarted" || e.eventType === "ToolExecutionCompleted") {
      const d = e.eventData;
      const name = (d.name as string) || (d.toolName as string) || "";
      if (name === "subagent_delegator" || name === "subagent") {
        const result = d.result as string || d.output as string || "";
        if (result) {
          entries.push({
            id: e.id,
            task: (d.task as string) || (d.arguments as string) || "",
            result: result.slice(0, 2000),
            mode: (d.mode as string) || "research",
            status: d.success === false ? "failed" : "completed",
            createdAt: e.createdAt,
          });
        }
      }
    }
  }
  return entries;
}

export function SubAgentList({ events, onSelect, className }: SubAgentListProps) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [modeFilter, setModeFilter] = useState<string>("all");

  const subAgents = useMemo(() => extractSubAgents(events), [events]);

  const filtered = useMemo(() => {
    return subAgents.filter((sa) => {
      if (modeFilter !== "all" && sa.mode !== modeFilter) return false;
      if (search && !sa.task.toLowerCase().includes(search.toLowerCase()) && !sa.result.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [subAgents, search, modeFilter]);

  const modes = useMemo(() => {
    const set = new Set(subAgents.map((sa) => sa.mode));
    return ["all", ...Array.from(set)];
  }, [subAgents]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (subAgents.length === 0) {
    return (
      <div className={cn("border border-white/[0.06] rounded-3xl bg-surface p-6", className)}>
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Bot className="w-8 h-8 text-neutral-600 mb-2" strokeWidth={1.2} />
          <p className="text-xs text-neutral-500">No sub-agents spawned in this run</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("border border-white/[0.06] rounded-3xl bg-surface overflow-hidden", className)}>
      {/* Header with search */}
      <div className="p-3 border-b border-white/[0.06] space-y-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search sub-agents..."
            className="w-full h-8 pl-8 pr-3 rounded-lg bg-white/[0.03] border border-white/[0.06] text-xs text-neutral-300 placeholder:text-neutral-600 outline-none focus:border-white/[0.12] transition-colors"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {modes.map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setModeFilter(mode)}
              className={cn(
                "px-2 py-0.5 rounded-md text-[10px] font-medium transition-all",
                modeFilter === mode
                  ? "bg-white/[0.08] text-neutral-200"
                  : "text-neutral-500 hover:text-neutral-400 bg-white/[0.02]",
              )}
            >
              {mode === "all" ? "All" : mode}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="divide-y divide-white/[0.06] max-h-[400px] overflow-y-auto">
        <AnimatePresence initial={false}>
          {filtered.length === 0 ? (
            <div className="py-8 text-center">
              <p className="text-xs text-neutral-600">No sub-agents match your search</p>
            </div>
          ) : (
            filtered.map((sa, i) => (
              <motion.div
                key={sa.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03, duration: 0.2, ease: [0.16, 1, 0.3, 1] as const }}
              >
                <button
                  type="button"
                  onClick={() => toggleExpand(sa.id)}
                  className="w-full flex items-start gap-2.5 px-3 py-2.5 hover:bg-white/[0.02] transition-colors text-left"
                >
                  {expanded.has(sa.id) ? (
                    <ChevronDown className="w-3 h-3 text-neutral-500 mt-0.5 shrink-0" strokeWidth={1.5} />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-neutral-500 mt-0.5 shrink-0" strokeWidth={1.5} />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "w-1.5 h-1.5 rounded-full shrink-0",
                        sa.status === "completed" ? "bg-emerald-400" : "bg-red-400",
                      )} />
                      <span className="text-xs font-medium text-neutral-300 truncate">
                        {sa.task.slice(0, 80) || "Sub-agent task"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-neutral-500 font-mono">{sa.mode}</span>
                      <span className="text-[10px] text-neutral-600">·</span>
                      <span className="text-[10px] text-neutral-600">{new Date(sa.createdAt).toLocaleTimeString()}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onSelect(sa.id); }}
                    className="shrink-0 px-2 py-0.5 rounded text-[10px] text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all"
                  >
                    View
                  </button>
                </button>

                <AnimatePresence>
                  {expanded.has(sa.id) && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] as const }}
                      className="overflow-hidden"
                    >
                      <div className="px-3 pb-3">
                        <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5 mt-1">
                          <pre className="text-[11px] text-neutral-400 font-mono leading-relaxed whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                            {sa.result}
                          </pre>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-white/[0.06] flex items-center justify-between">
        <span className="text-[10px] text-neutral-600">{filtered.length} of {subAgents.length} sub-agents</span>
      </div>
    </div>
  );
}
