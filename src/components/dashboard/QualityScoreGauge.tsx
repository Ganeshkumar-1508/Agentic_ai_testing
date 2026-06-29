"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface QualityScoreGaugeProps {
  passRate?: number;
  flakyRate?: number;
  coverage?: number;
  score?: number;
  verdict?: string;
  components?: Record<string, { label?: string; raw: number; weighted: number; weight: number }>;
  loading?: boolean;
}

export function QualityScoreGauge({ passRate, flakyRate, coverage, score: externalScore, verdict, components, loading }: QualityScoreGaugeProps) {
  const hasData = (passRate != null && passRate > 0) || (externalScore != null && externalScore > 0) || (components && Object.keys(components).length > 0);

  const score = externalScore ?? Math.round(
    (passRate ?? 0) * 0.5 + ((1 - Math.min((flakyRate ?? 0) / 100, 1)) * 100 * 0.3) + ((coverage ?? 0) * 0.2)
  );
  const verdictLabel = verdict ?? (score >= 80 ? "go" : score >= 50 ? "caution" : "no-go");
  const color = score >= 80 ? "text-emerald-400" : score >= 60 ? "text-amber-400" : "text-red-400";
  const strokeColor = score >= 80 ? "#34d399" : score >= 60 ? "#fbbf24" : "#f87171";
  const bgPill = score >= 80 ? "bg-emerald-500/10 text-emerald-400" : score >= 60 ? "bg-amber-500/10 text-amber-400" : "bg-red-500/10 text-red-400";

  if (loading) {
    return (
      <div className="rounded-[2rem] p-6 space-y-3" style={{ background: "#0e0e18" }}>
        <div className="w-24 h-4 rounded-full shimmer-bg" />
        <div className="h-[120px] rounded-xl shimmer-bg" />
      </div>
    );
  }

  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  if (!hasData) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="card-label">Quality Score</div>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-mono uppercase bg-zinc-800 text-zinc-500">no data</span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-xl font-bold font-mono text-zinc-600">--</div>
            <div className="text-[10px] text-zinc-700 mt-1">Run pipelines to generate score</div>
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-[2rem] p-6 card-glow h-full flex flex-col"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="card-label">Quality Score</div>
        <span className={cn("text-[10px] px-2 py-0.5 rounded-full font-mono uppercase", bgPill)}>{verdictLabel}</span>
      </div>
      <div className="flex items-start gap-5 flex-1 min-h-0">
        <div className="flex flex-col items-center shrink-0">
          <div className="relative w-[120px] h-[120px]">
            <svg width="120" height="120" className="-rotate-90">
              <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
              <motion.circle
                cx="60" cy="60" r={radius} fill="none" stroke={strokeColor} strokeWidth="6" strokeLinecap="round"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset: offset }}
                transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className={cn("text-2xl font-bold font-mono tracking-tight", color)}>{score}</div>
              <div className="text-[10px] text-neutral-500">/ 100</div>
            </div>
          </div>
        </div>

        {components && (
          <div className="flex-1 space-y-2 min-w-0">
            {Object.entries(components).map(([key, comp]) => (
              <div key={key} className="flex items-center gap-2 text-[10px]">
                <span className="w-24 text-neutral-500 truncate">
                  {comp.label ?? key.replace(/_/g, " ")}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                  <motion.div
                    className="h-full rounded-full bg-emerald-500/60"
                    initial={{ width: 0 }}
                    animate={{ width: `${comp.raw}%` }}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
                <span className="w-10 text-right text-neutral-400 font-mono">
                  {comp.raw.toFixed(1)}%
                </span>
                <span className="w-7 text-right text-neutral-600 font-mono text-[9px]">
                  {comp.weight}%
                </span>
              </div>
            ))}
          </div>
        )}

        {!components && (
          <div className="flex flex-col gap-2 mt-2 text-[10px] text-neutral-500">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span>Pass</span>
              <span className="font-mono text-neutral-300">{passRate ?? "?"}%</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              <span>Flaky</span>
              <span className="font-mono text-neutral-300">{flakyRate ?? "?"}%</span>
            </div>
            {coverage !== undefined && (
              <div className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full bg-blue-400" />
                <span>Cov</span>
                <span className="font-mono text-neutral-300">{coverage}%</span>
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}
