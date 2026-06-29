"use client";

import { useState, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  List,
  Brain,
  Terminal,
  AlertCircle,
  MessageSquare,
  CheckCircle,
  XCircle,
  Clock,
  ChevronRight,
  ChevronDown,
  FileSearch,
  Code2,
  Beaker,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TraceEvent, RunStatus } from "@/lib/hooks/use-trace-events";

interface TraceWaterfallProps {
  events: TraceEvent[];
  status: RunStatus;
  selectedEventId: string | null;
  onSelectEvent: (id: string | null) => void;
  className?: string;
}

interface DisplayRow {
  id: string;
  eventType: string;
  name: string;
  depth: number;
  status: "running" | "completed" | "failed";
  duration: number | null;
  tokens: number | null;
  cost: number | null;
  data: Record<string, unknown>;
  parentId: string;
  pipelineStep: string;
  startTime: string;
  isEndEvent: boolean;
}

const STEP_LABELS: Record<string, string> = {
  full_workflow: "Workflow",
  ci_pipeline: "CI Pipeline",
};

const EVENT_ICONS: Record<string, typeof Bot> = {
  "agent.started": Bot,
  "agent.completed": CheckCircle,
  "round.started": List,
  "round.completed": CheckCircle,
  "llmcall.started": Brain,
  "llmcall.completed": CheckCircle,
  "ToolExecutionStarted": Terminal,
  "ToolExecutionCompleted": CheckCircle,
  "tool:error": AlertCircle,
  reasoning: MessageSquare,
};

const EVENT_NAMES: Record<string, string> = {
  "agent.started": "Agent Start",
  "agent.completed": "Agent Complete",
  "round.started": "Round",
  "round.completed": "Round Complete",
  "llmcall.started": "LLM Call",
  "llmcall.completed": "LLM Call Complete",
  "ToolExecutionStarted": "Tool Call",
  "ToolExecutionCompleted": "Tool Complete",
  "tool:error": "Tool Failed",
  reasoning: "Reasoning",
};

function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function formatTokens(n: number | null): string {
  if (n === null) return "";
  if (n < 1000) return `${n}t`;
  return `${(n / 1000).toFixed(1)}kt`;
}

function formatCost(n: number | null): string {
  if (n === null) return "";
  return `$${n.toFixed(2)}`;
}

function getToolName(data: Record<string, unknown>): string {
  return (data.name as string) || (data.toolName as string) || "";
}

function getEventName(event: TraceEvent): string {
  const base = EVENT_NAMES[event.eventType] || event.eventType;
  if (event.eventType === "ToolExecutionStarted" || event.eventType === "ToolExecutionCompleted") {
    const toolName = getToolName(event.eventData);
    return toolName || base;
  }
  if (event.eventType === "round.started") {
    const round = event.eventData.round;
    return round !== undefined ? `Round ${Number(round) + 1}` : base;
  }
  if (event.eventType === "llmcall.started") {
    const model = event.eventData.model as string;
    return model ? `LLM: ${model}` : base;
  }
  if (event.eventType === "agent.started") {
    const input = event.eventData.input as string;
    return input ? `Agent: ${input.slice(0, 60)}` : base;
  }
  return base;
}

