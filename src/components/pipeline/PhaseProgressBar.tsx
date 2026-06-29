"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { PhaseName, PhaseState } from "@/lib/types/pipeline";
import {
  Rocket,
  Search,
  Package,
  Play,
  CheckSquare,
  GitPullRequest,
  Database,
} from "lucide-react";

const PHASE_META: Record<PhaseName, { label: string; icon: typeof Rocket; desc: string }> = {
  enter:    { label: "ENTER",    icon: Rocket,       desc: "Resolving repo, branch, auth, credentials" },
  analyze:  { label: "ANALYZE",  icon: Search,       desc: "Tech stack detection, file tree, code graph" },
  setup:    { label: "SETUP",    icon: Package,      desc: "Install dependencies, smoke-test framework" },
  work:     { label: "WORK",     icon: Play,         desc: "Generate, validate, heal — unified loop" },
  review:   { label: "REVIEW",   icon: CheckSquare,  desc: "Quality gates, coverage check, self-critique" },
  publish:  { label: "PUBLISH",  icon: GitPullRequest, desc: "Commit, push, open PR with summary" },
  persist:  { label: "PERSIST",  icon: Database,     desc: "Save artifacts, L1 facts, L2 lessons" },
};

const PHASE_ORDER: PhaseName[] = ["enter", "analyze", "setup", "work", "review", "publish", "persist"];

interface PhaseProgressBarProps {
  phases: PhaseState[];
  isLive?: boolean;
}

function PhaseDot({ status }: { status: PhaseState["status"] }) {
  if (status === "running") {
    return (
      <span className="relative flex h-3 w-3">
        <span className="absolute inset-0 rounded-full bg-emerald-400/40 animate-ping" />
        <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-400" />
      </span>
    );
  }
  if (status === "passed") {
    return (
      <span className="flex h-3 w-3 items-center justify-center">
        <span className="h-3 w-3 rounded-full bg-emerald-400" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex h-3 w-3 items-center justify-center">
        <span className="h-3 w-3 rounded-full bg-red-400" />
      </span>
    );
  }
  if (status === "skipped") {
    return (
      <span className="flex h-3 w-3 items-center justify-center">
        <span className="h-3 w-3 rounded-full bg-zinc-600" />
      </span>
    );
  }
  return (
    <span className="flex h-3 w-3 items-center justify-center">
      <span className="h-3 w-3 rounded-full bg-zinc-700" />
    </span>
  );
}

function PhaseIcon({ name, status }: { name: PhaseName; status: PhaseState["status"] }) {
  const meta = PHASE_META[name];
  const Icon = meta.icon;
  const isActive = status === "running" || status === "passed";
  return (
    <div
      className={cn(
        "w-8 h-8 rounded-xl flex items-center justify-center shrink-0 transition-all duration-300",
        status === "running" ? "bg-emerald-500/15 text-emerald-400" :
        status === "passed" ? "bg-emerald-500/10 text-emerald-400/70" :
        status === "failed" ? "bg-red-500/10 text-red-400" :
        status === "skipped" ? "bg-zinc-800/50 text-zinc-600" :
        "bg-zinc-800/30 text-zinc-600",
      )}
    >
      <Icon className={cn("w-4 h-4", isActive ? "" : "opacity-50")} strokeWidth={1.5} />
    </div>
  );
}

export function PhaseProgressBar({ phases, isLive }: PhaseProgressBarProps) {
  const phaseMap = useMemo(() => {
    const map = new Map<PhaseName, PhaseState>();
    for (const p of phases) map.set(p.name, p);
    return map;
  }, [phases]);

  const activeIdx = PHASE_ORDER.findIndex((name) => {
    const p = phaseMap.get(name);
    return p?.status === "running";
  });

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5">
      {/* Phase dots row */}
      <div className="flex items-center justify-between mb-4">
        {PHASE_ORDER.map((name, idx) => {
          const state = phaseMap.get(name) ?? { name, label: PHASE_META[name].label, status: "pending" as const, percent: 0 };
          const isActive = state.status === "running";
          const isPassed = state.status === "passed";
          const isLast = idx === PHASE_ORDER.length - 1;

          return (
            <div key={name} className="flex items-center flex-1">
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="flex flex-col items-center gap-1.5 relative group cursor-default"
              >
                <PhaseIcon name={name} status={state.status} />
                <span
                  className={cn(
                    "text-[10px] font-semibold tracking-wider uppercase transition-colors duration-300",
                    isActive ? "text-emerald-400" :
                    isPassed ? "text-emerald-400/60" :
                    state.status === "failed" ? "text-red-400" :
                    "text-zinc-600",
                  )}
                >
                  {PHASE_META[name].label}
                </span>
                {state.status === "running" && (
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${state.percent}%` }}
                    className="absolute -bottom-1 left-1/2 -translate-x-1/2 h-0.5 bg-emerald-400/50 rounded-full"
                    style={{ width: `${state.percent}%` }}
                  />
                )}
                {/* Tooltip */}
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 -translate-y-full opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-10">
                  <div className="bg-zinc-800 border border-white/[0.06] rounded-lg px-3 py-2 text-xs text-zinc-300 whitespace-nowrap shadow-xl">
                    <div className="font-medium text-zinc-100 mb-0.5">{PHASE_META[name].label}</div>
                    <div className="text-zinc-500">{PHASE_META[name].desc}</div>
                    {state.status === "running" && state.message && (
                      <div className="text-emerald-400/80 mt-1 font-mono text-[10px]">{state.message}</div>
                    )}
                  </div>
                </div>
              </motion.div>
              {!isLast && (
                <div className="flex-1 h-px mx-2 relative">
                  <div className="absolute inset-0 bg-zinc-800 rounded-full" />
                  <div
                    className={cn(
                      "absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out",
                      activeIdx >= idx ? "bg-emerald-400/30" : "",
                    )}
                    style={{ width: activeIdx >= idx ? "100%" : "0%" }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Active phase detail */}
      {activeIdx >= 0 && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="border-t border-white/[0.05] pt-4 mt-1"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <PhaseDot status="running" />
              <span className="text-sm font-medium text-zinc-100">
                {PHASE_META[PHASE_ORDER[activeIdx]].label}
              </span>
              <span className="text-xs text-zinc-500">
                {PHASE_META[PHASE_ORDER[activeIdx]].desc}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500 font-mono">
              {isLive && (
                <span className="flex items-center gap-1.5">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inset-0 rounded-full bg-emerald-400/60 animate-ping" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                  </span>
                  LIVE
                </span>
              )}
            </div>
          </div>
          {/* Sub-agent list within WORK phase would go here */}
        </motion.div>
      )}

      {/* Summary bar — phases passed / total */}
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-white/[0.03]">
        {PHASE_ORDER.map((name) => {
          const state = phaseMap.get(name);
          return (
            <div key={name} className="flex items-center gap-1.5">
              <PhaseDot status={state?.status ?? "pending"} />
              <span className={cn(
                "text-[10px] font-mono",
                state?.status === "running" ? "text-emerald-400" :
                state?.status === "passed" ? "text-emerald-400/50" :
                state?.status === "failed" ? "text-red-400" :
                "text-zinc-700",
              )}>
                {PHASE_META[name].label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
