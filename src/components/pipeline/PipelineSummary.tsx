"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useRouter } from "next/navigation";
import { CheckCircle2, XCircle, Clock, Cpu, DollarSign, Hash, ArrowRight, MessageSquare, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

function formatTokens(n: number): string {
  if (n > 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n > 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function PipelineSummary() {
  const router = useRouter();
  const { status, startTime, endTime, totalTokens, estimatedCost, tools, runId, sessionId, requirements } = usePipelineStore();

  const isVisible = status === "completed" || status === "failed";

  const stats = useMemo(() => {
    if (!startTime) return null;
    const durationMs = endTime ? endTime - startTime : Date.now() - startTime;
    const toolCount = tools.length;
    const completedTools = tools.filter((t) => t.status === "completed").length;
    const failedTools = tools.filter((t) => t.status === "failed").length;
    return { durationMs, toolCount, completedTools, failedTools };
  }, [startTime, endTime, tools]);

  if (!isVisible || !stats) return null;

  const isSuccess = status === "completed";

  const items = [
    { icon: Clock, label: "Duration", value: formatDuration(stats.durationMs), color: "text-blue-400" },
    { icon: Cpu, label: "Tokens Used", value: formatTokens(totalTokens), color: "text-zinc-400" },
    { icon: DollarSign, label: "Total Cost", value: `$${estimatedCost.toFixed(4)}`, color: "text-amber-400" },
    { icon: Hash, label: "Tool Calls", value: `${stats.completedTools}/${stats.toolCount}`, sub: stats.failedTools > 0 ? `${stats.failedTools} failed` : undefined, color: "text-emerald-400" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] as const }}
      className={cn(
        "rounded-3xl border p-6 space-y-5",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]",
        isSuccess
          ? "bg-emerald-500/[0.03] border-emerald-500/10"
          : "bg-red-500/[0.03] border-red-500/10",
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={cn(
            "w-11 h-11 rounded-2xl flex items-center justify-center shrink-0",
            "shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]",
            isSuccess ? "bg-emerald-500/10" : "bg-red-500/10",
          )}>
            {isSuccess ? (
              <CheckCircle2 size={20} className="text-emerald-400" strokeWidth={1.5} />
            ) : (
              <XCircle size={20} className="text-red-400" strokeWidth={1.5} />
            )}
          </div>
          <div>
            <p className="text-base font-semibold text-neutral-100 tracking-tight">
              Pipeline {isSuccess ? "completed successfully" : "failed"}
            </p>
            <p className="text-sm text-neutral-500 mt-0.5 leading-relaxed max-w-[65ch]">
              {isSuccess
                ? "All agents finished execution. Review the stats below or view the full run details."
                : "One or more agents encountered errors during execution."
              }
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {requirements && (
            <button
              onClick={() => {
                sessionStorage.setItem("pipeline_requirements", requirements);
                router.push("/pipeline");
              }}
              className="flex items-center gap-1.5 px-3.5 py-2 text-xs rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 transition-all duration-300 active:scale-[0.97] shrink-0"
            >
              <RotateCcw size={12} strokeWidth={1.5} />
              Run Again
            </button>
          )}
          <button
            onClick={() => {
              const summary = `Pipeline ${isSuccess ? "completed" : "failed"}. Duration: ${formatDuration(stats.durationMs)}. Tokens: ${formatTokens(totalTokens)}. Cost: $${estimatedCost.toFixed(4)}. Tool calls: ${stats.completedTools}/${stats.toolCount}.`;
              sessionStorage.setItem("agent_prompt", summary);
              router.push("/chat");
            }}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs rounded-xl bg-white/[0.04] border border-white/[0.06] text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.08] hover:border-white/[0.1] transition-all duration-300 active:scale-[0.97] shrink-0"
          >
            <MessageSquare size={12} strokeWidth={1.5} />
            Discuss
          </button>
          <button
            onClick={() => {
              if (runId) router.push(`/history/${runId}`);
              else if (sessionId) router.push("/sessions");
            }}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs rounded-xl bg-white/[0.04] border border-white/[0.06] text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.08] hover:border-white/[0.1] transition-all duration-300 active:scale-[0.97] shrink-0"
          >
            View details
            <ArrowRight size={12} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {items.map((item, i) => (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 100, damping: 20, delay: 0.08 + i * 0.06 }}
            className="bg-white/[0.02] border border-white/[0.05] rounded-[1.5rem] px-4 py-3.5 space-y-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
          >
            <div className="flex items-center gap-1.5">
              <item.icon size={12} className={cn(item.color)} strokeWidth={1.5} />
              <span className="text-[10px] text-neutral-500 font-medium uppercase tracking-wider">{item.label}</span>
            </div>
            <p className="text-xl font-semibold text-neutral-100 font-mono tabular-nums tracking-tight">{item.value}</p>
            {item.sub && (
              <p className="text-[11px] text-neutral-600 font-mono">{item.sub}</p>
            )}
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
