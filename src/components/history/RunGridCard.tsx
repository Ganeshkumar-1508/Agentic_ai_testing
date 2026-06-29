"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface RunRecord {
  id: string;
  repoUrl?: string | null;
  branch?: string | null;
  status: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
  skippedCount: number;
  duration: number;
  createdAt: string;
}

interface RunGridCardProps {
  run: RunRecord;
  index: number;
  onClick: () => void;
}

const STATUS_STRIP: Record<string, string> = {
  completed: "bg-emerald-400",
  failed: "bg-red-400",
  running: "bg-amber-400",
  pending: "bg-zinc-500",
};

function formatDuration(ms: number): string {
  if (ms === 0) return "\u2014";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

export function RunGridCard({ run, index, onClick }: RunGridCardProps) {
  const pct = run.testCount > 0 ? Math.round((run.passedCount / run.testCount) * 100) : 0;
  const pctColor = pct >= 80 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      onClick={onClick}
      className="bg-surface border border-white/[0.06] rounded-xl overflow-hidden cursor-pointer hover:border-emerald-500/20 transition-all duration-300 active:scale-[0.98] group"
    >
      {/* Status color strip */}
      <div className={cn("h-[3px] w-full", STATUS_STRIP[run.status] ?? "bg-zinc-600")} />

      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-medium text-zinc-200 truncate">
              {run.repoUrl || `Run ${run.id.slice(0, 8)}`}
            </div>
            <div className="text-[10px] font-mono text-zinc-600 truncate mt-0.5">{run.id.slice(0, 12)}</div>
          </div>
          {run.branch && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-500/10 text-zinc-400 font-mono text-[9px] shrink-0 ml-2">
              {run.branch}
            </span>
          )}
        </div>

        {/* Mini pass rate bar */}
        <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden mb-3">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className={cn("h-full rounded-full", pct >= 80 ? "bg-emerald-400" : pct >= 50 ? "bg-amber-400" : "bg-red-400")}
          />
        </div>

        {/* Mini-chart area */}
        <div className="h-10 rounded-lg bg-white/[0.02] mb-3 overflow-hidden relative">
          <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-full opacity-40">
            <path
              d={`M0,${35 - (run.passedCount / Math.max(run.testCount, 1)) * 15} Q25,${30 - (run.passedCount / Math.max(run.testCount, 1)) * 10} 50,${25 - (run.passedCount / Math.max(run.testCount, 1)) * 5} T100,${20 - (run.passedCount / Math.max(run.testCount, 1)) * 15}`}
              fill="none" stroke="#34d399" strokeWidth="1.5"
            />
          </svg>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-4 gap-2 pt-3 border-t border-white/[0.06]">
          {[
            { label: "Total", value: run.testCount, color: "text-zinc-300" },
            { label: "Passed", value: run.passedCount, color: "text-emerald-400" },
            { label: "Failed", value: run.failedCount, color: "text-red-400" },
            { label: "Skip", value: run.skippedCount, color: "text-zinc-600" },
          ].map((s) => (
            <div key={s.label} className="text-center">
              <div className={cn("text-[11px] font-semibold font-mono tabular-nums", s.color)}>
                {s.value ?? "\u2014"}
              </div>
              <div className="text-[8px] text-zinc-700 uppercase tracking-wider mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-2.5 border-t border-white/[0.06] bg-zinc-950/[0.12]">
        <span className="text-[10px] text-zinc-600 font-mono">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="inline mr-1 -mt-0.5">
            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
          </svg>
          {formatDuration(run.duration)}
        </span>
        <span className={cn("text-[11px] font-semibold font-mono tabular-nums", pctColor)}>{pct}%</span>
      </div>
    </motion.div>
  );
}
