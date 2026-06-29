"use client";

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  Play, Pause, SkipBack, SkipForward, ChevronRight,
  RotateCcw, FastForward, Wrench, Lightbulb, MessageSquare,
  CheckCircle, XCircle, Clock,
} from "lucide-react";

interface ReplayEvent {
  id: number;
  type: string;
  label: string;
  detail?: string;
  status?: string;
  timestamp?: string;
  offsetMs: number;
}

interface SessionReplayProps {
  events: Array<{
    type: string;
    data?: any;
    createdAt?: string;
  }>;
  isLoading?: boolean;
}

function buildTimeline(events: SessionReplayProps["events"]): ReplayEvent[] {
  return events
    .filter((e) => e.type && e.type !== "metrics")
    .map((e, i) => {
      const data = e.data ?? {};
      let label = e.type;
      let detail: string | undefined;
      let status: string | undefined;

      if (e.type === "tool_calls" && data.calls?.length) {
        label = `tool: ${data.calls[0]?.function?.name ?? "unknown"}`;
        detail = data.calls[0]?.function?.arguments?.slice(0, 80);
      } else if (e.type === "tool_result") {
        label = `result: ${data.name ?? "tool"}`;
        detail = data.result?.slice(0, 120);
        status = data.success ? "completed" : "failed";
      } else if (e.type === "ToolExecutionStarted") {
        label = data.tool_name ?? "tool";
        detail = (data.tool_input ?? "").slice(0, 80);
        status = "running";
      } else if (e.type === "ToolExecutionCompleted") {
        label = data.tool_name ?? "tool";
        detail = data.success ? "completed" : "failed";
        status = data.success ? "completed" : "failed";
      } else if (e.type === "reasoning") {
        label = "reasoning";
        detail = (data.content ?? "").slice(0, 80);
      } else if (e.type === "token") {
        label = "text";
        detail = (data.content ?? "").slice(0, 60);
      } else if (e.type === "error") {
        label = "error";
        detail = (data.message ?? "").slice(0, 80);
        status = "failed";
      } else if (e.type === "done") {
        label = "completed";
        status = "completed";
      } else if (e.type === "approval:required") {
        label = `approval: ${data.tool ?? "unknown"}`;
        detail = JSON.stringify(data.args ?? {}).slice(0, 80);
        status = "pending";
      } else if (e.type === "phase:enter" || e.type === "phase:complete") {
        label = `phase: ${data.phase ?? data.label ?? e.type}`;
        detail = data.message;
        status = e.type === "phase:complete" ? (data.status ?? "passed") : "running";
      }

      return {
        id: i,
        type: e.type,
        label,
        detail,
        status,
        timestamp: e.createdAt,
        offsetMs: i * 600 + Math.random() * 200,
      };
    });
}

function EventIcon({ type, status }: { type: string; status?: string }) {
  if (type === "reasoning") return <Lightbulb className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />;
  if (type === "tool_calls" || type === "ToolExecutionStarted") return <Wrench className="w-3.5 h-3.5 text-blue-400" strokeWidth={1.5} />;
  if (type === "ToolExecutionCompleted" || type === "tool_result") {
    return status === "failed"
      ? <XCircle className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />
      : <CheckCircle className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />;
  }
  if (type === "error") return <XCircle className="w-3.5 h-3.5 text-red-400" strokeWidth={1.5} />;
  if (type === "done") return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />;
  if (type === "phase:enter" || type === "phase:complete") return <ChevronRight className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />;
  if (type === "token") return <MessageSquare className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />;
  return <Clock className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />;
}

