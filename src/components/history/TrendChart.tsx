"use client";

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

export interface TrendPoint {
  date: string;
  passRate: number;
  flakyRate?: number;
  failed: number;
}

interface TrendChartProps {
  data: TrendPoint[];
  loading?: boolean;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 shadow-xl">
      <div className="text-[10px] text-zinc-500 mb-1">{label}</div>
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2 text-[11px]">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-zinc-400">{p.name}:</span>
          <span className="text-zinc-200 font-semibold font-mono">{p.value}%</span>
        </div>
      ))}
    </div>
  );
}

export function TrendChart({ data, loading }: TrendChartProps) {
  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="w-44 h-4 rounded-full bg-white/[0.03] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
          <div className="flex gap-3">
            <div className="w-16 h-3 rounded-full bg-white/[0.03]" />
            <div className="w-16 h-3 rounded-full bg-white/[0.03]" />
          </div>
        </div>
        <div className="h-[200px] rounded-xl bg-white/[0.02] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.03] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
      </div>
    );
  }

  if (!data || data.length < 2) return null;

  return (
    <div className="bg-surface border border-white/[0.06] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[13px] font-semibold text-zinc-100">Pass Rate Trend &mdash; Last 30 Days</h2>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-[10px] text-zinc-500">Pass Rate</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span className="text-[10px] text-zinc-500">Flaky Rate</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-400" />
            <span className="text-[10px] text-zinc-500">Failure Threshold</span>
          </div>
        </div>
      </div>
      <div className="h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#52525b", fontSize: 10, fontFamily: "Geist Mono, monospace" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: string) => v.slice(5)}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: "#52525b", fontSize: 10, fontFamily: "Geist Mono, monospace" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `${v}%`}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(255,255,255,0.08)" }} />
            <Line
              type="monotone"
              dataKey="passRate"
              stroke="#34d399"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "#34d399", stroke: "#12121c", strokeWidth: 2 }}
            />
            <Line
              type="monotone"
              dataKey="flakyRate"
              stroke="#f59e0b"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: "#f59e0b", stroke: "#12121c", strokeWidth: 2 }}
            />
            <Line
              type="monotone"
              dataKey="failureThreshold"
              stroke="#f87171"
              strokeWidth={1.5}
              strokeDasharray="6 4"
              dot={false}
              activeDot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
