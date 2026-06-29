"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Globe, Webhook, TerminalIcon, Plus, Check, X, Edit3, Trash2 } from "lucide-react";
import { api } from "@/lib/api/api-client";

const API = typeof window !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001" : "http://localhost:8001";

export function ChannelsPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", url: "", events: "run:completed" });

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "webhooks"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/webhooks`))?.webhooks ?? [];
    },
  });

  const webhooks = data ?? [];

  const channelIcons: Record<string, any> = { webhook: Webhook, webui: Globe, cli: TerminalIcon };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-zinc-100 tracking-tight">Delivery Channels</h2>
          <p className="text-sm text-zinc-500 mt-1">Webhook targets and platform integrations</p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.97]">
          {showForm ? <X size={14} strokeWidth={1.5} /> : <Plus size={14} strokeWidth={1.5} />}
          {showForm ? "Cancel" : "Add Channel"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-3xl p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-zinc-500">Name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. discord-bot" className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-300 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-zinc-500">Type</label>
                  <select className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-300 outline-none focus:border-emerald-500/40">
                    <option>Webhook</option><option>Slack</option><option>Discord</option>
                  </select>
                </div>
                <div className="space-y-1.5 col-span-2">
                  <label className="text-xs text-zinc-500">URL</label>
                  <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
                    placeholder="https://hooks.example.com/..." className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-300 placeholder-zinc-600 font-mono outline-none focus:border-emerald-500/40" />
                </div>
              </div>
              <div className="flex justify-end">
                <button className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-black font-medium hover:bg-emerald-400 transition-colors active:scale-[0.97]">
                  <Check size={14} strokeWidth={1.5} /> Create
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl overflow-hidden">
        {webhooks.length === 0 && !isLoading ? (
          <div className="flex flex-col items-center justify-center h-48 text-zinc-600 text-sm gap-3">
            <Globe size={32} strokeWidth={1} className="opacity-30" />
            <p>No channels configured</p>
            <button onClick={() => setShowForm(true)} className="text-xs text-emerald-400 hover:text-emerald-300">Add your first channel</button>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/20">
            <div className="flex items-center justify-between px-5 py-3 text-xs text-zinc-500 font-medium">
              <span>Channel</span><span>Status</span>
            </div>
            {webhooks.map((w: any, i: number) => {
              const Icon = channelIcons[w.type] || Globe;
              return (
                <div key={w.id || i} className="flex items-center justify-between px-5 py-3 hover:bg-zinc-900/30 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-zinc-800/50 flex items-center justify-center text-zinc-500">
                      <Icon size={14} strokeWidth={1.5} />
                    </div>
                    <div>
                      <p className="text-sm text-zinc-300">{w.name}</p>
                      <p className="text-xs text-zinc-600 font-mono truncate max-w-[240px]">{w.url}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${w.enabled ? "bg-emerald-500/10 text-emerald-400/80" : "bg-zinc-800/50 text-zinc-500"}`}>
                      {w.enabled ? "Active" : "Disabled"}
                    </span>
                    <button className="p-1 rounded hover:bg-zinc-800 text-zinc-600 hover:text-zinc-400 transition-colors">
                      <Trash2 size={12} strokeWidth={1.5} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
