"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, CheckCheck, Loader2, ExternalLink } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

interface Notification {
  id: string;
  channel: string;
  recipient: string;
  subject: string;
  body: string;
  status: string;
  error: string;
  source: string;
  run_id: string;
  created_at: string;
  delivered_at: string;
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ notifications: Notification[]; unread: number }>("/api/notifications?limit=10"),
    refetchInterval: 30_000,
  });

  const markAllRead = useMutation({
    mutationFn: () => api.post("/api/notifications/read-all", {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const notifications = data?.notifications ?? [];
  const unread = data?.unread ?? 0;

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)}
        className="relative w-8 h-8 rounded-lg bg-zinc-800/40 flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60 transition-all active:scale-[0.95]">
        <Bell size={14} strokeWidth={1.5} />
        {unread > 0 && (
          <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }}
            className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-[8px] font-bold text-white flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </motion.span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -4, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.96 }} transition={{ duration: 0.15 }}
            className="absolute right-0 top-full mt-1 w-80 rounded-xl bg-zinc-900/95 backdrop-blur-md border border-zinc-800/60 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.5)] overflow-hidden z-50">
            <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800/40">
              <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Notifications</span>
              {unread > 0 && (
                <button onClick={() => markAllRead.mutate()}
                  className="text-[9px] text-zinc-600 hover:text-zinc-400 transition-colors flex items-center gap-1">
                  <CheckCheck size={10} strokeWidth={1.5} /> Mark all read
                </button>
              )}
            </div>

            <div className="max-h-[360px] overflow-y-auto">
              {isLoading ? (
                <div className="flex items-center justify-center py-8"><Loader2 size={14} className="animate-spin text-zinc-600" /></div>
              ) : notifications.length === 0 ? (
                <div className="flex flex-col items-center py-8 text-zinc-600 gap-1">
                  <Bell size={16} strokeWidth={1} className="text-zinc-700" />
                  <p className="text-[11px]">No notifications</p>
                </div>
              ) : (
                notifications.map((n) => (
                  <div key={n.id} className={cn("px-3 py-2.5 border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors",
                    n.status === "pending" ? "bg-emerald-500/3" : "")}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-[12px] text-zinc-300 font-medium truncate">{n.subject || n.channel}</p>
                        <p className="text-[10px] text-zinc-600 mt-0.5 line-clamp-2">{n.body || "(no content)"}</p>
                      </div>
                      <span className="text-[9px] text-zinc-700 font-mono shrink-0 mt-0.5">{timeAgo(n.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[9px] text-zinc-700 font-mono capitalize">{n.channel}</span>
                      {n.status === "pending" && <span className="text-[8px] text-amber-400/60 font-mono">pending</span>}
                      {n.error && <span className="text-[8px] text-red-400/60 font-mono truncate">error</span>}
                      {n.run_id && (
                        <span className="text-[8px] text-zinc-700 font-mono">{n.run_id.slice(0, 8)}</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