function processEvents(events: TraceEvent[]): {
  rows: DisplayRow[];
  steps: string[];
} {
  const startEvents = new Map<string, TraceEvent>();
  const endData = new Map<string, { duration?: number; tokens?: number; cost?: number; status?: string }>();

  for (const e of events) {
    if (e.eventType.endsWith(":start") || e.eventType === "reasoning" || e.eventType === "tool:error") {
      startEvents.set(e.id, e);
    } else if (e.eventType.endsWith(":end") || e.eventType === "tool:error") {
      const baseType = e.eventType.replace(/:end$/, ":start");
      const pairingId = e.parentId;
      for (const [id, se] of startEvents) {
        if (se.eventType === baseType && se.parentId === pairingId && !endData.has(id)) {
          const d = e.eventData;
          endData.set(id, {
            duration: (d.timestamp as number)
              ? ((d.timestamp as number) - (se.eventData.timestamp as number || 0)) * 1000
              : undefined,
            tokens: (d.total_tokens as number) || (d.completion_tokens as number) || undefined,
            cost: (d.cost as number) || undefined,
            status: d.success === false ? "failed" : "completed",
          });
          break;
        }
      }
    }
  }

  const stepMap = new Map<string, DisplayRow[]>();
  const stepOrder: string[] = [];

  const depthMap = new Map<string, number>();
  for (const e of events) {
    if (!e.parentId) {
      depthMap.set(e.id, 0);
    }
  }
  for (const e of events) {
    if (e.parentId && depthMap.has(e.parentId)) {
      depthMap.set(e.id, depthMap.get(e.parentId)! + 1);
    }
  }
  for (const e of events) {
    if (e.parentId) {
      const parentDepth = depthMap.get(e.parentId);
      if (parentDepth !== undefined) {
        depthMap.set(e.id, parentDepth + 1);
      }
    }
  }

  for (const e of events) {
    if (e.eventType.endsWith(":end") && e.eventType !== "tool:error") continue;

    const step = (e.eventData.pipeline_step as string) || "default";
    if (!stepMap.has(step)) {
      stepMap.set(step, []);
      stepOrder.push(step);
    }

    const endInfo = endData.get(e.id);
    const isEndEvent = e.eventType.endsWith(":end") || false;

    const row: DisplayRow = {
      id: e.id,
      eventType: e.eventType,
      name: getEventName(e),
      depth: depthMap.get(e.id) ?? 0,
      status: e.eventType === "tool:error" ? "failed" : (endInfo?.status as "running" | "completed" | "failed") ?? "running",
      duration: endInfo?.duration ?? null,
      tokens: endInfo?.tokens ?? null,
      cost: endInfo?.cost ?? null,
      data: e.eventData,
      parentId: e.parentId,
      pipelineStep: step,
      startTime: e.createdAt,
      isEndEvent,
    };

    stepMap.get(step)!.push(row);
  }

  return { rows: Array.from(stepMap.values()).flat(), steps: stepOrder };
}

function getStepTokens(rows: DisplayRow[]): number {
  return rows.reduce((sum, r) => sum + (r.tokens || 0), 0);
}

function getStepDuration(rows: DisplayRow[]): number {
  let max = 0;
  for (const r of rows) {
    if (r.duration && r.duration > max) max = r.duration;
  }
  return max;
}

function getStepCost(rows: DisplayRow[]): number {
  return rows.reduce((sum, r) => sum + (r.cost || 0), 0);
}

function WaterfallRowSkeleton() {
  return (
    <div className="flex items-center gap-3 py-2.5 px-4">
      <div className="w-4 h-4 rounded-full shimmer-bg" />
      <div className="h-3.5 w-48 bg-white/[0.04] rounded animate-pulse" />
      <div className="ml-auto flex items-center gap-4">
        <div className="h-3 w-12 bg-white/[0.04] rounded animate-pulse" />
        <div className="h-3 w-10 bg-white/[0.04] rounded animate-pulse" />
      </div>
    </div>
  );
}

function getEventColor(eventType: string, depth: number): string {
  if (depth === 0) return "text-emerald-400";
  if (depth === 1) return "text-neutral-300";
  if (eventType.startsWith("llm:")) return "text-zinc-400";
  if (eventType.startsWith("tool:")) return "text-amber-400";
  return "text-neutral-400";
}

function getStatusDotColor(status: string): string {
  switch (status) {
    case "running": return "bg-amber-400";
    case "completed": return "bg-emerald-400";
    case "failed": return "bg-red-400";
    default: return "bg-neutral-500";
  }
}

