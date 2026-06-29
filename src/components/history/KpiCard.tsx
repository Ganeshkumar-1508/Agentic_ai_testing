"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface SparklineData {
  value: number;
  date: string;
}

interface KpiCardProps {
  label: string;
  value: number;
  suffix?: string;
  sub?: string;
  delta?: { value: string; positive: boolean };
  icon: React.ReactNode;
  sparklineData?: SparklineData[];
  qualityGate?: { label: string; ready: boolean };
  loading?: boolean;
  index?: number;
}

function Sparkline({ data, color, id }: { data: SparklineData[]; color: string; id: string }) {
  if (!data || data.length < 2) return null;
  const width = 200;
  const height = 40;
  const max = Math.max(...data.map((d) => d.value), 1);
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - (d.value / max) * height;
    return `${x},${y}`;
  });
  const line = points.join(" L ");
  const area = `M${points[0]} L ${line} L ${width},${height} L 0,${height} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="w-full h-full">
      <defs>
        <linearGradient id={`sparkGrad-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`M${points[0]} L ${line}`} fill="none" stroke={color} strokeWidth="1.5" />
      <path d={area} fill={`url(#sparkGrad-${id})`} opacity="0.3" />
    </svg>
  );
}

function CountUp({ value, suffix = "" }: { value: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const duration = 800;
    const steps = 30;
    const increment = value / steps;
    let current = 0;
    let step = 0;
    const timer = setInterval(() => {
      step++;
      current = Math.min(current + increment, value);
      setDisplay(current);
      if (step >= steps) {
        setDisplay(value);
        clearInterval(timer);
      }
    }, duration / steps);
    return () => clearInterval(timer);
  }, [value]);

  const formatted = suffix === "%"
    ? `${display.toFixed(1)}%`
    : suffix
    ? `${Math.round(display)}${suffix}`
    : display >= 1000
    ? `${(display / 1000).toFixed(1)}k`
    : Math.round(display).toLocaleString();

  return <>{formatted}</>;
}

export function KpiCard({
  label,
  value,
  suffix = "",
  sub,
  delta,
  icon,
  sparklineData,
  qualityGate,
  loading,
  index = 0,
}: KpiCardProps) {
  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.06] rounded-3xl p-5 space-y-3 relative overflow-hidden">
        <div className="flex items-center justify-between">
          <div className="w-20 h-3 rounded-full bg-white/[0.03] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
          <div className="w-8 h-8 rounded-xl bg-white/[0.03] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
        </div>
        <div className="w-16 h-8 rounded-lg bg-white/[0.03] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
        <div className="w-24 h-3 rounded-full bg-white/[0.03] relative overflow-hidden after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent after:animate-[shimmer_2s_ease-in-out_infinite]" />
      </div>
    );
  }

  const sparkColor = label === "Avg Duration" ? "#f59e0b"
    : label === "Flaky Tests" ? "#f59e0b"
    : label === "Quality Score" ? "#a78bfa"
    : "#34d399";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 100, damping: 20, delay: index * 0.08 }}
      className="bg-surface border border-white/[0.06] rounded-3xl p-5 relative overflow-hidden hover:border-emerald-500/20 transition-all duration-300 cursor-default active:scale-[0.98]"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-[0.05em]">{label}</span>
        <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-emerald-500/10 text-emerald-400">
          {icon}
        </div>
      </div>

      <div className="text-2xl font-semibold tracking-tight text-zinc-100 leading-none tabular-nums">
        <CountUp value={value} suffix={suffix} />
      </div>

      <div className="flex items-center gap-2 mt-1.5">
        {delta && (
          <span className={cn(
            "inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-md",
            delta.positive ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10"
          )}>
            <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              {delta.positive
                ? <polyline points="18 15 12 9 6 15" />
                : <polyline points="6 9 12 15 18 9" />}
            </svg>
            {delta.value}
          </span>
        )}
        {sub && <span className="text-[10px] text-zinc-600">{sub}</span>}
        {qualityGate && (
          <span className={cn(
            "inline-flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded-md border",
            qualityGate.ready
              ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
              : "text-red-400 bg-red-500/10 border-red-500/20"
          )}>
            <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              {qualityGate.ready
                ? <polyline points="20 6 9 17 4 12" />
                : <line x1="18" y1="6" x2="6" y2="18" />}
            </svg>
            {qualityGate.label}
          </span>
        )}
      </div>

      {sparklineData && sparklineData.length >= 2 && (
        <div className="absolute bottom-0 left-0 right-0 h-10 opacity-30 pointer-events-none">
          <Sparkline data={sparklineData} color={sparkColor} id={`kpi-${label.replace(/\s/g, "")}`} />
        </div>
      )}
    </motion.div>
  );
}
