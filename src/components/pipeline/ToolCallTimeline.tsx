"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Terminal, Search, Code2, GitBranch, CheckCircle2, XCircle, Clock } from "lucide-react";

export interface ToolCall {
  id: string;
  tool: string;
  input: string;
  status: "running" | "success" | "failed";
  duration?: number;
  timestamp: string;
}

const TOOL_ICONS: Record<string, typeof Terminal> = {
  bash: Terminal,
  // C3.1: CodeGraph MCP tools (4 names, replaces the old kg_* trio).
  // `codegraph_node` gets its own Code2 icon to differentiate it from
  // the search-style tools; the others share the Search icon.
  codegraph_explore: Search,
  codegraph_search: Search,
  codegraph_callers: Search,
  codegraph_node: Code2,
  read_file: Code2,
  write_file: Code2,
  edit_file: Code2,
  git: GitBranch,
};

export function ToolCallTimeline({ calls = [], className = "" }: { calls: ToolCall[]; className?: string }) {
  return (
    <div className={`bg-card border border-white/[0.06] rounded-xl p-5 ${className}`}>
      <div className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-3 flex items-center gap-2">
        <Terminal className="w-3.5 h-3.5" strokeWidth={1.5} />
        Tool Calls
        {calls.length > 0 && (
          <span className="text-[10px] font-mono text-zinc-600 font-normal">{calls.length} total</span>
        )}
      </div>

      <div className="space-y-1 max-h-[320px] overflow-y-auto">
        <AnimatePresence initial={false}>
          {calls.length === 0 ? (
            <div className="py-8 text-center">
              <Terminal className="w-5 h-5 mx-auto mb-2 text-zinc-700" strokeWidth={1.5} />
              <p className="text-[12px] text-zinc-600">Waiting for tool calls...</p>
            </div>
          ) : (
            [...calls].reverse().map((call) => {
              const Icon = TOOL_ICONS[call.tool] || Terminal;
              return (
                <motion.div
                  key={call.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  transition={{ type: "spring", stiffness: 200, damping: 25 }}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.03] transition-colors group"
                >
                  <div className={`shrink-0 ${call.status === "running" ? "text-emerald-400" : call.status === "success" ? "text-emerald-500" : "text-red-400"}`}>
                    {call.status === "running" ? (
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse block" />
                    ) : call.status === "success" ? (
                      <CheckCircle2 className="w-3.5 h-3.5" strokeWidth={2} />
                    ) : (
                      <XCircle className="w-3.5 h-3.5" strokeWidth={2} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Icon className="w-3 h-3 text-zinc-500 shrink-0" strokeWidth={1.5} />
                      <span className="text-[12px] font-mono font-medium text-zinc-300">{call.tool}</span>
                      <span className="text-[10px] text-zinc-600 truncate">{call.input}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {call.duration != null && (
                      <span className="flex items-center gap-1 text-[10px] font-mono text-zinc-600">
                        <Clock className="w-2.5 h-2.5" strokeWidth={1.5} />
                        {call.duration.toFixed(0)}ms
                      </span>
                    )}
                    <span className="text-[9px] font-mono text-zinc-700">{call.timestamp}</span>
                  </div>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
