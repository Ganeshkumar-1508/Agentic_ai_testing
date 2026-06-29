"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from "recharts";
import { TrendingUp, Calendar, Beaker, DollarSign, Clock } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface ReleasePoint {
  label: string;
  date: string;
  passRate: number;
  testCount: number;
  coverage: number;
  cost: number;
  duration: number;
  flakyCount: number;
}

export function ReleaseTracking() {
  const { data, isLoading } = useQuery({
    queryKey: ["release-tracking"],
    queryFn: async () => {
      const [runsRes, covRes] = await Promise.all([
        api.get<{ runs: any[] }>(`/api/runs?limit=200`),
        api.get<{ reports?: any[] }>(`/api/coverage/history?limit=50`),
      ]);
      const runs = runsRes?.runs ?? [];
      const reports = covRes?.reports ?? [];

      const byDate = new Map<string, {
        total: number; passed: number; tests: number;
        costs: number[]; durations: number[]; flaky: number;
      }>();

      for (const r of runs) {
        if (!r.createdAt) continue;
        const week = new Date(r.createdAt).toISOString().slice(0, 7);
        const bucket = byDate.get(week) ?? { total: 0, passed: 0, tests: 0, costs: [], durations: [], flaky: 0 };
        bucket.total += 1;
        if (r.status === "completed") bucket.passed += 1;
        bucket.tests += r.testCount || 0;
        if (r.duration) bucket.durations.push(r.duration);
        byDate.set(week, bucket);
      }

      const avgCoverage = reports.length > 0
        ? reports.reduce((s: number, r: any) => s + (r.lineCoverage ?? 0), 0) / reports.length
        : 0;

      const points: ReleasePoint[] = Array.from(byDate.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([label, b]) => ({
          label,
          date: label,
          passRate: b.total > 0 ? Math.round((b.passed / b.total) * 100) : 0,
          testCount: b.tests,
          coverage: Math.round(avgCoverage),
          cost: b.costs.length > 0 ? +(b.costs.reduce((s, c) => s + c, 0) / b.costs.length).toFixed(2) : 0,
          duration: b.durations.length > 0 ? Math.round(b.durations.reduce((s, d) => s + d, 0) / b.durations.length) : 0,
          flakyCount: 0,
        }));

      return points;
    },
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5 space-y-4">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        <div className="h-48 bg-white/[0.02] rounded-xl animate-pulse" />
      </div>
    );
  }

  if (!data || data.length < 2) return null;

  const latest = data[data.length - 1];
  const prev = data[data.length - 2];
  const change = prev ? latest.passRate - prev.passRate : 0;

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
          </div>
          <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Quality Trend</span>
          <span className="text-[10px] font-mono text-zinc-600">{data.length} periods</span>
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          <span className="flex items-center gap-1 text-zinc-500">
            <Beaker className="w-3 h-3" strokeWidth={1.5} />
            Latest: <span className="text-zinc-200 font-semibold">{latest.passRate}%</span>
          </span>
          {change !== 0 && (
            <span className={change > 0 ? "text-emerald-400" : "text-red-400"}>
              {change > 0 ? "+" : ""}{change}%
            </span>
          )}
        </div>
      </div>

      <div className="h-48 min-h-[192px]">
        <ResponsiveContainer width="100%" height={192} debounce={50}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="passGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.15} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fill: "#52525b", fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "#181825", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, fontSize: 11 }}
              labelStyle={{ color: "#f0f0f5" }}
            />
            <Area type="monotone" dataKey="passRate" stroke="#34d399" strokeWidth={2} fill="url(#passGrad)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-4 gap-3 mt-4 pt-4 border-t border-white/[0.05]">
        {[
          { label: "Avg Pass Rate", value: `${data.reduce((s, p) => s + p.passRate, 0) / data.length}%`, icon: Beaker },
          { label: "Total Tests", value: data.reduce((s, p) => s + p.testCount, 0).toLocaleString(), icon: Beaker },
          { label: "Avg Coverage", value: `${data.reduce((s, p) => s + p.coverage, 0) / data.length}%`, icon: TrendingUp },
          { label: "Periods Tracked", value: `${data.length}`, icon: Calendar },
        ].map((stat, i) => {
          const Icon = stat.icon;
          return (
            <div key={i} className="text-center">
              <div className="text-[10px] text-zinc-600 font-medium uppercase tracking-wider">{stat.label}</div>
              <div className="text-lg font-semibold text-zinc-100 font-mono tabular-nums mt-1">{stat.value}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
