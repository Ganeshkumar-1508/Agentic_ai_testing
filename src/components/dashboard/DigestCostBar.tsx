"use client";

import { motion } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer, Tooltip } from "recharts";
import { Coins, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface DigestCostBarProps {
  trend: Array<{ day: string; cost: number | string; total_tokens: number | string }>;
}

const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 110, damping: 22 } },
};

function fmtUSD(n: number) {
  if (n >= 100) return `$${n.toFixed(0)}`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(3)}`;
}

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

export function DigestCostBar({ trend }: DigestCostBarProps) {
  const data = (trend || []).slice(-14).map((d, i) => ({
    i,
    day: typeof d.day === "string" ? d.day.slice(5) : `d${i}`,
    cost: typeof d.cost === "string" ? parseFloat(d.cost) : d.cost || 0,
    tokens: typeof d.total_tokens === "string" ? parseInt(d.total_tokens) : d.total_tokens || 0,
  }));

  const last7 = data.slice(-7);
  const prior7 = data.slice(-14, -7);
  const sum = (arr: typeof data) => arr.reduce((a, b) => a + b.cost, 0);
  const sumTokens = (arr: typeof data) => arr.reduce((a, b) => a + b.tokens, 0);
  const lastSum = sum(last7);
  const priorSum = sum(prior7);
  const delta = priorSum > 0 ? ((lastSum - priorSum) / priorSum) * 100 : 0;
  const trendDirection: "up" | "down" | "flat" =
    Math.abs(delta) < 1 ? "flat" : delta > 0 ? "up" : "down";

  const totalCost = sum(data);
  const totalTokens = sumTokens(data);

  return (
    <motion.section
      variants={item}
      className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4"
    >
      <div className="rounded-[2rem] p-6 card-wireframe">
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600 mb-3">
          Burn · 14d
        </div>
        <div className="flex items-baseline gap-2">
          <Coins className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          <span className="text-4xl font-semibold tracking-tighter font-mono text-zinc-50">
            {fmtUSD(totalCost)}
          </span>
        </div>
        <div className="text-[11px] font-mono text-zinc-600 mt-2">
          {fmtTokens(totalTokens)} tokens · {data.length} day window
        </div>
        <div
          className={cn(
            "mt-4 inline-flex items-center gap-1.5 text-[11px] font-mono px-2 py-1 rounded-full border",
            trendDirection === "up" && "text-amber-400 border-amber-500/20 bg-amber-500/5",
            trendDirection === "down" && "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
            trendDirection === "flat" && "text-zinc-500 border-white/[0.06] bg-white/[0.02]"
          )}
        >
          {trendDirection === "up" && <TrendingUp className="w-3 h-3" strokeWidth={2} />}
          {trendDirection === "down" && <TrendingDown className="w-3 h-3" strokeWidth={2} />}
          {trendDirection === "flat" && <span className="w-3 h-3 inline-block">·</span>}
          {priorSum > 0
            ? `${delta > 0 ? "+" : ""}${delta.toFixed(1)}% wow`
            : "baseline"}
        </div>
      </div>

      <div className="rounded-[2rem] p-6 card-wireframe min-h-[180px]">
        <div className="flex items-end justify-between mb-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-600 mb-1.5">
              Daily cost trend
            </div>
            <h2 className="text-base font-medium text-zinc-100 tracking-tight">
              Token spend, last 14 days
            </h2>
          </div>
          <div className="text-[10px] font-mono text-zinc-700">
            peak: {fmtUSD(Math.max(...data.map((d) => d.cost), 0))}
          </div>
        </div>

        <div className="h-28 min-h-[112px] -mx-2">
          {data.length > 0 ? (
            <ResponsiveContainer width="100%" height={112} debounce={50}>
              <AreaChart data={data} margin={{ top: 8, right: 12, left: 12, bottom: 0 }}>
                <defs>
                  <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#34d399" stopOpacity={0.32} />
                    <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Tooltip
                  cursor={{ stroke: "rgba(255,255,255,0.08)", strokeWidth: 1 }}
                  contentStyle={{
                    background: "#12121c",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 8,
                    fontSize: 11,
                    color: "#f0f0f5",
                  }}
                  labelStyle={{ color: "#87879b", fontSize: 10, fontFamily: "monospace" }}
                  formatter={(v) => [fmtUSD(Number(v) || 0), "cost"]}
                />
                <Area
                  type="monotone"
                  dataKey="cost"
                  stroke="#34d399"
                  strokeWidth={1.5}
                  fill="url(#costGrad)"
                  dot={false}
                  activeDot={{ r: 3, stroke: "#34d399", strokeWidth: 1.5, fill: "#0a0a0f" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-zinc-700 font-mono">
              No cost data available
            </div>
          )}
        </div>
      </div>
    </motion.section>
  );
}
