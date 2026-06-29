"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function ProviderEventsSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["provider-events"],
    queryFn: () => api.get<{ events: any[] }>("/api/settings/provider-events?limit=50"),
    refetchInterval: 30_000,
  });

  const events = data?.events ?? [];

  return (
    <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Activity size={14} className="text-zinc-500" strokeWidth={1.5} />
        <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Provider Events</h2>
        <span className="text-[10px] text-zinc-600 font-mono">{events.length} events</span>
      </div>

      {isLoading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-8 shimmer-bg rounded" />)}</div>
      ) : events.length === 0 ? (
        <p className="text-sm text-zinc-600 text-center py-6">No provider events recorded yet</p>
      ) : (
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {events.map((ev: any, i: number) => (
            <div key={i} className="flex items-start gap-3 py-1.5 px-2 rounded-lg hover:bg-zinc-800/30 transition-colors">
              <span className="text-[10px] font-mono text-zinc-600 w-16 shrink-0">
                {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ""}
              </span>
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 ${
                ev.event_type === "circuit_open" ? "bg-red-900/30 text-red-400" :
                ev.event_type === "recovery" ? "bg-emerald-900/30 text-emerald-400" :
                ev.event_type === "failure" ? "bg-amber-900/30 text-amber-400" :
                "bg-zinc-800/50 text-zinc-500"
              }`}>
                {ev.event_type || ev.type || "info"}
              </span>
              <span className="text-[11px] text-zinc-500 font-mono">{ev.provider || ev.message?.split(":")[0] || ""}</span>
              <span className="text-[11px] text-zinc-600 flex-1 truncate">{ev.message || ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
