"use client";

import { motion } from "framer-motion";
import { Gauge, ChevronUp, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export type ThrottleStep = 0 | 1 | 2 | 3 | 4;

export interface ThrottleState {
  spent_usd: number;
  soft_cap_usd: number;
  hard_cap_usd: number;
  throttle_step: ThrottleStep;
  hitl_active: boolean;
  sequential_active: boolean;
  cheaper_model_active: boolean;
  pause_requested: boolean;
}

interface ThrottleIndicatorProps {
  state: ThrottleState;
  compact?: boolean;
  className?: string;
}

const STEP_LABEL: Record<ThrottleStep, string> = {
  0: "ok",
  1: "hitl",
  2: "sequential",
  3: "cheaper",
  4: "pause",
};

const STEP_TITLE: Record<ThrottleStep, string> = {
  0: "OK",
  1: "HITL",
  2: "Sequential",
  3: "Cheaper model",
  4: "Pause requested",
};

function pipClass(step: ThrottleStep, current: ThrottleStep, isPaused: boolean): string {
  if (isPaused && step === current) {
    return "bg-rose-500 ring-2 ring-rose-500/30";
  }
  if (step < current) {
    return "bg-zinc-950 dark:bg-zinc-100";
  }
  if (step === current) {
    return "bg-emerald-500 ring-2 ring-emerald-500/30";
  }
  return "bg-zinc-700/40 dark:bg-zinc-700/40";
}

function formatUsd(value: number): string {
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

export function ThrottleIndicator({ state, compact, className }: ThrottleIndicatorProps) {
  const current = state.throttle_step;
  const isPaused = state.pause_requested;
  const steps: ThrottleStep[] = [0, 1, 2, 3, 4];
  const spentPct =
    state.soft_cap_usd > 0
      ? Math.min(100, (state.spent_usd / state.soft_cap_usd) * 100)
      : 0;
  const isWarning = current >= 1;
  const isCritical = current >= 4;

  if (compact) {
    return (
      <div className={cn("flex items-baseline gap-3", className)}>
        <div className="flex items-center gap-1.5">
          {steps.map((step) => (
            <span
              key={step}
              title={STEP_TITLE[step]}
              className={cn(
                "h-1.5 w-4 rounded-sm transition-colors",
                pipClass(step, current, isPaused),
              )}
            />
          ))}
        </div>
        <span
          className={cn(
            "font-mono text-xs tabular-nums tracking-tight",
            isCritical ? "text-rose-500" : isWarning ? "text-amber-500" : "text-zinc-500",
          )}
        >
          {formatUsd(state.spent_usd)} / {formatUsd(state.soft_cap_usd)}
        </span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "w-full",
        isCritical ? "" : "",
        className,
      )}
    >
      <div className="flex items-baseline justify-between gap-4 pb-3">
        <div className="flex items-center gap-2">
          {isCritical ? (
            <ShieldAlert className="h-4 w-4 text-rose-500" strokeWidth={1.5} />
          ) : (
            <Gauge className="h-4 w-4 text-zinc-400" strokeWidth={1.5} />
          )}
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            Budget throttle
          </span>
        </div>
        <div className="flex items-baseline gap-2">
          <span
            className={cn(
              "text-sm font-semibold tracking-tight",
              isCritical
                ? "text-rose-500"
                : current === 3
                  ? "text-amber-500"
                  : current >= 1
                    ? "text-amber-500"
                    : "text-zinc-900 dark:text-zinc-100",
            )}
          >
            Step {current}
          </span>
          {current > 0 && (
            <ChevronUp className="h-3.5 w-3.5 text-amber-500" strokeWidth={2} />
          )}
          <span className="text-xs text-zinc-500">
            {STEP_TITLE[current]}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1.5 pb-3">
        {steps.map((step) => (
          <motion.div
            key={step}
            initial={false}
            animate={{
              scale: step === current ? 1.05 : 1,
            }}
            transition={{ type: "spring", stiffness: 240, damping: 22 }}
            className="flex flex-1 flex-col items-center gap-1.5"
            title={STEP_TITLE[step]}
          >
            <span
              className={cn(
                "h-2 w-full rounded-full transition-colors duration-200",
                pipClass(step, current, isPaused),
              )}
            />
            <span
              className={cn(
                "text-[10px] font-mono uppercase tracking-wide",
                step === current
                  ? isCritical
                    ? "text-rose-500"
                    : "text-emerald-600 dark:text-emerald-400"
                  : "text-zinc-400",
              )}
            >
              {STEP_LABEL[step]}
            </span>
          </motion.div>
        ))}
      </div>

      <div className="flex items-baseline justify-between gap-3">
        <span
          className={cn(
            "font-mono text-sm tabular-nums tracking-tight",
            isCritical
              ? "text-rose-500"
              : isWarning
                ? "text-amber-600 dark:text-amber-400"
                : "text-zinc-700 dark:text-zinc-300",
          )}
        >
          {formatUsd(state.spent_usd)}
        </span>
        <span className="text-[11px] font-mono tabular-nums text-zinc-400">
          {spentPct.toFixed(0)}% of soft cap
        </span>
        <span className="font-mono text-sm tabular-nums text-zinc-400">
          {formatUsd(state.soft_cap_usd)}
        </span>
      </div>
    </div>
  );
}
