"use client";

import { useRef, useEffect, useState, useMemo } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ReasoningBlock } from "@/components/shared/ReasoningBlock";
import { ToolCallCard } from "@/components/shared/ToolCallCard";
import { StackTrace } from "@/components/shared/StackTrace";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, AlertCircle, CheckCircle2, Brain, Sparkles, ChevronDown, ChevronRight } from "lucide-react";

type FlattenedEvent = {
  key: string;
  variant: "reasoning" | "tool" | "error" | "approval" | "metrics" | "done" | "info" | "token_group";
  ts: number;
};

function formatTokenCount(n: number): string {
  if (n > 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n > 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function EventStream() {
  const { events, status, connected } = usePipelineStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  const flattened = useMemo(() => {
    const result: FlattenedEvent[] = [];
    let reasoningAccum: string[] = [];
    let tokenAccum: string[] = [];
    let metricAccum: { tokens: number; cost: number } | null = null;

    const filtered = filter === "all"
      ? events
      : events.filter((e) => {
          if (filter === "token") return e.type === "token";
          if (filter === "tool") return ["tool_calls", "ToolExecutionStarted", "ToolExecutionCompleted", "tool_result", "ToolProgress"].includes(e.type);
          if (filter === "reasoning") return e.type === "reasoning";
          return true;
        });

    for (let i = 0; i < filtered.length; i++) {
      const event = filtered[i];

      if (event.type === "token") {
        tokenAccum.push(event.content);
        continue;
      }

      if (event.type === "reasoning") {
        reasoningAccum.push(event.content);
        continue;
      }

      if (event.type === "metrics") {
        if (!metricAccum) metricAccum = { tokens: 0, cost: 0 };
        metricAccum.tokens += event.total_tokens || 0;
        metricAccum.cost = event.estimated_cost_usd || metricAccum.cost;
        continue;
      }

      if (tokenAccum.length > 0) {
        result.push({ key: `tok-${i}-${tokenAccum.length}`, variant: "token_group", ts: Date.now() });
        tokenAccum = [];
      }

      if (reasoningAccum.length > 0) {
        result.push({ key: `re-${i}-${reasoningAccum.length}`, variant: "reasoning", ts: Date.now() });
        reasoningAccum = [];
      }

      if (metricAccum) {
        result.push({ key: `met-${i}`, variant: "metrics", ts: Date.now() });
        metricAccum = null;
      }

      switch (event.type) {
        case "tool_calls":
        case "ToolExecutionStarted":
        case "ToolExecutionCompleted":
        case "tool_result":
          result.push({ key: `tool-${i}`, variant: "tool", ts: Date.now() });
          break;
        case "error":
          result.push({ key: `err-${i}`, variant: "error", ts: Date.now() });
          break;
        case "approval:required":
          result.push({ key: `app-${i}`, variant: "approval", ts: Date.now() });
          break;
        case "done":
          result.push({ key: `done-${i}`, variant: "done", ts: Date.now() });
          break;
        case "mode":
        case "pipeline:start":
          result.push({ key: `info-${i}`, variant: "info", ts: Date.now() });
          break;
      }
    }

    // Flush accumulators
    if (tokenAccum.length > 0) result.push({ key: `tok-end-${tokenAccum.length}`, variant: "token_group", ts: Date.now() });
    if (reasoningAccum.length > 0) result.push({ key: `re-end-${reasoningAccum.length}`, variant: "reasoning", ts: Date.now() });
    if (metricAccum) result.push({ key: `met-end`, variant: "metrics", ts: Date.now() });

    return result;
  }, [events, filter]);

  const eventCount = events.length;
  const tokenCount = events.reduce((sum, e) => sum + (e.type === "token" ? e.content.length : 0), 0);
  const duration = usePipelineStore((s) => {
    if (!s.startTime) return 0;
    const end = s.endTime || Date.now();
    return Math.round((end - s.startTime) / 1000);
  });
  const tools = usePipelineStore((s) => s.tools);

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
            Event Stream
          </div>
          <div className="text-[10px] text-neutral-600 font-mono mt-0.5">
            {connected ? "api/delegate/{sessionId}/stream" : "disconnected"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-[10px]">
            <span className={cn("w-1.5 h-1.5 rounded-full", connected ? "bg-emerald-400 animate-pulse" : "bg-neutral-600")} />
            <span className="text-neutral-500">{connected ? "live" : "idle"}</span>
          </div>
          <button
            type="button"
            onClick={() => setShowRaw(!showRaw)}
            className={cn(
              "text-[10px] px-2 py-0.5 rounded border transition-colors",
              showRaw
                ? "border-emerald-500/30 text-emerald-400"
                : "border-white/[0.06] text-neutral-500 hover:text-neutral-300",
            )}
          >
            {showRaw ? "structured" : "raw"}
          </button>
          <button
            type="button"
            onClick={() => setAutoScroll((v) => !v)}
            className={cn(
              "text-[10px] px-2 py-0.5 rounded border transition-colors",
              autoScroll
                ? "border-emerald-500/30 text-emerald-400"
                : "border-white/[0.06] text-neutral-500 hover:text-neutral-300",
            )}
          >
            {autoScroll ? "auto-scroll" : "paused"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-1">
        {["all", "token", "tool", "reasoning"].map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={cn(
              "text-[10px] px-2 py-0.5 rounded transition-colors",
              filter === f ? "bg-white/[0.08] text-neutral-100" : "text-neutral-600 hover:text-neutral-300",
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Structured view */}
      {!showRaw && (
        <ScrollArea className="h-[360px] rounded-xl bg-surface border border-white/[0.05]" ref={scrollRef}>
          <div className="p-3 space-y-2">
            {flattened.length === 0 && (
              <div className="text-neutral-600 text-center py-8 text-sm">No events yet. Start a pipeline run.</div>
            )}
            <AnimatePresence mode="popLayout">
              {flattened.map((item) => {
                switch (item.variant) {
                  case "reasoning": {
                    const reasoningEvents = events.filter((e) => e.type === "reasoning");
                    const latest = reasoningEvents[reasoningEvents.length - 1];
                    const text = reasoningEvents.map((e) => e.content).join("");
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                        <ReasoningBlock
                          content={text}
                          isStreaming={status === "running"}
                          startedAt={Date.now() - duration * 1000}
                          completedAt={status === "completed" ? Date.now() : undefined}
                        />
                      </motion.div>
                    );
                  }

                  case "tool": {
                    const toolEvents = events.filter((e) =>
                      ["tool_calls", "ToolExecutionStarted", "ToolExecutionCompleted", "tool_result"].includes(e.type)
                    );
                    const latestTool = toolEvents[toolEvents.length - 1];
                    if (!latestTool) return null;
                    const toolName =
                      latestTool.type === "tool_calls" ? latestTool.calls[0]?.function?.name :
                      latestTool.type === "ToolExecutionStarted" ? latestTool.tool_name :
                      latestTool.type === "ToolExecutionCompleted" ? latestTool.tool_name :
                      latestTool.type === "tool_result" ? latestTool.name :
                      "tool";
                    const toolDetail = tools.find((t) => t.name === toolName);
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                        <ToolCallCard
                          name={toolDetail?.name || toolName}
                          status={(toolDetail?.status as "running" | "completed" | "error" | "pending") || "pending"}
                          durationMs={toolDetail?.startTime && toolDetail?.endTime ? toolDetail.endTime - toolDetail.startTime : undefined}
                          args={toolDetail?.args || undefined}
                          result={toolDetail?.output || undefined}
                          error={toolDetail?.error || undefined}
                        />
                      </motion.div>
                    );
                  }

                  case "error": {
                    const errEvent = [...events].reverse().find((e) => e.type === "error");
                    const errMsg = errEvent?.message || "Unknown error";
                    const isTrace = errMsg.includes("Traceback") || errMsg.includes("    at ") || /^\w*(Error|TypeError)/.test(errMsg);
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                        {isTrace ? (
                          <StackTrace trace={errMsg} />
                        ) : (
                          <div className="flex items-start gap-2.5 px-3.5 py-2.5 rounded-xl border border-red-500/15 bg-red-500/[0.04]">
                            <AlertCircle size={14} className="text-red-400 shrink-0 mt-0.5" strokeWidth={1.5} />
                            <div>
                              <p className="text-xs font-medium text-red-400">Pipeline Error</p>
                              <p className="text-[11px] text-red-400/70 font-mono mt-0.5">{errMsg}</p>
                            </div>
                          </div>
                        )}
                      </motion.div>
                    );
                  }

                  case "approval": {
                    const appEvent = [...events].reverse().find((e) => e.type === "approval:required");
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                        <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl border border-amber-500/15 bg-amber-500/[0.04]">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shrink-0" />
                          <span className="text-xs font-medium text-amber-400/80">Approval required</span>
                          <span className="text-[10px] text-amber-400/60 font-mono">{appEvent?.tool}</span>
                        </div>
                      </motion.div>
                    );
                  }

                  case "metrics": {
                    const totalTokens = events
                      .filter((e) => e.type === "metrics")
                      .reduce((s, e) => s + ((e as any).total_tokens || 0), 0);
                    const cost = events
                      .filter((e) => e.type === "metrics")
                      .reduce((s, e) => s + ((e as any).estimated_cost_usd || 0), 0);
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <div className="flex items-center gap-2 px-2.5 py-1">
                          <Sparkles size={10} className="text-neutral-600" strokeWidth={1.5} />
                          <span className="text-[10px] text-neutral-500 font-mono tabular-nums">
                            {formatTokenCount(totalTokens)} tokens
                          </span>
                          {cost > 0 && (
                            <span className="text-[10px] text-neutral-600 font-mono tabular-nums">
                              ${cost.toFixed(4)}
                            </span>
                          )}
                        </div>
                      </motion.div>
                    );
                  }

                  case "done":
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                        <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl border border-emerald-500/10 bg-emerald-500/[0.03]">
                          <CheckCircle2 size={14} className="text-emerald-400 shrink-0" strokeWidth={1.5} />
                          <span className="text-xs font-medium text-emerald-400">Pipeline completed</span>
                          <span className="text-[10px] text-neutral-500 font-mono ml-auto">{duration}s</span>
                        </div>
                      </motion.div>
                    );

                  case "info":
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <div className="flex items-center gap-2 px-2.5 py-1">
                          <Terminal size={10} className="text-neutral-600" strokeWidth={1.5} />
                          <span className="text-[10px] text-neutral-500 font-mono">
                            Pipeline started
                          </span>
                        </div>
                      </motion.div>
                    );

                  case "token_group": {
                    const tokenTexts = events.filter((e) => e.type === "token").map((e) => e.content);
                    const fullText = tokenTexts.join("");
                    if (!fullText) return null;
                    return (
                      <motion.div key={item.key} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <div className="border border-zinc-800/30 rounded-xl overflow-hidden">
                          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/30 text-[10px] text-neutral-500 font-mono">
                            <Terminal size={10} strokeWidth={1.5} className="text-neutral-600" />
                            <span>LLM Output</span>
                            <span className="text-neutral-700 ml-auto">{formatTokenCount(fullText.length)} chars</span>
                          </div>
                          <div className="px-3 py-2 text-[11px] text-neutral-400 font-mono leading-relaxed whitespace-pre-wrap max-h-24 overflow-y-auto bg-zinc-950/20">
                            {fullText.slice(0, 2000)}
                            {fullText.length > 2000 && (
                              <span className="text-neutral-600 italic"> ... ({formatTokenCount(fullText.length - 2000)} more)</span>
                            )}
                          </div>
                        </div>
                      </motion.div>
                    );
                  }

                  default:
                    return null;
                }
              })}
            </AnimatePresence>
          </div>
        </ScrollArea>
      )}

      {/* Raw JSON view */}
      {showRaw && (
        <ScrollArea className="h-[360px] rounded-xl bg-zinc-950/40 border border-white/[0.05]" ref={scrollRef}>
          <div className="p-3 space-y-1 font-mono text-[11px] leading-relaxed">
            {events.length === 0 && (
              <div className="text-neutral-600 text-center py-8">No events yet.</div>
            )}
            {events.map((event, i) => {
              const prefix = getEventPrefix(event.type);
              const color = getEventColor(event.type);
              let content = "";
              if (event.type === "token") content = event.content;
              else if (event.type === "reasoning") content = event.content;
              else if (event.type === "tool_calls") content = event.calls.map((c) => c.function.name).join(", ");
              else if (event.type === "tool_result") content = `${event.name}: ${event.result.slice(0, 200)}`;
              else if (event.type === "ToolExecutionStarted") content = `${event.tool_name} ${event.tool_input?.slice(0, 100) ?? ""}`;
              else if (event.type === "ToolExecutionCompleted") content = `${event.tool_name} ${event.success ? "OK" : "FAIL"}`;
              else if (event.type === "approval:required") content = `${event.tool} awaiting approval`;
              else if (event.type === "metrics") content = `tokens=${event.total_tokens} cost=$${event.estimated_cost_usd?.toFixed(4) || "0"}`;
              else if (event.type === "error") content = event.message;
              else if (event.type === "done") content = "Pipeline complete";
              else content = JSON.stringify(event).slice(0, 200);
              return (
                <div key={i} className="flex gap-2 group">
                  <span className={cn("shrink-0 select-none", color)}>{prefix}</span>
                  <span className="text-neutral-300 break-all">{content}</span>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      )}

      {/* Bottom bar */}
      <div className="flex items-center justify-between text-[10px] text-neutral-500 font-mono">
        <div className="flex items-center gap-3">
          <span>events: {eventCount}</span>
          <span>chars: {tokenCount}</span>
          <span>dur: {duration}s</span>
        </div>
        <button
          type="button"
          onClick={() => {
            const blob = new Blob([JSON.stringify(events, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `pipeline-${Date.now()}.json`;
            a.click();
          }}
          className="text-neutral-500 hover:text-neutral-300 transition-colors"
        >
          export
        </button>
      </div>
    </div>
  );
}

function getEventPrefix(type: string) {
  switch (type) {
    case "token": return "[token]";
    case "reasoning": return "[think]";
    case "tool_calls": return "[tool]";
    case "tool_result": return "[result]";
    case "ToolExecutionStarted": return "[start]";
    case "ToolExecutionCompleted": return "[end]";
    case "ToolProgress": return "[progress]";
    case "approval:required": return "[approve]";
    case "metrics": return "[metrics]";
    case "done": return "[done]";
    case "error": return "[error]";
    case "mode": return "[mode]";
    case "pipeline:start": return "[start]";
    default: return `[${type}]`;
  }
}

function getEventColor(type: string) {
  switch (type) {
    case "token": return "text-neutral-400";
    case "reasoning": return "text-amber-400/70 italic";
    case "tool_calls":
    case "ToolExecutionStarted":
    case "ToolExecutionCompleted":
    case "ToolProgress":
    case "tool_result": return "text-emerald-400";
    case "approval:required": return "text-amber-400";
    case "error": return "text-red-400";
    case "done": return "text-emerald-400 font-semibold";
    case "metrics": return "text-blue-400";
    default: return "text-neutral-500";
  }
}
