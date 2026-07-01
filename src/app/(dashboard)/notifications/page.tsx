"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import { type ElementType } from "react";
import {
  Bell, CheckCheck, Mail, Slack, Globe,
  Loader2, Clock, CheckCircle2, XCircle, AlertTriangle,
} from "lucide-react";

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

const CHANNEL_ICONS: Record<string, ElementType> = { email: Mail, slack: Slack, webhook: Globe };

function formatTime(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

const springProps = { type: "spring" as const, stiffness: 200, damping: 24 };

export default function NotificationsPage() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["notifications-all"],
    queryFn: () => api.get<{ notifications: Notification[]; unread: number }>("/api/notifications?limit=100"),
    refetchInterval: 30_000,
  });

  const markAllRead = useMutation({
    mutationFn: () => api.post("/api/notifications/read-all", {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications-all"] }),
  });

  const notifications = data?.notifications ?? [];
  const unread = data?.unread ?? 0;

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
        <span className="text-xs font-mono text-zinc-600">/notifications</span>
      </div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
            <Bell size={16} className="text-zinc-400" strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Notifications</h1>
            <p className="text-sm text-zinc-600 mt-1">
              {unread > 0 ? `${unread} unread` : "All caught up"}
              &nbsp;·&nbsp;{notifications.length} total
            </p>
          </div>
        </div>
        {unread > 0 && (
          <button onClick={() => markAllRead.mutate()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-all active:scale-[0.97]">
            <CheckCheck size={12} strokeWidth={1.5} />
            Mark All Read
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl border border-zinc-800/30 bg-zinc-900/20 shimmer" />
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-zinc-600 gap-3">
          <Bell size={24} strokeWidth={1} className="text-zinc-700" />
          <p className="text-sm">No notifications yet</p>
          <p className="text-xs text-zinc-700">Notifications appear when runs complete, fail, or trigger alerts</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {notifications.map((n, i) => {
            const Icon = CHANNEL_ICONS[n.channel] ?? Bell;
            return (
              <motion.div key={n.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                transition={{ ...springProps, delay: i * 0.015 }}
                className={cn("flex items-start gap-3 px-4 py-3 rounded-xl border transition-all",
                  n.status === "pending"
                    ? "border-emerald-500/20 bg-emerald-500/3"
                    : n.error
                      ? "border-red-500/20 bg-red-500/3"
                      : "border-zinc-800/30 bg-zinc-900/20 hover:border-zinc-700/40")}>
                <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
                  n.status === "pending" ? "bg-emerald-500/10" : n.error ? "bg-red-500/10" : "bg-zinc-800/40")}>
                  <Icon size={13} className={cn(
                    n.status === "pending" ? "text-emerald-400" : n.error ? "text-red-400" : "text-zinc-500"
                  )} strokeWidth={1.5} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-zinc-200">{n.subject || n.channel}</span>
                    {n.status === "pending" && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 font-mono">pending</span>
                    )}
                    {n.error && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400 font-mono">failed</span>
                    )}
                    <span className="ml-auto text-[9px] text-zinc-700 font-mono">{formatTime(n.created_at)}</span>
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-3">{n.body || "(no content)"}</p>
                  <div className="flex items-center gap-2 mt-1.5 text-[9px] text-zinc-700 font-mono">
                    <span>via {n.channel}</span>
                    {n.recipient && <span>to {n.recipient}</span>}
                    {n.source && <span>source: {n.source}</span>}
                    {n.run_id && <span>run: {n.run_id.slice(0, 8)}</span>}
                    {n.delivered_at && <span>delivered {formatTime(n.delivered_at)}</span>}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
