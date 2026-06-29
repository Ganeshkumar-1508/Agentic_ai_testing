"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, CheckCheck, Loader2, CheckCircle2, XCircle, AlertTriangle, Info } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

export interface NotificationItem {
  id: string;
  channel: string;
  subject: string;
  body: string;
  status: string;
  source: string;
  run_id: string;
  created_at: string | null;
  delivered_at: string | null;
}

interface NotificationsData {
  items: NotificationItem[];
  unread: number;
  count: number;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

function statusTone(status: string): "success" | "danger" | "warning" | "info" {
  if (status === "delivered" || status === "sent" || status === "completed") return "success";
  if (status === "failed" || status === "error") return "danger";
  if (status === "pending" || status === "retrying") return "warning";
  return "info";
}

const ICON_BY_TONE = {
  success: CheckCircle2,
  danger: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const ICON_COLOR_BY_TONE = {
  success: "text-emerald-400 bg-emerald-500/10",
  danger: "text-red-400 bg-red-500/10",
  warning: "text-amber-400 bg-amber-500/10",
  info: "text-blue-400 bg-blue-500/10",
};

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data, isLoading } = useQuery<NotificationsData>({
    queryKey: ["dashboard-notifications"],
    queryFn: () => api.get<NotificationsData>("/api/dashboard/widgets/notifications"),
    refetchInterval: 30_000,
    retry: 1,
  });

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", onClick);
      document.addEventListener("keydown", onEsc);
    }
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const items = data?.items ?? [];
  const count = data?.unread ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "relative inline-flex items-center justify-center w-9 h-9 rounded-lg border transition-colors",
          open
            ? "border-emerald-500/30 bg-emerald-500/[0.08]"
            : "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15] hover:bg-white/[0.06]"
        )}
        aria-label="Notifications"
      >
        <Bell className="w-4 h-4 text-zinc-300" strokeWidth={1.5} />
        {count > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center border-2 border-[#0a0a0f]">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="absolute right-0 top-11 w-[360px] max-h-[480px] flex flex-col rounded-[1.25rem] border border-white/[0.08] bg-[#0e0e18] shadow-[0_24px_60px_-12px_rgba(0,0,0,0.5)] z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
              <h4 className="text-[12px] font-semibold text-zinc-200">Notifications</h4>
              <button
                onClick={() => setOpen(false)}
                className="text-[10px] text-zinc-500 hover:text-emerald-400 transition-colors flex items-center gap-1"
              >
                <CheckCheck className="w-3 h-3" strokeWidth={1.5} />
                Mark all read
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {isLoading && !data ? (
                <div className="flex items-center justify-center py-12 text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
                </div>
              ) : items.length === 0 ? (
                <div className="px-4 py-10 text-center">
                  <p className="text-[12px] text-zinc-500">No notifications</p>
                  <p className="text-[10px] text-zinc-700 mt-1">Pipeline events will appear here</p>
                </div>
              ) : (
                items.map((n) => {
                  const tone = statusTone(n.status);
                  const Icon = ICON_BY_TONE[tone];
                  return (
                    <div
                      key={n.id}
                      className="flex items-start gap-3 px-4 py-3 border-b border-white/[0.06] hover:bg-white/[0.02] transition-colors"
                    >
                      <div className={cn("w-7 h-7 rounded-md flex items-center justify-center shrink-0", ICON_COLOR_BY_TONE[tone])}>
                        <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] text-zinc-200 leading-snug line-clamp-2">
                          {n.subject || "(no subject)"}
                        </div>
                        {n.body && (
                          <div className="text-[10px] text-zinc-500 mt-0.5 line-clamp-1">
                            {n.body}
                          </div>
                        )}
                        <div className="flex items-center gap-2 mt-1 text-[9px] font-mono uppercase tracking-wider">
                          <span className="text-zinc-600">{n.channel}</span>
                          {n.source && (
                            <>
                              <span className="text-zinc-800">·</span>
                              <span className="text-zinc-600">{n.source}</span>
                            </>
                          )}
                          <span className="text-zinc-700 ml-auto">{timeAgo(n.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
