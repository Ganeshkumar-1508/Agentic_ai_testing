"use client";

/**
 * ActivityItem — render a single event in the activity feed.
 *
 * Visual key:
 *   - subagent.heartbeat  → zinc (low signal, dimmed)
 *   - subagent.spawned    → blue
 *   - subagent.completed  → emerald/red (status-dependent)
 *   - kg.refreshed        → emerald
 *   - kg.refreshed.failed → red
 *   - board.completed     → emerald
 *   - board.failed        → red
 *   - team.created        → violet
 *   - team.dissolved      → zinc (soft)
 *   - job.cancelled       → red
 *   - job.paused          → amber
 *
 * The summary is built from the payload via small per-type
 * formatters so the feed reads like a log, not a JSON dump.
 */

import { motion } from "framer-motion";
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronUp,
  CircleDot,
  Cpu,
  Gauge,
  GitMerge,
  Hammer,
  Network,
  Pause,
  ShieldAlert,
  Sparkles,
  Square,
  StopCircle,
  Users,
  Wrench,
  XCircle,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ActivityEvent } from "@/lib/hooks/use-activity-feed";

interface ActivityItemProps {
  event: ActivityEvent;
  highlight?: boolean;
}

type VisualTone = "neutral" | "info" | "success" | "warn" | "danger" | "accent" | "muted";

interface Visual {
  Icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  tone: VisualTone;
  label: string;
  summary: (payload: Record<string, unknown>) => string;
}

