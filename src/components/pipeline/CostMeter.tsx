"use client";

import { useState, useEffect, useRef } from "react";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { cn } from "@/lib/utils";
import { DollarSign, Cpu, HardDrive, Wrench } from "lucide-react";

interface CostMeterProps {
  currentCost: number;
  budgetCap: number;
  breakdown?: { llm: number; sandbox: number; tools: number };
  tokens?: { total: number; prompt: number; completion: number };
  isLive?: boolean;
}

function AnimatedNumber({ value, prefix = "" }: { value: number; prefix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prevValue = useRef(value);

  useEffect(() => {
    if (!ref.current) return;
    const start = prevValue.current;
    const diff = value - start;
    if (Math.abs(diff) < 0.001) return;

    const controls = animate(start, value, {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = `${prefix}${v.toFixed(4)}`;
      },
    });
    prevValue.current = value;
    return () => controls.stop();
  }, [value, prefix]);

  return <span ref={ref}>{prefix}{value.toFixed(4)}</span>;
}

export function CostMeter({ currentCost, budgetCap, breakdown, tokens, isLive }: CostMeterProps) {
  const percent = Math.min((currentCost / budgetCap) * 100, 100);
  const pctMotion = useMotionValue(percent);

  useEffect(() => {
    pctMotion.set(percent);
  }, [percent, pctMotion]);

  const barColor = percent > 90 ? "bg-red-400" : percent > 70 ? "bg-amber-400" : "bg-emerald-400";

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <DollarSign className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
          </div>
          <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Cost</span>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono tabular-nums">
          <AnimatedNumber value={currentCost} prefix="$" />
          <span className="text-zinc-600">/</span>
          <span className="text-zinc-500">${budgetCap.toFixed(2)}</span>
          {isLive && (
            <span className="flex items-center gap-1 ml-1">
              <span className="relative flex h-2 w-2">
                <span className="absolute inset-0 rounded-full bg-emerald-400/60 animate-ping" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
              </span>
            </span>
          )}
        </div>
      </div>

      {/* Bar */}
      <div className="relative h-2 bg-zinc-800 rounded-full overflow-hidden mb-3">
        <motion.div
          className={cn("absolute inset-y-0 left-0 rounded-full transition-colors duration-500", barColor)}
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>

      {/* Threshold markers */}
      <div className="relative h-0 -top-1 mb-2">
        <div className="absolute left-[70%] -translate-x-1/2 w-px h-3 bg-amber-500/40" />
        <div className="absolute left-[90%] -translate-x-1/2 w-px h-3 bg-red-500/40" />
      </div>

      {/* Breakdown */}
      {breakdown && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div className="bg-white/[0.02] rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Cpu className="w-3 h-3 text-emerald-400/70" strokeWidth={1.5} />
              <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">LLM</span>
            </div>
            <span className="text-sm font-mono tabular-nums text-zinc-200">${breakdown.llm.toFixed(4)}</span>
          </div>
          <div className="bg-white/[0.02] rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <HardDrive className="w-3 h-3 text-blue-400/70" strokeWidth={1.5} />
              <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Sandbox</span>
            </div>
            <span className="text-sm font-mono tabular-nums text-zinc-200">${breakdown.sandbox.toFixed(4)}</span>
          </div>
          <div className="bg-white/[0.02] rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Wrench className="w-3 h-3 text-amber-400/70" strokeWidth={1.5} />
              <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Tools</span>
            </div>
            <span className="text-sm font-mono tabular-nums text-zinc-200">${breakdown.tools.toFixed(4)}</span>
          </div>
        </div>
      )}

      {/* Token stats */}
      {tokens && (
        <div className="flex items-center gap-4 text-[10px] font-mono tabular-nums text-zinc-600 border-t border-white/[0.05] pt-3">
          <span>Total: {(tokens.total / 1000).toFixed(1)}k</span>
          <span>Prompt: {(tokens.prompt / 1000).toFixed(1)}k</span>
          <span>Completion: {(tokens.completion / 1000).toFixed(1)}k</span>
          {isLive && (
            <span className="ml-auto text-emerald-400/60">updating live</span>
          )}
        </div>
      )}
    </div>
  );
}
