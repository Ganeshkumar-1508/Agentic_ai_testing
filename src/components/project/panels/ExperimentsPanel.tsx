"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StyledSelect } from "@/components/ui/styled-select";
import { FlaskConical, Beaker, Trophy, Plus, Trash2, X, Check, BarChart3 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";

const API = typeof window !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001" : "http://localhost:8001";

export function ExperimentsPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", targetMetric: "pass_rate", totalRuns: 100 });

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "experiments"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/experiments`))?? {};
    },
  });

  const experiments = (data as any)?.experiments ?? [];

  const createExperiment = useMutation({
    mutationFn: async () => {
      await api.post(`/api/settings/experiments`, { name: form.name, description: form.description, target_metric: form.targetMetric, total_runs: form.totalRuns, control_config: {}, variant_config: {} });
    },
    onSuccess: () => { setShowForm(false); setForm({ name: "", description: "", targetMetric: "pass_rate", totalRuns: 100 }); queryClient.invalidateQueries({ queryKey: ["settings", "experiments"] }); },
  });

  const deleteExperiment = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/settings/experiments/${id}`); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "experiments"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-neutral-100">Experiment Tracker</h2>
          <p className="text-sm text-neutral-500 mt-1">A/B test different prompts, models, and configurations</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.98]">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {showForm ? "Cancel" : "New Experiment"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. DeepSeek vs Groq" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50 active:scale-[0.98]" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Target Metric</label>
                  <StyledSelect value={form.targetMetric} onChange={(e) => setForm({ ...form, targetMetric: e.target.value })}>
                    <option value="pass_rate" className="bg-surface">Pass Rate</option>
                    <option value="flaky_rate" className="bg-surface">Flaky Rate</option>
                    <option value="duration" className="bg-surface">Duration</option>
                    <option value="cost" className="bg-surface">Cost</option>
                  </StyledSelect>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Total Runs</label>
                  <input type="number" value={form.totalRuns} onChange={(e) => setForm({ ...form, totalRuns: +e.target.value })} className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-emerald-500/50" />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-neutral-400">Description</label>
                <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} placeholder="What are you comparing?" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50 resize-none" />
              </div>
              <div className="flex justify-end">
                <button onClick={() => createExperiment.mutate()} disabled={!form.name || createExperiment.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98]">
                  {createExperiment.isPending ? "Saving..." : <><Check className="w-3.5 h-3.5" strokeWidth={1.5} /> Create Experiment</>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {experiments.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-48 text-neutral-600 text-sm gap-3">
          <FlaskConical className="w-10 h-10 opacity-30" strokeWidth={1} />
          <p>No experiments yet. Click &quot;New Experiment&quot; to compare configurations.</p>
        </div>
      )}

      <div className="space-y-4">
        {experiments.map((e: any) => {
          const progress = e.totalRuns > 0 ? (e.runsCompleted / e.totalRuns) * 100 : 0;
          const confidence = e.confidence ?? 0;
          return (
            <div key={e.id} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Beaker className="w-4 h-4 text-amber-400" strokeWidth={1.5} />
                  <h3 className="text-sm font-medium text-neutral-200">{e.name}</h3>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${e.status === "running" ? "bg-emerald-500/10 text-emerald-400" : e.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : "bg-neutral-500/10 text-neutral-500"}`}>{e.status}</span>
                  <button onClick={() => deleteExperiment.mutate(e.id)} className="p-1 rounded hover:bg-white/[0.06] text-neutral-500 hover:text-red-400 transition-colors active:scale-[0.98]">
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                </div>
              </div>

              {e.description && <p className="text-xs text-neutral-500">{e.description}</p>}

              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-neutral-500">Progress: {e.runsCompleted}/{e.totalRuns} runs</span>
                  <span className="text-neutral-400 font-mono">{progress.toFixed(0)}%</span>
                </div>
                <div className="w-full h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                  <div className="h-full rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${Math.min(progress, 100)}%` }} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white/[0.04] rounded-lg p-4 space-y-2">
                  <span className="text-xs text-neutral-500 font-medium">Control</span>
                  <div className="flex items-end gap-2">
                    <BarChart3 className="w-4 h-4 text-neutral-400" strokeWidth={1.5} />
                    <span className="text-lg font-semibold text-neutral-200 font-mono">{e.targetMetric}</span>
                  </div>
                  <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-neutral-500" style={{ width: "50%" }} />
                  </div>
                </div>
                <div className="bg-white/[0.04] rounded-lg p-4 space-y-2">
                  <span className="text-xs text-neutral-500 font-medium">Variant</span>
                  <div className="flex items-end gap-2">
                    <BarChart3 className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                    <span className="text-lg font-semibold text-neutral-200 font-mono">{e.targetMetric}</span>
                  </div>
                  <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: "65%" }} />
                  </div>
                </div>
              </div>

              {confidence > 0 && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-neutral-500">Statistical Confidence</span>
                    <span className="text-neutral-300 font-mono">{(confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-500 ${confidence > 0.8 ? "bg-emerald-500" : confidence > 0.5 ? "bg-amber-500" : "bg-neutral-500"}`} style={{ width: `${confidence * 100}%` }} />
                  </div>
                </div>
              )}

              {e.winner && (
                <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/5 rounded-lg px-3 py-2">
                  <Trophy className="w-3.5 h-3.5" strokeWidth={1.5} />
                  <span>Winner: {e.winner}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
