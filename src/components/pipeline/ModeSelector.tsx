"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api/api-client";

const API = typeof window !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001" : "http://localhost:8001";

interface Mode {
  name: string;
  description: string;
  toolsets: string[];
}

export function ModeSelector() {
  const { mode, setMode, events } = usePipelineStore();
  const [agentSwitchedTo, setAgentSwitchedTo] = useState<string | null>(null);
  const prevModeRef = useRef(mode);

  useEffect(() => {
    const lastEvent = events[events.length - 1];
    if (lastEvent?.type === "mode" && (lastEvent as any).source === "agent") {
      const newMode = lastEvent.mode;
      if (newMode && newMode !== prevModeRef.current) {
        setAgentSwitchedTo(newMode);
        prevModeRef.current = newMode;
        setTimeout(() => setAgentSwitchedTo(null), 2500);
      }
    }
  }, [events]);

  const { data: modes } = useQuery({
    queryKey: ["modes"],
    queryFn: async () => {
      const json = await api.get<{ modes: Mode[] }>(`/api/modes`);
      return json?.modes ?? [];
    },
    staleTime: 300_000,
  });

  if (!modes || modes.length === 0) return null;

  return (
    <div className="relative flex items-center gap-1 bg-white/[0.03] rounded-xl p-0.5 border border-white/[0.06]">
      {modes.map((m) => {
        const isActive = mode === m.name;
        const isAgentSwitched = agentSwitchedTo === m.name;

        return (
          <button
            key={m.name}
            type="button"
            onClick={() => setMode(m.name)}
            className={cn(
              "relative px-4 py-1.5 rounded-lg text-xs font-medium transition-all",
              isActive
                ? "bg-white/[0.08] text-neutral-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                : "text-neutral-500 hover:text-neutral-300",
            )}
            title={
              isAgentSwitched
                ? `Agent switched to ${m.name} mode`
                : m.description
            }
          >
            {m.name.charAt(0).toUpperCase() + m.name.slice(1)}
            {isAgentSwitched && (
              <motion.span
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: [1, 1.2, 1], opacity: [1, 0.8, 0] }}
                transition={{ duration: 1.5, ease: "easeOut" }}
                className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-emerald-400"
              />
            )}
          </button>
        );
      })}

      <AnimatePresence>
        {agentSwitchedTo && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: "spring", stiffness: 200, damping: 20 }}
            className="absolute -bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[10px] text-emerald-400 whitespace-nowrap"
          >
            <Sparkles className="w-3 h-3" strokeWidth={1.5} />
            Agent switched to {agentSwitchedTo}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
