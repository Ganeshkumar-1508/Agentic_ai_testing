"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Terminal, Loader2, AlertCircle } from "lucide-react";

interface FlowEvent {
  id: string; type: string; raw_type: string;
  agent_id: string; parent_id: string | null; depth: number;
  duration_ms: number | null; token_count: number | null;
  tool_name: string | null; content_preview: string | null;
  created_at: string | null; payload: any;
}

interface EventStreamProps {
  events: FlowEvent[];
  selectedEventId: string | null;
  eventFilters: string[];
  hasMore: boolean;
  loading: boolean;
  apiError: string | boolean | null;
  liveTail: boolean;
  sessionId: string | null;
  onEventFilter: (key: string) => void;
  onEventSelect?: (event: FlowEvent) => void;
  onLoadMore: () => void;
  onToggleLive?: () => void;
}

export function EventStream({
  events, selectedEventId, eventFilters, hasMore, loading, apiError, liveTail, sessionId,
  onEventFilter, onEventSelect, onLoadMore, onToggleLive,
}: EventStreamProps) {
  if (apiError && typeof apiError === "string") {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
        <AlertCircle className="w-6 h-6 mb-2" strokeWidth={1.5} />
        <p className="text-sm">{apiError}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        {["tool", "token", "reasoning", "delegate", "approval"].map((key) => (
          <button key={key} onClick={() => onEventFilter(key)}
            className={cn("px-2 py-0.5 rounded text-[10px] font-medium transition-all capitalize",
              eventFilters.includes(key) ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-zinc-400"
            )}>{key}</button>
        ))}
        {liveTail && <Loader2 className="w-3 h-3 animate-spin text-emerald-400 ml-auto" strokeWidth={2} />}
      </div>
      <AnimatePresence>
        {events.length === 0 && !loading && (
          <div className="text-center py-8 text-xs text-zinc-600">No events{sessionId ? "" : " — select a session"}</div>
        )}
        {events.map((ev) => (
          <motion.div key={ev.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            onClick={() => onEventSelect?.(ev)}
            className={cn("flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors text-[11px] font-mono",
              selectedEventId === ev.id ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-500 hover:bg-zinc-900/30"
            )}>
            <Terminal className="w-3 h-3 shrink-0 opacity-60" strokeWidth={1.5} />
            <span className="truncate flex-1">{ev.tool_name || ev.type}</span>
            {ev.duration_ms != null && <span className="text-[10px] text-zinc-700">{ev.duration_ms}ms</span>}
          </motion.div>
        ))}
      </AnimatePresence>
      {hasMore && (
        <button onClick={onLoadMore} disabled={loading}
          className="w-full text-[10px] text-zinc-600 hover:text-zinc-400 py-2 transition-colors">
          {loading ? "Loading..." : "Load more"}
        </button>
      )}
    </div>
  );
}
