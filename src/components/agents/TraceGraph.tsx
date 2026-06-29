"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  List,
  Brain,
  Terminal,
  AlertCircle,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TraceEvent, TraceTreeNode } from "@/lib/hooks/use-trace-events";

interface TraceGraphProps {
  tree: TraceTreeNode[];
  selectedEventId: string | null;
  onSelectEvent: (id: string | null) => void;
  className?: string;
}

const EVENT_ICONS: Record<string, typeof Bot> = {
  "agent.started": Bot,
  "round.started": List,
  "llmcall.started": Brain,
  "llmcall.completed": Brain,
  "ToolExecutionStarted": Terminal,
  "ToolExecutionCompleted": Terminal,
  "tool:error": AlertCircle,
};

function getNodeColor(eventType: string): string {
  if (eventType.startsWith("agent:")) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (eventType.startsWith("round:")) return "border-neutral-500/20 bg-white/[0.03] text-neutral-300";
  if (eventType.startsWith("llm:")) return "border-zinc-500/20 bg-zinc-500/5 text-zinc-400";
  if (eventType.startsWith("tool:")) return "border-amber-500/20 bg-amber-500/5 text-amber-400";
  return "border-white/[0.06] bg-white/[0.02] text-neutral-400";
}

function getNodeLabel(event: TraceEvent): string {
  const d = event.eventData;
  if (event.eventType === "ToolExecutionStarted" || event.eventType === "ToolExecutionCompleted") {
    return (d.name as string) || (d.toolName as string) || "Tool";
  }
  if (event.eventType === "round.started") {
    const round = d.round;
    return round !== undefined ? `Round ${Number(round) + 1}` : "Round";
  }
  if (event.eventType === "llmcall.started") {
    const model = d.model as string;
    return model ? model.split("/").pop() || "LLM" : "LLM";
  }
  if (event.eventType === "agent.started") return "Orchestrator";
  return event.eventType;
}

function getNodeSubtitle(event: TraceEvent): string {
  const d = event.eventData;
  const parts: string[] = [];
  if (d.total_tokens) parts.push(`${d.total_tokens}t`);
  else if (d.completion_tokens) parts.push(`${d.completion_tokens}t`);
  if (d.success === false) parts.push("failed");
  return parts.join(" · ");
}

function TreeNode({
  node,
  depth,
  selectedEventId,
  onSelectEvent,
}: {
  node: TraceTreeNode;
  depth: number;
  selectedEventId: string | null;
  onSelectEvent: (id: string | null) => void;
}) {
  const isSelected = node.event.id === selectedEventId;
  const Icon = EVENT_ICONS[node.event.eventType] || Bot;
  const color = getNodeColor(node.event.eventType);
  const label = getNodeLabel(node.event);
  const subtitle = getNodeSubtitle(node.event);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] as const }}
      className="flex flex-col items-center"
    >
      <button
        type="button"
        onClick={() => onSelectEvent(isSelected ? null : node.event.id)}
        className={cn(
          "flex flex-col items-center gap-1 px-4 py-2.5 rounded-xl border transition-all duration-200 min-w-[100px]",
          color,
          isSelected
            ? "ring-1 ring-emerald-400/40 scale-[1.02]"
            : "hover:scale-[1.02] active:scale-[0.98]",
        )}
      >
        <Icon className="w-4 h-4" strokeWidth={1.5} />
        <span className="text-[11px] font-medium leading-tight text-center">{label}</span>
        {subtitle && (
          <span className="text-[9px] text-neutral-500 font-mono">{subtitle}</span>
        )}
      </button>

      {node.children.length > 0 && (
        <>
          <div className="w-px h-4 bg-white/[0.08]" />
          <div className="flex items-start gap-3 relative">
            {node.children.length > 1 && (
              <div className="absolute top-0 left-[calc(50%-1px)] w-[calc(100%-24px)] h-px bg-white/[0.06]" />
            )}
            {node.children.map((child, i) => (
              <div key={child.event.id} className="flex flex-col items-center relative">
                {node.children.length > 1 && (
                  <div className={cn(
                    "absolute top-0 w-px bg-white/[0.06]",
                    i === 0 ? "left-1/2 right-0" : i === node.children.length - 1 ? "left-0 right-1/2" : "left-0 right-0",
                  )} />
                )}
                <div className="w-px h-4 bg-white/[0.08]" />
                <TreeNode
                  node={child}
                  depth={depth + 1}
                  selectedEventId={selectedEventId}
                  onSelectEvent={onSelectEvent}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </motion.div>
  );
}

export function TraceGraph({
  tree,
  selectedEventId,
  onSelectEvent,
  className,
}: TraceGraphProps) {
  if (tree.length === 0) {
    return (
      <div className={cn("flex items-center justify-center py-16 text-sm text-neutral-600", className)}>
        No trace data available
      </div>
    );
  }

  return (
    <div className={cn("overflow-x-auto py-8", className)}>
      <div className="flex justify-center min-w-[400px]">
        {tree.map((node) => (
          <TreeNode
            key={node.event.id}
            node={node}
            depth={0}
            selectedEventId={selectedEventId}
            onSelectEvent={onSelectEvent}
          />
        ))}
      </div>
    </div>
  );
}
