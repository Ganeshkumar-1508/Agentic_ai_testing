"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Shield, Eye, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";

export const TIER_LABEL: Record<number, string> = {
  1: "Autonomous",
  2: "Supervised",
  3: "Human",
};

const TIER_DESC: Record<number, string> = {
  1: "Agent runs to completion autonomously",
  2: "Agent pauses for human review before actions",
  3: "Agent creates a proposal for human to execute",
};

const TIER_ICONS: Record<number, React.ElementType> = {
  1: Shield,
  2: Eye,
  3: UserCheck,
};

const TIER_COLORS: Record<number, string> = {
  1: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  2: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  3: "bg-blue-500/10 text-blue-400 border-blue-500/20",
};

interface TierBadgeProps {
  tier: number;
  onChange?: (tier: number) => void;
  disabled?: boolean;
}

export function TierBadge({ tier, onChange, disabled }: TierBadgeProps) {
  const [open, setOpen] = useState(false);

  const Icon = TIER_ICONS[tier] || Shield;
  const label = TIER_LABEL[tier] || `Tier ${tier}`;

  const handleSelect = useCallback((t: number) => {
    onChange?.(t);
    setOpen(false);
  }, [onChange]);

  return (
    <div className="relative">
      <button
        type="button"
        className={cn(
          "agent-meta-chip flex items-center gap-1.5",
          TIER_COLORS[tier],
          disabled && "opacity-40 cursor-not-allowed",
        )}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        title={`Tier ${tier}: ${label}`}
      >
        <span className="agent-chip-icon">
          <Icon width={11} height={11} strokeWidth={1.5} />
        </span>
        <span className="text-[10px]">{label}</span>
        <ChevronDown className="agent-chev" width={9} height={9} strokeWidth={2.5} />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40"
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.96 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="absolute bottom-full left-0 mb-1 z-50 w-56 rounded-xl bg-zinc-900/95 backdrop-blur-md border border-zinc-800/60 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,255,255,0.04)] overflow-hidden"
            >
              <div className="px-3 py-2 text-[9px] font-semibold uppercase tracking-[0.8px] text-zinc-600 border-b border-zinc-800/30">
                Autonomy Tier
              </div>
              <div className="p-1 space-y-0.5">
                {([1, 2, 3] as const).map((t) => {
                  const TierIcon = TIER_ICONS[t] || Shield;
                  const isActive = t === tier;
                  return (
                    <button
                      key={t}
                      onClick={() => handleSelect(t)}
                      className={cn(
                        "w-full flex items-start gap-2.5 px-3 py-2 rounded-lg text-left transition-all duration-200 active:scale-[0.98]",
                        isActive ? "bg-zinc-800/60" : "text-zinc-300 hover:bg-zinc-800/40"
                      )}
                    >
                      <div className={cn(
                        "w-7 h-7 rounded-lg flex items-center justify-center mt-0.5",
                        TIER_COLORS[t],
                      )}>
                        <TierIcon size={12} strokeWidth={1.5} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium">{TIER_LABEL[t]}</div>
                        <div className="text-[10px] text-zinc-600 mt-0.5">{TIER_DESC[t]}</div>
                      </div>
                      {isActive && (
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-2 shrink-0 shadow-[0_0_4px_rgba(52,211,153,0.6)]" />
                      )}
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
