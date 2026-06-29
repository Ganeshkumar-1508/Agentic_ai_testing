"use client";

import { useMemo } from "react";
import {
  Line,
  LineChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts";
import { cn } from "@/lib/utils";

interface TrendPoint {
  date: string;
  score: number;
  verdict: string;
}

interface Props {
  data: TrendPoint[];
  isLoading: boolean;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso.slice(5, 10);
  }
}

export function QualityTrendChart({ data, isLoading }: Props) {
  const chartData = useMemo(() => {
    return data.map((d) => ({
      label: formatDate(d.date),
      score: Math.round(d.score),
      verdict: d.verdict,
    }));
  }, [data]);

  const hasData = chartData.length > 0;
  const maxScore = 100;
  const currentScore = chartData[chartData.length - 1]?.score ?? 0;

  return (
    <div className="h-[260px] min-h-[260px]">
      {isLoading ? (
        <div className="h-full rounded-xl shimmer-bg" />
      ) : !hasData ? (
        <div className="h-full flex items-center justify-center text-[12px] text-neutral-600">
          No trend data available.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260} debounce={50}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "#737373", fontSize: 10, fontFamily: "var(--font-mono)" }}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              tickLine={false}
              interval={Math.max(1, Math.floor(chartData.length / 5))}
            />
            <YAxis
              domain={[0, maxScore]}
              tick={{ fill: "#737373", fontSize: 10, fontFamily: "var(--font-mono)" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `${v}`}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.[0]) return null;
                const d = payload[0].payload as { label: string; score: number };
                return (
                  <div className="bg-surface/95 backdrop-blur-sm border border-white/[0.06] rounded-lg px-3 py-2 text-[11px] font-mono shadow-lg">
                    <div className="text-neutral-500">{d.label}</div>
                    <div className="text-neutral-100 font-semibold">{d.score}/100</div>
                  </div>
                );
              }}
            />
            <ReferenceLine
              y={80}
              stroke="#34d399"
              strokeDasharray="4 4"
              strokeWidth={1}
              label={{
                value: "go",
                fill: "#34d399",
                fontSize: 9,
                fontFamily: "var(--font-mono)",
                position: "right",
              }}
            />
            <ReferenceLine
              y={60}
              stroke="#fbbf24"
              strokeDasharray="4 4"
              strokeWidth={1}
              label={{
                value: "warn",
                fill: "#fbbf24",
                fontSize: 9,
                fontFamily: "var(--font-mono)",
                position: "right",
              }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="#34d399"
              strokeWidth={2}
              dot={{ r: 3, fill: "#34d399", stroke: "none" }}
              activeDot={{ r: 5, fill: "#34d399", stroke: "#0a0a0f", strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
