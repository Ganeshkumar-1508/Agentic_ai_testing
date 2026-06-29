"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, Loader2, CheckCircle2, XCircle, Clock, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToolCallCardProps {
  name: string;
  status: "running" | "completed" | "error" | "pending";
  result?: string;
  durationMs?: number;
  args?: Record<string, unknown>;
  error?: string;
}

const statusConfig = {
  running: { dot: "bg-amber-400 animate-pulse", label: "Running", icon: Loader2, iconClass: "text-amber-400 animate-spin" },
  completed: { dot: "bg-emerald-400", label: "Completed", icon: CheckCircle2, iconClass: "text-emerald-400" },
  error: { dot: "bg-red-400", label: "Failed", icon: XCircle, iconClass: "text-red-400" },
  pending: { dot: "bg-zinc-600", label: "Pending", icon: Clock, iconClass: "text-zinc-500" },
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export function ToolCallCard({ name, status, result, durationMs, args, error }: ToolCallCardProps) {
  const [open, setOpen] = useState(false);
  const cfg = statusConfig[status] || statusConfig.pending;
  const StatusIcon = cfg.icon;
  const elapsed = durationMs ? formatDuration(durationMs) : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "border rounded-3xl overflow-hidden mt-2 transition-colors",
        status === "completed" && "border-emerald-500/10 bg-emerald-500/[0.02]",
        status === "running" && "border-amber-500/15 bg-amber-500/[0.03]",
        status === "error" && "border-red-500/15 bg-red-500/[0.03]",
        status === "pending" && "border-zinc-800/30 bg-zinc-900/30",
      )}
    >
      <div className="flex items-center gap-2.5 px-3.5 py-2.5">
        <StatusIcon size={12} strokeWidth={2} className={cn("shrink-0", cfg.iconClass)} />
        <Terminal size={10} className="text-zinc-500 shrink-0" strokeWidth={1.5} />
        <span className="text-xs font-mono font-medium text-zinc-300 truncate">{name}</span>
        {elapsed && (
          <span className="text-[10px] text-zinc-600 font-mono tabular-nums shrink-0">{elapsed}</span>
        )}
        <span className={cn(
          "text-[10px] px-1.5 py-0.5 rounded font-medium ml-auto shrink-0",
          status === "running" && "text-amber-400/70 bg-amber-500/10",
          status === "completed" && "text-emerald-400/70 bg-emerald-500/10",
          status === "error" && "text-red-400 bg-red-500/10",
          status === "pending" && "text-zinc-600 bg-zinc-800/30",
        )}>
          {cfg.label}
        </span>
        {(result || args || error) && (
          <button
            onClick={() => setOpen(!open)}
            className="p-0.5 rounded text-zinc-600 hover:text-zinc-400 transition-colors active:scale-[0.97] shrink-0"
          >
            {open ? <ChevronDown size={12} strokeWidth={1.5} /> : <ChevronRight size={12} strokeWidth={1.5} />}
          </button>
        )}
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-zinc-800/20 divide-y divide-zinc-800/10">
              {args && Object.keys(args).length > 0 && (
                <div className="px-3.5 py-2">
                  <p className="text-[10px] text-zinc-600 font-medium mb-1 uppercase tracking-wider">Arguments</p>
                  <pre className="text-[11px] text-zinc-400 font-mono whitespace-pre-wrap break-all leading-relaxed">
                    {(JSON.stringify(args, null, 2) || "").slice(0, 300)}
                    {(JSON.stringify(args, null, 2) || "").length > 300 ? "..." : ""}
                  </pre>
                </div>
              )}
              {result && (
                <div className="px-3.5 py-2">
                  <p className="text-[10px] text-zinc-600 font-medium mb-1 uppercase tracking-wider">Result</p>
                  <pre className="text-[11px] text-zinc-400 font-mono whitespace-pre-wrap break-all leading-relaxed max-h-32 overflow-y-auto">
                    {result.slice(0, 500)}
                    {result.length > 500 ? "..." : ""}
                  </pre>
                </div>
              )}
              {error && (
                <div className="px-3.5 py-2">
                  <p className="text-[10px] text-red-400 font-medium mb-1 uppercase tracking-wider">Error</p>
                  <pre className="text-[11px] text-red-400/70 font-mono whitespace-pre-wrap break-all leading-relaxed">
                    {error}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
