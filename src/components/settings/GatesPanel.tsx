"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, Gauge } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";

interface Gate {
  id: string;
  name: string;
  metric: string;
  description: string;
  warn_threshold: number;
  fail_threshold: number;
  enabled: boolean;
  createdAt: string;
}

export function GatesPanel() {
  const [gates, setGates] = useState<Gate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [newGate, setNewGate] = useState({ name: "", metric: "", description: "", warn_threshold: 80, fail_threshold: 60 });

  const fetchGates = useCallback(async () => {
    try {
      const json = await api.get<{ gates?: Gate[] }>(`/api/settings/gates`);
      setGates(json?.gates ?? []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchGates(); }, [fetchGates]);

  const createGate = async () => {
    if (!newGate.name.trim() || !newGate.metric.trim()) return;
    try {
      await api.post(`/api/settings/gates`, newGate);
      toast.success("Gate created");
      setShowNew(false);
      setNewGate({ name: "", metric: "", description: "", warn_threshold: 80, fail_threshold: 60 });
      fetchGates();
    } catch { toast.error("Failed to create gate"); }
  };

  const deleteGate = async (id: string) => {
    try {
      await api.delete(`/api/settings/gates/${id}`);
      setGates((prev) => prev.filter((g) => g.id !== id));
      toast.success("Gate deleted");
    } catch { toast.error("Failed to delete gate"); }
  };

  const toggleGate = async (gate: Gate) => {
    try {
      await api.patch(`/api/settings/gates/${gate.id}`, { enabled: !gate.enabled });
      setGates((prev) => prev.map((g) => g.id === gate.id ? { ...g, enabled: !g.enabled } : g));
    } catch { toast.error("Failed to toggle gate"); }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Quality Gates</h3>
          <p className="text-xs text-zinc-600 mt-0.5">Define thresholds that block or warn on quality metrics</p>
        </div>
        <button onClick={() => setShowNew(!showNew)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors">
          <Plus className="w-3 h-3" strokeWidth={1.5} /> Add Gate
        </button>
      </div>

      <AnimatePresence>
        {showNew && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Name</label>
                  <input value={newGate.name} onChange={(e) => setNewGate({ ...newGate, name: e.target.value })}
                    placeholder="e.g. Pass Rate Gate"
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Metric</label>
                  <input value={newGate.metric} onChange={(e) => setNewGate({ ...newGate, metric: e.target.value })}
                    placeholder="e.g. pass_rate"
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Description</label>
                <input value={newGate.description} onChange={(e) => setNewGate({ ...newGate, description: e.target.value })}
                  placeholder="What does this gate check?"
                  className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Warn Threshold</label>
                  <input type="number" value={newGate.warn_threshold} onChange={(e) => setNewGate({ ...newGate, warn_threshold: parseFloat(e.target.value) || 0 })}
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40" />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Fail Threshold</label>
                  <input type="number" value={newGate.fail_threshold} onChange={(e) => setNewGate({ ...newGate, fail_threshold: parseFloat(e.target.value) || 0 })}
                    className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500/40" />
                </div>
              </div>
              <button onClick={createGate} disabled={!newGate.name.trim() || !newGate.metric.trim()}
                className="px-4 py-1.5 text-xs rounded-lg bg-emerald-500 text-black font-medium hover:bg-emerald-400 transition-all disabled:opacity-40">
                Create Gate
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-16 bg-white/[0.02] rounded-xl animate-pulse" />)}
        </div>
      ) : gates.length === 0 ? (
        <div className="flex flex-col items-center py-12 text-center">
          <Gauge className="w-8 h-8 text-zinc-800 mb-2" strokeWidth={1} />
          <p className="text-sm text-zinc-600">No quality gates configured</p>
          <p className="text-xs text-zinc-700 mt-1">Define thresholds to automatically block or warn on quality regressions</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {gates.map((gate, i) => (
            <motion.div key={gate.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
              className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 space-y-3 hover:border-white/[0.09] transition-colors">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${gate.enabled ? "bg-emerald-400" : "bg-zinc-700"}`} />
                  <span className="text-sm font-medium text-zinc-200">{gate.name}</span>
                  {!gate.enabled && <span className="text-[9px] text-zinc-600 font-mono">disabled</span>}
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => toggleGate(gate)}
                    className={`p-1 rounded text-[10px] transition-colors ${gate.enabled ? "text-zinc-600 hover:text-zinc-400" : "text-emerald-400 hover:text-emerald-300"}`}>
                    {gate.enabled ? "Pause" : "Enable"}
                  </button>
                  <button onClick={() => deleteGate(gate.id)}
                    className="p-1 rounded text-zinc-700 hover:text-red-400 transition-colors">
                    <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-4 text-[10px] text-zinc-600">
                <span className="font-mono">{gate.metric}</span>
                {gate.description && <span className="truncate">{gate.description}</span>}
              </div>
              <div className="flex items-center gap-4 text-[10px] text-zinc-600">
                <span className="flex items-center gap-1">Warn: <span className="text-amber-400 font-mono">{gate.warn_threshold}</span></span>
                <span className="flex items-center gap-1">Fail: <span className="text-red-400 font-mono">{gate.fail_threshold}</span></span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}


