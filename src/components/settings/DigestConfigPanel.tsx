"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PlusIcon, TrashIcon, ReloadIcon } from "@radix-ui/react-icons";
import { api } from "@/lib/api/api-client";

interface DigestConfig {
  id: string;
  platform: string;
  channel_id: string;
  schedule: string;
  enabled: boolean;
  created_at: string;
}

export function DigestConfigPanel() {
  const [configs, setConfigs] = useState<DigestConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ platform: "slack", channel_id: "", schedule: "0 8 * * 1-5" });
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ configs: DigestConfig[] }>("/api/digest/configs");
      setConfigs(d?.configs ?? []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addConfig = async () => {
    if (!form.channel_id.trim()) return;
    try {
      await api.post("/api/digest/configs", form);
      setShowForm(false);
      setForm({ platform: "slack", channel_id: "", schedule: "0 8 * * 1-5" });
      await load();
    } catch { /* ignore */ }
  };

  const deleteConfig = async (id: string) => {
    try {
      await api.delete(`/api/digest/configs/${id}`);
      await load();
    } catch { /* ignore */ }
  };

  const testDigest = async () => {
    setStatus("sending...");
    try {
      await api.post("/api/digest/run");
      setStatus("Digest sent");
    } catch { setStatus("Error"); }
    setTimeout(() => setStatus(null), 3000);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Daily Digest</h3>
          <p className="text-xs text-zinc-600 mt-1">Scheduled summary of test results sent to messaging platforms</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={testDigest} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-xs text-zinc-400 hover:text-zinc-200 transition-colors">
            <ReloadIcon className="w-3 h-3" /> Test Now
          </button>
          <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors text-xs">
            <PlusIcon className="w-3 h-3" /> Add Channel
          </button>
        </div>
      </div>

      {status && (
        <div className="text-xs text-zinc-500 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06]">{status}</div>
      )}

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] font-mono text-zinc-600 uppercase tracking-wider">Platform</label>
                  <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}
                    className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none">
                    <option value="slack">Slack</option>
                    <option value="teams">Teams</option>
                    <option value="telegram">Telegram</option>
                    <option value="email">Email</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-mono text-zinc-600 uppercase tracking-wider">Channel / Recipient</label>
                  <input value={form.channel_id} onChange={(e) => setForm({ ...form, channel_id: e.target.value })}
                    placeholder="#channel or user@email.com"
                    className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-700 font-mono outline-none focus:border-emerald-500/40" />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-mono text-zinc-600 uppercase tracking-wider">Cron Schedule</label>
                  <input value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })}
                    placeholder="0 8 * * 1-5"
                    className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-700 font-mono outline-none focus:border-emerald-500/40" />
                </div>
              </div>
              <button onClick={addConfig} disabled={!form.channel_id.trim()}
                className="px-4 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 text-xs font-medium disabled:opacity-40 transition-colors">
                Save Config
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="text-xs text-zinc-700 py-4">Loading...</div>
      ) : configs.length === 0 ? (
        <div className="text-xs text-zinc-700 py-4 text-center">No digest channels configured. Add one to receive daily summaries.</div>
      ) : (
        <div className="space-y-2">
          {configs.map((cfg) => (
            <div key={cfg.id} className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.02] border border-white/[0.06] text-xs">
              <span className="text-zinc-300 font-medium w-16">{cfg.platform}</span>
              <span className="text-zinc-500 font-mono flex-1">{cfg.channel_id}</span>
              <span className="text-zinc-700 font-mono">{cfg.schedule}</span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${cfg.enabled ? "bg-emerald-400/10 text-emerald-400" : "bg-zinc-800 text-zinc-600"}`}>
                {cfg.enabled ? "active" : "disabled"}
              </span>
              <button onClick={() => deleteConfig(cfg.id)} className="p-1 rounded text-zinc-700 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                <TrashIcon className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
