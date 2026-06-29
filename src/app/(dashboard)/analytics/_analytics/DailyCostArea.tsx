"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface DailyPoint {
  day: string;
  estimated_cost: number;
  sessions: number;
}

interface Props {
  data: DailyPoint[];
  range: number;
  isLoading: boolean;
}

export function DailyCostArea({ data, range, isLoading }: Props) {
  const chartData = useMemo(() => {
    return data.map((d) => ({
      day: d.day,
      label: formatLabel(d.day),
      cost: Number(d.estimated_cost || 0),
      sessions: d.sessions,
    }));
  }, [data]);

  const hasData = chartData.length > 0;
  const totalCost = chartData.reduce((s, d) => s + d.cost, 0);
  const maxCost = Math.max(0.01, ...chartData.map((d) => d.cost));

  return (
    <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider">
            Daily cost
          </div>
          <div className="text-[10.5px] font-mono text-neutral-600 mt-0.5">
            {hasData
              ? `${chartData.length} day${chartData.length === 1 ? "" : "s"} · $${totalCost.toFixed(4)} total`
              : `No data in the last ${range}d`}
          </div>
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono text-neutral-500">
          <Legend dot="bg-emerald-400" label="cost ($)" />
        </div>
      </div>

      <div className="h-[260px] min-h-[260px]">
        {isLoading ? (
          <div className="h-full rounded-xl shimmer-bg" />
        ) : !hasData ? (
          <div className="h-full flex items-center justify-center text-[12px] text-neutral-600">
            No daily usage recorded in this window.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260} debounce={50}>
            <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34d399" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fill: "#737373", fontSize: 10, fontFamily: "var(--font-mono)" }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                tickLine={false}
                interval={range > 14 ? Math.floor(chartData.length / 7) : 0}
              />
              <YAxis
                tick={{ fill: "#737373", fontSize: 10, fontFamily: "var(--font-mono)" }}
                axisLine={false}
                tickLine={false}
                width={56}
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                domain={[0, maxCost * 1.1]}
              />
              <Tooltip
                cursor={{ stroke: "rgba(52,211,153,0.25)", strokeWidth: 1, strokeDasharray: "3 3" }}
                content={<DarkTooltip />}
              />
              <Area
                type="monotone"
                dataKey="cost"
                stroke="#34d399"
                strokeWidth={1.5}
                fill="url(#costGradient)"
                dot={false}
                activeDot={{ r: 4, fill: "#34d399", stroke: "#0a0a0f", strokeWidth: 2 }}
                isAnimationActive
                animationDuration={700}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function formatLabel(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function Legend({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={dot + " w-2 h-2 rounded-full"} />
      <span className="uppercase tracking-wider">{label}</span>
    </span>
  );
}

interface TooltipPayloadEntry {
  name: string;
  value: number;
  color: string;
  dataKey: string;
  payload: { day: string; label: string; cost: number; sessions: number };
}

function DarkTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div
      className="rounded-lg border border-white/[0.08] px-3 py-2 backdrop-blur-md"
      style={{
        background: "rgba(10,10,15,0.92)",
        boxShadow: "0 8px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
      }}
    >
      <div className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider mb-1">
        {p.label}
      </div>
      <div className="flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">cost</span>
        <span className="text-[12px] font-medium text-emerald-300 tabular-nums">
          ${p.cost.toFixed(4)}
        </span>
      </div>
      {p.sessions > 0 && (
        <div className="flex items-center gap-2 mt-1">
          <span className="w-1.5 h-1.5 rounded-full bg-neutral-500" />
          <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">sessions</span>
          <span className="text-[12px] font-medium text-neutral-200 tabular-nums">{p.sessions}</span>
        </div>
      )}
    </div>
  );
}
