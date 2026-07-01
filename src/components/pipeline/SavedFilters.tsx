"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Filter, Plus, Trash2, Check, AlertCircle, Clock,
  TrendingUp, Bug, DollarSign, Beaker, Star,
} from "lucide-react";
import { api } from "@/lib/api/api-client";

const ICON_MAP = {
  Filter, AlertCircle, Clock, TrendingUp, Bug, DollarSign, Beaker, Star,
} as const;

type IconName = keyof typeof ICON_MAP;

const PRESET_FILTERS: { name: string; icon: IconName; filterData: Record<string, unknown>; description: string }[] = [
  { name: "Failed Runs", icon: "AlertCircle", filterData: { status: "failed" }, description: "All failed runs" },
  { name: "Last 7 Days", icon: "Clock", filterData: { since: "7d" }, description: "Runs from the past week" },
  { name: "Expensive", icon: "DollarSign", filterData: { minCost: 2.0 }, description: "Runs over $2.00" },
  { name: "High Coverage", icon: "TrendingUp", filterData: { minCoverage: 90 }, description: "Runs with >90% coverage" },
  { name: "Flaky", icon: "Bug", filterData: { hasFlaky: true }, description: "Runs with flaky tests" },
];

interface SavedFilter {
  id: string;
  name: string;
  description?: string;
  icon: IconName;
  filterData: Record<string, unknown>;
}

interface SavedFiltersProps {
  onApplyFilter: (filter: Record<string, unknown>) => void;
  activeFilter?: Record<string, unknown> | null;
}

export function SavedFilters({ onApplyFilter, activeFilter }: SavedFiltersProps) {
  const queryClient = useQueryClient();
  const [showPresets, setShowPresets] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["saved-filters"],
    queryFn: async () => {
      const json = await api.get<{ filters: SavedFilter[] }>(`/api/settings/saved-filters`);
      return json?.filters ?? [];
    },
  });

  const saveMut = useMutation({
    mutationFn: async (body: { name: string; description: string; filter_data: Record<string, unknown>; icon: IconName }) => {
      await api.post(`/api/settings/saved-filters`, body);
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["saved-filters"] }); toast.success("Filter saved"); },
  });

  const deleteMut = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/settings/saved-filters/${id}`); },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["saved-filters"] }); toast.success("Deleted"); },
  });

  const filters = data ?? [];
  const isActive = (f: SavedFilter | typeof PRESET_FILTERS[0]) =>
    JSON.stringify(activeFilter) === JSON.stringify(f.filterData);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between px-1 mb-2">
        <span className="text-[9px] font-semibold text-zinc-700 uppercase tracking-wider">Saved Filters</span>
        <button onClick={() => setShowPresets(!showPresets)} className="text-[9px] text-zinc-700 hover:text-zinc-500 transition-colors">
          + presets
        </button>
      </div>

      {isLoading ? (
        [1, 2, 3].map((i) => <div key={i} className="h-7 rounded-lg shimmer-bg mb-1" />)
      ) : (
        <>
          {filters.map((f) => {
            const Icon = ICON_MAP[f.icon] ?? Filter;
            return (
              <div key={f.id} className="group flex items-center">
                <button
                  onClick={() => onApplyFilter(f.filterData)}
                  className={cn(
                    "flex items-center gap-2 flex-1 px-2.5 py-1.5 rounded-lg text-[11px] transition-colors text-left",
                    isActive(f) ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02]",
                  )}
                >
                  <Icon className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                  <span className="truncate">{f.name}</span>
                  {isActive(f) && <Check className="w-2.5 h-2.5 ml-auto shrink-0" strokeWidth={2} />}
                </button>
                <button
                  onClick={() => { if (confirm("Delete?")) deleteMut.mutate(f.id); }}
                  className="p-1 rounded text-zinc-800 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 shrink-0"
                >
                  <Trash2 className="w-2.5 h-2.5" strokeWidth={1.5} />
                </button>
              </div>
            );
          })}
        </>
      )}

      <AnimatePresence>
        {showPresets && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="pt-1 border-t border-white/[0.03] mt-1 space-y-0.5">
              <span className="text-[8px] text-zinc-700 uppercase tracking-wider px-2.5 block mb-1">Presets</span>
              {PRESET_FILTERS.map((p) => {
                const Icon = ICON_MAP[p.icon] ?? Filter;
                const exists = filters.some((f) => f.name === p.name);
                return (
                  <div key={p.name} className="flex items-center gap-1 px-2.5 py-1 rounded-lg group">
                    <button
                      onClick={() => onApplyFilter(p.filterData)}
                      className={cn(
                        "flex items-center gap-2 flex-1 text-[10px] text-left transition-colors",
                        isActive(p) ? "text-emerald-400" : "text-zinc-600 hover:text-zinc-400",
                      )}
                    >
                      <Icon className="w-2.5 h-2.5 shrink-0" strokeWidth={1.5} />
                      <span>{p.name}</span>
                    </button>
                    {!exists && (
                      <button
                        onClick={() => saveMut.mutate({ name: p.name, description: p.description, filter_data: p.filterData, icon: p.icon })}
                        className="p-0.5 rounded text-zinc-800 hover:text-emerald-400 transition-colors opacity-0 group-hover:opacity-100"
                      >
                        <Plus className="w-2.5 h-2.5" strokeWidth={1.5} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