const VISUALS: Record<string, Visual> = {
  "subagent.heartbeat": {
    Icon: Activity,
    tone: "muted",
    label: "Heartbeat",
    summary: (p) =>
      typeof p.current_tool === "string" && p.current_tool.length > 0
        ? `${truncate(p.current_tool, 40)} (${p.api_call_count ?? 0} calls)`
        : `${p.api_call_count ?? 0} API calls`,
  },
  "subagent.spawned": {
    Icon: Bot,
    tone: "info",
    label: "Subagent spawned",
    summary: (p) => {
      const role = typeof p.role === "string" ? p.role : "agent";
      const goal = typeof p.goal === "string" ? truncate(p.goal, 80) : "";
      return goal ? `${role}: ${goal}` : role;
    },
  },
  "subagent.completed": {
    Icon: CheckCircle2,
    tone: "success",
    label: "Subagent completed",
    summary: (p) => {
      const status = (p.status as string) || "ok";
      const goal = typeof p.goal === "string" ? truncate(p.goal, 60) : "";
      const dur = formatDuration(p.duration_sec);
      const cost = formatCost(p.cost_usd);
      return `${status.toUpperCase()} · ${dur} · ${cost}${goal ? ` · ${goal}` : ""}`;
    },
  },
  "kg.refreshed": {
    Icon: Network,
    tone: "accent",
    label: "KG refreshed",
    summary: (p) => {
      const delta = (p.delta && typeof p.delta === "object"
        ? (p.delta as Record<string, unknown>).added
        : 0) as number;
      return `${p.nodeCount ?? 0} nodes · ${p.edgeCount ?? 0} edges · +${delta ?? 0} new · ${p.duration_ms ?? 0}ms`;
    },
  },
  "kg.refreshed.failed": {
    Icon: XCircle,
    tone: "danger",
    label: "KG refresh failed",
    summary: (p) => truncate(String(p.error || p.reason || "unknown"), 100),
  },
  "board.completed": {
    Icon: GitMerge,
    tone: "success",
    label: "Board completed",
    summary: (p) => `board ${truncate(String(p.board_id || ""), 30)}`,
  },
  "board.failed": {
    Icon: XCircle,
    tone: "danger",
    label: "Board failed",
    summary: (p) =>
      `board ${truncate(String(p.board_id || ""), 30)}${p.error ? ` · ${truncate(String(p.error), 60)}` : ""}`,
  },
  "team.created": {
    Icon: Users,
    tone: "info",
    label: "Team created",
    summary: (p) => truncate(String(p.name || p.team_id || ""), 60),
  },
  "team.dissolved": {
    Icon: Users,
    tone: "muted",
    label: "Team dissolved",
    summary: (p) => truncate(String(p.team_id || ""), 60),
  },
  "job.cancelled": {
    Icon: StopCircle,
    tone: "danger",
    label: "Job cancelled",
    summary: (p) => truncate(String(p.spec_id || ""), 60),
  },
  "job.paused": {
    Icon: Pause,
    tone: "warn",
    label: "Job paused",
    summary: (p) => truncate(String(p.spec_id || ""), 60),
  },
  "budget.throttled": {
    Icon: Gauge,
    tone: "warn",
    label: "Budget throttled",
    summary: (p) => {
      const prev = (p.prev_step as number) ?? 0;
      const next = (p.new_step as number) ?? 0;
      const spent = formatCost(p.spent_usd);
      const side: string[] = [];
      if (next >= 1) side.push("HITL");
      if (next >= 2) side.push("sequential");
      if (next >= 3) side.push("cheaper model");
      if (next >= 4) side.push("pause");
      return `step ${prev} → ${next} · ${spent}${side.length ? ` · ${side.join(" + ")}` : ""}`;
    },
  },
  "agent.started": {
    Icon: CircleDot,
    tone: "info",
    label: "Agent started",
    summary: (p) => `${truncate(String(p.model || "model"), 40)} · ${truncate(String(p.input || ""), 60)}`,
  },
  "agent.completed": {
    Icon: CheckCircle2,
    tone: "success",
    label: "Agent completed",
    summary: (p) => `${p.rounds ?? 0} rounds · ${truncate(String(p.output_preview || ""), 70)}`,
  },
  "round.started": {
    Icon: Square,
    tone: "muted",
    label: "Round started",
    summary: (p) => `round ${p.round ?? "?"} · ${p.message_count ?? 0} msgs`,
  },
  "round.completed": {
    Icon: CheckCircle2,
    tone: "muted",
    label: "Round completed",
    summary: (p) => `round ${p.round ?? "?"} · ${p.tool_calls ?? 0} tool calls`,
  },
  "llmcall.started": {
    Icon: Cpu,
    tone: "info",
    label: "LLM call",
    summary: (p) => `${truncate(String(p.model || "model"), 30)} · round ${p.round ?? "?"}`,
  },
  "llmcall.completed": {
    Icon: Cpu,
    tone: "muted",
    label: "LLM returned",
    summary: (p) => {
      const total = (p.total_tokens as number) ?? 0;
      const prompt = (p.prompt_tokens as number) ?? 0;
      const comp = (p.completion_tokens as number) ?? 0;
      return `${total} tok (${prompt} in / ${comp} out) · round ${p.round ?? "?"}`;
    },
  },
  "tool.execution.started": {
    Icon: Wrench,
    tone: "info",
    label: "Tool call",
    summary: (p) => {
      const name = String(p.tool_name || "tool");
      const input = typeof p.tool_input === "string" ? truncate(p.tool_input, 80) : "";
      return input ? `${name}(${input})` : name;
    },
  },
  "tool.execution.completed": {
    Icon: Hammer,
    tone: "muted",
    label: "Tool result",
    summary: (p) => {
      const name = String(p.tool_name || "tool");
      const preview = typeof p.output_preview === "string" ? truncate(p.output_preview, 80) : "";
      const err = p.is_error ? " · ERROR" : "";
      return `${name}${err}${preview ? ` · ${preview}` : ""}`;
    },
  },
  "toolprogress": {
    Icon: Activity,
    tone: "muted",
    label: "Tool progress",
    summary: (p) => `${p.tool_name || "tool"} · ${truncate(String(p.content || ""), 70)}`,
  },
  "token.generated": {
    Icon: Zap,
    tone: "muted",
    label: "Token",
    summary: (p) => truncate(String(p.content || ""), 90),
  },
  "reasoning.generated": {
    Icon: Sparkles,
    tone: "accent",
    label: "Reasoning",
    summary: (p) => truncate(String(p.content || ""), 90),
  },
  "approval.required": {
    Icon: ShieldAlert,
    tone: "warn",
    label: "Approval needed",
    summary: (p) => `${p.tool_name || "tool"} · ${truncate(String(p.tool_args || ""), 70)}`,
  },
  "reflexion.injected": {
    Icon: Sparkles,
    tone: "accent",
    label: "Reflexion",
    summary: (p) => `round ${p.round ?? "?"} · ${p.tool_count ?? 0} tools · ${p.reflection_count ?? 0} reflections`,
  },
  "error": {
    Icon: XCircle,
    tone: "danger",
    label: "Error",
    summary: (p) => truncate(String(p.message || ""), 100),
  },
  "status": {
    Icon: ChevronUp,
    tone: "muted",
    label: "Status",
    summary: (p) => truncate(String(p.message || ""), 100),
  },
};

