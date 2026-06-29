"use client";

import { cn } from "@/lib/utils";

interface FilterOption {
  value: string;
  label: string;
}

interface SearchFilterBarProps {
  search: string;
  onSearchChange: (v: string) => void;
  searchPlaceholder?: string;
  sourceFilters?: FilterOption[];
  sourceValue?: string;
  onSourceChange?: (v: string) => void;
  selects?: Array<{
    value: string;
    onChange: (v: string) => void;
    options: FilterOption[];
    placeholder: string;
  }>;
}

export function SearchFilterBar({ search, onSearchChange, searchPlaceholder = "Search...", sourceFilters, sourceValue, onSourceChange, selects }: SearchFilterBarProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-zinc-500 min-w-[200px]">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input value={search} onChange={(e) => onSearchChange(e.target.value)}
          placeholder={searchPlaceholder} className="bg-transparent text-xs text-zinc-300 placeholder:text-zinc-700 outline-none flex-1" />
        <span className="text-[9px] font-mono text-zinc-700">Ctrl+K</span>
      </div>
      {sourceFilters && onSourceChange && (
        <>
          {sourceFilters.map((o) => (
            <button key={o.value} onClick={() => onSourceChange(o.value)}
              className={cn("px-2.5 py-1 text-[11px] rounded-lg border transition-colors whitespace-nowrap",
                sourceValue === o.value ? "bg-white/[0.05] border-white/[0.1] text-zinc-100" : "border-white/[0.06] text-zinc-500 hover:text-zinc-300 bg-transparent")}>
              {o.label}
            </button>
          ))}
        </>
      )}
      {selects?.map((s, i) => (
        <select key={i} value={s.value} onChange={(e) => s.onChange(e.target.value)}
          className="px-2 py-1 text-[11px] rounded-lg border border-white/[0.06] bg-transparent text-zinc-500 outline-none">
          <option value="">{s.placeholder}</option>
          {s.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ))}
    </div>
  );
}
