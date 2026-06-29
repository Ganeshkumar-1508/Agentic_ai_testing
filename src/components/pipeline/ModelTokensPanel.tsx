"use client";

import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Cpu, Coins, Gauge, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";

/** Per-model token/call aggregation derived from the raw
 * `event_data` payload of the run's trace events. The backend
 * (harness/trace.py) writes OTel GenAI semconv attrs to the span
 * (`gen_ai.request.model`, `gen_ai.usage.input_tokens`,
 * `gen_ai.usage.output_tokens`, `gen_ai.provider.name`) and a
 * legacy payload to the `trace_events` row's `event_data` JSONB.
 *
 * Both are accepted here so the panel works on spans from any
 * version of `trace.py`. We project legacy keys to the semconv
 * names at the read site (no transform middleware).
 */
interface ModelStats {
  model: string;
  provider: string;
  calls: number;
  inputTokens: number;
  outputTokens: number;
}

interface RawTraceEvent {
  id?: string;
  eventType?: string;
  eventData?: Record<string, unknown>;
}

const PROVIDER_FROM_MODEL: Record<string, string> = {
  "gpt-4": "openai", "gpt-4o": "openai", "gpt-4-turbo": "openai", "gpt-3.5": "openai", "o1": "openai", "o3": "openai",
  "claude-3-5": "anthropic", "claude-3": "anthropic", "claude-sonnet": "anthropic", "claude-opus": "anthropic",
  "gemini-1.5": "google", "gemini-2": "google", "gemini-pro": "google",
  "deepseek-chat": "deepseek", "deepseek-coder": "deepseek", "deepseek-r1": "deepseek",
  "moonshot-v1": "moonshot", "kimi": "moonshot",
  "command-r": "cohere", "embed-english": "cohere",
  "mistral-large": "mistral_ai", "mistral": "mistral_ai", "mixtral": "mistral_ai",
};

function inferProvider(model: string): string {
  const m = (model || "").toLowerCase();
  for (const [prefix, provider] of Object.entries(PROVIDER_FROM_MODEL)) {
    if (m.startsWith(prefix)) return provider;
  }
  if (m.includes("/")) return m.split("/")[0];  // "openai/gpt-4o" -> "openai"
  return "unknown";
}

/** Project the raw event_data to the OTel semconv names. */
function project(data: Record<string, unknown>): ModelStats | null {
  if (!data) return null;
  // OTel semconv names (set by harness/trace.py post-C7.1)
  let model =
    (data["gen_ai.request.model"] as string) ??
    (data["model"] as string) ??
    (data["model_name"] as string);
  const inputTokens = Number(
    (data["gen_ai.usage.input_tokens"] as number) ??
    (data["prompt_tokens"] as number) ??
    (data["input_tokens"] as number) ??
    0,
  );
  const outputTokens = Number(
    (data["gen_ai.usage.output_tokens"] as number) ??
    (data["completion_tokens"] as number) ??
    (data["output_tokens"] as number) ??
    0,
  );
  if (!model && inputTokens === 0 && outputTokens === 0) return null;
  const provider =
    (data["gen_ai.provider.name"] as string) ??
    inferProvider(model || "");
  return {
    model: model || "(unknown)",
    provider,
    calls: 1,
    inputTokens,
    outputTokens,
  };
}

function aggregate(events: RawTraceEvent[]): {
  byModel: ModelStats[];
  totalInput: number;
  totalOutput: number;
  totalCalls: number;
} {
  const bucket = new Map<string, ModelStats>();
  let totalInput = 0;
  let totalOutput = 0;
  let totalCalls = 0;

  for (const ev of events) {
    const t = ev.eventType ?? "";
    if (
      t !== "llm:call" &&
      t !== "llm.completion" &&
      t !== "llm_completion" &&
      t !== "chat.completion" &&
      t !== "llmcall.completed" &&
      t !== "llmcall.started" &&
      t !== "agent.llm"
    ) {
      continue;
    }
    const stat = project(ev.eventData ?? {});
    if (!stat) continue;
    const key = `${stat.provider}::${stat.model}`;
    const cur = bucket.get(key);
    if (cur) {
      cur.calls += 1;
      cur.inputTokens += stat.inputTokens;
      cur.outputTokens += stat.outputTokens;
    } else {
      bucket.set(key, { ...stat });
    }
    totalInput += stat.inputTokens;
    totalOutput += stat.outputTokens;
    totalCalls += 1;
  }

  const byModel = Array.from(bucket.values()).sort(
    (a, b) => b.inputTokens + b.outputTokens - (a.inputTokens + a.outputTokens),
  );
  return { byModel, totalInput, totalOutput, totalCalls };
}

