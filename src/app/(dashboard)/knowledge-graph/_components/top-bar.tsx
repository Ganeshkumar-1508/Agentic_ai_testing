"use client";

import { AlertTriangle, CircleDot } from "lucide-react";
import { cn } from "@/lib/utils";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "\u2014";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function ErrorFallback({ error }: { error: Error }) {
  return (
    <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 bg-background/92 text-center">
      <AlertTriangle className="h-6 w-6 text-rose-300" strokeWidth={1.5} />
      <p className="text-[12px] font-medium text-rose-200">Graph rendering failed</p>
      <p className="max-w-md text-[11px] font-mono text-neutral-500">{error.message}</p>
    </div>
  );
}

export function LegendOverlay({ nodeTypeCounts, communityCount }: { nodeTypeCounts: Record<string, number>; communityCount: number }) {
  const topTypes = Object.entries(nodeTypeCounts).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const typeColors: Record<string, string> = {
    Function: "#34d399", Class: "#60a5fa", File: "#fb923c",
    Module: "#2dd4bf", Endpoint: "#f472b6", Service: "#fbbf24", Component: "#38bdf8",
  };
  return (
    <div className="absolute left-3 top-3 z-10 min-w-[136px] rounded-2xl border border-white/[0.06] bg-background/78 p-3 backdrop-blur-md">
      <div className="mb-2 flex items-center gap-2 text-[8px] font-semibold uppercase tracking-[0.28em] text-neutral-500">
        <CircleDot className="h-3 w-3" strokeWidth={1.8} /> Legend
      </div>
      <div className="space-y-1.5">
        {topTypes.map(([type, count]) => (
          <div key={type} className="flex items-center gap-2 text-[9px] text-neutral-400">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: typeColors[type] ?? "#34d399" }} />
            <span>{type}</span>
            <span className="ml-auto font-mono text-neutral-500">{formatCount(count)}</span>
          </div>
        ))}
      </div>
      {communityCount > 0 && (
        <div className="mt-3 border-t border-white/[0.05] pt-2 text-[8.5px] font-mono uppercase tracking-[0.18em] text-neutral-500">
          {formatCount(communityCount)} detected communities
        </div>
      )}
    </div>
  );
}

export function CanvasToolbar({
  taxonomy, onTaxonomyChange, direction, onDirectionChange,
  availableLanguages, languageFilter, onLanguageFilterChange,
  query, matchedCount, totalNodes, truncated, searchPerf,
}: {
  taxonomy: string; onTaxonomyChange: (value: string) => void;
  direction: string; onDirectionChange: (value: string) => void;
  availableLanguages: Array<[string, number]>;
  languageFilter: string | null; onLanguageFilterChange: (value: string | null) => void;
  query: string; matchedCount: number; totalNodes: number; truncated: boolean;
  searchPerf: { matched: number; timeMs: number; terms: number } | null;
}) {
  const taxonomyOptions = [
    { value: "all", label: "All" }, { value: "code", label: "Code" },
    { value: "files", label: "Files" }, { value: "domain", label: "Domain" },
  ];
  return (
    <div className="absolute right-3 top-3 z-10 flex flex-col items-end gap-2">
      <div className="flex items-center gap-1 rounded-2xl border border-white/[0.06] bg-background/76 p-1 backdrop-blur-md">
        {taxonomyOptions.map((opt) => {
          const active = opt.value === taxonomy;
          return (
            <button key={opt.value} type="button" onClick={() => onTaxonomyChange(opt.value)}
              className={cn("rounded-xl px-3 py-1.5 text-[9px] font-mono uppercase tracking-[0.18em] transition-colors",
                active ? "border border-emerald-400/25 bg-emerald-500/12 text-emerald-300" : "border border-transparent text-neutral-500 hover:text-neutral-200")}>
              {opt.label}
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-2">
        {availableLanguages.length > 1 ? (
          <Select value={languageFilter ?? "__all"} onValueChange={(value) => onLanguageFilterChange(value === "__all" ? null : value)}>
            <SelectTrigger className="h-8 min-w-[140px] border-white/[0.06] bg-background/76 text-[10px] font-mono text-neutral-200 shadow-none">
              <SelectValue placeholder="All languages" />
            </SelectTrigger>
            <SelectContent className="border-white/[0.08] bg-card text-neutral-100">
              <SelectItem value="__all">All languages</SelectItem>
              {availableLanguages.map(([language, count]) => (
                <SelectItem key={language} value={language}>{language} ({count})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        <div className="flex items-center gap-1 rounded-2xl border border-white/[0.06] bg-background/76 p-1 backdrop-blur-md">
          {[["LR", "Left → Right"], ["TB", "Top ↓ Bottom"]].map(([value, label]) => (
            <button key={value} type="button" onClick={() => onDirectionChange(value)}
              className={cn("rounded-xl px-3 py-1.5 text-[9px] font-mono uppercase tracking-[0.18em] transition-colors",
                value === direction ? "bg-white/[0.08] text-neutral-100" : "text-neutral-500 hover:text-neutral-200")}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {(query.trim() || truncated) && (
        <div className="rounded-xl border border-white/[0.05] bg-background/68 px-3 py-1.5 text-[9px] font-mono text-neutral-500 backdrop-blur-md">
          {formatCount(matchedCount)}/{formatCount(totalNodes)} visible
          {truncated ? <span className="ml-1 text-amber-300">(trimmed for performance)</span> : null}
          {searchPerf ? <span className="ml-1 text-emerald-300/70">· {searchPerf.timeMs.toFixed(1)}ms</span> : null}
        </div>
      )}
    </div>
  );
}