const TONE_CLASSES: Record<VisualTone, { dot: string; icon: string; label: string }> = {
  neutral: { dot: "bg-zinc-400", icon: "text-zinc-300", label: "text-zinc-300" },
  info: { dot: "bg-emerald-400/70", icon: "text-emerald-400/80", label: "text-emerald-300/80" },
  success: { dot: "bg-emerald-400", icon: "text-emerald-400", label: "text-emerald-300" },
  warn: { dot: "bg-amber-400", icon: "text-amber-400", label: "text-amber-300" },
  danger: { dot: "bg-red-400", icon: "text-red-400", label: "text-red-300" },
  accent: { dot: "bg-emerald-400", icon: "text-emerald-400", label: "text-emerald-300" },
  muted: { dot: "bg-zinc-700", icon: "text-zinc-500", label: "text-zinc-500" },
};

function toneClassBg(tone: VisualTone): string {
  switch (tone) {
    case "info":
      return "bg-emerald-500/10";
    case "success":
      return "bg-emerald-500/10";
    case "warn":
      return "bg-amber-500/10";
    case "danger":
      return "bg-red-500/10";
    case "accent":
      return "bg-emerald-500/10";
    default:
      return "bg-white/[0.04]";
  }
}

const FALLBACK: Visual = {
  Icon: Zap,
  tone: "neutral",
  label: "Event",
  summary: (p) => {
    const summary = p.summary || p.message || p.title;
    if (typeof summary === "string") return truncate(summary, 80);
    return Object.keys(p).length > 0 ? `payload: ${truncate(JSON.stringify(p), 80)}` : "(no payload)";
  },
};

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function formatDuration(raw: unknown): string {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n < 60) return `${n.toFixed(1)}s`;
  const m = Math.floor(n / 60);
  const s = Math.floor(n % 60);
  if (m < 60) return `${m}m${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h${m % 60}m`;
}

function formatCost(raw: unknown): string {
  const n = Number(raw);
  if (!Number.isFinite(n)) return "—";
  if (n < 0.01) return `$${(n * 1000).toFixed(2)}m`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

export function ActivityItem({ event, highlight }: ActivityItemProps) {
  const visual = VISUALS[event.type] || {
    ...FALLBACK,
    label: event.type,
  };
  const tone = TONE_CLASSES[visual.tone];
  const Icon = visual.Icon;
  const summary = visual.summary(event.payload);
  const isHeartbeat = event.type === "subagent.heartbeat";
  const eventSessionId =
    (event.payload as Record<string, unknown>)?.session_id as string | undefined;
  const isTool = event.type === "ToolExecutionStarted" || event.type === "tool.execution.started";
  const isToolDone = event.type === "ToolExecutionCompleted" || event.type === "tool.execution.completed";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -2 }}
      animate={{ opacity: isHeartbeat ? 0.5 : 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 24 }}
      className={cn(
        "group relative flex items-start gap-3 px-3 py-2.5 border-b border-white/[0.04] last:border-0 transition-colors",
        isTool
          ? "bg-emerald-500/[0.025] hover:bg-emerald-500/[0.05]"
          : isToolDone
            ? "hover:bg-white/[0.025]"
            : highlight
              ? "bg-emerald-500/[0.04]"
              : "hover:bg-white/[0.02]",
      )}
    >
      {isTool && (
        <motion.span
          aria-hidden
          className="absolute left-0 top-0 bottom-0 w-[2px] bg-emerald-400/40"
          initial={{ scaleY: 0 }}
          animate={{ scaleY: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 22 }}
          style={{ originY: 0.5 }}
        />
      )}
      <div
        className={cn(
          "w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
          visual.tone === "muted" ? "bg-white/[0.03]" : toneClassBg(visual.tone),
        )}
      >
        <Icon className={cn("w-3.5 h-3.5", tone.icon)} strokeWidth={1.5} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn("text-[12px] font-semibold tracking-tight", tone.label)}>
            {visual.label}
          </span>
          <span className="text-[10px] font-mono text-zinc-700 tabular-nums">
            {formatTime(event.timestamp)}
          </span>
          {eventSessionId && eventSessionId !== "_anon" && (
            <a
              href={`/activity?session=${encodeURIComponent(eventSessionId)}`}
              onClick={(e) => e.stopPropagation()}
              className="text-[9px] font-mono text-zinc-600 hover:text-emerald-400 truncate max-w-[140px] transition-colors"
              title={`Follow ${eventSessionId}`}
            >
              {eventSessionId}
            </a>
          )}
        </div>
        <div className="text-[12px] text-zinc-400 font-mono truncate mt-0.5" title={summary}>
          {summary}
        </div>
      </div>

      {highlight ? (
        <motion.span
          initial={{ opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 220, damping: 16 }}
          className="text-emerald-400/80"
        >
          <Sparkles className="w-3 h-3 mt-2" strokeWidth={1.5} />
        </motion.span>
      ) : null}
    </motion.div>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-US", { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}
