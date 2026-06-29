"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

type LogType = "console" | "network" | "errors";

interface LogEntry {
  id: string;
  time: string;
  level: string;
  event_type: string;
  agent_id: string;
  message: string;
  created_at: string;
}

const TABS: { key: LogType; label: string }[] = [
  { key: "console", label: "Console" },
  { key: "network", label: "Network" },
  { key: "errors", label: "Errors" },
];

const LEVEL_COLORS: Record<string, string> = {
  ERR: "text-red-400 bg-red-500/10",
  WARN: "text-amber-400 bg-amber-500/10",
  INFO: "text-emerald-400 bg-emerald-500/10",
  GET: "text-blue-400 bg-blue-500/10",
  POST: "text-blue-400 bg-blue-500/10",
  PUT: "text-blue-400 bg-blue-500/10",
};

export function LogsCard() {
  const [tab, setTab] = useState<LogType>("console");

  const { data, isLoading } = useQuery<{ events: LogEntry[]; count: number }>({
    queryKey: ["dashboard-logs", tab],
    queryFn: () => api.get<{ events: LogEntry[]; count: number }>(`/api/dashboard/widgets/logs?type=${tab}&limit=20`),
    refetchInterval: 10_000,
  });

  const events = data?.events ?? [];
  const isLive = tab === "console" || tab === "errors";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="rounded-[2rem] p-6 card-wireframe h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="card-label">Logs</div>
        {isLive && (
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] font-mono text-emerald-400">Live</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 mb-3 border-b border-white/[0.04] shrink-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "relative px-3 py-1.5 text-[11px] font-medium transition-colors",
              tab === t.key ? "text-neutral-100" : "text-neutral-500 hover:text-neutral-300"
            )}
          >
            {t.label}
            {tab === t.key && (
              <motion.span
                layoutId="logs-tab-indicator"
                className="absolute left-0 right-0 -bottom-px h-px bg-emerald-400"
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
              />
            )}
          </button>
        ))}
      </div>

      <div className="h-[320px] max-h-[320px] overflow-y-auto -mx-2 px-2 flex-1 min-h-0">
        {isLoading ? (
          <div className="space-y-1.5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-5 rounded shimmer-bg" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="text-xs text-neutral-600 text-center py-10">No {tab} events yet.</div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="space-y-0.5"
            >
              {events.map((e, i) => (
                <motion.div
                  key={e.id}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.02 }}
                  className="flex items-start gap-2 px-2 py-1 rounded text-[11px] font-mono hover:bg-white/[0.02] group"
                >
                  <span className="text-neutral-600 shrink-0 w-16">{e.time}</span>
                  <span
                    className={cn(
                      "shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider w-12 text-center",
                      LEVEL_COLORS[e.level] || "text-neutral-500 bg-white/[0.04]"
                    )}
                  >
                    {e.level}
                  </span>
                  <span className="flex-1 text-neutral-300 truncate">{e.message}</span>
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </motion.div>
  );
}
