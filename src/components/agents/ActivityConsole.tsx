"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Trash2, Terminal, ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LogEntry, ConsoleLine } from "@/lib/types/workflow";

interface ActivityConsoleProps {
  logs: LogEntry[];
  consoleLines: ConsoleLine[];
  workflowStatus: "idle" | "running" | "completed" | "failed";
}

const levelConfig: Record<
  string,
  { container: string; dot: string; label: string }
> = {
  info: {
    container: "border-l-neutral-500/30",
    dot: "bg-neutral-500",
    label: "INFO",
  },
  success: {
    container: "border-l-emerald-500/30",
    dot: "bg-emerald-400",
    label: "OK",
  },
  warning: {
    container: "border-l-amber-500/30",
    dot: "bg-amber-400",
    label: "WARN",
  },
  error: {
    container: "border-l-red-500/30",
    dot: "bg-red-400",
    label: "ERR",
  },
};

function formatTimestamp(ts: string): string {
  try {
    const date = new Date(ts);
    return date.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

export function ActivityConsole({
  logs,
  consoleLines,
  workflowStatus,
}: ActivityConsoleProps) {
  const logEndRef = useRef<HTMLDivElement>(null);
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState("activity");

  // Auto-scroll to bottom on new content
  useEffect(() => {
    if (activeTab === "activity") {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, activeTab]);

  useEffect(() => {
    if (activeTab === "console") {
      consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [consoleLines, activeTab]);

  const handleClear = useCallback(() => {
    // Clearing is handled by parent — this triggers the parent to reset
    // We just provide the button per spec
  }, []);

  const isIdle = workflowStatus === "idle";

  return (
    <div className="bg-surface border border-white/[0.05] rounded-[1.5rem] overflow-hidden">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        {/* Tabs Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <TabsList className="bg-white/[0.03] border border-white/[0.05] rounded-xl p-0.5">
            <TabsTrigger
              value="activity"
              className="rounded-lg text-xs data-[state=active]:bg-white/[0.08] data-[state=active]:text-neutral-100 text-neutral-500 gap-1.5"
            >
              <ScrollText className="w-3.5 h-3.5" strokeWidth={1.5} />
              Activity Log
            </TabsTrigger>
            <TabsTrigger
              value="console"
              className="rounded-lg text-xs data-[state=active]:bg-white/[0.08] data-[state=active]:text-neutral-100 text-neutral-500 gap-1.5"
            >
              <Terminal className="w-3.5 h-3.5" strokeWidth={1.5} />
              Agent Console
            </TabsTrigger>
          </TabsList>
          {!isIdle && (
            <Button
              variant="ghost"
              size="icon"
              className="w-7 h-7 text-neutral-500 hover:text-neutral-300"
              onClick={handleClear}
            >
              <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
            </Button>
          )}
        </div>

        {/* Activity Log Tab */}
        <TabsContent value="activity" className="m-0">
          {isIdle ? (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <ScrollText
                className="w-10 h-10 text-neutral-600 mb-3"
                strokeWidth={1.2}
              />
              <p className="text-sm text-neutral-500">
                Waiting for workflow to start...
              </p>
            </div>
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <div className="w-2 h-4 bg-emerald-400/60 animate-pulse rounded-sm mb-3" />
              <p className="text-sm text-neutral-500">
                Agent outputs will appear here...
              </p>
            </div>
          ) : (
            <ScrollArea className="h-80">
              <div className="px-4 pb-4 space-y-1">
                {logs.map((log) => {
                  const cfg = levelConfig[log.level] ?? levelConfig.info;
                  return (
                    <div
                      key={log.id}
                      className={cn(
                        "flex items-start gap-3 py-2 pl-3 border-l-2",
                        cfg.container
                      )}
                    >
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium shrink-0 mt-0.5",
                          cfg.dot
                        )}
                      >
                        {formatTimestamp(log.timestamp)}
                      </span>
                      <span className="text-xs text-neutral-400 leading-5">
                        {log.message}
                      </span>
                    </div>
                  );
                })}
                <div ref={logEndRef} />
              </div>
            </ScrollArea>
          )}
        </TabsContent>

        {/* Agent Console Tab */}
        <TabsContent value="console" className="m-0">
          {isIdle ? (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <Terminal
                className="w-10 h-10 text-neutral-600 mb-3"
                strokeWidth={1.2}
              />
              <p className="text-sm text-neutral-500">
                Waiting for workflow to start...
              </p>
            </div>
          ) : consoleLines.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <div className="w-2 h-4 bg-emerald-400/60 animate-pulse rounded-sm mb-3" />
              <p className="text-sm text-neutral-500">
                Agent outputs will appear here...
              </p>
            </div>
          ) : (
            <ScrollArea className="h-80">
              <div className="p-4 bg-black/50 font-mono text-xs leading-6 min-h-80">
                {consoleLines.map((line, index) => (
                  <p
                    key={index}
                    className={cn(
                      "whitespace-pre-wrap break-all",
                      line.type === "stdout" && "text-neutral-300",
                      line.type === "stderr" && "text-red-400",
                      line.type === "system" && "text-neutral-500"
                    )}
                  >
                    {line.text}
                  </p>
                ))}
                <div ref={consoleEndRef} />
              </div>
            </ScrollArea>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

