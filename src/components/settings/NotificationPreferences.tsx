"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Bell, Mail, Slack, Globe, Plus, Trash2, ToggleLeft, ToggleRight } from "lucide-react";
import { api } from "@/lib/api/api-client";

const EVENT_OPTIONS = [
  { value: "run:completed", label: "Run completed" },
  { value: "run:failed", label: "Run failed" },
  { value: "run:started", label: "Run started" },
  { value: "heal:escalated", label: "HEAL escalation" },
  { value: "phase:gate", label: "HITL gate raised" },
  { value: "budget:warning", label: "Budget warning" },
  { value: "agent:error", label: "Agent error" },
];

const CHANNEL_ICONS: Record<string, typeof Bell> = {
  email: Mail,
  slack: Slack,
  webhook: Globe,
};

interface NotificationPref {
  id: string;
  channel: string;
  enabled: boolean;
  events: string[];
  target: string;
}

export function NotificationPreferences() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [newChannel, setNewChannel] = useState("email");
  const [newTarget, setNewTarget] = useState("");
  const [newEvents, setNewEvents] = useState<string[]>(["run:completed", "run:failed"]);

  const { data, isLoading } = useQuery({
    queryKey: ["notification-prefs"],
    queryFn: async () => {
      const json = await api.get<{ preferences: NotificationPref[] }>(`/api/settings/notification-prefs`);
      const prefs = json?.preferences ?? [];
      // Parse events from JSON string if needed
      return prefs.map((p: any) => ({
        ...p,
        events: Array.isArray(p.events) ? p.events : typeof p.events === "string" ? JSON.parse(p.events) : [],
      }));
    },
  });

  const upsertMut = useMutation({
    mutationFn: (body: { channel: string; enabled: boolean; events: string[]; target: string }) =>
      api.post(`/api/settings/notification-prefs`, { ...body, project_id: "*" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-prefs"] });
      setShowForm(false); setNewTarget(""); setNewEvents(["run:completed", "run:failed"]);
      toast.success("Notification saved");
    },
    onError: () => toast.error("Failed to save"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/api/settings/notification-prefs/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["notification-prefs"] }); toast.success("Deleted"); },
  });

  const toggleMut = useMutation({
    mutationFn: (pref: NotificationPref) =>
      api.post(`/api/settings/notification-prefs`, {
        channel: pref.channel,
        enabled: !pref.enabled,
        events: pref.events,
        target: pref.target,
        project_id: "*",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notification-prefs"] }),
  });

  const toggleEvent = (val: string) => {
    setNewEvents((prev) => prev.includes(val) ? prev.filter((e) => e !== val) : [...prev, val]);
  };

  const prefs = data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Notifications</div>
          <p className="text-[11px] text-zinc-600 mt-0.5">Receive alerts when runs complete or fail</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-1.5 px-3 h-8 rounded-xl bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors"
        >
          <Plus className="w-3 h-3" strokeWidth={2} />
          Add Channel
        </button>
      </div>

      {showForm && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="bg-white/[0.02] border border-white/[0.05] rounded-xl p-4 space-y-3">
          <div className="flex gap-2">
            {["email", "slack", "webhook"].map((ch) => {
              const Icon = CHANNEL_ICONS[ch] ?? Bell;
              return (
                <button key={ch} onClick={() => setNewChannel(ch)}
                  className={cn("flex items-center gap-1.5 px-3 h-8 rounded-lg text-[11px] font-medium transition-colors",
                    newChannel === ch ? "bg-emerald-500/15 text-emerald-400" : "bg-white/[0.03] text-zinc-500 hover:text-zinc-300"
                  )}>
                  <Icon className="w-3 h-3" strokeWidth={1.5} />
                  {ch.charAt(0).toUpperCase() + ch.slice(1)}
                </button>
              );
            })}
          </div>
          <input value={newTarget} onChange={(e) => setNewTarget(e.target.value)}
            placeholder={newChannel === "email" ? "you@company.com" : newChannel === "slack" ? "#channel or @user" : "https://hooks.example.com/notify"}
            className="w-full h-8 px-3 rounded-lg bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30"
          />
          <div className="flex flex-wrap gap-1.5">
            {EVENT_OPTIONS.map((opt) => (
              <button key={opt.value} onClick={() => toggleEvent(opt.value)}
                className={cn("px-2 h-6 rounded text-[10px] font-medium transition-colors",
                  newEvents.includes(opt.value) ? "bg-emerald-500/15 text-emerald-400" : "bg-white/[0.03] text-zinc-600 hover:text-zinc-400"
                )}>
                {opt.label}
              </button>
            ))}
          </div>
          <button onClick={() => { if (!newTarget.trim()) { toast.error("Target is required"); return; } upsertMut.mutate({ channel: newChannel, enabled: true, events: newEvents, target: newTarget }); }}
            disabled={!newTarget.trim() || newEvents.length === 0}
            className="px-3 h-7 rounded-lg bg-emerald-500/15 text-emerald-400 text-[10px] font-semibold hover:bg-emerald-500/25 transition-colors disabled:opacity-40">
            Save
          </button>
        </motion.div>
      )}

      <div className="space-y-2">
        {isLoading ? (
          [1, 2].map((i) => <div key={i} className="h-14 rounded-xl shimmer-bg" />)
        ) : prefs.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-zinc-600">
            <Bell className="w-8 h-8 mb-2" strokeWidth={1} />
            <span className="text-xs">No notification channels configured</span>
          </div>
        ) : (
          prefs.map((p) => {
            const Icon = CHANNEL_ICONS[p.channel] ?? Bell;
            return (
              <div key={p.id} className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.01] border border-white/[0.04] group">
                <div className="w-7 h-7 rounded-lg bg-emerald-500/8 flex items-center justify-center shrink-0">
                  <Icon className="w-3.5 h-3.5 text-emerald-400/70" strokeWidth={1.5} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-zinc-200 capitalize">{p.channel}</span>
                    {p.target && <span className="text-[10px] font-mono text-zinc-600">{p.target}</span>}
                  </div>
                  <div className="flex gap-1 mt-0.5">
                    {p.events.map((e) => {
                      const label = EVENT_OPTIONS.find((o) => o.value === e)?.label ?? e;
                      return <span key={e} className="text-[8px] text-zinc-600 px-1 py-0.5 rounded bg-white/[0.03]">{label}</span>;
                    })}
                  </div>
                </div>
                <button onClick={() => toggleMut.mutate(p)} className="p-1 rounded text-zinc-600 hover:text-emerald-400 transition-colors">
                  {p.enabled ? <ToggleRight className="w-4 h-4 text-emerald-400" strokeWidth={1.5} /> : <ToggleLeft className="w-4 h-4" strokeWidth={1.5} />}
                </button>
                <button onClick={() => { if (confirm("Delete?")) deleteMut.mutate(p.id); }}
                  className="p-1 rounded text-zinc-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100">
                  <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

