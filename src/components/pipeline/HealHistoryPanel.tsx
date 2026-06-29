"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { CheckCircle, XCircle, Code2 } from "lucide-react";

interface HealAttempt {
  attempt: number;
  status: string;
  fixedCode?: string;
  output?: string;
}

interface HealHistoryPanelProps {
  testName: string;
  attempts: HealAttempt[];
  loading?: boolean;
}

export function HealHistoryPanel({ testName, attempts, loading }: HealHistoryPanelProps) {
  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-6 space-y-3">
        <div className="w-24 h-4 rounded-full shimmer-bg" />
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-16 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  if (!attempts || attempts.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
        className="bg-surface border border-white/[0.06] rounded-3xl p-6"
      >
        <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider mb-3">
          Heal History
        </div>
        <div className="text-sm text-neutral-500 text-center py-8">
          No self-heal attempts for this run.
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-3xl p-6"
    >
      <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider mb-3">
        Heal History — {testName}
      </div>
      <div className="space-y-2">
        {attempts.map((attempt, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className={cn(
              "p-3 rounded-xl border",
              attempt.status === "passed" || attempt.status === "healed"
                ? "bg-emerald-500/5 border-emerald-500/10"
                : "bg-red-500/5 border-red-500/10"
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              {attempt.status === "passed" || attempt.status === "healed" ? (
                <CheckCircle className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
              ) : (
                <XCircle className="w-4 h-4 text-red-400" strokeWidth={1.5} />
              )}
              <span className="text-sm font-medium text-neutral-300">
                Attempt {attempt.attempt}
              </span>
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded font-mono",
                attempt.status === "passed" || attempt.status === "healed"
                  ? "bg-emerald-500/10 text-emerald-400"
                  : "bg-red-500/10 text-red-400"
              )}>
                {attempt.status}
              </span>
            </div>
            {attempt.fixedCode && (
              <div className="mt-2">
                <div className="flex items-center gap-1 text-[10px] text-neutral-500 mb-1">
                  <Code2 className="w-3 h-3" strokeWidth={1.5} />
                  Fixed code
                </div>
                <pre className="text-[11px] font-mono text-emerald-300/80 bg-zinc-950/20 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap">
                  {attempt.fixedCode.slice(0, 300)}
                </pre>
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
