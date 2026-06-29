"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { ArrowLeft, RotateCcw, GitCompare, Download } from "lucide-react";
import { cn } from "@/lib/utils";

interface RunHeaderProps {
  runId: string;
  status: string;
  createdAt?: string;
  duration?: number;
  loading?: boolean;
  onReRun?: () => void;
  onCompare?: () => void;
}

function StatusDot({ status }: { status: string }) {
  const isRunning = status === "running" || status === "pending";
  const isFailed = status === "failed";
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full",
        isRunning && "bg-emerald-400 animate-pulse",
        isFailed && "bg-red-400",
        !isRunning && !isFailed && "bg-emerald-400/50"
      )}
    />
  );
}

export function RunHeader({ runId, status, createdAt, duration, loading, onReRun, onCompare }: RunHeaderProps) {
  const router = useRouter();

  if (loading) {
    return (
      <div className="flex items-center justify-between p-6 bg-surface border border-white/[0.06] rounded-[1.5rem]">
        <div className="space-y-2">
          <div className="w-32 h-4 rounded-full shimmer-bg" />
          <div className="w-48 h-3 rounded-full shimmer-bg" />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] as const }}
      className="flex items-center justify-between p-6 bg-surface border border-white/[0.06] rounded-[1.5rem]"
    >
      <div className="flex items-center gap-4">
        <button
          onClick={() => router.push("/history")}
          className="w-9 h-9 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] flex items-center justify-center text-neutral-400 hover:text-neutral-200 transition-all"
        >
          <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
        </button>
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-neutral-100 font-mono tracking-tight">
              {runId?.slice(0, 8) ?? "..."}
            </h1>
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/[0.04]">
              <StatusDot status={status} />
              <span className={cn(
                "text-[11px] font-medium",
                status === "completed" && "text-emerald-400",
                status === "failed" && "text-red-400",
                (status === "running" || status === "pending") && "text-amber-400"
              )}>
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3 mt-1 text-sm text-neutral-500">
            {createdAt && <span>{createdAt}</span>}
            {duration !== undefined && <span>{duration}s</span>}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {onReRun && (
          <button
            onClick={onReRun}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 text-sm font-medium transition-all active:scale-[0.98]"
          >
            <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />
            Re-run
          </button>
        )}
        {onCompare && (
          <button
            onClick={onCompare}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-neutral-300 text-sm font-medium transition-all active:scale-[0.98]"
          >
            <GitCompare className="w-3.5 h-3.5" strokeWidth={1.5} />
            Compare
          </button>
        )}
        <button className="w-9 h-9 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] flex items-center justify-center text-neutral-400 hover:text-neutral-200 transition-all">
          <Download className="w-4 h-4" strokeWidth={1.5} />
        </button>
      </div>
    </motion.div>
  );
}
