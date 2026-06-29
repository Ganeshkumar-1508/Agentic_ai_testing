"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface RunRecord {
  id: string;
  workflowId: string;
  repoUrl?: string | null;
  repoProvider?: string | null;
  branch?: string | null;
  status: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
  skippedCount: number;
  duration: number;
  cost: number;
  tokens: number;
  createdAt: string;
  completedAt?: string | null;
  techStack?: string | null;
}

interface RunCardProps {
  run: RunRecord;
  index: number;
  isSelected: boolean;
  onSelect: () => void;
  onReplay?: () => void;
  onCompare?: () => void;
  onViewDetails?: () => void;
  bulkMode?: boolean;
  bulkSelected?: boolean;
  onBulkToggle?: () => void;
}

const STATUS_COLORS: Record<string, { dot: string; bg: string; icon: "pass" | "fail" | "running" }> = {
  completed: { dot: "bg-emerald-400", bg: "bg-emerald-500/10", icon: "pass" },
  failed: { dot: "bg-red-400", bg: "bg-red-500/10", icon: "fail" },
  running: { dot: "bg-amber-400 animate-pulse", bg: "bg-amber-500/10", icon: "running" },
  pending: { dot: "bg-zinc-500", bg: "bg-zinc-500/10", icon: "running" },
};

const STATUS_BADGE: Record<string, string> = {
  completed: "bg-emerald-500/10 text-emerald-400 border-emerald-400/20",
  failed: "bg-red-500/10 text-red-400 border-red-400/20",
  running: "bg-amber-500/10 text-amber-400 border-amber-400/20",
  pending: "bg-zinc-500/10 text-zinc-400 border-zinc-400/20",
};

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") {
    return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-emerald-400"><polyline points="20 6 9 17 4 12" /></svg>;
  }
  if (status === "failed") {
    return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-red-400"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>;
  }
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-amber-400"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>;
}

