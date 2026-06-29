"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { GroupedError } from "@/lib/types/pipeline";
import { AlertTriangle, Bug, Info, ChevronDown, FileCode, Beaker } from "lucide-react";

interface GroupedErrorsProps {
  groups: GroupedError[];
  isLoading?: boolean;
}

function SeverityIcon({ severity }: { severity: GroupedError["severity"] }) {
  if (severity === "error") return <Bug className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />;
  if (severity === "warning") return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />;
  return <Info className="w-3.5 h-3.5 text-blue-400" strokeWidth={1.5} />;
}

export function GroupedErrors({ groups, isLoading }: GroupedErrorsProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5 space-y-4">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-xl shimmer-bg" />
          ))}
        </div>
      </div>
    );
  }

  if (groups.length === 0) {
    return (
      <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <Bug className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          </div>
          <div>
            <div className="text-sm font-medium text-zinc-100">No errors</div>
            <div className="text-xs text-zinc-500">All tests passed without failures</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-xl bg-red-500/10 flex items-center justify-center">
            <Bug className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />
          </div>
          <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">
            Failures
          </span>
          <span className="text-[10px] font-mono text-zinc-600 px-1.5 py-0.5 rounded bg-white/[0.03]">
            {groups.reduce((s, g) => s + g.count, 0)} total
          </span>
        </div>
        <span className="text-[10px] text-zinc-600 font-mono">{groups.length} unique root causes</span>
      </div>

      <div className="space-y-2">
        {groups.map((group, idx) => (
          <motion.div
            key={group.signature}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.03, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "rounded-xl border transition-all duration-200",
              group.severity === "error" ? "border-red-500/15 bg-red-500/[0.03]" :
              group.severity === "warning" ? "border-amber-500/15 bg-amber-500/[0.03]" :
              "border-blue-500/15 bg-blue-500/[0.03]",
              expanded === group.signature ? "ring-1 ring-white/[0.06]" : "",
            )}
          >
            <button
              onClick={() => setExpanded(expanded === group.signature ? null : group.signature)}
              className="w-full flex items-center gap-3 p-3.5 text-left"
            >
              <SeverityIcon severity={group.severity} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={cn(
                    "text-[10px] font-mono font-semibold uppercase tracking-wider",
                    group.severity === "error" ? "text-red-400" :
                    group.severity === "warning" ? "text-amber-400" : "text-blue-400",
                  )}>
                    {group.type}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-600">
                    x{group.count}
                  </span>
                </div>
                <div className="text-xs text-zinc-300 font-mono truncate">
                  {group.message.slice(0, 120)}
                  {group.message.length > 120 ? "..." : ""}
                </div>
              </div>
              <ChevronDown className={cn(
                "w-3.5 h-3.5 text-zinc-600 shrink-0 transition-transform duration-200",
                expanded === group.signature ? "rotate-180" : "",
              )} strokeWidth={1.5} />
            </button>

            <AnimatePresence>
              {expanded === group.signature && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden"
                >
                  <div className="px-3.5 pb-3.5 space-y-2 border-t border-white/[0.04] pt-2.5 mt-1">
                    {group.occurrences.map((occ, oi) => (
                      <div key={oi} className="flex items-start gap-2.5 text-[11px]">
                        <div className="flex items-center gap-1.5 mt-0.5 shrink-0">
                          {occ.testName && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.03] text-zinc-500 font-mono text-[10px]">
                              <Beaker className="w-2.5 h-2.5" strokeWidth={1.5} />
                              {occ.testName}
                            </span>
                          )}
                          {occ.file && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/[0.03] text-zinc-500 font-mono text-[10px]">
                              <FileCode className="w-2.5 h-2.5" strokeWidth={1.5} />
                              {occ.file}{occ.line ? `:${occ.line}` : ""}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                    <div className="text-[11px] font-mono text-zinc-500 leading-relaxed bg-white/[0.02] rounded-lg p-2.5 mt-1 break-all">
                      {group.message}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
