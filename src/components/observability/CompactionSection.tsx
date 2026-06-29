"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Layers, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

export interface CompactionStatus {
  threshold_percent: number;
  default_threshold_percent: number;
  env_var: string;
  context_length: number | null;
  model: string | null;
  threshold_tokens: number | null;
  compactions_total: number;
  last_before_tokens: number | null;
  last_after_tokens: number | null;
  last_saved_tokens: number | null;
  last_at: string | null;
}

const POLL_INTERVAL_MS = 5_000;

function formatTokens(n: number | null): string {
  if (n === null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = Date.now() - t;
  if (delta < 5_000) return "just now";
  if (delta < 60_000) return `${Math.round(delta / 1000)}s ago`;
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
  return `${Math.round(delta / 3_600_000)}h ago`;
}

interface ProgressBarProps {
  threshold: number;
  isConfigured: boolean;
}

function ProgressBar({ threshold, isConfigured }: ProgressBarProps) {
  const fillPercent = Math.min(100, Math.max(0, threshold * 100));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
          Trigger threshold
        </span>
        <span
          className={cn(
            "text-sm font-mono tabular-nums tracking-tight",
            isConfigured ? "text-zinc-200" : "text-zinc-500",
          )}
        >
          {(fillPercent).toFixed(0)}%
        </span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-zinc-800/50 overflow-hidden">
        <motion.div
          initial={false}
          animate={{ width: `${fillPercent}%` }}
          transition={{ type: "spring", stiffness: 200, damping: 24 }}
          className={cn(
            "absolute inset-y-0 left-0 rounded-full",
            isConfigured
              ? "bg-emerald-500/80"
              : "bg-zinc-700/40",
          )}
        />
        <div className="absolute inset-y-0 right-0 w-px bg-rose-500/30" />
      </div>
      <div className="flex items-baseline justify-between gap-2 text-[10px] font-mono tabular-nums text-zinc-500">
        <span>0%</span>
        <span>100% (hard wall)</span>
      </div>
    </div>
  );
}

export function CompactionSection() {
  const [status, setStatus] = useState<CompactionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const data = await api.get<CompactionStatus>("/api/observability/compaction");
        if (!cancelled) {
          setStatus(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    fetchOnce();
    const id = setInterval(fetchOnce, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-[2rem] p-6 border border-rose-500/20 bg-rose-500/[0.04]">
        <div className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4 text-rose-500" strokeWidth={1.5} />
          <span className="text-sm font-medium text-rose-400">
            Compaction status unavailable
          </span>
        </div>
        <div className="mt-2 text-[12px] font-mono text-zinc-500">{error}</div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="rounded-[2rem] p-6 text-sm text-zinc-500">
        Loading compaction status…
      </div>
    );
  }

  const isConfigured = status.context_length !== null;
  const isOverridden = Math.abs(
    status.threshold_percent - status.default_threshold_percent,
  ) > 1e-6;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 240, damping: 22 }}
      className="rounded-[2rem] p-6 border border-zinc-800/50 bg-zinc-900/40"
    >
      <div className="flex items-baseline justify-between gap-4 pb-4">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-zinc-400" strokeWidth={1.5} />
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            Context compaction
          </span>
        </div>
        {isOverridden && (
          <span className="inline-flex items-center gap-1.5 text-[10px] font-mono px-2 py-1 rounded-full border border-amber-500/20 text-amber-500 uppercase tracking-wide">
            env override
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-x-6 gap-y-5">
        <div className="md:col-span-5 flex flex-col gap-1.5">
          <ProgressBar
            threshold={status.threshold_percent}
            isConfigured={isConfigured}
          />
        </div>

        <div className="md:col-span-4 flex flex-col gap-1.5">
          <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            Context window
          </div>
          <div className="font-mono text-sm text-zinc-200 tabular-nums">
            {formatTokens(status.context_length)}
          </div>
          <div className="text-[11px] font-mono text-zinc-500 tabular-nums">
            fires at {formatTokens(status.threshold_tokens)}
          </div>
        </div>

        <div className="md:col-span-3 flex flex-col gap-1.5">
          <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            Compactions
          </div>
          <div className="font-mono text-sm text-zinc-200 tabular-nums">
            {status.compactions_total.toLocaleString()}
          </div>
          <div className="text-[11px] font-mono text-zinc-500 tabular-nums">
            {formatRelativeTime(status.last_at)}
          </div>
        </div>
      </div>

      {isConfigured && (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-x-6 gap-y-4 mt-5 pt-5 border-t border-zinc-800/50">
          <div className="md:col-span-7 flex flex-col gap-1.5">
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              Model
            </div>
            <div className="font-mono text-sm text-zinc-200 truncate" title={status.model ?? ""}>
              {status.model ?? "—"}
            </div>
            <div className="text-[11px] font-mono text-zinc-500 tabular-nums">
              env: <code className="text-zinc-300">{status.env_var}</code>
              {isOverridden ? " (override active)" : " (default)"}
            </div>
          </div>
          <div className="md:col-span-5 flex flex-col gap-1.5">
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              Last compaction
            </div>
            <div className="flex items-baseline gap-2 font-mono text-sm tabular-nums">
              <span className="text-zinc-400">
                {formatTokens(status.last_before_tokens)}
              </span>
              <span className="text-zinc-700">→</span>
              <span className="text-emerald-500">
                {formatTokens(status.last_after_tokens)}
              </span>
            </div>
            {status.last_saved_tokens !== null && status.last_saved_tokens > 0 && (
              <div className="text-[11px] font-mono text-zinc-500 tabular-nums">
                saved {formatTokens(status.last_saved_tokens)} tokens
              </div>
            )}
          </div>
        </div>
      )}

      {!isConfigured && (
        <div className="mt-4 rounded-[1rem] border border-zinc-800/50 bg-zinc-900/40 p-3">
          <div className="text-[12px] text-zinc-400 font-medium">
            No context compressor configured
          </div>
          <div className="text-[11px] font-mono text-zinc-500 mt-1">
            Configure a default model with a known context length to enable compaction.
          </div>
        </div>
      )}
    </motion.div>
  );
}
