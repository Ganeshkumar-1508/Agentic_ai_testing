"use client";

/**
 * ObservabilityPanels — proves "is the agent actually working?" at a glance.
 *
 * Three panels, all driven by `GET /api/events/_aggregations` (or scoped
 * to a single session via `?session_id=`):
 *
 *   1. Tools health      — per-tool success rate, error count, last seen.
 *                           Solves "which tool is failing?" in one glance.
 *   2. Cost burn         — token totals + USD estimate, bucketed per minute.
 *                           Solves "how fast is this costing me?".
 *   3. Error buckets     — `ErrorEvent.category` histogram (rate_limit,
 *                           context_length, auth, server_error, …).
 *                           Solves "is the agent stuck on a known category?".
 *
 * Design:
 *   - divide-y strip, no card grid (per design-taste-frontend).
 *   - emerald=good, amber=warn, red=danger, zinc=muted.
 *   - bars animate in with spring physics.
 *   - empty state: "Waiting for the first event."
 *
 * Polling: refetch every 10s while the page is mounted.  The live
 * ActivityFeed below the panels handles sub-second updates; this panel
 * is the "slow lane" for aggregated state.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Coins,
  Gauge,
  Wrench,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

const POLL_INTERVAL_MS = 10_000;

export interface ToolHealth {
  tool: string;
  started: number;
  completed: number;
  errors: number;
  success_rate: number;
  last_seen: string | null;
}

export interface EventCount {
  event_type: string;
  count: number;
}

export interface CostBurnPoint {
  bucket: string;
  tokens: number;
  calls: number;
  cost_usd: number;
}

export interface ErrorBucket {
  category: string;
  count: number;
}

export interface Aggregations {
  tool_health: ToolHealth[];
  event_counts: EventCount[];
  cost_burn: CostBurnPoint[];
  error_buckets: ErrorBucket[];
  window_minutes: number;
  scoped_session: string | null;
}

interface ObservabilityPanelsProps {
  sessionId?: string;
  sinceMinutes?: number;
}

export function ObservabilityPanels({ sessionId, sinceMinutes = 60 }: ObservabilityPanelsProps) {
  const aggsQ = useQuery<Aggregations>({
    queryKey: ["event-aggregations", sessionId ?? "_global", sinceMinutes],
    queryFn: async () => {
      const params = new URLSearchParams({ since_minutes: String(sinceMinutes) });
      if (sessionId) params.set("session_id", sessionId);
      return api.get<Aggregations>(`/api/events/_aggregations?${params.toString()}`);
    },
    refetchInterval: POLL_INTERVAL_MS,
    staleTime: POLL_INTERVAL_MS / 2,
  });

  return (
    <div className="border border-white/[0.06] divide-y divide-white/[0.06] grid grid-cols-1 lg:grid-cols-3">
      <ToolsHealthPanel data={aggsQ.data?.tool_health ?? []} loading={aggsQ.isLoading} />
      <CostBurnPanel data={aggsQ.data?.cost_burn ?? []} loading={aggsQ.isLoading} />
      <ErrorBucketsPanel data={aggsQ.data?.error_buckets ?? []} loading={aggsQ.isLoading} />
    </div>
  );
}

function PanelHeader({
  icon: Icon,
  label,
  hint,
  tone = "default",
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  hint?: string;
  tone?: "default" | "warn" | "danger";
}) {
  const toneClass =
    tone === "warn" ? "text-amber-400" : tone === "danger" ? "text-red-400" : "text-zinc-500";
  return (
    <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-white/[0.05]">
      <Icon className={cn("w-3 h-3", toneClass)} strokeWidth={1.5} />
      <span className="text-[10px] uppercase tracking-[0.14em] text-zinc-500 font-medium">{label}</span>
      {hint && <span className="text-[9.5px] text-zinc-700 font-mono ml-auto">{hint}</span>}
    </div>
  );
}

function EmptyState({ message, icon: Icon = Activity }: { message: string; icon?: React.ComponentType<{ className?: string; strokeWidth?: number }> }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 text-center gap-2">
      <div className="w-8 h-8 rounded-full border border-dashed border-white/10 flex items-center justify-center">
        <Icon className="w-3.5 h-3.5 text-zinc-700" strokeWidth={1.5} />
      </div>
      <p className="text-[11px] text-zinc-600 font-mono">{message}</p>
    </div>
  );
}

function ToolsHealthPanel({ data, loading }: { data: ToolHealth[]; loading: boolean }) {
  const sorted = [...data].sort((a, b) => b.started - a.started).slice(0, 8);
  const totalStarted = data.reduce((s, t) => s + t.started, 0);
  const totalCompleted = data.reduce((s, t) => s + t.completed, 0);
  const totalErrors = data.reduce((s, t) => s + t.errors, 0);
  const hint = loading
    ? "loading…"
    : totalStarted > 0
      ? `${totalStarted} calls · ${totalErrors} err`
      : "no data";
  return (
    <div>
      <PanelHeader icon={Wrench} label="Tools health" hint={hint} tone={totalErrors > 0 ? "warn" : "default"} />
      {sorted.length === 0 ? (
        <EmptyState message="No tool calls in this window." icon={Wrench} />
      ) : (
        <ul className="divide-y divide-white/[0.04]">
          {sorted.map((t, i) => (
            <motion.li
              key={t.tool}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.02 * i, type: "spring", stiffness: 200, damping: 22 }}
              className="flex items-center gap-2.5 px-4 py-2"
            >
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full shrink-0",
                  t.errors > 0
                    ? "bg-amber-400"
                    : t.success_rate >= 0.95 || t.completed === 0
                      ? "bg-emerald-400"
                      : "bg-zinc-500",
                )}
              />
              <span className="text-[11px] font-mono text-zinc-300 truncate flex-1" title={t.tool}>
                {t.tool}
              </span>
              <span className="text-[10px] font-mono tabular-nums text-zinc-500">
                {t.started}·{t.completed}
              </span>
              <span
                className={cn(
                  "text-[10px] font-mono tabular-nums w-10 text-right",
                  t.errors > 0 ? "text-amber-400" : "text-zinc-600",
                )}
              >
                {t.errors > 0 ? `${t.errors} err` : "ok"}
              </span>
            </motion.li>
          ))}
        </ul>
      )}
      {totalCompleted > 0 && (
        <div className="px-4 py-2 border-t border-white/[0.04] flex items-center gap-1.5 text-[9.5px] text-zinc-600 font-mono">
          <Gauge className="w-2.5 h-2.5" strokeWidth={1.5} />
          <span>success rate: {(((totalCompleted - totalErrors) / totalCompleted) * 100).toFixed(1)}%</span>
        </div>
      )}
    </div>
  );
}

function CostBurnPanel({ data, loading }: { data: CostBurnPoint[]; loading: boolean }) {
  const totalTokens = data.reduce((s, p) => s + p.tokens, 0);
  const totalCost = data.reduce((s, p) => s + p.cost_usd, 0);
  const totalCalls = data.reduce((s, p) => s + p.calls, 0);
  const maxTokens = Math.max(1, ...data.map((p) => p.tokens));
  const hint = loading
    ? "loading…"
    : totalTokens > 0
      ? `${formatTokens(totalTokens)} · ${formatCost(totalCost)}`
      : "no data";
  return (
    <div>
      <PanelHeader icon={Coins} label="Cost burn" hint={hint} tone={totalCost > 1 ? "warn" : "default"} />
      {data.length === 0 ? (
        <EmptyState message="No LLM calls in this window." icon={Coins} />
      ) : (
        <div className="px-4 py-3 space-y-1.5">
          {data.slice(-12).map((p, i) => {
            const pct = p.tokens / maxTokens;
            return (
              <motion.div
                key={p.bucket}
                initial={{ opacity: 0, scaleX: 0.6 }}
                animate={{ opacity: 1, scaleX: 1 }}
                transition={{ delay: 0.015 * i, type: "spring", stiffness: 180, damping: 22 }}
                style={{ transformOrigin: "left center" }}
                className="flex items-center gap-2"
              >
                <span className="text-[9.5px] text-zinc-700 font-mono w-12 shrink-0 tabular-nums">
                  {p.bucket?.slice(11, 16) ?? "—"}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.03] overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct * 100}%` }}
                    transition={{ delay: 0.05 + 0.015 * i, type: "spring", stiffness: 100, damping: 18 }}
                    className="h-full bg-emerald-400/70"
                  />
                </div>
                <span className="text-[9.5px] text-zinc-500 font-mono tabular-nums w-16 text-right shrink-0">
                  {formatTokens(p.tokens)} · {p.calls}c
                </span>
              </motion.div>
            );
          })}
        </div>
      )}
      {totalCalls > 0 && (
        <div className="px-4 py-2 border-t border-white/[0.04] flex items-center gap-1.5 text-[9.5px] text-zinc-600 font-mono">
          <Coins className="w-2.5 h-2.5" strokeWidth={1.5} />
          <span>{totalCalls} LLM calls · est. {formatCost(totalCost)}</span>
        </div>
      )}
    </div>
  );
}

function ErrorBucketsPanel({ data, loading }: { data: ErrorBucket[]; loading: boolean }) {
  const total = data.reduce((s, b) => s + b.count, 0);
  const max = Math.max(1, ...data.map((b) => b.count));
  const hint = loading ? "loading…" : total > 0 ? `${total} errors` : "no errors";
  const tone: "default" | "warn" | "danger" = total === 0 ? "default" : data.some((b) => b.category === "auth" || b.category === "quota") ? "danger" : "warn";
  return (
    <div>
      <PanelHeader
        icon={tone === "danger" ? XCircle : AlertTriangle}
        label="Error categories"
        hint={hint}
        tone={tone}
      />
      {data.length === 0 ? (
        <EmptyState message="No errors in this window. Healthy." icon={XCircle} />
      ) : (
        <ul className="divide-y divide-white/[0.04]">
          {data.slice(0, 8).map((b, i) => (
            <motion.li
              key={b.category}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.02 * i, type: "spring", stiffness: 200, damping: 22 }}
              className="flex items-center gap-2.5 px-4 py-2"
            >
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full shrink-0",
                  b.category === "auth" || b.category === "quota"
                    ? "bg-red-400"
                    : b.category === "rate_limit" || b.category === "model_overload"
                      ? "bg-amber-400"
                      : "bg-zinc-500",
                )}
              />
              <span className="text-[11px] font-mono text-zinc-300 truncate flex-1" title={b.category}>
                {b.category}
              </span>
              <div className="flex-1 max-w-[80px] h-1 rounded-full bg-white/[0.03] overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${(b.count / max) * 100}%` }}
                  transition={{ delay: 0.05 + 0.02 * i, type: "spring", stiffness: 100, damping: 18 }}
                  className={cn(
                    "h-full",
                    b.category === "auth" || b.category === "quota"
                      ? "bg-red-400/70"
                      : b.category === "rate_limit" || b.category === "model_overload"
                        ? "bg-amber-400/70"
                        : "bg-zinc-500/70",
                  )}
                />
              </div>
              <span className="text-[10px] font-mono tabular-nums text-zinc-500 w-6 text-right">
                {b.count}
              </span>
            </motion.li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatCost(n: number): string {
  if (n < 0.01) return `$${(n * 1000).toFixed(2)}m`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}
