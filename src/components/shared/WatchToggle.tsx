"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { Eye, EyeOff } from "lucide-react";
import { BACKEND_URL } from "@/lib/api/api-client";
import { useEventSource } from "@/lib/hooks/use-event-source";

interface WatchToggleProps {
  endpoint?: string;
  onEvent?: (data: any) => void;
  label?: string;
}

export function WatchToggle({ endpoint = "/api/stream/recent", onEvent, label = "Watch" }: WatchToggleProps) {
  const [watching, setWatching] = useState(false);
  const [eventCount, setEventCount] = useState(0);

  const { state } = useEventSource({
    url: watching ? `${BACKEND_URL}${endpoint}` : null,
    onMessage: (data) => {
      setEventCount((c) => c + 1);
      onEvent?.(data);
    },
  });

  const handleClick = useCallback(() => {
    setWatching((w) => !w);
  }, []);

  const isLive = watching && state === "open";
  const isReconnecting = watching && (state === "reconnecting" || state === "connecting");

  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.97 }}
      onClick={handleClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${
        isLive
          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
          : isReconnecting
            ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
            : "bg-white/[0.04] text-zinc-500 hover:text-zinc-300 border border-transparent hover:border-white/[0.08]"
      }`}
    >
      {isLive ? (
        <>
          <motion.span
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
          >
            <Eye className="w-3 h-3" strokeWidth={1.5} />
          </motion.span>
          <span>Live</span>
          {eventCount > 0 && <span className="text-[9px] font-mono tabular-nums text-emerald-400/70">+{eventCount}</span>}
        </>
      ) : isReconnecting ? (
        <>
          <Eye className="w-3 h-3" strokeWidth={1.5} />
          <span>Reconnecting</span>
        </>
      ) : (
        <>
          <EyeOff className="w-3 h-3" strokeWidth={1.5} />
          <span>{label}</span>
        </>
      )}
    </motion.button>
  );
}
