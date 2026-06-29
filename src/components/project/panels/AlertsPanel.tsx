"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StyledSelect } from "@/components/ui/styled-select";
import { Bell, BellOff, Plus, Trash2, X, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";

const CONDITION_TYPES = ["pipeline_fail", "flaky_rate", "pass_rate", "duration", "cost"];
const ACTION_TYPES = ["slack", "email", "webhook", "pagerduty", "custom"];

export function AlertsPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", conditionType: "pipeline_fail", conditionValue: 0, actionType: "slack", enabled: true });

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "alerts"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/alerts`))?? {};
    },
  });

  const alerts = (data as any)?.alerts ?? [];

  const createAlert = useMutation({
    mutationFn: async () => {
      await api.post(`/api/settings/alerts`, { name: form.name, condition_type: form.conditionType, condition_value: form.conditionValue, condition_direction: "above", action_type: form.actionType, action_config: {}, enabled: form.enabled });
    },
    onSuccess: () => { setShowForm(false); setForm({ name: "", conditionType: "pipeline_fail", conditionValue: 0, actionType: "slack", enabled: true }); queryClient.invalidateQueries({ queryKey: ["settings", "alerts"] }); },
  });

  const deleteAlert = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/settings/alerts/${id}`); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "alerts"] }),
  });

  const toggleAlert = useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => { await api.patch(`/api/settings/alerts/${id}`, { enabled }); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "alerts"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-neutral-100">Alert Rules</h2>
          <p className="text-sm text-neutral-500 mt-1">Notifications for pipeline events crossing thresholds</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.98]">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {showForm ? "Cancel" : "Add Alert"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. High Flaky Rate" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Condition</label>
                  <StyledSelect value={form.conditionType} onChange={(e) => setForm({ ...form, conditionType: e.target.value })}>
                    {CONDITION_TYPES.map((t) => <option key={t} value={t} className="bg-surface">{t.replace(/_/g, " ")}</option>)}
                  </StyledSelect>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Threshold</label>
                  <input type="number" value={form.conditionValue} onChange={(e) => setForm({ ...form, conditionValue: +e.target.value })} className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-emerald-500/50" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Action</label>
                  <StyledSelect value={form.actionType} onChange={(e) => setForm({ ...form, actionType: e.target.value })}>
                    {ACTION_TYPES.map((t) => <option key={t} value={t} className="bg-surface">{t}</option>)}
                  </StyledSelect>
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={() => createAlert.mutate()} disabled={!form.name || createAlert.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98]">
                  {createAlert.isPending ? "Saving..." : <><Check className="w-3.5 h-3.5" strokeWidth={1.5} /> Create Alert</>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {alerts.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-48 text-neutral-600 text-sm gap-3">
          <BellOff className="w-10 h-10 opacity-30" strokeWidth={1} />
          <p>No alert rules configured. Click "Add Alert" to create one.</p>
        </div>
      )}

      <div className="space-y-3">
        {alerts.map((a: any) => (
          <div key={a.id} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-neutral-400" strokeWidth={1.5} />
                <h3 className="text-sm font-medium text-neutral-200">{a.name}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => toggleAlert.mutate({ id: a.id, enabled: !a.enabled })} className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${a.enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-neutral-500/10 text-neutral-500"}`}>
                  {a.enabled ? "Active" : "Disabled"}
                </button>
                <button onClick={() => deleteAlert.mutate(a.id)} className="p-1 rounded hover:bg-white/[0.06] text-neutral-500 hover:text-red-400 transition-colors">
                  <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs text-neutral-500">
              <span>When <strong className="text-neutral-300">{a.conditionType}</strong> {a.conditionDirection} <strong className="text-neutral-300 font-mono">{a.conditionValue}</strong></span>
              <span>to <strong className="text-neutral-300">{a.actionType}</strong></span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
