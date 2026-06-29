"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface StatsCardProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  sub?: string;
  trend?: { value: string; positive: boolean };
  loading?: boolean;
  index?: number;
  delay?: number;
  className?: string;
}

export function StatsCard({ label, value, icon, sub, trend, loading, index = 0, delay, className }: StatsCardProps) {
  if (loading) {
    return (
      <div className="shimmer-bg border border-zinc-800/30 rounded-[1.5rem] p-6 space-y-3">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 animate-pulse" />
        <div className="w-24 h-3 rounded-full bg-zinc-800/50 animate-pulse" />
        <div className="w-16 h-8 rounded-lg bg-zinc-800/50 animate-pulse" />
        <div className="w-32 h-3 rounded-full bg-zinc-800/50 animate-pulse" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: delay ?? index * 0.08, ease: [0.16, 1, 0.3, 1] }}
      whileHover={{ scale: 1.02, transition: { type: "spring", stiffness: 100, damping: 20 } }}
      className={cn("shimmer-bg border border-zinc-800/30 rounded-2xl p-5 hover:border-zinc-700/50 transition-colors cursor-default", className)}
    >
      {icon && (
        <div className="flex items-center gap-2 mb-3">
          <span className="w-8 h-8 rounded-xl bg-zinc-800/80 flex items-center justify-center text-zinc-500">
            {icon}
          </span>
        </div>
      )}
      <div className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-1">
        {label}
      </div>
      <div className="text-2xl font-semibold text-zinc-100 tracking-tight tabular-nums">
        {value}
      </div>
      {sub && <div className="text-xs text-zinc-600 mt-1">{sub}</div>}
      {trend && (
        <div className={cn("flex items-center gap-1 mt-2 text-sm", trend.positive ? "text-emerald-400" : "text-red-400")}>
          <span>{trend.positive ? "\u25B2" : "\u25BC"}</span>
          <span>{trend.value}</span>
        </div>
      )}
    </motion.div>
  );
}