function formatDuration(ms: number): string {
  if (ms === 0) return "\u2014";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function timeAgo(dateStr: string): string {
  const d = new Date(dateStr).getTime();
  const sec = Math.floor((Date.now() - d) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

export function RunCard({ run, index, isSelected, onSelect, onReplay, onCompare, onViewDetails, bulkMode, bulkSelected, onBulkToggle }: RunCardProps) {
  const pct = run.testCount > 0 ? Math.round((run.passedCount / run.testCount) * 100) : 0;
  const pctColor = pct >= 80 ? "bg-emerald-400" : pct >= 50 ? "bg-amber-400" : "bg-red-400";
  const pctTextColor = pct >= 80 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400";
  const statusStyle = STATUS_COLORS[run.status] ?? STATUS_COLORS.pending;

  let techTags: string[] = [];
  if (run.techStack) {
    try {
      const st = typeof run.techStack === "string" ? JSON.parse(run.techStack) : run.techStack;
      techTags = Object.values(st).filter((v): v is string => typeof v === "string").slice(0, 3);
    } catch { /* ignore */ }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      onClick={onSelect}
      className={cn(
        "relative rounded-xl border transition-all cursor-pointer overflow-hidden group",
        isSelected ? "bg-white/[0.03] border-emerald-500/30" : "bg-surface border-white/[0.06] hover:border-white/[0.12] active:scale-[0.995]",
        bulkSelected && "border-emerald-500/40 bg-emerald-500/[0.02]"
      )}
    >
      <div className="flex items-center gap-4 px-4 py-3">
        {/* Bulk checkbox */}
        {bulkMode && (
          <div
            onClick={(e) => { e.stopPropagation(); onBulkToggle?.(); }}
            className={cn(
              "w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 transition-colors cursor-pointer",
              bulkSelected ? "bg-emerald-400 border-emerald-400" : "border-white/[0.15] hover:border-emerald-400/50"
            )}
          >
            {bulkSelected && (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
            )}
          </div>
        )}

        {/* Status dot */}
        <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0", statusStyle.bg)}>
          <StatusIcon status={run.status} />
        </div>

        {/* Main content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-zinc-200 truncate">
              {run.repoUrl || `Run ${run.id.slice(0, 8)}`}
            </span>
            <span className={cn("text-[9px] font-medium px-1.5 py-0.5 rounded border uppercase shrink-0", STATUS_BADGE[run.status] ?? "bg-zinc-800 text-zinc-500")}>
              {run.status}
            </span>
            {run.repoProvider && (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-700 shrink-0">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
              </svg>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-zinc-600 flex-wrap">
            <span className="text-zinc-500">{run.id.slice(0, 8)}</span>
            {run.branch && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-500/10 text-zinc-400 font-mono text-[9px]">
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="6" y1="3" x2="6" y2="15" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M18 9a9 9 0 0 1-9 9" /></svg>
                {run.branch}
              </span>
            )}
            {run.testCount > 0 && <span>{run.testCount} tests</span>}
            {run.duration > 0 && (
              <span className="inline-flex items-center gap-1">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
                {formatDuration(run.duration)}
              </span>
            )}
            {run.createdAt && <span>{timeAgo(run.createdAt)} ago</span>}
            {techTags.map((tag) => (
              <span key={tag} className="px-1 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[9px]">{tag}</span>
            ))}
          </div>
        </div>

        {/* Stats */}
        <div className="hidden sm:flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2">
            {[
              { label: "T", value: run.testCount, color: "text-zinc-400" },
              { label: "P", value: run.passedCount, color: "text-emerald-400" },
              { label: "F", value: run.failedCount, color: "text-red-400" },
            ].map((s) => (
              <div key={s.label} className="text-center">
                <div className={cn("text-[11px] font-semibold font-mono tabular-nums", s.color)}>{s.value}</div>
                <div className="text-[8px] text-zinc-700 uppercase tracking-wider">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Pass rate */}
        <div className="hidden sm:flex flex-col items-center gap-1 min-w-[4rem] shrink-0">
          <span className={cn("text-[13px] font-semibold font-mono tabular-nums", pctTextColor)}>{pct}%</span>
          <div className="w-full h-1 bg-white/[0.06] rounded-full overflow-hidden">
            <div className={cn("h-full rounded-full transition-all duration-500", pctColor)} style={{ width: `${pct}%` }} />
          </div>
        </div>

        {/* Quick actions (hover reveal) */}
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          {onReplay && (
            <button onClick={(e) => { e.stopPropagation(); onReplay(); }} className="w-7 h-7 rounded-lg flex items-center justify-center bg-zinc-800 border border-white/[0.06] text-zinc-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all" title="Re-run">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" /></svg>
            </button>
          )}
          {onCompare && (
            <button onClick={(e) => { e.stopPropagation(); onCompare(); }} className="w-7 h-7 rounded-lg flex items-center justify-center bg-zinc-800 border border-white/[0.06] text-zinc-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all" title="Compare">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg>
            </button>
          )}
          {onViewDetails && (
            <button onClick={(e) => { e.stopPropagation(); onViewDetails(); }} className="w-7 h-7 rounded-lg flex items-center justify-center bg-zinc-800 border border-white/[0.06] text-zinc-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all" title="View Details">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
            </button>
          )}
          <button onClick={(e) => { e.stopPropagation(); }} className="w-7 h-7 rounded-lg flex items-center justify-center bg-zinc-800 border border-white/[0.06] text-zinc-500 hover:text-emerald-400 hover:border-emerald-500/30 transition-all" title="Export">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
          </button>
        </div>
      </div>

      {/* Progress bar for running/completed */}
      {(run.status === "running" || run.status === "completed") && (
        <div className="h-[2px] bg-white/[0.04] mx-4 mb-0">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${run.status === "running" ? Math.min(pct + 10, 90) : 100}%` }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className={cn("h-full rounded-full", pctColor)}
          />
        </div>
      )}
    </motion.div>
  );
}
