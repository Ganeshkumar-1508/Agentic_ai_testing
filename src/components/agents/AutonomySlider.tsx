"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Sparkles,
  Rocket,
  ChevronDown,
} from "lucide-react";
import { api } from "@/lib/api/api-client";

type AutonomyLevel = "suggest" | "auto" | "autopilot";

interface AutonomySliderProps {
  sessionId?: string;
  initialLevel?: AutonomyLevel;
  onChange?: (level: AutonomyLevel) => void;
}

const LEVELS: { key: AutonomyLevel; label: string; icon: typeof Brain; description: string }[] = [
  {
    key: "suggest",
    label: "Suggest",
    icon: Brain,
    description: "Agent recommends actions, you approve each one before execution",
  },
  {
    key: "auto",
    label: "Auto",
    icon: Sparkles,
    description: "Agent acts on routine tasks automatically, asks for dangerous operations",
  },
  {
    key: "autopilot",
    label: "Autopilot",
    icon: Rocket,
    description: "Full autonomy — agent handles everything and reports results",
  },
];

const LEVEL_COLORS: Record<AutonomyLevel, string> = {
  suggest: "border-amber-500/30 bg-amber-500/5 text-amber-400",
  auto: "border-emerald-500/30 bg-emerald-500/5 text-emerald-400",
  autopilot: "border-blue-500/30 bg-blue-500/5 text-blue-400",
};

const SLIDER_POSITIONS: Record<AutonomyLevel, string> = {
  suggest: "left-0",
  auto: "left-1/3",
  autopilot: "left-2/3",
};

export function AutonomySlider({ sessionId, initialLevel = "auto", onChange }: AutonomySliderProps) {
  const [level, setLevel] = useState<AutonomyLevel>(initialLevel);
  const [expanded, setExpanded] = useState(false);

  const handleChange = async (newLevel: AutonomyLevel) => {
    setLevel(newLevel);
    setExpanded(false);
    onChange?.(newLevel);

    if (sessionId) {
      try {
        await api.post(`/api/delegate/${sessionId}/steer`, {
          text: `[Autonomy mode changed to: ${newLevel}]`,
          mode: "next",
        });
      } catch {
        // ignore
      }
    }
  };

  const current = LEVELS.find((l) => l.key === level)!;

  return (
    <div className="relative">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-all ${LEVEL_COLORS[level]} active:scale-[0.98]`}
      >
        <current.icon size={14} strokeWidth={1.5} />
        <span>{current.label}</span>
        <ChevronDown
          size={12}
          strokeWidth={2}
          className={`transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="absolute right-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-xl border border-zinc-800/50 bg-zinc-900 shadow-xl"
          >
            <div className="p-3">
              <div className="mb-3 text-[10px] font-medium uppercase tracking-wider text-zinc-500">
                Agent Autonomy
              </div>

              <div className="space-y-1">
                {LEVELS.map((l) => {
                  const Icon = l.icon;
                  const isActive = level === l.key;
                  return (
                    <button
                      key={l.key}
                      onClick={() => handleChange(l.key)}
                      className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left text-xs transition-all ${
                        isActive
                          ? "bg-zinc-800/80 text-zinc-200"
                          : "text-zinc-400 hover:bg-zinc-800/40 hover:text-zinc-300"
                      }`}
                    >
                      <Icon
                        size={16}
                        strokeWidth={1.5}
                        className={`mt-0.5 shrink-0 ${
                          isActive ? LEVEL_COLORS[l.key].split(" ")[2] : "text-zinc-600"
                        }`}
                      />
                      <div>
                        <div className="font-medium">{l.label}</div>
                        <div className="mt-0.5 text-[10px] leading-relaxed text-zinc-500">
                          {l.description}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="mt-3 border-t border-zinc-800/50 pt-2">
                <div className="relative mx-2 h-1.5 rounded-full bg-zinc-800">
                  <motion.div
                    className={`absolute h-full rounded-full transition-all ${
                      level === "autopilot"
                        ? "bg-blue-500/60"
                        : level === "auto"
                        ? "bg-emerald-500/60"
                        : "bg-amber-500/60"
                    }`}
                    initial={false}
                    animate={{
                      width: level === "suggest" ? "10%" : level === "auto" ? "50%" : "90%",
                    }}
                    transition={{ type: "spring", stiffness: 200, damping: 25 }}
                  />
                </div>
                <div className="mt-1.5 flex justify-between px-2 text-[9px] text-zinc-600">
                  <span>Suggest</span>
                  <span>Auto</span>
                  <span>Autopilot</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
