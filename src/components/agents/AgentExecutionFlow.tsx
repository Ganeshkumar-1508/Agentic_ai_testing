"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  FileSearch,
  GitBranch,
  Code2,
  Database,
  PlayCircle,
  FileText,
  ChevronDown,
  ChevronRight,
  Terminal,
  Sparkles,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentExecutionDetail, ToolState } from "@/lib/types/pipeline";
import { AgentOutput } from "@/components/shared/MarkdownRenderer";
import { ReasoningBlock } from "@/components/shared/ReasoningBlock";
import { ToolCallCard } from "@/components/shared/ToolCallCard";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useState, useRef, useEffect } from "react";

// ─── Agent Config ───────────────────────────────────────────────────────────

const AGENT_VISUALS: Record<string, { label: string; icon: LucideIcon; color: string }> = {
  research: { label: "Research Agent", icon: FileSearch, color: "emerald" },
  env_setup: { label: "Environment Setup", icon: Database, color: "cyan" },
  requirements_analyst: { label: "Requirements Analyst", icon: FileSearch, color: "emerald" },
  task_decomposer: { label: "Task Decomposer", icon: GitBranch, color: "cyan" },
  test_generator: { label: "Test Generator", icon: Code2, color: "violet" },
  test_data_generator: { label: "Test Data Generator", icon: Database, color: "orange" },
  test_runner: { label: "Test Runner", icon: PlayCircle, color: "amber" },
  reporter: { label: "Reporter", icon: FileText, color: "rose" },
};

const COLOR_CLASSES: Record<string, { text: string; bg: string; border: string; pulse: string; glow: string }> = {
  emerald: { text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-l-emerald-400/30", pulse: "before:bg-emerald-400/20", glow: "" },
  cyan: { text: "text-zinc-400", bg: "bg-zinc-500/10", border: "border-l-zinc-400/30", pulse: "before:bg-zinc-400/20", glow: "" },
  violet: { text: "text-zinc-400", bg: "bg-zinc-500/10", border: "border-l-zinc-400/30", pulse: "before:bg-zinc-400/20", glow: "" },
  orange: { text: "text-zinc-400", bg: "bg-zinc-500/10", border: "border-l-zinc-400/30", pulse: "before:bg-zinc-400/20", glow: "" },
  amber: { text: "text-amber-400", bg: "bg-amber-500/10", border: "border-l-amber-400/30", pulse: "before:bg-amber-400/20", glow: "" },
  rose: { text: "text-rose-400", bg: "bg-rose-500/10", border: "border-l-rose-400/30", pulse: "before:bg-rose-400/20", glow: "" },
};

function getColors(color: string) {
  return COLOR_CLASSES[color] ?? COLOR_CLASSES.emerald;
}

// ─── Stagger ────────────────────────────────────────────────────────────────

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.15 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 100, damping: 20 } },
};

// ─── Utility ────────────────────────────────────────────────────────────────

function formatTime(ts?: number | string) {
  if (ts == null) return "—";
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return "—";
  }
}

// ─── Props ──────────────────────────────────────────────────────────────────

interface AgentExecutionFlowProps {
  agents: AgentExecutionDetail[];
}

// ─── Token Stream (auto-scrolling terminal) ─────────────────────────────────

