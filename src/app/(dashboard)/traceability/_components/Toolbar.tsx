"use client";

import { motion } from "framer-motion";
import { Search, X, ArrowDown, ArrowRight, Plus, Sparkles, ListTree, Table2, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ViewMode, LayoutDirection, Priority, ReqStatus } from "./types";
import { PRIORITY_TONE, REQ_STATUS_TONE } from "./constants";

const REQ_STATUSES: ReqStatus[] = ["active", "draft", "archived"];
const PRIORITIES: Priority[] = ["high", "medium", "low"];

export type TraceFilters = {
  query: string;
  statuses: Set<ReqStatus>;
  priorities: Set<Priority>;
};

export function buildEmptyFilters(): TraceFilters {
  return { query: "", statuses: new Set<ReqStatus>(), priorities: new Set<Priority>() };
}

export function matchesFilters(
  text: string,
  priority: Priority | undefined,
  status: ReqStatus | TestStatusEquiv | undefined,
  f: TraceFilters
): boolean {
  if (f.query) {
    if (!text.toLowerCase().includes(f.query.toLowerCase())) return false;
  }
  if (f.priorities.size > 0) {
    if (!priority || !f.priorities.has(priority)) return false;
  }
  if (f.statuses.size > 0) {
    if (!status || !f.statuses.has(status as ReqStatus)) return false;
  }
  return true;
}

type TestStatusEquiv = "passed" | "failed" | "pending" | "skipped" | "running";

