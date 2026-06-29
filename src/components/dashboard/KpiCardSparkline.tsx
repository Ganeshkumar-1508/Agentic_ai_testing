"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const SPARKLINE_COLORS: Record<string, { bar: string; last: string; track: string }> = {
  default: { bar: "rgba(52,211,153,0.25)", last: "#34d399", track: "rgba(52,211,153,0.06)" },
  accent: { bar: "rgba(52,211,153,0.2)", last: "#34d399", track: "rgba(52,211,153,0.06)" },
  danger: { bar: "rgba(248,113,113,0.15)", last: "#f87171", track: "rgba(248,113,113,0.06)" },
  warning: { bar: "rgba(245,158,11,0.15)", last: "#f59e0b", track: "rgba(245,158,11,0.06)" },
  blue: { bar: "rgba(59,130,246,0.2)", last: "#3b82f6", track: "rgba(59,130,246,0.06)" },
  purple: { bar: "rgba(167,139,250,0.15)", last: "#a78bfa", track: "rgba(167,139,250,0.06)" },
};

interface KpiCardSparklineProps {
  label: string;
  value: string | number;
  trend?: { value: string; positive: boolean };
  sparklineData?: number[];
  icon?: React.ReactNode;
  color?: keyof typeof SPARKLINE_COLORS;
  loading?: boolean;
  index?: number;
  subtitle?: string;
}

export function KpiCardSparkline({ label, value, trend, sparklineData, icon, color = "default", loading, index = 0, subtitle }: KpiCardSparklineProps) {
  const c = SPARKLINE_COLORS[color] ?? SPARKLINE_COLORS.default;
  const bars = sparklineData ?? [];
  const maxVal = bars.length > 0 ? Math.max(...bars, 1) : 1;

  if (loading) {
    return (
      <div className="rounded-[2rem] p-5 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="w-20 h-3 rounded shimmer-bg" />
        <div className="w-16 h-8 rounded-lg shimmer-bg" />
        <div className="flex gap-1 items-end h-5 mt-2">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="flex-1 rounded-sm shimmer-bg" style={{ height: `${30 + Math.random() * 50}%` }} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-[2rem] p-5 cursor-default card-wireframe"
    >
      <div className="flex items-center justify-between mb-2.5">
        <span className="card-label">{label}</span>
        {icon && <div className="w-5 h-5 rounded-md bg-white/[0.03] flex items-center justify-center">{icon}</div>}
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.06 + 0.15, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="kpi-value text-zinc-100 mb-1"
      >
        {value}
      </motion.div>

      {trend && (
        <div className={cn(
          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium font-mono",
          trend.positive ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
        )}>
          <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            {trend.positive
              ? <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
              : <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
            }
          </svg>
          <span>{trend.value}</span>
        </div>
      )}

      {bars.length > 0 && (
        <div className="flex gap-[2px] items-end h-5 mt-3" style={{ background: `linear-gradient(180deg, transparent 50%, ${c.track} 100%)` }}>
          {bars.map((v, i) => {
            const isLast = i === bars.length - 1;
            const h = Math.max(3, (v / maxVal) * 100);
            return (
              <motion.div
                key={i}
                initial={{ height: 0 }}
                animate={{ height: `${h}%` }}
                transition={{ delay: index * 0.06 + i * 0.03, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="w-[3px] rounded-sm transition-all duration-200 hover:opacity-80"
                style={{ background: isLast ? c.last : c.bar }}
              />
            );
          })}
        </div>
      )}

      {subtitle && (
        <div className="mt-2 text-[10px] font-mono text-zinc-600 truncate">
          {subtitle}
        </div>
      )}
    </motion.div>
  );
}
