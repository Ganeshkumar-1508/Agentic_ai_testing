"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { Cpu, DollarSign, Activity } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function ModelRoutingStats() {
  const [period, setPeriod] = useState(30);
  const [sortBy, setSortBy] = useState<"cost" | "calls">("cost");

  const { data, isLoading } = useQuery({
    queryKey: ["model-routing-stats", period],
    queryFn: async () => {
      return api.get<{
        models?: Array<{
          model: string;
          provider: string;
          total_calls: number;
          total_input: number;
          total_output: number;
          total_cost: number;
        }>;
        total_days?: number;
        error?: string;
      }>(`/api/cost/models/stats?days=${period}`);
    },
    refetchInterval: 60_000,
  });

  const models = (data?.models ?? [])
    .sort((a, b) => sortBy === "cost" ? (b.total_cost || 0) - (a.total_cost || 0) : (b.total_calls || 0) - (a.total_calls || 0));

  const totalCost = models.reduce((s, m) => s + (m.total_cost || 0), 0);
  const totalCalls = models.reduce((s, m) => s + (m.total_calls || 0), 0);

  if (isLoading) {
    return (
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4">
        <div className="w-40 h-4 rounded-full shimmer-bg" />
        <div className="h-[300px] rounded-xl shimmer-bg" />
      </div>
    );
  }

  if (data?.error) {
    return (
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-6 text-center">
        <p className="text-sm text-zinc-500">No model routing data yet</p>
        <p className="text-xs text-zinc-700 mt-1">Run pipelines to generate model usage statistics</p>
      </div>
    );
  }

  const COLORS = ["#34d399", "#60a5fa", "#a78bfa", "#fb923c", "#f472b6", "#fbbf24", "#4ade80", "#818cf8"];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 80, damping: 18 }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-5"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-zinc-500" strokeWidth={1.5} />
          <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Model Routing Stats</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 bg-white/[0.03] border border-white/[0.05] rounded-lg p-0.5">
            {[7, 14, 30, 90].map((d) => (
              <button key={d} onClick={() => setPeriod(d)}
                className={`px-2 py-1 text-[10px] rounded-md transition-colors ${period === d ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>
                {d}d
              </button>
            ))}
          </div>
          <div className="flex gap-1 bg-white/[0.03] border border-white/[0.05] rounded-lg p-0.5">
            <button onClick={() => setSortBy("cost")}
              className={`px-2 py-1 text-[10px] rounded-md transition-colors ${sortBy === "cost" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>
              <DollarSign className="w-3 h-3 inline" strokeWidth={1.5} /> Cost
            </button>
            <button onClick={() => setSortBy("calls")}
              className={`px-2 py-1 text-[10px] rounded-md transition-colors ${sortBy === "calls" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"}`}>
              <Activity className="w-3 h-3 inline" strokeWidth={1.5} /> Calls
            </button>
          </div>
        </div>
      </div>

      {models.length === 0 ? (
        <div className="flex flex-col items-center py-12 text-center">
          <Cpu className="w-8 h-8 text-zinc-800 mb-2" strokeWidth={1} />
          <p className="text-sm text-zinc-600">No model usage data for this period</p>
          <p className="text-xs text-zinc-700 mt-1">Run pipelines with configured providers to populate</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white/[0.01] border border-white/[0.04] rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-[10px] text-zinc-600">
                <DollarSign className="w-3 h-3" strokeWidth={1.5} />
                Total Cost
              </div>
              <div className="text-xl font-semibold tracking-tight text-zinc-100 mt-1">
                ${totalCost.toFixed(4)}
              </div>
            </div>
            <div className="bg-white/[0.01] border border-white/[0.04] rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-[10px] text-zinc-600">
                <Activity className="w-3 h-3" strokeWidth={1.5} />
                Total Calls
              </div>
              <div className="text-xl font-semibold tracking-tight text-zinc-100 mt-1">
                {totalCalls}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_240px] gap-5">
            <div className="h-64 min-h-[256px]">
              <ResponsiveContainer width="100%" height={256} debounce={50}>
                <BarChart data={models} layout="vertical" margin={{ left: 100 }}>
                  <XAxis type="number" tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey={sortBy === "cost" ? "model" : "model"} tick={{ fill: "#71717a", fontSize: 10 }} axisLine={false} tickLine={false} width={90} />
                  <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 11 }}
                    formatter={(value) => {
                      const n = typeof value === "number" ? value : Number(value) || 0;
                      return [sortBy === "cost" ? `$${n.toFixed(4)}` : n, sortBy === "cost" ? "Cost" : "Calls"] as [string, string];
                    }} />
                  <Bar dataKey={sortBy === "cost" ? "total_cost" : "total_calls"} radius={[0, 3, 3, 0]}>
                    {models.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} fillOpacity={0.7} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="h-64 min-h-[256px]">
              <ResponsiveContainer width="100%" height={256} debounce={50}>
                <PieChart>
                  <Pie data={models} dataKey="total_cost" nameKey="model" cx="50%" cy="50%" outerRadius={80} innerRadius={50}>
                    {models.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} fillOpacity={0.7} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 11 }}
                    formatter={(value) => {
                      const n = typeof value === "number" ? value : Number(value) || 0;
                      return [`$${n.toFixed(4)}`, "Cost"] as [string, string];
                    }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.05] text-zinc-500">
                  <th className="text-left py-2 px-3 font-medium">Model</th>
                  <th className="text-left py-2 px-3 font-medium">Provider</th>
                  <th className="text-right py-2 px-3 font-medium">Calls</th>
                  <th className="text-right py-2 px-3 font-medium">Input Tokens</th>
                  <th className="text-right py-2 px-3 font-medium">Output Tokens</th>
                  <th className="text-right py-2 px-3 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m, i) => (
                  <tr key={`${m.model}-${m.provider}`} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="py-2 px-3 text-zinc-300 font-mono">{m.model}</td>
                    <td className="py-2 px-3 text-zinc-500">{m.provider || "-"}</td>
                    <td className="py-2 px-3 text-right text-zinc-400 font-mono tabular-nums">{m.total_calls || 0}</td>
                    <td className="py-2 px-3 text-right text-zinc-400 font-mono tabular-nums">{(m.total_input || 0).toLocaleString()}</td>
                    <td className="py-2 px-3 text-right text-zinc-400 font-mono tabular-nums">{(m.total_output || 0).toLocaleString()}</td>
                    <td className="py-2 px-3 text-right text-zinc-400 font-mono tabular-nums">${(m.total_cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </motion.div>
  );
}
