"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Flag, Plus, Trash2, ToggleLeft, ToggleRight, FlaskConical } from "lucide-react";
import { api } from "@/lib/api/api-client";

const SEED_FLAGS = [
  { flag_key: "knowledge-graph", label: "Knowledge Graph", description: "Enable code graph indexing with Understand-Anything" },
  { flag_key: "multi-repo", label: "Multi-Repo", description: "Allow cross-repository runs" },
  { flag_key: "slack-integration", label: "Slack Integration", description: "Enable @testai Slack bot" },
  { flag_key: "heal-v2", label: "HEAL v2 Algorithm", description: "Use new deterministic + LLM hybrid healing" },
  { flag_key: "session-replay", label: "Session Replay", description: "Enable timeline-based agent session replay" },
  { flag_key: "batch-rerun", label: "Batch Re-Run", description: "Allow selecting and re-running multiple tests" },
];

interface FeatureFlag {
  key: string;
  flag_key?: string;
  label: string;
  description: string;
  enabled: boolean;
  rollout_percent: number;
}

export function FeatureFlags() {
  const queryClient = useQueryClient();
  const [showSeed, setShowSeed] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newRollout, setNewRollout] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["feature-flags"],
    queryFn: async () => {
      const json = await api.get<{ flags?: FeatureFlag[] }>(`/api/settings/feature-flags`);
      return json?.flags ?? [];
    },
  });

  const upsertMut = useMutation({
    mutationFn: async (body: { flag_key: string; label: string; description?: string; enabled: boolean; rollout_percent: number }) => {
      await api.post(`/api/settings/feature-flags`, body);
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["feature-flags"] }); toast.success("Flag saved"); },
    onError: (e: Error) => toast.error(e?.message ?? "Failed to save flag"),
  });

  const deleteMut = useMutation({
    mutationFn: async (key: string) => { await api.delete(`/api/settings/feature-flags/${key}`); },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["feature-flags"] }); toast.success("Flag deleted"); },
    onError: (e: Error) => toast.error(e?.message ?? "Failed to delete flag"),
  });

  const flags = data ?? [];
  const existingKeys = new Set(flags.map((f) => f.key || f.flag_key));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Feature Flags</div>
          <p className="text-[11px] text-zinc-600 mt-0.5">Roll out features gradually with percentage-based targeting</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowSeed(!showSeed)}
            className="flex items-center gap-1.5 px-3 h-8 rounded-xl bg-white/[0.03] text-zinc-500 text-xs hover:text-zinc-300 transition-colors">
            <FlaskConical className="w-3 h-3" strokeWidth={1.5} />
            Seed
          </button>
          <button onClick={() => { setShowAddForm(!showAddForm); setNewKey(""); setNewLabel(""); setNewDescription(""); setNewRollout(0); }}
            className="flex items-center gap-1.5 px-3 h-8 rounded-xl bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors">
            <Plus className="w-3 h-3" strokeWidth={2} />
            Add Flag
          </button>
        </div>
      </div>

      {showSeed && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 space-y-1">
          {SEED_FLAGS.filter((s) => !existingKeys.has(s.flag_key)).map((s) => (
            <button key={s.flag_key} onClick={() => upsertMut.mutate({
              flag_key: s.flag_key, label: s.label, description: s.description, enabled: false, rollout_percent: 0,
            })}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02] transition-colors text-left">
              <Plus className="w-3 h-3 shrink-0" strokeWidth={1.5} />
              <span className="font-mono text-[10px] font-medium">{s.flag_key}</span>
              <span className="truncate">{s.label}</span>
            </button>
          ))}
        </motion.div>
      )}

      {showAddForm && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Flag Key</label>
              <input value={newKey} onChange={(e) => setNewKey(e.target.value)}
                placeholder="e.g. dark-mode"
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Label</label>
              <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)}
                placeholder="e.g. Dark Mode"
                className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Description</label>
            <input value={newDescription} onChange={(e) => setNewDescription(e.target.value)}
              placeholder="What does this flag control?"
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Rollout %</label>
            <input type="number" value={newRollout} min={0} max={100}
              onChange={(e) => setNewRollout(parseInt(e.target.value) || 0)}
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40" />
          </div>
          <div className="flex gap-2">
            <button onClick={() => {
              if (!newKey.trim()) return;
              upsertMut.mutate({ flag_key: newKey.trim(), label: newLabel.trim() || newKey.trim(), description: newDescription, enabled: false, rollout_percent: newRollout });
              setShowAddForm(false);
              setNewKey(""); setNewLabel(""); setNewDescription(""); setNewRollout(0);
            }} disabled={!newKey.trim()}
              className="px-4 py-1.5 text-xs rounded-lg bg-emerald-500 text-black font-medium hover:bg-emerald-400 transition-all disabled:opacity-40">
              Create Flag
            </button>
            <button onClick={() => { setShowAddForm(false); setNewKey(""); setNewLabel(""); setNewDescription(""); setNewRollout(0); }}
              className="px-4 py-1.5 text-xs rounded-lg bg-white/[0.03] text-zinc-500 hover:text-zinc-300 transition-colors">
              Cancel
            </button>
          </div>
        </motion.div>
      )}

      <div className="space-y-2">
        {isLoading ? (
          [1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl shimmer-bg" />)
        ) : flags.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-zinc-600">
            <Flag className="w-8 h-8 mb-2" strokeWidth={1} />
            <span className="text-xs">No feature flags configured</span>
          </div>
        ) : (
          flags.map((f) => (
            <div key={f.key || f.flag_key} className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.01] border border-white/[0.04] group">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/8 flex items-center justify-center shrink-0">
                <Flag className={cn("w-3.5 h-3.5", f.enabled ? "text-emerald-400" : "text-zinc-700")} strokeWidth={1.5} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-semibold text-zinc-200">{f.key || f.flag_key}</span>
                  <span className="text-[11px] text-zinc-400">{f.label}</span>
                </div>
                {f.description && <div className="text-[10px] text-zinc-600">{f.description}</div>}
              </div>
              {f.rollout_percent > 0 && (
                <div className="flex items-center gap-1.5">
                  <input
                    type="number" min={0} max={100} defaultValue={f.rollout_percent}
                    onBlur={(e) => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 0 && v <= 100 && v !== f.rollout_percent) upsertMut.mutate({ flag_key: f.key ?? f.flag_key ?? "", label: f.label, description: f.description, enabled: f.enabled, rollout_percent: v }); }}
                    className="w-12 bg-white/[0.04] border border-white/[0.06] rounded px-1 py-0.5 text-[9px] font-mono text-zinc-400 outline-none focus:border-emerald-500/40 text-center"
                  />
                  <span className="text-[9px] font-mono text-zinc-600">%</span>
                </div>
              )}
              <button
                onClick={() => upsertMut.mutate({
                  flag_key: f.key ?? f.flag_key ?? "", label: f.label, description: f.description, enabled: !f.enabled, rollout_percent: f.enabled ? f.rollout_percent : 100,
                })}
                className="p-1 rounded transition-colors"
              >
                {f.enabled
                  ? <ToggleRight className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
                  : <ToggleLeft className="w-4 h-4 text-zinc-600" strokeWidth={1.5} />
                }
              </button>
              <button onClick={() => { if (confirm("Delete?")) deleteMut.mutate(f.key ?? f.flag_key ?? ""); }}
                className="p-1 rounded text-zinc-800 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100">
                <Trash2 className="w-3 h-3" strokeWidth={1.5} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

