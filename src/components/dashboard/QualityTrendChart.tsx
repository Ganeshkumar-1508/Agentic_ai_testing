"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart,
} from "recharts";
import { api } from "@/lib/api/api-client";

const METRICS_CONFIG: Record<string, { label: string; color: string }> = {
  pass_rate: { label: "Pass Rate", color: "#34d399" },
  flaky_rate: { label: "Flaky Rate", color: "#fb923c" },
  total_tests: { label: "Total Tests", color: "#818cf8" },
  coverage_line: { label: "Line Coverage", color: "#60a5fa" },
  pipeline_status: { label: "Pipeline Status", color: "#a78bfa" },
};

export function QualityTrendChart() {
  const { data, isLoading } = useQuery({
    queryKey: ["quality-trend-chart"],
    queryFn: async () => {
      const json = await api.get<{ metrics: Record<string, Array<{ date: string; value: number | string }>> }>("/api/quality/metrics?period=30d");
      const metrics = json?.metrics ?? {};
      const series = Object.entries(metrics).map(([key, points]) => ({
        key,
        label: METRICS_CONFIG[key]?.label ?? key,
        color: METRICS_CONFIG[key]?.color ?? "#71717a",
        data: (points ?? []).slice(-30).map((p) => ({
          date: p.date?.slice(5, 10) ?? "",
          value: typeof p.value === "number" ? p.value : parseFloat(String(p.value)) || 0,
        })),
      }));
      return series.filter((s) => s.data.length > 1);
    },
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-3">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        <div className="h-[200px] rounded-xl shimmer-bg" />
      </div>
    );
  }

  if (!data || data.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 space-y-4 h-full flex flex-col"
    >
      <div className="flex items-center justify-between shrink-0">
        <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">Quality Metrics (30d)</span>
        <div className="flex items-center gap-3">
          {data.map((s) => (
            <span key={s.key} className="flex items-center gap-1.5 text-[10px] text-zinc-600">
              <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-0">
        {data.map((series, idx) => (
          <div key={series.key} className="bg-white/[0.01] border border-white/[0.04] rounded-lg p-3">
            <span className="text-[10px] font-medium text-zinc-500 mb-2 block">{series.label}</span>
            <div className="h-[100px] min-h-[100px]">
              <ResponsiveContainer width="100%" height={100} debounce={50}>
              <AreaChart data={series.data}>
                <defs>
                  <linearGradient id={`grad-${idx}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={series.color} stopOpacity={0.15} />
                    <stop offset="100%" stopColor={series.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" hide />
                <YAxis hide domain={["dataMin - 5", "dataMax + 5"]} />
                <Tooltip
                  contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 11 }}
                  formatter={(value) => {
                    const n = typeof value === "number" ? value : Number(value) || 0;
                    return [n.toFixed(1)] as [string];
                  }}
                />
                <Area type="monotone" dataKey="value" stroke={series.color} strokeWidth={1.5} fill={`url(#grad-${idx})`} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
