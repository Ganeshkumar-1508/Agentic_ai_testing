"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp, DollarSign, Play, Cpu } from "lucide-react";
import { api } from "@/lib/api/api-client";

const API = typeof window !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001" : "http://localhost:8001";

type DailyEntry = { day: string; input_tokens: number; output_tokens: number; estimated_cost: number; sessions: number };
type ModelEntry = { model: string; input_tokens: number; output_tokens: number; estimated_cost: number; api_calls: number };

export function AnalyticsPanel() {
  const [period, setPeriod] = useState(30);

  const { data: usageData, isLoading } = useQuery({
    queryKey: ["analytics", "usage", period],
    queryFn: async () => {
      return (await api.get<any>(`/api/analytics/usage?days=${period}`)) ?? { daily: [], totals: {} };
    },
  });

  const { data: modelData } = useQuery({
    queryKey: ["analytics", "models", period],
    queryFn: async () => {
      return (await api.get<any>(`/api/analytics/models?days=${period}`)) ?? { models: [] };
    },
  });

  const daily: DailyEntry[] = (usageData?.daily || []).map((d: any) => ({
    day: d.day?.slice(5) || "", input_tokens: d.input_tokens || 0, output_tokens: d.output_tokens || 0,
    estimated_cost: d.estimated_cost || 0, sessions: d.sessions || 0,
  }));
  const models: ModelEntry[] = (modelData?.models || []).map((m: any) => ({
    model: m.model, input_tokens: m.input_tokens || 0, output_tokens: m.output_tokens || 0,
    estimated_cost: m.estimated_cost || 0, api_calls: m.api_calls || 0,
  }));

  const t = usageData?.totals || {};
  const totalTokens = (t.total_input || 0) + (t.total_output || 0);
  const periods = [7, 14, 30];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-zinc-100 tracking-tight">Usage Analytics</h2>
          <p className="text-sm text-zinc-500 mt-1">Token consumption, cost trends, and model breakdown</p>
        </div>
        <div className="flex gap-1 bg-zinc-900/60 border border-zinc-800/50 rounded-lg p-0.5">
          {periods.map((d) => (
            <button key={d} onClick={() => setPeriod(d)}
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${period === d ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>{d}d</button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-64 rounded-3xl shimmer-bg border border-zinc-800/30" />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_1fr] gap-4">
            {[
              { icon: TrendingUp, label: "Total Tokens", value: totalTokens > 1_000_000 ? `${(totalTokens / 1_000_000).toFixed(1)}M` : `${(totalTokens / 1_000).toFixed(1)}K`, sub: "input + output" },
              { icon: DollarSign, label: "Total Cost", value: `$${(t.total_estimated_cost || 0).toFixed(2)}`, sub: "estimated API costs" },
              { icon: Play, label: "Sessions", value: String(t.total_sessions || 0), sub: "total pipeline runs" },
            ].map((k, i) => (
              <motion.div key={k.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 hover:border-zinc-700/50 transition-colors">
                <div className="flex items-center gap-2 mb-3">
                  <k.icon size={14} className="text-zinc-500" strokeWidth={1.5} />
                  <span className="text-xs font-medium text-zinc-500 tracking-wider uppercase">{k.label}</span>
                </div>
                <div className="text-2xl font-semibold tracking-tight text-zinc-100 font-mono">{k.value}</div>
                <div className="text-xs text-zinc-600 mt-1">{k.sub}</div>
              </motion.div>
            ))}
          </div>

          <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl p-5">
            <p className="text-xs font-medium text-zinc-500 tracking-wider uppercase mb-4">Daily Trend</p>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={daily.length > 0 ? daily : [{ day: "N/A", input_tokens: 0, output_tokens: 0 } as DailyEntry]}>
                <XAxis dataKey="day" tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} interval={4} />
                <YAxis tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="input_tokens" stroke="#34d399" strokeWidth={1.5} dot={false} name="Input" />
                <Line type="monotone" dataKey="output_tokens" stroke="#34d399" strokeWidth={1.5} strokeDasharray="4 2" dot={false} opacity={0.5} name="Output" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl p-5">
            <p className="text-xs font-medium text-zinc-500 tracking-wider uppercase mb-4">Daily Usage Stream</p>
            <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
              {daily.length === 0 ? (
                <p className="text-sm text-zinc-600">No data yet</p>
              ) : (
                [...daily].reverse().map((d) => (
                  <div key={d.day} className="shrink-0 bg-zinc-900/50 border border-zinc-800/30 rounded-xl px-4 py-3 min-w-[140px]">
                    <p className="text-[11px] text-zinc-500 font-mono">{d.day}</p>
                    <p className="text-sm font-medium text-zinc-200 font-mono mt-1">{(d.input_tokens + d.output_tokens).toLocaleString()}</p>
                    <div className="flex items-center gap-2 text-[10px] text-zinc-600 mt-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-400/60" /> {d.input_tokens.toLocaleString()} in
                      <span className="w-2 h-2 rounded-full bg-emerald-400/30 ml-1" /> {d.output_tokens.toLocaleString()} out
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {models.length > 0 && (
            <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl overflow-hidden">
              <div className="px-5 py-3 border-b border-zinc-800/30">
                <p className="text-xs text-zinc-500 tracking-wider uppercase">By Model</p>
              </div>
              <div className="divide-y divide-zinc-800/20">
                {models.map((m) => (
                  <div key={m.model} className="flex items-center justify-between px-5 py-3 hover:bg-zinc-900/30 transition-colors">
                    <span className="text-sm text-zinc-300 font-mono text-xs">{m.model}</span>
                    <div className="text-right text-sm">
                      <span className="text-zinc-300 font-mono">{(m.input_tokens + m.output_tokens).toLocaleString()} tokens</span>
                      <span className="text-xs text-zinc-600 ml-3">${m.estimated_cost.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
