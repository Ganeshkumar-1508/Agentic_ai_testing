"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { DollarSign, Plus, Trash2, ToggleLeft, ToggleRight } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface Budget {
  id: string;
  scope: string;
  name: string;
  softUsd: number;
  hardUsd: number;
  enabled: boolean;
}

const SCOPE_LABELS: Record<string, string> = {
  subagent: "Per-Subagent",
  phase: "Per-Phase",
  run: "Per-Run",
  user_day: "Per-User/Day",
};

const DEFAULT_SCOPES = [
  { scope: "subagent", name: "default", soft: 0.50, hard: 1.00 },
  { scope: "phase", name: "default", soft: 2.00, hard: 3.00 },
  { scope: "run", name: "default (cron)", soft: 5.00, hard: 10.00 },
  { scope: "run", name: "default (ui)", soft: 10.00, hard: 20.00 },
  { scope: "user_day", name: "default", soft: 50.00, hard: 75.00 },
];

export function BudgetSettings() {
  const queryClient = useQueryClient();
  const [showSeed, setShowSeed] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["budgets"],
    queryFn: async () => {
      const d = await api.get<{ budgets: Budget[] }>("/api/settings/budgets");
      return d?.budgets ?? [];
    },
  });

  const upsertMut = useMutation({
    mutationFn: (body: { scope: string; name: string; soft_usd: number; hard_usd: number; enabled: boolean }) =>
      api.post("/api/settings/budgets", body),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["budgets"] }); toast.success("Budget saved"); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/api/settings/budgets/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["budgets"] }); },
  });

  const budgets = data ?? [];
  const existingKeys = new Set(budgets.map((b) => `${b.scope}:${b.name}`));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Cost Budgets</div>
          <p className="text-[11px] text-zinc-600 mt-0.5">4 scopes: subagent → phase → run → user/day. Soft = warn, Hard = throttle.</p>
        </div>
        <button onClick={() => setShowSeed(!showSeed)} className="flex items-center gap-1.5 px-3 h-8 rounded-xl bg-white/[0.03] text-zinc-500 text-xs hover:text-zinc-300 transition-colors">
          <Plus className="w-3 h-3" strokeWidth={1.5} /> Defaults
        </button>
      </div>

      {showSeed && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 space-y-1">
          {DEFAULT_SCOPES.filter((s) => !existingKeys.has(`${s.scope}:${s.name}`)).map((s) => (
            <button key={`${s.scope}-${s.name}`} onClick={() => upsertMut.mutate({ scope: s.scope, name: s.name, soft_usd: s.soft, hard_usd: s.hard, enabled: true })}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02] transition-colors text-left">
              <Plus className="w-3 h-3 shrink-0" strokeWidth={1.5} />
              <span className="font-medium">{SCOPE_LABELS[s.scope] ?? s.scope}</span>
              <span className="text-zinc-700 font-mono">${s.soft} soft / ${s.hard} hard</span>
            </button>
          ))}
        </motion.div>
      )}

      <div className="space-y-2">
        {isLoading ? (
          [1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl shimmer-bg" />)
        ) : budgets.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-zinc-600">
            <DollarSign className="w-8 h-8 mb-2" strokeWidth={1} />
            <span className="text-xs">No budgets configured</span>
          </div>
        ) : (
          ["subagent", "phase", "run", "user_day"].map((scope) => {
            const scopeBudgets = budgets.filter((b) => b.scope === scope);
            if (scopeBudgets.length === 0) return null;
            return (
              <div key={scope}>
                <div className="text-[9px] text-zinc-700 uppercase tracking-wider px-1 mb-1">{SCOPE_LABELS[scope] ?? scope}</div>
                {scopeBudgets.map((b) => (
                  <div key={b.id} className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.01] border border-white/[0.04] group mb-1">
                    <DollarSign className="w-4 h-4 text-emerald-400/60 shrink-0" strokeWidth={1.5} />
                    <div className="flex-1">
                      <div className="text-xs font-mono font-semibold text-zinc-200">{b.name}</div>
                      <div className="text-[10px] text-zinc-600 font-mono">
                        ${b.softUsd.toFixed(2)} soft · ${b.hardUsd.toFixed(2)} hard
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1 text-[9px] text-zinc-700 font-mono">
                        <span className="text-zinc-500">throttle:</span>
                        <span>{b.hardUsd > 10 ? "pause" : b.hardUsd > 5 ? "cheap model" : "sequential"}</span>
                      </div>
                      <button onClick={() => upsertMut.mutate({ scope: b.scope, name: b.name, soft_usd: b.softUsd, hard_usd: b.hardUsd, enabled: !b.enabled })}
                        className="p-1 rounded transition-colors">
                        {b.enabled
                          ? <ToggleRight className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                          : <ToggleLeft className="w-4 h-4 text-zinc-600" strokeWidth={1.5} />}
                      </button>
                      <button onClick={() => { if (confirm("Delete?")) deleteMut.mutate(b.id); }}
                        className="p-1 rounded text-zinc-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100">
                        <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

