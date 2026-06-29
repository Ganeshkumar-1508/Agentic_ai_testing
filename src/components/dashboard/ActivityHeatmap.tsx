"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { Calendar, Clock, Layers } from "lucide-react";
import { api } from "@/lib/api/api-client";

function Skeleton() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 80, damping: 18 }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4 overflow-hidden relative"
    >
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.03] to-transparent -translate-x-full"
        animate={{ x: ["0%", "200%"] }}
        transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
      />
      <div className="w-32 h-4 rounded-full bg-white/[0.04]" />
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: 35 }).map((_, i) => (
          <div key={i} className="aspect-square rounded-sm bg-white/[0.02]" />
        ))}
      </div>
    </motion.div>
  );
}

export function ActivityHeatmap() {
  const [tab, setTab] = useState<"calendar" | "hourly" | "tools">("calendar");

  const { data: heatmapData, isLoading } = useQuery({
    queryKey: ["activity-heatmap"],
    queryFn: async () => {
      try {
        const [sessionsRes, tokensRes] = await Promise.all([
          api.get<{ daily?: any[] }>("/api/analytics/usage?days=90").catch(() => ({})),
          api.get<{ models?: any[] }>("/api/cost/models/stats?days=7").catch(() => ({})),
        ]);
        return { sessions: (sessionsRes as any)?.daily ?? [], models: (tokensRes as any)?.models ?? [] };
      } catch {
        return { sessions: [], models: [] };
      }
    },
    staleTime: 60_000,
  });

  if (isLoading) return <Skeleton />;

  const daily = (heatmapData?.sessions ?? []) as any[];
  const models = (heatmapData?.models ?? []) as any[];

  const today = new Date();
  const calendarDays = Array.from({ length: 91 }).map((_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (90 - i));
    const dayStr = d.toISOString().slice(0, 10);
    const match = daily.find((s: any) => s.day === dayStr || s.day?.startsWith(dayStr));
    const count = match?.sessions ?? match?.total_tokens ?? 0;
    return { date: dayStr, count, day: d.getDate(), month: d.getMonth() };
  });

  const maxCount = Math.max(...calendarDays.map(d => d.count), 1);
  const getIntensity = (count: number) => {
    if (count === 0) return "bg-white/[0.02]";
    const ratio = count / maxCount;
    if (ratio < 0.25) return "bg-emerald-500/15";
    if (ratio < 0.5) return "bg-emerald-500/30";
    if (ratio < 0.75) return "bg-emerald-500/50";
    return "bg-emerald-500/70";
  };

  const weeks: typeof calendarDays[] = [];
  for (let i = 0; i < calendarDays.length; i += 7) {
    weeks.push(calendarDays.slice(i, i + 7));
  }

  const toolRanking = models
    .sort((a: any, b: any) => (b.total_calls || 0) - (a.total_calls || 0))
    .slice(0, 10);

  const TABS = [
    { id: "calendar" as const, label: "Calendar", icon: Calendar },
    { id: "hourly" as const, label: "24h Series", icon: Clock },
    { id: "tools" as const, label: "Tool Ranking", icon: Layers },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 80, damping: 18 }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4"
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">Activity</span>
        <div className="flex gap-1 bg-white/[0.03] border border-white/[0.05] rounded-lg p-0.5">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-md transition-colors ${tab === t.id ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>
                <Icon className="w-3 h-3" strokeWidth={1.5} />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {tab === "calendar" && (
          <motion.div key="calendar" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}
            transition={{ type: "spring", stiffness: 100, damping: 20 }}
            className="space-y-1">
            <div className="grid grid-cols-7 gap-1">
              {["Mon","","Wed","","Fri","",""].map((d, i) => (
                <span key={i} className="text-[8px] text-zinc-700 text-center">{d}</span>
              ))}
              {calendarDays.map((d, i) => (
                <div key={i} title={`${d.date}: ${d.count} sessions`}
                  className={`aspect-square rounded-sm ${getIntensity(d.count)} hover:ring-1 hover:ring-emerald-400/40 transition-all cursor-default`}
                />
              ))}
            </div>
            <div className="flex items-center gap-2 justify-end text-[9px] text-zinc-700">
              <span>Less</span>
              {[0, 0.25, 0.5, 0.75, 1].map((r) => (
                <div key={r} className={`w-3 h-3 rounded-sm ${r === 0 ? "bg-white/[0.02]" : `bg-emerald-500/${Math.round(r * 70)}`}`} />
              ))}
              <span>More</span>
            </div>
          </motion.div>
        )}
        {tab === "hourly" && (
          <motion.div key="hourly" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}
            transition={{ type: "spring", stiffness: 100, damping: 20 }}
            className="h-48 min-h-[192px]">
            {daily.length > 0 ? (
              <ResponsiveContainer width="100%" height={192} debounce={50}>
                <BarChart data={daily.slice(-30)}>
                  <XAxis dataKey="day" tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} interval={6} />
                  <YAxis tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 11 }} />
                  <Bar dataKey="sessions" fill="#34d399" radius={[2, 2, 0, 0]} opacity={0.7} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-xs text-zinc-700">No hourly data yet</div>
            )}
          </motion.div>
        )}
        {tab === "tools" && (
          <motion.div key="tools" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}
            transition={{ type: "spring", stiffness: 100, damping: 20 }}
            className="space-y-2">
            {toolRanking.length > 0 ? (
              toolRanking.map((m: any, i: number) => (
                <div key={m.model} className="flex items-center gap-3">
                  <span className="text-[10px] text-zinc-600 font-mono w-5 text-right">{i + 1}</span>
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] text-zinc-300 truncate font-mono">{m.model}</span>
                      <span className="text-[10px] text-zinc-500 font-mono tabular-nums">{m.total_calls || 0}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                      <div className="h-full rounded-full bg-emerald-500/60 transition-all" style={{ width: `${Math.min(100, ((m.total_calls || 0) / Math.max(...toolRanking.map((x: any) => x.total_calls || 0), 1)) * 100)}%` }} />
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-xs text-zinc-700">No tool usage data yet</div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
