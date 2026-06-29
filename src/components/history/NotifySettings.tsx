"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

interface Channel {
  id: string;
  name: string;
  url: string;
  type: string;
  events: string[];
  enabled: boolean;
}

const EVENT_OPTIONS = [
  { value: "flaky.quarantine", label: "Flaky Quarantine" },
  { value: "session.failed", label: "Pipeline Failed" },
  { value: "session.completed", label: "Pipeline Completed" },
  { value: "budget.alert", label: "Budget Alert" },
  { value: "pipeline.started", label: "Pipeline Started" },
];

export function NotifySettings() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>(["flaky.quarantine"]);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["notify-channels"],
    queryFn: async () => {
      const d = await api.get<{ channels: Channel[] }>("/api/notify/channels");
      return d?.channels ?? [];
    },
  });

  const addMutation = useMutation({
    mutationFn: () => api.post("/api/notify/channels", { name, url, events: selectedEvents }),
    onSuccess: () => {
      setName("");
      setUrl("");
      setSelectedEvents(["flaky.quarantine"]);
      qc.invalidateQueries({ queryKey: ["notify-channels"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/notify/channels/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notify-channels"] }),
  });

  const testMutation = useMutation({
    mutationFn: () => api.post("/api/notify/test"),
  });

  const channels = data ?? [];

  const toggleEvent = (evt: string) => {
    setSelectedEvents((prev) =>
      prev.includes(evt) ? prev.filter((e) => e !== evt) : [...prev, evt]
    );
  };

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] rounded-lg border transition-colors",
          open ? "bg-white/[0.05] border-white/[0.1] text-zinc-200" : "border-white/[0.06] text-zinc-500 hover:text-zinc-300"
        )}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l2-3h6l2 3h3a2 2 0 0 1 2 2v8z" />
          <circle cx="12" cy="13" r="3" />
        </svg>
        Notifications
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, y: -8, height: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="bg-surface border border-white/[0.06] rounded-xl p-4 space-y-4 overflow-hidden"
          >
            {/* Existing channels */}
            <div>
              <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-[0.05em] mb-2">Configured Channels</div>
              {isLoading ? (
                <div className="h-8 rounded-lg shimmer-bg" />
              ) : channels.length === 0 ? (
                <div className="text-[11px] text-zinc-600 py-2">No channels configured.</div>
              ) : (
                <div className="space-y-1.5">
                  {channels.map((ch) => (
                    <div key={ch.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/[0.02]">
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] text-zinc-300 truncate">{ch.name}</div>
                        <div className="text-[9px] text-zinc-600 font-mono truncate">{ch.url}</div>
                        {ch.events && ch.events.length > 0 && (
                          <div className="flex gap-1 mt-1 flex-wrap">
                            {ch.events.map((e) => (
                              <span key={e} className="text-[8px] px-1 py-0.5 rounded bg-zinc-800 text-zinc-500">{e}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0 ml-2">
                        <span className={cn("w-1.5 h-1.5 rounded-full", ch.enabled ? "bg-emerald-400" : "bg-zinc-600")} />
                        <button
                          onClick={() => deleteMutation.mutate(ch.id)}
                          className="w-6 h-6 rounded flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add new */}
            <div className="space-y-2.5 pt-3 border-t border-white/[0.06]">
              <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-[0.05em]">Add Webhook</div>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Channel name (e.g. #team-ci)"
                className="w-full bg-zinc-900 border border-white/[0.06] rounded-lg px-3 py-1.5 text-[11px] text-zinc-300 placeholder-zinc-700 outline-none focus:border-emerald-500/40 transition-colors"
              />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Webhook URL (Slack, Teams, etc.)"
                className="w-full bg-zinc-900 border border-white/[0.06] rounded-lg px-3 py-1.5 text-[11px] text-zinc-300 placeholder-zinc-700 font-mono outline-none focus:border-emerald-500/40 transition-colors"
              />
              <div>
                <div className="text-[9px] text-zinc-600 mb-1.5">Events to notify:</div>
                <div className="flex flex-wrap gap-1.5">
                  {EVENT_OPTIONS.map((evt) => (
                    <button
                      key={evt.value}
                      onClick={() => toggleEvent(evt.value)}
                      className={cn(
                        "px-2 py-1 text-[9px] rounded-lg border transition-colors",
                        selectedEvents.includes(evt.value)
                          ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                          : "bg-zinc-900 border-white/[0.06] text-zinc-500 hover:text-zinc-300"
                      )}
                    >
                      {evt.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={() => addMutation.mutate()}
                  disabled={!url.trim() || addMutation.isPending}
                  className="px-3 py-1.5 text-[10px] font-semibold rounded-lg bg-emerald-400/10 text-emerald-400 border border-emerald-400/20 hover:bg-emerald-400/20 transition-colors disabled:opacity-40"
                >
                  {addMutation.isPending ? "Adding..." : "Add Channel"}
                </button>
                <button
                  onClick={() => testMutation.mutate()}
                  disabled={testMutation.isPending || channels.length === 0}
                  className="px-3 py-1.5 text-[10px] rounded-lg bg-zinc-900 border border-white/[0.06] text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40"
                >
                  {testMutation.isPending ? "Sending..." : "Test All"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