export function SessionReplay({ events, isLoading }: SessionReplayProps) {
  const timeline = useMemo(() => buildTimeline(events), [events]);
  const [playState, setPlayState] = useState<"idle" | "playing" | "paused">("idle");
  const [currentIdx, setCurrentIdx] = useState(0);
  const [speed, setSpeed] = useState(2);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const advance = useCallback(() => {
    setCurrentIdx((prev) => {
      const next = prev + 1;
      if (next >= timeline.length) {
        setPlayState("idle");
        return 0;
      }
      return next;
    });
  }, [timeline.length]);

  useEffect(() => {
    if (playState !== "playing") {
      if (timerRef.current) clearTimeout(timerRef.current);
      return;
    }
    timerRef.current = setTimeout(advance, 400 / speed);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [playState, currentIdx, speed, advance]);

  const togglePlay = () => {
    if (playState === "playing") {
      setPlayState("paused");
    } else {
      if (currentIdx >= timeline.length - 1) setCurrentIdx(0);
      setPlayState("playing");
    }
  };

  const goTo = (idx: number) => {
    setCurrentIdx(Math.max(0, Math.min(idx, timeline.length - 1)));
  };

  const currentEvent = timeline[currentIdx];

  if (isLoading) {
    return (
      <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5 space-y-4">
        <div className="w-32 h-4 rounded-full shimmer-bg" />
        <div className="h-48 bg-white/[0.02] rounded-xl animate-pulse" />
      </div>
    );
  }

  if (timeline.length === 0) return null;

  const totalEvents = timeline.length;

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <RotateCcw className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
          </div>
          <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Session Replay</span>
          <span className="text-[10px] font-mono text-zinc-600 px-1.5 py-0.5 rounded bg-white/[0.03]">
            {totalEvents} events
          </span>
        </div>
      </div>

      {/* Timeline track */}
      <div className="relative h-8 bg-zinc-800/50 rounded-xl mb-4 overflow-hidden cursor-pointer" onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        goTo(Math.floor(pct * totalEvents));
      }}>
        {timeline.map((ev, i) => (
          <div
            key={i}
            className={cn(
              "absolute top-0 bottom-0 w-0.5 transition-all duration-150",
              i === currentIdx ? "bg-emerald-400 z-10 w-1" :
              i < currentIdx ? "bg-emerald-400/30" :
              ev.status === "failed" ? "bg-red-500/20" :
              "bg-zinc-700",
            )}
            style={{ left: `${(i / totalEvents) * 100}%` }}
          />
        ))}
        {/* Playhead */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-emerald-400 z-20 transition-all duration-200"
          style={{ left: `${(currentIdx / Math.max(totalEvents - 1, 1)) * 100}%` }}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => goTo(0)}
          className="w-7 h-7 rounded-lg bg-white/[0.03] flex items-center justify-center hover:bg-white/[0.06] transition-colors"
          disabled={currentIdx === 0}
        >
          <SkipBack className="w-3 h-3 text-zinc-400" strokeWidth={1.5} />
        </button>
        <button
          onClick={() => goTo(currentIdx - 1)}
          className="w-7 h-7 rounded-lg bg-white/[0.03] flex items-center justify-center hover:bg-white/[0.06] transition-colors"
          disabled={currentIdx === 0}
        >
          <ChevronRight className="w-3 h-3 text-zinc-400 rotate-180" strokeWidth={1.5} />
        </button>
        <button
          onClick={togglePlay}
          className="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center hover:bg-emerald-500/25 transition-colors"
        >
          {playState === "playing"
            ? <Pause className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
            : <Play className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
          }
        </button>
        <button
          onClick={() => goTo(currentIdx + 1)}
          className="w-7 h-7 rounded-lg bg-white/[0.03] flex items-center justify-center hover:bg-white/[0.06] transition-colors"
          disabled={currentIdx >= totalEvents - 1}
        >
          <ChevronRight className="w-3 h-3 text-zinc-400" strokeWidth={1.5} />
        </button>
        <button
          onClick={() => goTo(totalEvents - 1)}
          className="w-7 h-7 rounded-lg bg-white/[0.03] flex items-center justify-center hover:bg-white/[0.06] transition-colors"
          disabled={currentIdx >= totalEvents - 1}
        >
          <SkipForward className="w-3 h-3 text-zinc-400" strokeWidth={1.5} />
        </button>
        <div className="w-px h-5 bg-white/[0.06] mx-1" />
        {[1, 2, 4, 8].map((s) => (
          <button
            key={s}
            onClick={() => setSpeed(s)}
            className={cn(
              "px-2 h-7 rounded-lg text-[10px] font-mono transition-colors",
              speed === s
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-white/[0.03] text-zinc-600 hover:text-zinc-400 hover:bg-white/[0.06]",
            )}
          >
            {s}x
          </button>
        ))}
        <span className="ml-auto text-[10px] font-mono text-zinc-600 tabular-nums">
          {currentIdx + 1} / {totalEvents}
        </span>
      </div>

      {/* Current event detail */}
      {currentEvent && (
        <motion.div
          key={currentEvent.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className={cn(
            "rounded-xl border p-4",
            currentEvent.status === "failed" ? "border-red-500/15 bg-red-500/[0.03]" :
            currentEvent.status === "completed" ? "border-emerald-500/10 bg-emerald-500/[0.02]" :
            "border-white/[0.05] bg-white/[0.01]",
          )}
        >
          <div className="flex items-center gap-2.5 mb-2">
            <EventIcon type={currentEvent.type} status={currentEvent.status} />
            <span className={cn(
              "text-xs font-semibold uppercase tracking-wider",
              currentEvent.status === "failed" ? "text-red-400" :
              currentEvent.status === "completed" ? "text-emerald-400" :
              "text-zinc-300",
            )}>
              {currentEvent.type}
            </span>
            {currentEvent.timestamp && (
              <span className="text-[9px] font-mono text-zinc-600 ml-auto">
                {new Date(currentEvent.timestamp).toLocaleTimeString()}
              </span>
            )}
          </div>
          <div className="text-xs text-zinc-400 font-mono leading-relaxed break-all">
            {currentEvent.label}
          </div>
          {currentEvent.detail && (
            <div className="mt-2 text-[11px] text-zinc-500 font-mono bg-white/[0.02] rounded-lg p-2.5 leading-relaxed break-all">
              {currentEvent.detail}
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