function TokenStream({ lines }: { lines: string[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [lines.length]);

  if (lines.length === 0) return null;

  return (
    <Collapsible>
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition-colors group mt-3">
        <Terminal className="w-3.5 h-3.5" strokeWidth={1.5} />
        LLM Stream
        <span className="text-neutral-600 ml-1">({lines.length} tokens)</span>
        <ChevronDown className="w-3 h-3 group-data-[state=open]:rotate-180 transition-transform ml-auto" strokeWidth={1.5} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 bg-black/40 rounded-xl p-3 max-h-32 overflow-auto font-mono text-[11px] leading-relaxed text-emerald-400/70">
          {lines.map((line, i) => (
            <span key={i}>{line}</span>
          ))}
          <div ref={endRef} />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}



// ─── Tool Calls List ────────────────────────────────────────────────────────

function ToolCallsList({ tools }: { tools: ToolState[] }) {
  if (tools.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {tools.map((tool, i) => (
        <ToolCallCard
          key={tool.name + i}
          name={tool.name}
          status={tool.status as "running" | "completed" | "error" | "pending"}
          result={tool.output}
          durationMs={tool.endTime && tool.startTime ? tool.endTime - tool.startTime : undefined}
          args={tool.args || undefined}
        />
      ))}
    </div>
  );
}

// ─── Agent Execution Card ────────────────────────────────────────────────────

interface AgentExecutionCardProps {
  agent: AgentExecutionDetail;
  isLast: boolean;
}

function AgentExecutionCard({ agent, isLast }: AgentExecutionCardProps) {
  const visual = AGENT_VISUALS[agent.type] ?? { label: agent.name, icon: Sparkles, color: "emerald" };
  const Icon = visual.icon;
  const colors = getColors(visual.color);
  const isRunning = agent.status === "running";
  const isCompleted = agent.status === "completed";
  const isFailed = agent.status === "failed";
  const [outputOpen, setOutputOpen] = useState(false);

  return (
    <motion.div layout variants={cardVariants} className="relative">
      {/* Card */}
      <div className={cn(
        "relative bg-surface border border-white/[0.05] rounded-[1.5rem] p-5 transition-all",
        isRunning && cn("border-l-[3px]", colors.border, colors.pulse, "before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:animate-pulse"),
        isCompleted && "border-l-emerald-400/20",
        isFailed && "border-l-red-400/30",
      )}>
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0", colors.bg)}>
              <Icon className={cn("w-5 h-5", colors.text)} strokeWidth={1.5} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-neutral-100">{visual.label}</h3>
                <StatusBadge status={agent.status} />
              </div>
              {agent.currentTask && isRunning && (
                <p className="text-xs text-neutral-500 mt-0.5">{agent.currentTask}</p>
              )}
              {agent.currentTool && isRunning && (
                <p className="text-xs text-emerald-400/70 font-mono mt-0.5 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />
                  {agent.currentTool}
                </p>
              )}
            </div>
          </div>
          <span className="text-[10px] text-neutral-600 font-mono shrink-0">
            {agent.startedAt && formatTime(agent.startedAt)}
          </span>
        </div>

        {/* Progress (running only) */}
        {isRunning && (
          <div className="w-full h-1 bg-white/[0.05] rounded-full overflow-hidden mb-4">
            <motion.div
              className="h-full bg-emerald-500 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${agent.progress}%` }}
              transition={{ type: "spring", stiffness: 80, damping: 15 }}
            />
          </div>
        )}

        {/* Reasoning */}
        {agent.reasoning.length > 0 && (
          <ReasoningBlock
            content={agent.reasoning.join("\n")}
            isStreaming={isRunning}
            startedAt={agent.startedAt ? new Date(agent.startedAt).getTime() : undefined}
            completedAt={agent.endedAt ? new Date(agent.endedAt).getTime() : undefined}
          />
        )}

        {/* Token Stream */}
        {agent.streamOutput.length > 0 && (
          <TokenStream lines={agent.streamOutput} />
        )}

        {/* Tool Calls */}
        {agent.toolCalls.length > 0 && (
          <ToolCallsList tools={agent.toolCalls} />
        )}

        {/* Error */}
        {isFailed && agent.error && (
          <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-xl p-3">
            <p className="text-xs text-red-400">{agent.error}</p>
          </div>
        )}

        {/* Output (completed only) */}
        {(isCompleted && agent.output != null) && (
          <div className={cn("mt-3 bg-black/20 rounded-xl overflow-hidden border border-white/[0.05]", outputOpen ? "p-4" : "p-3")}>
            <button onClick={() => setOutputOpen(!outputOpen)} className="flex items-center gap-1 text-[10px] text-neutral-500 hover:text-neutral-400 transition-colors w-full">
              {outputOpen ? <ChevronDown className="w-3 h-3" strokeWidth={1.5} /> : <ChevronRight className="w-3 h-3" strokeWidth={1.5} />}
              Output
              {!outputOpen && <span className="text-neutral-600 ml-1">({typeof agent.output === "string" ? (agent.output as string).slice(0, 60) : "..."})</span>}
            </button>
            {outputOpen && (
              <AgentOutput output={agent.output as any} />
            )}
          </div>
        )}
      </div>

      {/* Connecting line */}
      {!isLast && (
        <div className="flex justify-center py-3">
          <div className="flex flex-col items-center gap-1">
            <div className="w-[2px] h-5 bg-white/[0.05]" />
            <div className="w-1.5 h-1.5 rounded-full bg-white/[0.08]" />
            <div className="w-[2px] h-5 bg-white/[0.05]" />
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ─── Status Badge ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; className: string }> = {
    running: { label: "Running", className: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" },
    completed: { label: "Done", className: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5" },
    failed: { label: "Failed", className: "text-red-400 border-red-500/30 bg-red-500/10" },
    pending: { label: "Pending", className: "text-neutral-500 border-white/[0.08] bg-white/[0.03]" },
  };
  const c = config[status] ?? config.pending;
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border", c.className)}>
      {status === "running" && <Loader2 className="w-2.5 h-2.5 animate-spin" strokeWidth={2.5} />}
      {c.label}
    </span>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────

export function AgentExecutionFlow({ agents }: AgentExecutionFlowProps) {
  if (agents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Sparkles className="w-10 h-10 text-neutral-600 mb-3" strokeWidth={1.2} />
        <p className="text-sm text-neutral-500">No agents to display</p>
      </div>
    );
  }

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-col"
    >
      <AnimatePresence mode="popLayout">
        {agents.map((agent, index) => (
          <AgentExecutionCard
            key={agent.id}
            agent={agent}
            isLast={index === agents.length - 1}
          />
        ))}
      </AnimatePresence>
    </motion.div>
  );
}
