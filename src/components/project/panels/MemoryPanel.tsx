"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StyledSelect } from "@/components/ui/styled-select";
import { Brain, Database, Plus, Trash2, X, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";

export function MemoryPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ key: "", value: "", category: "general" });

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "memory"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/memory`))?? {};
    },
  });

  const entries = (data as any)?.entries ?? [];

  const createEntry = useMutation({
    mutationFn: async () => {
      await api.post("/api/settings/memory", { key: form.key, value: form.value, source: "manual", category: form.category });
    },
    onSuccess: () => { setShowForm(false); setForm({ key: "", value: "", category: "general" }); queryClient.invalidateQueries({ queryKey: ["settings", "memory"] }); },
  });

  const deleteEntry = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/settings/memory/${id}`); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "memory"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-neutral-100">Agent Auto Memory</h2>
          <p className="text-sm text-neutral-500 mt-1">What the agent has learned about the project across sessions</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.98]">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {showForm ? "Cancel" : "Add Entry"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Key</label>
                  <input value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} placeholder="e.g. test_framework" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 font-mono focus:outline-none focus:border-emerald-500/50" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Category</label>
                  <StyledSelect value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                    {["general", "build", "test", "conventions", "deployment"].map((c) => <option key={c} value={c} className="bg-surface">{c}</option>)}
                  </StyledSelect>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-neutral-400">Value</label>
                <textarea value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} rows={2} placeholder="e.g. vitest" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 font-mono focus:outline-none focus:border-emerald-500/50 resize-none" />
              </div>
              <div className="flex justify-end">
                <button onClick={() => createEntry.mutate()} disabled={!form.key || !form.value || createEntry.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98]">
                  {createEntry.isPending ? "Saving..." : <><Check className="w-3.5 h-3.5" strokeWidth={1.5} /> Add Entry</>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {entries.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-48 text-neutral-600 text-sm gap-3">
          <Database className="w-10 h-10 opacity-30" strokeWidth={1} />
          <p>No memory entries yet. Add one manually or let the agent auto-discover patterns.</p>
        </div>
      )}

      <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06]">
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Key</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Value</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Source</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Category</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-neutral-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e: any) => (
                <tr key={e.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="px-4 py-3 text-sm text-neutral-300 font-mono">{e.key}</td>
                  <td className="px-4 py-3 text-xs text-neutral-400 max-w-[300px] truncate">{e.value}</td>
                  <td className="px-4 py-3">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${e.source === "auto" ? "bg-blue-500/10 text-blue-400" : "bg-emerald-500/10 text-emerald-400"}`}>{e.source}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-500">{e.category}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => deleteEntry.mutate(e.id)} className="p-1 rounded hover:bg-white/[0.06] text-neutral-500 hover:text-red-400 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
