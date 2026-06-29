"use client";

import { memo, useMemo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Cpu,
  Wrench,
  Loader2,
  Terminal,
  DollarSign,
  Clock,
  BarChart3,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useShadowStream, type ShadowAgentState } from "@/lib/hooks/use-shadow-stream";

interface AgentThinkingPanelProps {
  sessionId: string;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function formatTime(ms: number): string {
  return new Date(ms).toISOString().slice(11, 23);
}

const LiveDot = memo(function LiveDot() {
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      <motion.span
        className="absolute inset-0 rounded-full bg-emerald-400/60"
        animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
      />
      <span className="relative inline-block h-2 w-2 rounded-full bg-emerald-400" />
    </span>
  );
});

function ThinkingContent({ text }: { text: string }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [text]);

  if (!text) {
    return (
      <div className="flex items-center gap-2 py-3 text-zinc-600">
        <Loader2 size={12} className="animate-spin" strokeWidth={2} />
        <span className="text-[11px] font-mono">waiting for agent response...</span>
      </div>
    );
  }

  return (
    <div className="max-h-[180px] overflow-y-auto text-[11px] text-zinc-400 font-mono leading-relaxed whitespace-pre-wrap">
      {text}
      <div ref={endRef} />
    </div>
  );
}

function TokenBurnChart({ points }: { points: ShadowAgentState["tokenBurn"] }) {
  const maxVal = useMemo(() => Math.max(...points.map((p) => p.tokens), 1), [points]);
  const totalCost = useMemo(() => points.reduce((s, p) => s + p.cost, 0), [points]);
  const totalTokens = useMemo(() => points.reduce((s, p) => s + p.tokens, 0), [points]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[10px] text-zinc-600 font-mono">
        <span className="flex items-center gap-1">
          <BarChart3 size={10} strokeWidth={1.5} />
          token burn
        </span>
        <span className="flex items-center gap-2">
          <span>{totalTokens.toLocaleString()} tok</span>
          <span className="flex items-center gap-0.5">
            <DollarSign size={9} strokeWidth={1.5} />${totalCost.toFixed(4)}
          </span>
        </span>
      </div>
      <div className="flex items-end gap-[1px] h-6">
        {points.slice(-30).map((pt, i) => {
          const h = (pt.tokens / maxVal) * 100;
          return (
            <div
              key={i}
              className="flex-1 min-w-[2px] rounded-sm bg-emerald-500/20 hover:bg-emerald-500/40 transition-colors"
              style={{ height: `${Math.max(h, 4)}%` }}
              title={`${pt.tokens.toLocaleString()} tok · $${pt.cost.toFixed(4)} · ${pt.model}`}
            />
          );
        })}
      </div>
    </div>
  );
}

function StatusBar({ state, elapsed }: { state: ShadowAgentState; elapsed: number }) {
  return (
    <div className="flex items-center gap-3 text-[10px] text-zinc-600 font-mono">
      <span className="flex items-center gap-1">
        <Clock size={10} strokeWidth={1.5} />
        {formatDuration(elapsed)}
      </span>
      {state.currentTool && (
        <span className="flex items-center gap-1 text-amber-400/70">
          <Wrench size={10} strokeWidth={1.5} />
          {state.currentTool.name}
        </span>
      )}
      <span className="flex items-center gap-1">
        <Cpu size={10} strokeWidth={1.5} />
        {state.recentToolResults.length} tools
      </span>
    </div>
  );
}

export function AgentThinkingPanel({ sessionId }: AgentThinkingPanelProps) {
  const { state, connectionState } = useShadowStream(sessionId);

  if (connectionState === "idle" || connectionState === "connecting") {
    return (
      <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/20 p-5">
        <div className="flex items-center justify-center gap-3 py-8 text-zinc-600">
          <Loader2 size={16} className="animate-spin" strokeWidth={2} />
          <span className="text-xs font-mono">connecting to agent session...</span>
        </div>
      </div>
    );
  }

  if (connectionState === "error") {
    return (
      <div className="rounded-xl border border-zinc-800/50 bg-zinc-900/20 p-5">
        <div className="flex items-center justify-center gap-2 py-6 text-zinc-600">
          <span className="text-xs font-mono text-red-400/60">connection lost</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <LiveDot />
          <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-emerald-400/80">
            agent thinking
          </span>
        </div>
        <StatusBar state={state} elapsed={state.elapsed} />
      </div>

      {/* Current tool */}
      <AnimatePresence mode="wait">
        {state.currentTool ? (
          <motion.div
            key={state.currentTool.name}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1.5"
          >
            <div className="flex items-center gap-1.5 text-[11px] text-amber-400/80 font-medium">
              <Wrench size={12} strokeWidth={1.5} />
              {state.currentTool.name}
              <span className="text-[10px] text-zinc-600 font-mono ml-auto">
                {formatDuration(state.currentTool.elapsed)}
              </span>
            </div>
            {state.currentTool.input && (
              <p className="text-[10px] text-zinc-500 font-mono truncate">
                {state.currentTool.input.slice(0, 150)}
              </p>
            )}
          </motion.div>
        ) : null}
      </AnimatePresence>

      {/* Thinking content */}
      <div className="rounded-lg border border-zinc-800/30 bg-zinc-900/20 p-3">
        <div className="flex items-center gap-1.5 mb-2 text-[10px] text-zinc-600 font-medium uppercase tracking-wider">
          <Sparkles size={10} strokeWidth={1.5} />
          reasoning
        </div>
        <ThinkingContent text={state.reasoning} />
      </div>

      {/* Token burn */}
      {state.tokenBurn.length > 1 && (
        <div className="rounded-lg border border-zinc-800/30 bg-zinc-900/20 p-3">
          <TokenBurnChart points={state.tokenBurn} />
        </div>
      )}

      {/* Recent tool results */}
      {state.recentToolResults.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-[10px] text-zinc-600 font-medium uppercase tracking-wider">
            <Terminal size={10} strokeWidth={1.5} />
            recent tool results
          </div>
          <div className="space-y-1">
            {state.recentToolResults.slice(0, 5).map((tr, i) => (
              <motion.div
                key={`${tr.tool}-${i}`}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                className="flex items-start gap-2 rounded-md bg-zinc-900/30 px-2.5 py-1.5 text-[10px]"
              >
                <span className="shrink-0 font-mono text-zinc-500">{tr.tool}</span>
                <span className="text-zinc-600 truncate">{tr.result.slice(0, 120)}</span>
                {tr.duration > 0 && (
                  <span className="shrink-0 font-mono text-zinc-700 ml-auto">{tr.duration}ms</span>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
