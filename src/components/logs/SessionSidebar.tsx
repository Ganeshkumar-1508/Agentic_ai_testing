"use client";

import { motion } from "framer-motion";
import { Search, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_CHIPS = [
  { label: "All", value: null },
  { label: "Running", value: "running" },
  { label: "Failed", value: "failed" },
  { label: "Completed", value: "completed" },
  { label: "High cost", value: "high-cost" },
];

interface Session {
  id: string; status: string; prompt: string;
  total_tokens: number; total_cost: number;
  event_count: number; created_at: string; updated_at: string;
}

interface Props {
  sessions: Session[];
  selectedSession: string | null;
  search: string;
  statusFilter: string | null;
  hasMore: boolean;
  loading: boolean;
  error: string | null;
  onSearch: (val: string) => void;
  onStatusFilter: (status: string | null) => void;
  onSelect: (id: string) => void;
  onLoadMore: () => void;
}

function fmtTime(iso: string | undefined | null): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleTimeString("en-US", { hour12: false }); }
  catch { return ""; }
}

export function SessionSidebar({
  sessions, selectedSession, search, statusFilter,
  hasMore, loading, error, onSearch, onStatusFilter, onSelect, onLoadMore,
}: Props) {
  return (
    <div className="w-64 flex-shrink-0 flex flex-col bg-white/[0.015] border border-white/[0.06] rounded-3xl overflow-hidden shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
          Sessions
        </span>
        <span className="text-[10px] text-neutral-600 font-mono tabular-nums">
          {sessions.length}
        </span>
      </div>

      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 bg-white/[0.04] border border-white/[0.06] rounded-3xl px-3 py-1.5 transition-colors focus-within:border-white/[0.1]">
          <Search className="w-3 h-3 text-neutral-500 shrink-0" strokeWidth={1.5} />
          <input
            type="text"
            value={search}
            onChange={e => onSearch(e.target.value)}
            placeholder="Search sessions..."
            className="bg-transparent border-none outline-none text-xs text-neutral-300 w-full placeholder:text-neutral-600 font-sans"
          />
        </div>
      </div>

      <div className="flex gap-1 px-3 pb-3 flex-wrap">
        {STATUS_CHIPS.map(chip => (
          <button
            key={chip.label}
            onClick={() => onStatusFilter(chip.value)}
            className={cn(
              "text-[10px] px-2.5 py-1 rounded-full transition-colors active:scale-[0.95]",
              statusFilter === chip.value
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/15"
                : "bg-white/[0.04] text-neutral-500 hover:text-neutral-300 border border-transparent"
            )}
          >
            {chip.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5" style={{ scrollbarGutter: "stable" }}>
        {error && (
          <div className="flex flex-col items-center justify-center py-8 text-center px-4">
            <div className="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center mb-2">
              <svg className="w-4 h-4 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
              </svg>
            </div>
            <p className="text-xs text-red-400/80">{error}</p>
            <p className="text-[10px] text-neutral-600 mt-1">Try refreshing the page</p>
          </div>
        )}

        {loading && sessions.length === 0 && (
          <div className="space-y-2 px-2 pt-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-16 bg-white/[0.03] rounded-[1rem] animate-pulse" />
            ))}
          </div>
        )}

        {!error && !loading && sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center px-4">
            <Search className="w-6 h-6 text-neutral-600 mb-2" strokeWidth={1.2} />
            <p className="text-xs text-neutral-600">No sessions found</p>
            <p className="text-[10px] text-neutral-700 mt-1">Run a test to see session logs</p>
          </div>
        )}

        <AnimatedSessionList
          sessions={sessions}
          selectedSession={selectedSession}
          onSelect={onSelect}
        />

        {hasMore && (
          <button
            onClick={onLoadMore}
            disabled={loading}
            className="w-full text-[11px] text-neutral-600 hover:text-neutral-400 py-3 transition-colors disabled:opacity-40"
          >
            {loading ? "Loading..." : "Load more ↓"}
          </button>
        )}
      </div>
    </div>
  );
}

function AnimatedSessionList({ sessions, selectedSession, onSelect }: {
  sessions: Session[]; selectedSession: string | null; onSelect: (id: string) => void;
}) {
  return (
    <>
      {sessions.map((s, i) => (
        <motion.button
          key={s.id}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.02, type: "spring", stiffness: 120, damping: 18 }}
          onClick={() => onSelect(s.id)}
            className={cn(
            "w-full text-left px-3 py-2.5 rounded-3xl transition-all active:scale-[0.98] border",
            selectedSession === s.id
              ? "bg-emerald-500/8 border-emerald-500/15"
              : "bg-transparent border-transparent hover:bg-white/[0.03]"
          )}
        >
          <div className="flex items-center gap-2">
            <StatusDot status={s.status} />
            <span className="flex-1 min-w-0">
              <span className="block text-[12px] font-medium text-neutral-300 truncate leading-tight">
                {s.prompt?.slice(0, 60) || "—"}
              </span>
              <span className="block text-[10px] text-neutral-600 mt-0.5 font-mono">
                {s.id.slice(0, 8)}...
              </span>
            </span>
            <ChevronRight className="w-3 h-3 text-neutral-600 shrink-0" strokeWidth={1.5} />
          </div>
          <div className="flex items-center gap-3 mt-1.5 text-[10px] font-mono tabular-nums">
            <span className="text-emerald-500/80">${s.total_cost.toFixed(2)}</span>
            <span className="text-neutral-500">{s.total_tokens}tok</span>
            <span className="text-neutral-600 ml-auto">{fmtTime(s.created_at)}</span>
          </div>
        </motion.button>
      ))}
    </>
  );
}

function StatusDot({ status }: { status: string }) {
  return (
    <span className={cn("w-1.5 h-1.5 rounded-full shrink-0 mt-0.5", {
      "bg-emerald-400": status === "completed",
      "bg-blue-400 animate-pulse": status === "running",
      "bg-red-400": status === "failed",
      "bg-neutral-600": !status || status === "pending",
    })} />
  );
}
