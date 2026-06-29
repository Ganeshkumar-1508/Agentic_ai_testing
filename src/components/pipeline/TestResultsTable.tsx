"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, AlertCircle, ChevronDown, Bug, Beaker } from "lucide-react";

interface TestResult {
  testName: string;
  status: string;
  durationMs?: number;
  error?: string;
  healed?: boolean;
}

interface TestResultsTableProps {
  tests: TestResult[];
  loading?: boolean;
  onAnalyze?: (testName: string) => void;
}

const FILTERS = ["All", "Passed", "Failed"] as const;

export function TestResultsTable({ tests, loading, onAnalyze }: TestResultsTableProps) {
  const [filter, setFilter] = useState<string>("All");
  const [expandedError, setExpandedError] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6 space-y-3">
        <div className="w-24 h-4 rounded-full shimmer-bg" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  const filtered = tests.filter((t) => {
    if (filter === "Passed") return t.status === "passed";
    if (filter === "Failed") return t.status === "failed";
    return true;
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
          Test Results
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
        <div className="text-sm text-neutral-500 text-center py-8">
          No {filter.toLowerCase()} tests.
        </div>
      ) : (
        <div className="space-y-1">
          <AnimatePresence>
            {filtered.map((test, i) => (
              <motion.div
                key={test.testName}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
              >
                <button
                  onClick={() => setExpandedError(expandedError === test.testName ? null : test.testName)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/[0.04] transition-colors text-left"
                >
                  {test.status === "passed" ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" strokeWidth={1.5} />
                  ) : test.status === "failed" ? (
                    <XCircle className="w-4 h-4 text-red-400 shrink-0" strokeWidth={1.5} />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" strokeWidth={1.5} />
                  )}
                  <span className="flex-1 text-sm text-neutral-300 font-mono truncate">
                    {test.testName}
                  </span>
                  {test.healed && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-medium">
                      Healed
                    </span>
                  )}
                  {test.durationMs !== undefined && (
                    <span className="text-xs text-neutral-500 font-mono w-14 text-right">
                      {(test.durationMs / 1000).toFixed(1)}s
                    </span>
                  )}
                  {test.status === "failed" && (
                    <ChevronDown className={cn("w-3.5 h-3.5 text-neutral-500 transition-transform", expandedError === test.testName && "rotate-180")} strokeWidth={1.5} />
                  )}
                </button>
                {/* Expanded error detail */}
                <AnimatePresence>
                  {expandedError === test.testName && test.error && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mx-3 mb-2 p-3 rounded-xl bg-red-500/5 border border-red-500/10">
                        <pre className="text-xs text-red-300/80 font-mono whitespace-pre-wrap">{test.error}</pre>
                        <div className="flex gap-2 mt-2">
                          {onAnalyze && (
                            <button
                              onClick={(e) => { e.stopPropagation(); onAnalyze(test.testName); }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-xs font-medium transition-all"
                            >
                              <Bug className="w-3 h-3" strokeWidth={1.5} />
                              Analyze & Heal
                            </button>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}
