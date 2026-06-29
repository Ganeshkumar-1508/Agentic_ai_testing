"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Trash2, Terminal, Copy, Download, X } from "lucide-react";
import type { ConsoleLine, AgentState } from "@/lib/types/workflow";

// ─── Types ────────────────────────────────────────────────────────────────────

interface AgentConsoleMultiTabProps {
  agents: AgentState[];
  consoleLines: ConsoleLine[];
  workflowStatus: "idle" | "running" | "completed" | "failed";
}

// ─── Agent ID display names ───────────────────────────────────────────────────

const AGENT_DISPLAY_NAMES: Record<string, string> = {
  research: "Research",
  env_setup: "Setup",
  requirements_analyst: "Analyst",
  task_decomposer: "Decomposer",
  test_generator: "Generator",
  test_data_generator: "Data Gen",
  test_runner: "Runner",
  reporter: "Reporter",
};

const AGENT_COLORS: Record<string, string> = {
  research: "text-emerald-400",
  env_setup: "text-zinc-400",
  requirements_analyst: "text-emerald-400",
  task_decomposer: "text-zinc-400",
  test_generator: "text-zinc-400",
  test_data_generator: "text-zinc-400",
  test_runner: "text-amber-400",
  reporter: "text-rose-400",
};

// ─── Component ────────────────────────────────────────────────────────────────

export function AgentConsoleMultiTab({
  agents,
  consoleLines,
  workflowStatus,
}: AgentConsoleMultiTabProps) {
  const [activeTab, setActiveTab] = useState<string>("all");
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Build tab list: "All" + each unique agent
  const agentTypes = [...new Set(agents.map((a) => a.type))];
  const tabs = ["all", ...agentTypes];

  // Filter lines by active tab
  const filteredLines =
    activeTab === "all"
      ? consoleLines
      : consoleLines.filter((l) => !l.agentId || l.agentId === activeTab);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll) {
      consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [filteredLines.length, autoScroll]);

  // Handle scroll — detect if user scrolled up (pause auto-scroll)
  const handleScroll = useCallback(
    (area: HTMLDivElement | null) => {
      if (!area) return;
      const { scrollTop, scrollHeight, clientHeight } = area;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 40;
      setAutoScroll(isAtBottom);
    },
    [],
  );

  const handleCopyAll = () => {
    const text = filteredLines.map((l) => l.text).join("\n");
    navigator.clipboard.writeText(text);
  };

  const handleClear = () => {
    // Cleared by parent reset on next workflow start
  };

  const isIdle = workflowStatus === "idle";

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] overflow-hidden flex flex-col">
      {/* Header with tabs */}
      <div className="flex items-center justify-between px-4 pt-4 pb-2 border-b border-white/[0.05]">
        <div className="flex items-center gap-1 overflow-x-auto">
          {tabs.map((tab) => {
            const displayName = tab === "all" ? "All" : AGENT_DISPLAY_NAMES[tab] || tab;
            const color = tab === "all" ? "" : AGENT_COLORS[tab] || "";
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all shrink-0",
                  activeTab === tab
                    ? "bg-white/[0.08] text-neutral-100"
                    : "text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.03]",
                )}
              >
                {tab !== "all" && <span className={cn("mr-1", color)}>●</span>}
                {displayName}
              </button>
            );
          })}
        </div>

        {!isIdle && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="w-7 h-7 text-neutral-500 hover:text-neutral-300"
              onClick={handleCopyAll}
              title="Copy all output"
            >
              <Copy className="w-3.5 h-3.5" strokeWidth={1.5} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="w-7 h-7 text-neutral-500 hover:text-neutral-300"
              onClick={handleClear}
              title="Clear console"
            >
              <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
            </Button>
          </div>
        )}
      </div>

      {/* Console output */}
      <div className="flex-1">
        {isIdle ? (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <Terminal className="w-10 h-10 text-neutral-600 mb-3" strokeWidth={1.2} />
            <p className="text-sm text-neutral-500">Waiting for workflow to start...</p>
          </div>
        ) : filteredLines.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <div className="w-2 h-4 bg-emerald-400/60 animate-pulse rounded-sm mb-3" />
            <p className="text-sm text-neutral-500">Agent outputs will appear here...</p>
          </div>
        ) : (
          <ScrollArea
            className="h-80"
            onScroll={(e) => handleScroll(e.currentTarget as HTMLDivElement)}
          >
            <div className="p-4 bg-black/50 font-mono text-xs leading-6 min-h-80">
              {filteredLines.map((line, index) => {
                const agentName = line.agentId
                  ? AGENT_DISPLAY_NAMES[line.agentId]
                  : null;
                const color =
                  line.agentId && AGENT_COLORS[line.agentId]
                    ? AGENT_COLORS[line.agentId]
                    : "";

                return (
                  <p
                    key={index}
                    className={cn(
                      "whitespace-pre-wrap break-all",
                      line.type === "stdout" && "text-neutral-300",
                      line.type === "stderr" && "text-red-400",
                      line.type === "system" && "text-neutral-500",
                    )}
                  >
                    {agentName && (
                      <span className={cn("mr-1.5 font-semibold", color)}>
                        [{agentName}]
                      </span>
                    )}
                    {line.text}
                  </p>
                );
              })}
              <div ref={consoleEndRef} />
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}

