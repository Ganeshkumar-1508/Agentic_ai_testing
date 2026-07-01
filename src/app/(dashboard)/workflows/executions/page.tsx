"use client";

import { Suspense, useState, useMemo, type ElementType } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import {
  Loader2, CheckCircle2, XCircle, Clock, GitBranch,
  RotateCcw, ChevronDown, ChevronRight, Cpu, UserRound, GitFork,
} from "lucide-react";

interface StepRecord {
  step_id: string;
  label: string;
  type: string;
  status: string;
  started_at: string;
  duration_sec: number;
  output: string;
  error: string;
}

interface ExecutionRecord {
  id: string;
  workflow_key: string;
  status: string;
  started_at: string;
  completed_at: string;
  duration_sec: number;
  steps: StepRecord[];
  error: string;
  triggered_by: string;
  retry_of: string;
}

const TYPE_ICONS: Record<string, ElementType> = {
  agent: Cpu,
  human_input: UserRound,
  router: GitFork,
};

function formatDuration(sec: number): string {
  if (sec < 1) return "<1s";
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const springProps = { type: "spring" as const, stiffness: 200, damping: 24 };

function WorkflowExecutionsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workflowFilter = searchParams?.get("workflow") || "";
  const [expanded, setExpanded] = useState<string | null>(null);

  const apiPath = workflowFilter
    ? `/api/workflows/${workflowFilter}/executions?limit=50`
    : "/api/workflows/executions?limit=50";

  const { data, isLoading } = useQuery({
    queryKey: ["workflow-executions", workflowFilter],
    queryFn: async () => {
      const res = await api.get<{ executions: ExecutionRecord[] }>(apiPath);
      return res?.executions ?? [];
    },
  });

  const retryMutation = useMutation({
    mutationFn: async (executionId: string) =>
      api.post(`/api/workflows/executions/${executionId}/retry`, {}),
  });

  const executions = Array.isArray(data) ? data : [];

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
        <span className="text-xs font-mono text-zinc-600">/workflows/executions</span>
      </div>
      <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100">Execution History</h1>
      <p className="text-sm text-zinc-600 mt-1">Past workflow runs with step-level detail and retry</p>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-16 rounded-xl border border-zinc-800/30 bg-zinc-900/20 shimmer" />
          ))}
        </div>
      ) : executions.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-zinc-600 gap-3">
          <Clock size={24} strokeWidth={1} className="text-zinc-700" />
          <p className="text-sm">No executions yet</p>
          <p className="text-xs text-zinc-700">Run a workflow to see its execution history here</p>
        </div>
      ) : (
        <div className="space-y-2">
          {executions.map((ex, i) => (
            <motion.div key={ex.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ ...springProps, delay: i * 0.02 }}
              className="rounded-xl border border-zinc-800/40 bg-zinc-900/20 overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-zinc-900/40 transition-colors"
                   onClick={() => setExpanded(expanded === ex.id ? null : ex.id)}>
                {ex.status === "completed" ? (
                  <CheckCircle2 size={16} className="text-emerald-400 shrink-0" strokeWidth={1.5} />
                ) : ex.status === "failed" ? (
                  <XCircle size={16} className="text-red-400 shrink-0" strokeWidth={1.5} />
                ) : (
                  <Clock size={16} className="text-zinc-500 shrink-0" strokeWidth={1.5} />
                )}
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <GitBranch size={12} className="text-zinc-600 shrink-0" strokeWidth={1.5} />
                  <span className="text-sm text-zinc-200 font-medium">{ex.workflow_key}</span>
                  <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-mono",
                    ex.status === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                    ex.status === "failed" ? "bg-red-500/10 text-red-400" :
                    "bg-zinc-500/10 text-zinc-400")}>
                    {ex.status}
                  </span>
                  {ex.triggered_by === "retry" && (
                    <span className="text-[9px] text-zinc-600 font-mono flex items-center gap-0.5">
                      <RotateCcw size={8} strokeWidth={1.5} /> retry
                    </span>
                  )}
                  {ex.retry_of && (
                    <span className="text-[9px] text-zinc-700 font-mono">retry of {ex.retry_of.slice(0, 8)}</span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-[10px] text-zinc-600 font-mono">
                  <span>{formatDuration(ex.duration_sec)}</span>
                  <span>{timeAgo(ex.started_at)}</span>
                  <span>{ex.steps.length} steps</span>
                </div>
                {ex.status === "failed" && (
                  <button onClick={(e) => { e.stopPropagation(); retryMutation.mutate(ex.id); }}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg bg-zinc-800/40 text-zinc-400 hover:text-emerald-400 text-[10px] transition-all active:scale-[0.97]">
                    <RotateCcw size={10} strokeWidth={1.5} /> Retry
                  </button>
                )}
                {expanded === ex.id ? <ChevronDown size={12} className="text-zinc-600" /> : <ChevronRight size={12} className="text-zinc-600" />}
              </div>

              <AnimatePresence>
                {expanded === ex.id && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    transition={springProps} className="border-t border-zinc-800/30 px-4 py-3 space-y-2">
                    {ex.steps.length === 0 && (
                      <p className="text-[11px] text-zinc-700 italic py-2">No step data recorded</p>
                    )}
                    {ex.steps.map((step, j) => {
                      const Icon = TYPE_ICONS[step.type] || Cpu;
                      return (
                        <motion.div key={step.step_id} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: j * 0.03 }}
                          className="flex items-start gap-2.5 py-1.5">
                          <div className={cn("w-5 h-5 rounded-md flex items-center justify-center mt-0.5 shrink-0",
                            step.type === "agent" ? "bg-emerald-500/10" :
                            step.type === "human_input" ? "bg-violet-500/10" :
                            step.type === "router" ? "bg-amber-500/10" : "bg-zinc-800/40")}>
                            <Icon size={9} className={cn(
                              step.type === "agent" ? "text-emerald-400" :
                              step.type === "human_input" ? "text-violet-400" :
                              step.type === "router" ? "text-amber-400" : "text-zinc-500"
                            )} strokeWidth={1.5} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-[12px] text-zinc-300">{step.label}</span>
                              <span className={cn("text-[9px] px-1 py-0.5 rounded font-mono",
                                step.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400")}>
                                {step.status}
                              </span>
                              <span className="text-[9px] text-zinc-700 font-mono ml-auto">{formatDuration(step.duration_sec)}</span>
                            </div>
                            {step.output && (
                              <p className="text-[10px] text-zinc-600 font-mono mt-0.5 truncate">{step.output.slice(0, 200)}</p>
                            )}
                            {step.error && (
                              <p className="text-[10px] text-red-400/70 font-mono mt-0.5">{step.error.slice(0, 300)}</p>
                            )}
                          </div>
                        </motion.div>
                      );
                    })}
                    {ex.error && !ex.steps.some(s => s.error) && (
                      <div className="mt-2 rounded-lg bg-red-500/5 border border-red-500/20 px-3 py-2 text-[11px] text-red-400 font-mono">
                        {ex.error}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function WorkflowExecutionsPage() {
  return (
    <Suspense fallback={null}>
      <WorkflowExecutionsContent />
    </Suspense>
  );
}
