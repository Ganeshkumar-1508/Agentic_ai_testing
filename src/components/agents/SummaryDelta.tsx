"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface DeltaItem {
  label: string;
  valueA: number;
  valueB: number;
  suffix?: string;
  higherIsBetter?: boolean;
  confidence?: number;
  sparkline?: number[];
}

interface SummaryDeltaProps {
  items: DeltaItem[];
  loading?: boolean;
}

function Sparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 60;
  const h = 20;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`).join(" ");
  return (
    <svg width={w} height={h} className="shrink-0">
      <polyline points={points} fill="none" stroke="rgba(52,211,153,0.4)" strokeWidth={1.5} />
    </svg>
  );
}

function DeltaBadge({ value, higherIsBetter }: { value: number; higherIsBetter?: boolean }) {
  const isPositive = value >= 0;
  const isGood = higherIsBetter ? isPositive : !isPositive;
  return (
    <span className={cn(
      "inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full",
      value === 0 ? "bg-white/[0.04] text-neutral-500" :
      isGood ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
    )}>
      {value > 0 ? <TrendingUp className="w-3 h-3" strokeWidth={1.5} /> : value < 0 ? <TrendingDown className="w-3 h-3" strokeWidth={1.5} /> : <Minus className="w-3 h-3" strokeWidth={1.5} />}
      {value > 0 ? "+" : ""}{value}
    </span>
  );
}

export function SummaryDelta({ items, loading }: SummaryDeltaProps) {
  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-10 rounded-lg shimmer-bg" />
        ))}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-6"
    >
      <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wider mb-4">
        Metric Comparison
      </div>
      <div className="space-y-3">
        {items.map((item, i) => {
          const delta = item.valueB - item.valueA;
          return (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
              className="flex items-center gap-4 py-2 px-3 rounded-xl hover:bg-white/[0.02] transition-colors"
            >
              <span className="w-28 text-sm text-neutral-400 shrink-0">{item.label}</span>
              <span className="w-16 text-sm font-mono text-neutral-200 text-right">{item.valueA}{item.suffix ?? ""}</span>
              <span className="text-xs text-neutral-600 w-6 text-center">→</span>
              <span className="w-16 text-sm font-mono text-neutral-200">{item.valueB}{item.suffix ?? ""}</span>
              <DeltaBadge value={delta} higherIsBetter={item.higherIsBetter} />
              {item.sparkline && <Sparkline data={item.sparkline} />}
              {item.confidence !== undefined && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded font-mono",
                  item.confidence > 90 ? "bg-emerald-500/10 text-emerald-400" :
                  item.confidence > 70 ? "bg-amber-500/10 text-amber-400" :
                  "bg-neutral-500/10 text-neutral-500"
                )}>
                  {item.confidence}%
                </span>
              )}
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
