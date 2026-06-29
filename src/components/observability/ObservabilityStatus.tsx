"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Gauge, Radio, ServerCrash, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

export interface ObservabilityStatus {
  enabled: boolean;
  available: boolean;
  endpoint: string;
  service_name: string;
  service_version: string;
  span_counts: Record<string, number>;
  last_span_at: string | null;
}

const POLL_INTERVAL_MS = 5_000;

const OPERATION_LABELS: Record<string, { label: string; tone: "primary" | "warn" | "info" | "muted" }> = {
  chat: { label: "LLM chat", tone: "primary" },
  execute_tool: { label: "Tool calls", tone: "info" },
  agent_run: { label: "Agent runs", tone: "muted" },
  agent_round: { label: "Rounds", tone: "muted" },
  agent_reasoning: { label: "Reasoning", tone: "muted" },
  subagent_invoke: { label: "Subagents", tone: "info" },
  kanban_transition: { label: "Kanban transitions", tone: "warn" },
  kanban_board: { label: "Kanban boards", tone: "warn" },
  budget_throttle: { label: "Budget throttles", tone: "warn" },
};

function statusTone(s: ObservabilityStatus): { tone: "ok" | "warn" | "danger"; label: string } {
  if (!s.enabled) return { tone: "warn", label: "off" };
  if (!s.available) return { tone: "danger", label: "failed" };
  return { tone: "ok", label: "ok" };
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

interface CountCardProps {
  operation: string;
  label: string;
  count: number;
  tone: "primary" | "warn" | "info" | "muted";
}

function CountCard({ operation, label, count, tone }: CountCardProps) {
  const toneClass =
    tone === "primary"
      ? "border-emerald-500/20 bg-emerald-500/[0.04]"
      : tone === "warn"
        ? "border-amber-500/20 bg-amber-500/[0.04]"
        : tone === "info"
          ? "border-blue-500/20 bg-blue-500/[0.04]"
          : "border-zinc-800/50 bg-zinc-900/40";
  const numberClass =
    tone === "primary"
      ? "text-emerald-500"
      : tone === "warn"
        ? "text-amber-500"
        : tone === "info"
          ? "text-blue-400"
          : "text-zinc-300";
  return (
    <motion.div
      key={operation}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 240, damping: 22 }}
      className={cn(
        "rounded-[1.25rem] border p-4 flex flex-col gap-2 min-w-0",
        toneClass,
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500 truncate">
          {label}
        </span>
        <span className="text-[10px] font-mono text-zinc-600 tabular-nums">
          {operation}
        </span>
      </div>
      <div className={cn("text-2xl font-mono tabular-nums tracking-tight", numberClass)}>
        {count.toLocaleString()}
      </div>
    </motion.div>
  );
}

export function ObservabilityStatus() {
  const [status, setStatus] = useState<ObservabilityStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const data = await api.get<ObservabilityStatus>("/api/observability/status");
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
          <ServerCrash className="h-4 w-4 text-rose-500" strokeWidth={1.5} />
          <span className="text-sm font-medium text-rose-400">
            Observability status unavailable
          </span>
        </div>
        <div className="mt-2 text-[12px] font-mono text-zinc-500">{error}</div>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="rounded-[2rem] p-6 text-sm text-zinc-500">Loading status…</div>
    );
  }

  const tone = statusTone(status);
  const counts = status.span_counts || {};
  const totalSpans = Object.values(counts).reduce((a, b) => a + b, 0);
  const orderedOps = Object.keys(OPERATION_LABELS).filter(
    (op) => counts[op] !== undefined,
  );
  const extraOps = Object.keys(counts).filter(
    (op) => !Object.prototype.hasOwnProperty.call(OPERATION_LABELS, op),
  );

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 240, damping: 22 }}
        className="rounded-[2rem] p-6 border border-zinc-800/50 bg-zinc-900/40"
      >
        <div className="flex items-baseline justify-between gap-4 pb-4">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-zinc-400" strokeWidth={1.5} />
            <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              OpenTelemetry
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-[10px] font-mono px-2 py-1 rounded-full border tabular-nums uppercase tracking-wide",
                tone.tone === "ok"
                  ? "border-emerald-500/20 text-emerald-500"
                  : tone.tone === "warn"
                    ? "border-amber-500/20 text-amber-500"
                    : "border-rose-500/20 text-rose-500",
              )}
            >
              {tone.tone === "ok" ? (
                <ShieldCheck className="h-3 w-3" strokeWidth={1.5} />
              ) : (
                <Radio className="h-3 w-3" strokeWidth={1.5} />
              )}
              {tone.label}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-x-6 gap-y-4">
          <div className="md:col-span-7 flex flex-col gap-1.5">
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              Endpoint
            </div>
            <div className="font-mono text-sm text-zinc-200 truncate" title={status.endpoint}>
              {status.endpoint}
            </div>
            <div className="flex items-baseline gap-2 text-[11px] font-mono text-zinc-500 tabular-nums">
              <span>{status.service_name}</span>
              <span className="text-zinc-700">·</span>
              <span>v{status.service_version}</span>
            </div>
          </div>
          <div className="md:col-span-5 flex flex-col gap-1.5">
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              Last span
            </div>
            <div className="font-mono text-sm text-zinc-200 tabular-nums">
              {formatRelativeTime(status.last_span_at)}
            </div>
            <div className="text-[11px] font-mono text-zinc-500 tabular-nums">
              {totalSpans.toLocaleString()} total spans
            </div>
          </div>
        </div>

        {tone.tone === "warn" && (
          <div className="mt-4 rounded-[1rem] border border-amber-500/20 bg-amber-500/[0.04] p-3">
            <div className="text-[12px] text-amber-300 font-medium">
              OpenTelemetry is not enabled
            </div>
            <div className="text-[11px] font-mono text-zinc-400 mt-1">
              Set <code className="text-amber-200">OTEL_ENABLED=true</code> and{" "}
              <code className="text-amber-200">OTEL_EXPORTER_OTLP_ENDPOINT</code> then restart
              the backend.
            </div>
          </div>
        )}
        {tone.tone === "danger" && (
          <div className="mt-4 rounded-[1rem] border border-rose-500/20 bg-rose-500/[0.04] p-3">
            <div className="text-[12px] text-rose-300 font-medium">
              OTel SDK not available
            </div>
            <div className="text-[11px] font-mono text-zinc-400 mt-1">
              The opentelemetry SDK failed to import. Check the backend logs.
            </div>
          </div>
        )}
      </motion.div>

      {orderedOps.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {orderedOps.map((op) => {
            const meta = OPERATION_LABELS[op];
            return (
              <CountCard
                key={op}
                operation={op}
                label={meta.label}
                count={counts[op] || 0}
                tone={meta.tone}
              />
            );
          })}
        </div>
      )}

      {extraOps.length > 0 && (
        <div className="rounded-[1.5rem] border border-zinc-800/50 p-4">
          <div className="flex items-center gap-2 pb-2">
            <Activity className="h-3.5 w-3.5 text-zinc-500" strokeWidth={1.5} />
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              Other operations
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-4 gap-y-1">
            {extraOps.map((op) => (
              <div
                key={op}
                className="flex items-baseline justify-between gap-2 text-[11px] font-mono tabular-nums"
              >
                <span className="text-zinc-500 truncate">{op}</span>
                <span className="text-zinc-300">{(counts[op] || 0).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {orderedOps.length === 0 && extraOps.length === 0 && (
        <div className="rounded-[1.5rem] border border-dashed border-zinc-800/50 p-6 text-center">
          <div className="text-[12px] text-zinc-500">
            No spans recorded yet. Run a job to see live span counts.
          </div>
        </div>
      )}
    </div>
  );
}
