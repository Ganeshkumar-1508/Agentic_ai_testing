"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, ChevronDown, Code2, Sparkles } from "lucide-react";

interface TestDiff {
  name: string;
  statusA?: string;
  statusB?: string;
  confidence?: number;
  codeA?: string;
  codeB?: string;
}

interface TestDiffTableProps {
  tests: TestDiff[];
  loading?: boolean;
}

const FILTERS = ["All", "Regressed", "Improved", "New"] as const;

export function TestDiffTable({ tests, loading }: TestDiffTableProps) {
  const [filter, setFilter] = useState<string>("All");
  const [expanded, setExpanded] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6 space-y-3">
        <div className="w-24 h-4 rounded-full shimmer-bg" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  const filtered = tests.filter((t) => {
    const regressed = t.statusA === "passed" && t.statusB === "failed";
    const improved = t.statusA === "failed" && t.statusB === "passed";
    const isNew = !t.statusA && t.statusB === "passed";
    if (filter === "Regressed") return regressed;
    if (filter === "Improved") return improved;
    if (filter === "New") return isNew;
    return true;
  });

  const regressedCount = tests.filter((t) => t.statusA === "passed" && t.statusB === "failed").length;
  const improvedCount = tests.filter((t) => t.statusA === "failed" && t.statusB === "passed").length;
  const newCount = tests.filter((t) => !t.statusA && t.statusB === "passed").length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
          Test Diff
        </div>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-3 py-1.5 text-xs rounded-lg transition-colors",
                filter === f ? "bg-emerald-500/15 text-emerald-400" : "text-neutral-500 hover:text-neutral-300"
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="text-sm text-neutral-500 text-center py-8">No tests match this filter.</div>
      ) : (
        <div className="space-y-1">
          <AnimatePresence>
            {filtered.map((test, i) => {
              const regressed = test.statusA === "passed" && test.statusB === "failed";
              const improved = test.statusA === "failed" && test.statusB === "passed";
              const isNew = !test.statusA && test.statusB;
              return (
                <motion.div
                  key={test.name}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <button
                    onClick={() => setExpanded(expanded === test.name ? null : test.name)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/[0.04] transition-colors text-left"
                  >
                    {/* Status A */}
                    <span className="w-14 text-xs font-mono text-center">
                      {test.statusA === "passed" ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400/60 inline" strokeWidth={1.5} /> :
                       test.statusA === "failed" ? <XCircle className="w-3.5 h-3.5 text-red-400/60 inline" strokeWidth={1.5} /> :
                       <span className="text-neutral-600">—</span>}
                    </span>
                    {/* Status B */}
                    <span className="w-14 text-xs font-mono text-center">
                      {test.statusB === "passed" ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 inline" strokeWidth={1.5} /> :
                       test.statusB === "failed" ? <XCircle className="w-3.5 h-3.5 text-red-400 inline" strokeWidth={1.5} /> :
                       <span className="text-neutral-600">—</span>}
                    </span>
                    {/* Test name */}
                    <span className="flex-1 text-sm text-neutral-300 font-mono truncate">{test.name}</span>
                    {/* Change badge */}
                    {regressed && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400 font-medium">Regressed</span>}
                    {improved && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-medium">Improved</span>}
                    {isNew && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 font-medium">New</span>}
                    {/* Confidence */}
                    {test.confidence !== undefined && (
                      <span className={cn("text-[10px] font-mono w-10 text-right", test.confidence > 90 ? "text-emerald-400" : "text-amber-400")}>
                        {test.confidence}%
                      </span>
                    )}
                    {(test.codeA || test.codeB) && (
                      <ChevronDown className={cn("w-3.5 h-3.5 text-neutral-500 transition-transform", expanded === test.name && "rotate-180")} strokeWidth={1.5} />
                    )}
                  </button>
                  {/* Expanded code diff */}
                  <AnimatePresence>
                    {expanded === test.name && (test.codeA || test.codeB) && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="mx-3 mb-2 grid grid-cols-2 gap-2 p-3 rounded-xl bg-black/20 border border-white/[0.06]">
                          <div>
                            <div className="text-[10px] text-emerald-400/60 font-medium mb-1">Run A (passing)</div>
                            <pre className="text-[11px] font-mono text-emerald-300/60 whitespace-pre-wrap">{test.codeA}</pre>
                          </div>
                          <div>
                            <div className="text-[10px] text-red-400/60 font-medium mb-1">Run B (failing)</div>
                            <pre className="text-[11px] font-mono text-red-300/60 whitespace-pre-wrap">{test.codeB}</pre>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {/* Summary bar */}
      <div className="flex items-center gap-4 mt-4 pt-3 border-t border-white/[0.06] text-xs text-neutral-500">
        <span className={regressedCount > 0 ? "text-red-400" : ""}>▼ {regressedCount} regressed</span>
        <span className={improvedCount > 0 ? "text-emerald-400" : ""}>▲ {improvedCount} improved</span>
        <span className={newCount > 0 ? "text-blue-400" : ""}>✚ {newCount} new</span>
      </div>
    </motion.div>
  );
}
