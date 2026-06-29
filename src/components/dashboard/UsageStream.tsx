"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Activity, Terminal, Brain, DollarSign, AlertCircle, CheckCircle2, Clock, RefreshCw } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
type StreamItem = {
  id: string;
  type: string;
  data: Record<string, unknown>;
  createdAt: string;
  runHint?: string;
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour12: false, minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function eventIcon(type: string) {
  switch (type) {
    case "tool_calls":
    case "ToolExecutionStarted":
    case "ToolExecutionCompleted":
    case "ToolProgress":
    case "tool_result":
      return Terminal;
    case "reasoning":
      return Brain;
    case "metrics":
      return DollarSign;
    case "error":
      return AlertCircle;
    case "done":
      return CheckCircle2;
    default:
      return Activity;
  }
}

function eventColor(type: string): string {
  switch (type) {
    case "tool_calls":
    case "ToolExecutionStarted":
    case "ToolExecutionCompleted":
    case "ToolProgress":
    case "tool_result":
      return "text-emerald-400 bg-emerald-500/10 border-emerald-500/15";
    case "reasoning":
      return "text-amber-400/70 bg-amber-500/5 border-amber-500/10";
    case "metrics":
      return "text-zinc-400 bg-zinc-500/10 border-zinc-500/15";
    case "error":
      return "text-red-400 bg-red-500/10 border-red-500/15";
    case "done":
      return "text-emerald-400 bg-emerald-500/10 border-emerald-500/15";
    default:
      return "text-zinc-500 bg-zinc-800/30 border-zinc-800/20";
  }
}

function eventLabel(type: string, data: Record<string, unknown>): string {
  switch (type) {
    case "tool_calls": {
      const calls = data.calls as Array<{ function: { name: string } }> | undefined;
      return calls?.map((c) => c.function.name).join(", ") || "Tool call";
    }
    case "ToolExecutionStarted": return (data as any).tool_name || "Tool started";
    case "ToolExecutionCompleted": return `${(data as any).tool_name || "Tool"} ${(data as any).success ? "completed" : "failed"}`;
    case "tool_result": return (data as any).name || "Tool result";
    case "reasoning": return "Agent reasoning";
    case "metrics": {
      const t = (data as any).total_tokens || 0;
      const c = (data as any).estimated_cost_usd || 0;
      return `${t.toLocaleString()} tokens · $${c.toFixed(4)}`;
    }
    case "error": return (data as any).message || "Error";
    case "done": return "Pipeline completed";
    case "token": return "Token output";
    case "mode": return `Mode: ${(data as any).mode || data}`;
    case "pipeline:start": return "Pipeline started";
    default: return type;
  }
}

export function UsageStream() {
  const [paused, setPaused] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["usage-stream"],
    queryFn: () => api.get<{ events: StreamItem[] }>("/api/stream/recent?limit=40"),
    refetchInterval: paused ? false : 15_000,
    retry: 1,
  });

  const items = (data?.events ?? []).reverse();

  useEffect(() => {
    if (autoScroll && endRef.current) {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [items, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(dist < 40);
  }, []);

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-6 space-y-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <Activity size={15} className="text-emerald-400" strokeWidth={1.5} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-neutral-100 tracking-tight">Usage Stream</h3>
            <p className="text-[11px] text-neutral-500 mt-0.5">Recent pipeline activity</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {items.length > 0 && (
            <span className="text-[10px] text-neutral-600 font-mono tabular-nums">{items.length} events</span>
          )}
          {error && (
            <button onClick={() => refetch()} className="text-[10px] px-2 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors" title="Retry">
              <RefreshCw size={10} strokeWidth={1.5} />
            </button>
          )}
          <button
            onClick={() => setPaused(!paused)}
            className={cn(
              "text-[10px] px-2 py-1 rounded-lg border transition-all duration-300 active:scale-[0.97]",
              paused
                ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
                : "bg-white/[0.03] border-white/[0.06] text-neutral-500 hover:text-neutral-300",
            )}
          >
            {paused ? "paused" : "live"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-3">
            <AlertCircle size={20} strokeWidth={1} className="text-red-400" />
          </div>
          <p className="text-sm text-red-400">Failed to load activity</p>
          <p className="text-xs text-neutral-600 mt-1">{error instanceof Error ? error.message : "Connection error"}</p>
          <button onClick={() => refetch()} className="mt-4 text-[11px] px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-neutral-400 hover:text-neutral-300 transition-colors">
            Retry
          </button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2 py-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-12 bg-white/[0.02] rounded-xl animate-pulse" style={{ animationDelay: `${i * 100}ms` }} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 rounded-2xl bg-zinc-900/50 border border-zinc-800/30 flex items-center justify-center mb-3">
            <Activity size={20} strokeWidth={1} className="text-zinc-600" />
          </div>
          <p className="text-sm text-neutral-500">No pipeline activity yet</p>
          <p className="text-xs text-neutral-700 mt-1">Run a pipeline to see events stream here</p>
        </div>
      ) : (
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1 -mr-1"
        >
          <AnimatePresence mode="popLayout">
            {items.map((item) => {
              const Icon = eventIcon(item.type);
              const colors = eventColor(item.type);
              return (
                <motion.div
                  key={item.id}
                  layout
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ type: "spring", stiffness: 200, damping: 28 }}
                  className={cn(
                    "flex items-start gap-3 px-3.5 py-2.5 rounded-xl border transition-colors",
                    colors,
                  )}
                >
                  <Icon size={13} className="shrink-0 mt-0.5" strokeWidth={1.5} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-neutral-200 truncate">
                        {eventLabel(item.type, item.data)}
                      </span>
                      <span className="text-[10px] text-neutral-600 font-mono tabular-nums shrink-0">
                        {formatTime(item.createdAt)}
                      </span>
                    </div>
                    {item.runHint && (
                      <p className="text-[10px] text-neutral-600 mt-0.5 truncate">{item.runHint}</p>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
          {!autoScroll && items.length > 0 && (
            <div className="flex justify-center pt-1">
              <button
                onClick={() => { setAutoScroll(true); endRef.current?.scrollIntoView({ behavior: "smooth" }); }}
                className="flex items-center gap-1 text-[10px] text-neutral-600 hover:text-neutral-400 bg-zinc-900/60 border border-zinc-800/30 rounded-full px-3 py-1 transition-colors active:scale-[0.97]"
              >
                <Clock size={10} strokeWidth={1.5} />
                Scroll to latest
              </button>
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}
    </div>
  );
}
