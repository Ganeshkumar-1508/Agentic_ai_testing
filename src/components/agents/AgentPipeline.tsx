"use client";

import { motion } from "framer-motion";
import {
  FileSearch,
  GitBranch,
  Code2,
  Database,
  PlayCircle,
  FileText,
  ChevronDown,
  type LucideIcon,
} from "lucide-react";
import { AgentBadge } from "@/components/shared/AgentBadge";
import { AgentOutput } from "@/components/shared/MarkdownRenderer";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { AgentState } from "@/lib/types/workflow";
import { useState } from "react";

// ─── Agent Config ───────────────────────────────────────────────────────────

const AGENT_CONFIGS: Record<
  string,
  { label: string; icon: LucideIcon; color: string }
> = {
  research: {
    label: "Research Agent",
    icon: FileSearch,
    color: "emerald",
  },
  env_setup: {
    label: "Environment Setup",
    icon: Database,
    color: "cyan",
  },
  requirements_analyst: {
    label: "Requirements Analyst",
    icon: FileSearch,
    color: "emerald",
  },
  task_decomposer: {
    label: "Task Decomposer",
    icon: GitBranch,
    color: "cyan",
  },
  test_generator: {
    label: "Test Generator",
    icon: Code2,
    color: "violet",
  },
  test_data_generator: {
    label: "Test Data Generator",
    icon: Database,
    color: "orange",
  },
  test_runner: {
    label: "Test Runner",
    icon: PlayCircle,
    color: "amber",
  },
  reporter: {
    label: "Reporter",
    icon: FileText,
    color: "rose",
  },
};

// ─── Color utilities ────────────────────────────────────────────────────────

function getColorClasses(color: string) {
  const map: Record<string, { text: string; glow: string; pulse: string; border: string; bg: string }> = {
    emerald: {
      text: "text-emerald-400",
      glow: "",
      pulse: "before:bg-emerald-400/20",
      border: "border-l-emerald-400/30",
      bg: "bg-emerald-500/10",
    },
    cyan: {
      text: "text-zinc-400",
      glow: "",
      pulse: "before:bg-zinc-400/20",
      border: "border-l-zinc-400/30",
      bg: "bg-zinc-500/10",
    },
    violet: {
      text: "text-zinc-400",
      glow: "",
      pulse: "before:bg-zinc-400/20",
      border: "border-l-zinc-400/30",
      bg: "bg-zinc-500/10",
    },
    orange: {
      text: "text-zinc-400",
      glow: "",
      pulse: "before:bg-zinc-400/20",
      border: "border-l-zinc-400/30",
      bg: "bg-zinc-500/10",
    },
    amber: {
      text: "text-amber-400",
      glow: "",
      pulse: "before:bg-amber-400/20",
      border: "border-l-amber-400/30",
      bg: "bg-amber-500/10",
    },
    rose: {
      text: "text-rose-400",
      glow: "",
      pulse: "before:bg-rose-400/20",
      border: "border-l-rose-400/30",
      bg: "bg-rose-500/10",
    },
  };
  return map[color] ?? map.emerald;
}

// ─── Stagger animation variants ─────────────────────────────────────────────

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.12 },
  },
};

const agentVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 100, damping: 20 },
  },
};

// ─── Props ──────────────────────────────────────────────────────────────────

interface AgentPipelineProps {
  agents: AgentState[];
  streamOutputs: Record<string, string[]>;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function AgentPipeline({ agents, streamOutputs }: AgentPipelineProps) {
  // If no agents yet but workflow is running, show skeleton placeholders
  const displayAgents =
    agents.length > 0
      ? agents
      : Object.entries(AGENT_CONFIGS).map(([id, config]) => ({
          id,
          name: config.label,
          type: id,
          status: "pending" as const,
          progress: 0,
          currentTask: null,
        }));

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-col"
    >
      {displayAgents.map((agent, index) => {
        const config = AGENT_CONFIGS[agent.type];
        if (!config) return null;
        const Icon = config.icon;
        const colors = getColorClasses(config.color);
        const isRunning = agent.status === "running";
        const isCompleted = agent.status === "completed";
        const isFailed = agent.status === "failed";
        const outputs = streamOutputs[agent.id] ?? [];

        // Last 4 lines of streaming output
        const snippet = outputs.slice(-4);

        return (
          <motion.div key={agent.id} variants={agentVariants} layout>
            {/* Agent Card */}
            <div
              className={cn(
                "relative bg-surface border border-white/[0.05] rounded-[1.5rem] p-5 transition-all overflow-hidden",
                isRunning &&
                  "before:absolute before:inset-y-2 before:left-0 before:w-[2px] before:rounded-full before:animate-pulse",
                isRunning && colors.pulse,
                isRunning && colors.border,
                isCompleted && "border-l-emerald-400/20",
                isFailed && "border-l-red-400/30"
              )}
            >
              {/* Header Row */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      "w-9 h-9 rounded-xl flex items-center justify-center",
                      colors.bg
                    )}
                  >
                    <Icon
                      className={cn("w-4.5 h-4.5", colors.text)}
                      strokeWidth={1.5}
                    />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-neutral-100">
                      {config.label}
                    </p>
                    {isRunning && agent.currentTask && (
                      <p className="text-xs text-neutral-500 mt-0.5">
                        {agent.currentTask}
                      </p>
                    )}
                  </div>
                </div>
                <AgentBadge status={agent.status} size="sm" />
              </div>

              {/* Progress bar (only when running) */}
              {isRunning && (
                <div className="w-full h-1 bg-white/[0.05] rounded-full overflow-hidden mb-3">
                  <motion.div
                    className="h-full bg-emerald-500 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${agent.progress}%` }}
                    transition={{
                      type: "spring",
                      stiffness: 100,
                      damping: 20,
                    }}
                  />
                </div>
              )}

              {/* Streaming snippet (only when running and has output) */}
              {isRunning && snippet.length > 0 && (
                <div className="bg-black/30 rounded-lg p-3 mb-2 max-h-[88px] overflow-hidden">
                  {snippet.map((line, i) => (
                    <p
                      key={i}
                      className="font-mono text-[11px] leading-5 text-emerald-400/80 truncate"
                    >
                      {line}
                    </p>
                  ))}
                </div>
              )}

              {/* Error message */}
              {isFailed && agent.error && (
                <p className="text-xs text-red-400 mt-2 bg-red-500/10 rounded-lg px-3 py-2">
                  {agent.error}
                </p>
              )}

              {/* View Output collapsible (on completion) */}
              {isCompleted && agent.output && (
                <Collapsible className="mt-2">
                  <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition-colors group">
                    <ChevronDown
                      className="w-3.5 h-3.5 group-data-[state=open]:rotate-180 transition-transform"
                      strokeWidth={1.5}
                    />
                    View Output
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="mt-2 bg-black/30 rounded-lg p-3 max-h-80 overflow-auto">
                      <AgentOutput output={agent.output} />
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>

            {/* Connecting line between agents */}
            {index < displayAgents.length - 1 && (
              <div className="flex justify-center py-2">
                <div className="flex flex-col items-center gap-1">
                  <div className="w-[2px] h-6 bg-white/[0.05]" />
                  <div className="w-1.5 h-1.5 rounded-full bg-white/[0.08]" />
                  <div className="w-[2px] h-6 bg-white/[0.05]" />
                </div>
              </div>
            )}
          </motion.div>
        );
      })}
    </motion.div>
  );
}