export function ModelTokensPanel({ runId }: { runId: string }) {
  const [events, setEvents] = useState<RawTraceEvent[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    api.get<{ events?: RawTraceEvent[] }>(`/api/runs/${runId}/trace-events?limit=1000`)
      .then((data) => {
        setEvents(data?.events ?? []);
      })
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [runId]);

  const stats = useMemo(() => aggregate(events), [events]);

  if (loading) {
    return (
      <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
        <div className="flex items-center gap-2 text-[11px] text-neutral-500">
          <Loader2 className="w-3 h-3 animate-spin" />
          Loading model usage…
        </div>
      </div>
    );
  }

  if (stats.totalCalls === 0) {
    return (
      <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
        <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5" strokeWidth={1.5} />
          Model &amp; Tokens
        </div>
        <div className="text-[11px] text-neutral-600 text-center py-3">
          No LLM events in this run. OTel attrs surface here when the
          orchestrator emits a chat-completion trace.
        </div>
      </div>
    );
  }

  const maxTokens = Math.max(
    1,
    ...stats.byModel.map((m) => m.inputTokens + m.outputTokens),
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="bg-surface border border-white/[0.05] rounded-3xl p-5"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5" strokeWidth={1.5} />
          Model &amp; Tokens
          <span className="text-[9px] font-mono text-neutral-600 normal-case tracking-normal ml-1">
            (OTel&nbsp;gen_ai.*)
          </span>
        </div>
        <div className="text-[10px] font-mono text-neutral-600">
          {stats.totalCalls} calls
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-4">
        <div className="rounded-lg border border-white/[0.04] bg-white/[0.02] p-2.5">
          <div className="text-[9px] uppercase tracking-wider text-neutral-600 mb-0.5">
            Input
          </div>
          <div className="text-[14px] font-mono tabular-nums text-zinc-300">
            {stats.totalInput.toLocaleString()}
          </div>
        </div>
        <div className="rounded-lg border border-white/[0.04] bg-white/[0.02] p-2.5">
          <div className="text-[9px] uppercase tracking-wider text-neutral-600 mb-0.5">
            Output
          </div>
          <div className="text-[14px] font-mono tabular-nums text-emerald-300">
            {stats.totalOutput.toLocaleString()}
          </div>
        </div>
        <div className="rounded-lg border border-white/[0.04] bg-white/[0.02] p-2.5">
          <div className="text-[9px] uppercase tracking-wider text-neutral-600 mb-0.5 flex items-center gap-1">
            <Gauge className="w-2.5 h-2.5" /> Models
          </div>
          <div className="text-[14px] font-mono tabular-nums text-zinc-300">
            {stats.byModel.length}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {stats.byModel.map((m) => {
          const total = m.inputTokens + m.outputTokens;
          const pct = Math.round((total / maxTokens) * 100);
          return (
            <div key={`${m.provider}::${m.model}`} className="space-y-1">
              <div className="flex items-center gap-2 text-[11px]">
                <span className="font-mono text-neutral-200 truncate flex-1">
                  {m.model}
                </span>
                <span className="text-[9px] font-mono text-neutral-600 shrink-0">
                  {m.provider}
                </span>
                <span className="text-[10px] font-mono tabular-nums text-neutral-400 shrink-0">
                  {total.toLocaleString()}t
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-white/[0.04] overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  className={cn(
                    "h-full rounded-full",
                    "bg-emerald-500/70",
                  )}
                />
              </div>
              <div className="flex items-center gap-3 text-[9px] font-mono text-neutral-600">
                <span>
                  in{" "}
                  <span className="text-zinc-300/80">
                    {m.inputTokens.toLocaleString()}
                  </span>
                </span>
                <span>
                  out{" "}
                  <span className="text-emerald-300/80">
                    {m.outputTokens.toLocaleString()}
                  </span>
                </span>
                <span>
                  <Coins className="w-2.5 h-2.5 inline" /> {m.calls} calls
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
