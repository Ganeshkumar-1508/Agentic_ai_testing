"use client";

import { Search, X } from "lucide-react";

export type FilterStatus = "all" | "passed" | "failed" | "skipped";

interface TestFilterBarProps {
  search: string;
  onSearchChange: (v: string) => void;
  status: FilterStatus;
  onStatusChange: (v: FilterStatus) => void;
  tags?: string[];
  selectedTags?: string[];
  onTagToggle?: (tag: string) => void;
  total?: number;
}

const STATUS_OPTIONS: { value: FilterStatus; label: string }[] = [
  { value: "all", label: "All" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

export function TestFilterBar({ search, onSearchChange, status, onStatusChange, tags, selectedTags, onTagToggle, total }: TestFilterBarProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-600" strokeWidth={1.5} />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search by test name..."
            className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg pl-7 pr-8 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors"
          />
          {search && (
            <button onClick={() => onSearchChange("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400">
              <X className="w-3 h-3" strokeWidth={1.5} />
            </button>
          )}
        </div>
        <div className="flex gap-1 bg-white/[0.03] border border-white/[0.05] rounded-lg p-0.5">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onStatusChange(opt.value)}
              className={`px-2.5 py-1 text-[10px] rounded-md transition-colors font-medium ${
                status === opt.value ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {total !== undefined && (
          <span className="text-[10px] text-zinc-600 font-mono tabular-nums">{total}</span>
        )}
      </div>

      {tags && tags.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {tags.map((tag) => {
            const active = selectedTags?.includes(tag);
            return (
              <button
                key={tag}
                onClick={() => onTagToggle?.(tag)}
                className={`text-[9px] px-2 py-0.5 rounded-full font-mono transition-colors ${
                  active ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" : "bg-white/[0.03] text-zinc-600 border border-white/[0.06] hover:text-zinc-400"
                }`}
              >
                @{tag}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
