"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export type HealthTone = "healthy" | "warn" | "down";

export interface SystemHealthData {
  database: { status: HealthTone; detail: string; latency_ms?: number | null };
  queue: { status: HealthTone; detail: string; count: number };
  sessions: { status: HealthTone; detail: string; count: number };
  pipeline: { status: HealthTone; detail: string; running: number };
  agents: { status: HealthTone; detail: string; count: number };
  containers: { status: HealthTone; detail: string; running: number; total: number };
  timestamp: string;
}

interface SystemHealthBarProps {
  data?: SystemHealthData;
  loading?: boolean;
}

const SEGMENTS: Array<{
  key: keyof Omit<SystemHealthData, "timestamp">;
  label: string;
}> = [
  { key: "database",   label: "Database" },
  { key: "queue",      label: "Queue" },
  { key: "sessions",   label: "Sessions" },
  { key: "pipeline",   label: "Pipeline" },
  { key: "agents",     label: "Agents" },
  { key: "containers", label: "Containers" },
];

function dotToneClasses(tone: HealthTone): string {
  if (tone === "down") return "bg-red-400";
  if (tone === "warn") return "bg-amber-400";
  return "bg-emerald-400";
}

function valueToneClasses(tone: HealthTone): string {
  if (tone === "down") return "text-red-400";
  if (tone === "warn") return "text-amber-400";
  return "text-zinc-100";
}

const item = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
};

export function SystemHealthBar({ data, loading }: SystemHealthBarProps) {
  if (loading && !data) {
    return (
      <div className="flex items-center gap-4 px-4 py-2.5 bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem]">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full shimmer-bg" />
            <div className="w-20 h-3 rounded shimmer-bg" />
          </div>
        ))}
      </div>
    );
  }

  if (!data) return null;

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.05, delayChildren: 0.1 } } }}
      className="flex items-center gap-4 px-4 py-2.5 bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem] text-[11px] flex-wrap"
    >
      {SEGMENTS.map((seg, i) => {
        const cell = data[seg.key];
        const tone = (cell?.status ?? "healthy") as HealthTone;
        const isPulsing = tone === "healthy" && (seg.key === "database" || seg.key === "sessions" || seg.key === "agents");
        return (
          <motion.div key={seg.key} variants={item} className="flex items-center gap-2">
            <span className="relative flex items-center justify-center w-2 h-2">
              <span className={cn("absolute inset-0 rounded-full opacity-40", dotToneClasses(tone), isPulsing && "animate-ping")} />
              <span className={cn("relative w-2 h-2 rounded-full", dotToneClasses(tone))} />
            </span>
            <span className="text-zinc-500 font-mono uppercase tracking-[0.05em] text-[10px]">
              {seg.label}
            </span>
            <span className={cn("font-mono font-semibold text-[11px]", valueToneClasses(tone))}>
              {cell?.detail ?? "—"}
            </span>
            {i < SEGMENTS.length - 1 && (
              <span className="hidden md:inline-block w-px h-3.5 bg-white/[0.06] ml-2" />
            )}
          </motion.div>
        );
      })}
    </motion.div>
  );
}