export function Toolbar({
  filters,
  onFiltersChange,
  view,
  onViewChange,
  direction,
  onDirectionChange,
  depth,
  onDepthChange,
  onAdd,
  onGenerate,
  resultCount,
}: {
  filters: TraceFilters;
  onFiltersChange: (next: TraceFilters) => void;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
  direction: LayoutDirection;
  onDirectionChange: (d: LayoutDirection) => void;
  depth: number;
  onDepthChange: (d: number) => void;
  onAdd: () => void;
  onGenerate: () => void;
  resultCount: number;
}) {
  const toggleStatus = (s: ReqStatus) => {
    const next = new Set(filters.statuses);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    onFiltersChange({ ...filters, statuses: next });
  };

  const togglePriority = (p: Priority) => {
    const next = new Set(filters.priorities);
    if (next.has(p)) next.delete(p);
    else next.add(p);
    onFiltersChange({ ...filters, priorities: next });
  };

  const clearAll = () => onFiltersChange(buildEmptyFilters());

  const anyFilterActive =
    filters.query.length > 0 || filters.statuses.size > 0 || filters.priorities.size > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05, duration: 0.4, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-3xl p-3.5 card-glow"
    >
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-600" strokeWidth={1.5} />
          <input
            type="text"
            value={filters.query}
            onChange={(e) => onFiltersChange({ ...filters, query: e.target.value })}
            placeholder="Search requirements, tests…"
            className="w-full pl-10 pr-9 py-2 bg-white/[0.03] border border-white/[0.06] rounded-lg text-[13px] text-neutral-200 placeholder:text-neutral-600 focus:outline-none focus:border-emerald-500/40 focus:bg-white/[0.04] transition-colors font-mono"
          />
          {filters.query && (
            <button
              onClick={() => onFiltersChange({ ...filters, query: "" })}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center text-neutral-600 hover:text-neutral-300 transition-colors"
              aria-label="Clear search"
            >
              <X className="w-3 h-3" strokeWidth={2} />
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {REQ_STATUSES.map((s) => {
            const active = filters.statuses.has(s);
            const tone = REQ_STATUS_TONE[s];
            return (
              <button
                key={s}
                onClick={() => toggleStatus(s)}
                className={cn(
                  "px-2.5 py-1.5 rounded-md text-[11px] font-medium uppercase tracking-wider transition-all border",
                  active
                    ? "bg-white/[0.06] border-white/[0.12] text-neutral-200"
                    : "bg-transparent border-white/[0.05] text-neutral-500 hover:text-neutral-300 hover:border-white/[0.08]"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <span className={cn("w-1.5 h-1.5 rounded-full", tone.dot)} />
                  {tone.label}
                </span>
              </button>
            );
          })}
        </div>

        <div className="h-5 w-px bg-white/[0.06]" />

        <div className="flex items-center gap-1.5">
          {PRIORITIES.map((p) => {
            const active = filters.priorities.has(p);
            const tone = PRIORITY_TONE[p];
            return (
              <button
                key={p}
                onClick={() => togglePriority(p)}
                className={cn(
                  "px-2.5 py-1.5 rounded-md text-[11px] font-medium uppercase tracking-wider transition-all border",
                  active
                    ? "bg-white/[0.06] border-white/[0.12] text-neutral-200"
                    : "bg-transparent border-white/[0.05] text-neutral-500 hover:text-neutral-300 hover:border-white/[0.08]"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <span className={cn("w-1.5 h-1.5 rounded-full", tone.dot)} />
                  {tone.label}
                </span>
              </button>
            );
          })}
        </div>

        {anyFilterActive && (
          <button
            onClick={clearAll}
            className="text-[10.5px] font-mono text-neutral-500 hover:text-emerald-400 transition-colors ml-auto"
          >
            Clear
          </button>
        )}

        <div className="h-5 w-px bg-white/[0.06] ml-auto" />

        <div className="flex items-center gap-1 p-0.5 bg-white/[0.03] border border-white/[0.06] rounded-lg">
          <ViewBtn active={view === "graph"} onClick={() => onViewChange("graph")} label="Graph" icon={ListTree} />
          <ViewBtn active={view === "matrix"} onClick={() => onViewChange("matrix")} label="Matrix" icon={LayoutGrid} />
          <ViewBtn active={view === "table"} onClick={() => onViewChange("table")} label="Table" icon={Table2} />
        </div>

        {view === "graph" && (
          <>
            <div className="h-5 w-px bg-white/[0.06]" />
            <div className="flex items-center gap-1 p-0.5 bg-white/[0.03] border border-white/[0.06] rounded-lg">
              <button
                onClick={() => onDirectionChange("TB")}
                className={cn(
                  "px-2 py-1 rounded text-[10.5px] font-mono transition-colors flex items-center gap-1.5",
                  direction === "TB"
                    ? "bg-white/[0.06] text-neutral-100"
                    : "text-neutral-500 hover:text-neutral-300"
                )}
                title="Top to bottom"
              >
                <ArrowDown className="w-3 h-3" strokeWidth={2} />
                TB
              </button>
              <button
                onClick={() => onDirectionChange("LR")}
                className={cn(
                  "px-2 py-1 rounded text-[10.5px] font-mono transition-colors flex items-center gap-1.5",
                  direction === "LR"
                    ? "bg-white/[0.06] text-neutral-100"
                    : "text-neutral-500 hover:text-neutral-300"
                )}
                title="Left to right"
              >
                <ArrowRight className="w-3 h-3" strokeWidth={2} />
                LR
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider">Depth</span>
              <input
                type="range"
                min={1}
                max={5}
                value={depth}
                onChange={(e) => onDepthChange(Number(e.target.value))}
                className="w-20 accent-emerald-500"
              />
              <span className="text-[10.5px] font-mono text-neutral-400 tabular-nums w-3">{depth}</span>
            </div>
          </>
        )}

        <div className="h-5 w-px bg-white/[0.06]" />

        <button
          onClick={onGenerate}
          className="px-3 py-1.5 rounded-lg text-[12px] font-medium text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/15 hover:border-emerald-500/30 transition-colors flex items-center gap-1.5"
        >
          <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />
          Generate
        </button>
        <button
          onClick={onAdd}
          className="px-3 py-1.5 rounded-lg text-[12px] font-medium text-neutral-100 bg-white/[0.06] border border-white/[0.08] hover:bg-white/[0.09] transition-colors flex items-center gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
          Add requirement
        </button>
      </div>

      <div className="mt-2.5 flex items-center gap-2 text-[10.5px] font-mono text-neutral-600">
        <span className="tabular-nums">{resultCount}</span>
        <span>items in view</span>
      </div>
    </motion.div>
  );
}

function ViewBtn({
  active,
  onClick,
  label,
  icon: Icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2.5 py-1 rounded text-[11px] font-medium flex items-center gap-1.5 transition-colors",
        active ? "bg-white/[0.06] text-neutral-100" : "text-neutral-500 hover:text-neutral-300"
      )}
    >
      <Icon className="w-3 h-3" strokeWidth={1.5} />
      {label}
    </button>
  );
}