export function TraceWaterfall({
  events,
  status,
  selectedEventId,
  onSelectEvent,
  className,
}: TraceWaterfallProps) {
  const [collapsedSteps, setCollapsedSteps] = useState<Set<string>>(new Set());

  const { rows, steps } = useMemo(() => processEvents(events), [events]);

  const toggleStep = useCallback((step: string) => {
    setCollapsedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(step)) next.delete(step);
      else next.add(step);
      return next;
    });
  }, []);

  if (status === "loading" || status === "idle") {
    return (
      <div className={cn("space-y-1", className)}>
        {Array.from({ length: 6 }).map((_, i) => (
          <WaterfallRowSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className={cn("flex flex-col items-center justify-center py-16 px-6 text-center", className)}>
        <AlertCircle className="w-10 h-10 text-red-400/60 mb-3" strokeWidth={1.5} />
        <p className="text-sm text-neutral-500">Failed to load trace events</p>
      </div>
    );
  }

  if (rows.length === 0 && (status === "completed" || status === "streaming")) {
    return (
      <div className={cn("flex flex-col items-center justify-center py-16 px-6 text-center", className)}>
        <Bot className="w-10 h-10 text-neutral-600 mb-3" strokeWidth={1.2} />
        <p className="text-sm text-neutral-500 mb-1">No trace events yet</p>
        <p className="text-xs text-neutral-600">Waiting for pipeline to emit events...</p>
      </div>
    );
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.04, delayChildren: 0.1 },
    },
  };

  const rowVariants = {
    hidden: { opacity: 0, y: 12, filter: "blur(2px)" },
    visible: {
      opacity: 1,
      y: 0,
      filter: "blur(0px)",
      transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const },
    },
  };

  return (
    <motion.div
      className={cn("", className)}
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {steps.map((step) => {
        const stepRows = rows.filter((r) => r.pipelineStep === step);
        const isCollapsed = collapsedSteps.has(step);
        const stepTokens = getStepTokens(stepRows);
        const stepDuration = getStepDuration(stepRows);
        const stepCost = getStepCost(stepRows);

        return (
          <div key={step} className="border-t border-white/[0.06] first:border-t-0">
            <button
              type="button"
              onClick={() => toggleStep(step)}
              className="flex items-center gap-2 w-full px-4 py-2.5 hover:bg-white/[0.02] transition-colors group"
            >
              {isCollapsed ? (
                <ChevronRight className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />
              )}
              <span className="text-xs font-mono font-medium text-neutral-300 uppercase tracking-wider">
                {STEP_LABELS[step] || step}
              </span>
              <span className="text-[10px] text-neutral-600 font-mono ml-2">
                {formatDuration(stepDuration)}
              </span>
              <span className="text-[10px] text-neutral-600 font-mono">
                {formatTokens(stepTokens)}
              </span>
              {stepCost > 0 && (
                <span className="text-[10px] text-neutral-600 font-mono">
                  {formatCost(stepCost)}
                </span>
              )}
            </button>

            <AnimatePresence initial={false}>
              {!isCollapsed && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] as const }}
                >
                  {stepRows.map((row) => {
                    const isSelected = row.id === selectedEventId;
                    const Icon = EVENT_ICONS[row.eventType] || Terminal;
                    const color = getEventColor(row.eventType, row.depth);

                    return (
                      <motion.button
                        key={row.id}
                        type="button"
                        variants={rowVariants}
                        onClick={() => onSelectEvent(isSelected ? null : row.id)}
                        className={cn(
                          "flex items-center gap-3 w-full text-left px-4 py-2 transition-all duration-200",
                          isSelected
                            ? "bg-white/[0.04]"
                            : "hover:bg-white/[0.02] active:bg-white/[0.03]",
                        )}
                        style={{ paddingLeft: `${16 + row.depth * 20}px` }}
                      >
                        <span className="relative flex items-center justify-center shrink-0">
                          {row.status === "running" && !row.isEndEvent ? (
                            <span className="relative flex w-3.5 h-3.5">
                              <span className="absolute inset-0 rounded-full bg-amber-400/30 animate-ping" />
                              <span className="relative w-3.5 h-3.5 rounded-full bg-amber-400" />
                            </span>
                          ) : (
                            <Icon
                              className={cn("w-3.5 h-3.5", color)}
                              strokeWidth={1.5}
                            />
                          )}
                        </span>

                        <span className="text-xs text-neutral-300 truncate min-w-0 flex-1 font-medium">
                          {row.name}
                        </span>

                        <span className="flex items-center gap-3 shrink-0">
                          {row.duration !== null && (
                            <span className="text-[11px] text-neutral-500 font-mono tabular-nums w-12 text-right">
                              {formatDuration(row.duration)}
                            </span>
                          )}
                          {row.tokens !== null && (
                            <span className="text-[11px] text-neutral-500 font-mono tabular-nums w-12 text-right">
                              {formatTokens(row.tokens)}
                            </span>
                          )}
                          {row.cost !== null && (
                            <span className="text-[11px] text-neutral-500 font-mono tabular-nums w-12 text-right">
                              {formatCost(row.cost)}
                            </span>
                          )}
                          {row.status === "failed" && (
                            <XCircle className="w-3 h-3 text-red-400" strokeWidth={1.5} />
                          )}
                          {row.status === "completed" && !row.isEndEvent && (
                            <CheckCircle className="w-3 h-3 text-emerald-400/50" strokeWidth={1.5} />
                          )}
                        </span>
                      </motion.button>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}

      {status === "streaming" && rows.length > 0 && (
        <div className="flex items-center justify-center gap-2 py-4 text-[11px] text-neutral-600 font-mono">
          <span className="relative flex w-2 h-2">
            <span className="absolute inset-0 rounded-full bg-emerald-400/40 animate-ping" />
            <span className="relative w-2 h-2 rounded-full bg-emerald-400" />
          </span>
          Streaming events...
        </div>
      )}
    </motion.div>
  );
}
