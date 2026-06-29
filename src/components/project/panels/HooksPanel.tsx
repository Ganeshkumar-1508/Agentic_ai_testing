"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StyledSelect } from "@/components/ui/styled-select";
import { Webhook, Plus, Trash2, X, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";

export function HooksPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", hookType: "post", actionType: "webhook", targetUrl: "" });

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "hooks"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/hooks`))?? {};
    },
  });

  const hooks = (data as any)?.hooks ?? [];

  const createHook = useMutation({
    mutationFn: async () => {
      await api.post(`/api/settings/hooks`, { name: form.name, hook_type: form.hookType, action_type: form.actionType, target_url: form.targetUrl, enabled: true, sort_order: 0 });
    },
    onSuccess: () => { setShowForm(false); setForm({ name: "", hookType: "post", actionType: "webhook", targetUrl: "" }); queryClient.invalidateQueries({ queryKey: ["settings", "hooks"] }); },
  });

  const deleteHook = useMutation({
    mutationFn: async (id: string) => { await api.delete(`/api/settings/hooks/${id}`); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "hooks"] }),
  });

  const toggleHook = useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => { await api.patch(`/api/settings/hooks/${id}`, { enabled }); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "hooks"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-neutral-100">Pipeline Hooks</h2>
          <p className="text-sm text-neutral-500 mt-1">Pre/post pipeline automation scripts</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.98]">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {showForm ? "Cancel" : "Add Hook"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Notify Slack" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Type</label>
                  <StyledSelect value={form.hookType} onChange={(e) => setForm({ ...form, hookType: e.target.value })}>
                    <option value="pre" className="bg-surface">Pre-pipeline</option>
                    <option value="post" className="bg-surface">Post-pipeline</option>
                  </StyledSelect>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Action</label>
                  <StyledSelect value={form.actionType} onChange={(e) => setForm({ ...form, actionType: e.target.value })}>
                    <option value="webhook" className="bg-surface">Webhook</option>
                    <option value="api_call" className="bg-surface">API Call</option>
                    <option value="script" className="bg-surface">Script</option>
                  </StyledSelect>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Target URL</label>
                  <input value={form.targetUrl} onChange={(e) => setForm({ ...form, targetUrl: e.target.value })} placeholder="https://..." className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50" />
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={() => createHook.mutate()} disabled={!form.name || createHook.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98]">
                  {createHook.isPending ? "Saving..." : <><Check className="w-3.5 h-3.5" strokeWidth={1.5} /> Create Hook</>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {hooks.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-48 text-neutral-600 text-sm gap-3">
          <Webhook className="w-10 h-10 opacity-30" strokeWidth={1} />
          <p>No pipeline hooks configured. Click "Add Hook" to create one.</p>
        </div>
      )}

      <div className="space-y-3">
        {hooks.map((h: any) => (
          <div key={h.id} className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 flex items-start justify-between">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${h.hookType === "pre" ? "bg-blue-500/10 text-blue-400" : "bg-amber-500/10 text-amber-400"}`}>{h.hookType}</span>
                <h3 className="text-sm font-medium text-neutral-200">{h.name}</h3>
              </div>
              <p className="text-xs text-neutral-500">{h.actionType} &mdash; {h.targetUrl || "—"}</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => toggleHook.mutate({ id: h.id, enabled: !h.enabled })} className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${h.enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-neutral-500/10 text-neutral-500"}`}>
                {h.enabled ? "Active" : "Disabled"}
              </button>
              <button onClick={() => deleteHook.mutate(h.id)} className="p-1 rounded hover:bg-white/[0.06] text-neutral-500 hover:text-red-400 transition-colors">
                <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
