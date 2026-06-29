"use client";

import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { Cpu, DollarSign, Activity, CheckCircle2, XCircle, Loader2, HeartPulse } from "lucide-react";

interface Provider {
  provider: string; model: string; base_url: string; enabled: boolean; has_key: boolean;
  display_name?: string; auth_type?: string; api_mode?: string;
}

interface ModelCost {
  model: string; input_tokens: number; output_tokens: number; estimated_cost: number; api_calls: number;
}

function containerVariants(delay: number) {
  return { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const, delay } } };
}

const PROVIDER_ORDER = ["openai", "anthropic", "google", "deepseek", "openrouter", "together", "groq"];

export default function ModelsPage() {
  const { data: providers, isLoading: pl } = useQuery<Provider[]>({
    queryKey: ["providers"],
    queryFn: () => api.get("/api/settings/providers"),
  });

  const { data: costData, isLoading: cl } = useQuery<{ models: ModelCost[] }>({
    queryKey: ["model-costs"],
    queryFn: () => api.get("/api/cost/models/stats?days=30"),
  });

  const sorted = [...(providers ?? [])].sort((a, b) => {
    const ai = PROVIDER_ORDER.indexOf(a.provider);
    const bi = PROVIDER_ORDER.indexOf(b.provider);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  const models = costData?.models ?? [];
  const totalCost = models.reduce((s, m) => s + m.estimated_cost, 0);
  const totalCalls = models.reduce((s, m) => s + m.api_calls, 0);

  return (
    <div className="max-w-7xl mx-auto px-8 pt-6 pb-12">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">Infrastructure</div>
        <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Models & Providers</h1>
        <p className="text-[13px] text-zinc-500 mt-0.5">Configured LLM providers and model cost breakdown</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <motion.div variants={containerVariants(0.1)} initial="hidden" animate="show"
          className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5 flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px]">Providers</span>
          <span className="text-2xl font-semibold font-mono tracking-tight text-zinc-100">{sorted.length}</span>
          <span className="text-[11px] text-zinc-600">{sorted.filter(p => p.enabled).length} enabled</span>
        </motion.div>
        <motion.div variants={containerVariants(0.15)} initial="hidden" animate="show"
          className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5 flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px]">Total Cost (30d)</span>
          <span className="text-2xl font-semibold font-mono tracking-tight text-zinc-100">${totalCost.toFixed(2)}</span>
          <span className="text-[11px] text-zinc-600">{totalCalls} API calls</span>
        </motion.div>
        <motion.div variants={containerVariants(0.2)} initial="hidden" animate="show"
          className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5 flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px]">Models Used</span>
          <span className="text-2xl font-semibold font-mono tracking-tight text-zinc-100">{models.length}</span>
          <span className="text-[11px] text-zinc-600">Across all providers</span>
        </motion.div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4 mb-6">
        <motion.div variants={containerVariants(0.2)} initial="hidden" animate="show"
          className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px] mb-3">Provider Configuration</div>
          {pl ? (
            <div className="flex items-center justify-center py-8"><Loader2 className="w-4 h-4 animate-spin text-zinc-600" strokeWidth={1.5} /></div>
          ) : sorted.length === 0 ? (
            <div className="text-center py-8">
              <Cpu className="w-6 h-6 text-zinc-700 mx-auto mb-2" strokeWidth={1} />
              <p className="text-xs text-zinc-600">No providers configured</p>
              <p className="text-[10px] text-zinc-700 mt-1">Go to Settings to add a provider.</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {sorted.map((p, i) => (
                <motion.div key={p.provider} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
                  className="flex items-center justify-between p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                  <div className="flex items-center gap-2.5">
                    {p.enabled && p.has_key ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" strokeWidth={1.5} />
                    ) : (
                      <XCircle className="w-3.5 h-3.5 text-zinc-700 shrink-0" strokeWidth={1.5} />
                    )}
                    <div>
                      <p className="text-xs font-medium text-zinc-300">{p.display_name || p.provider}</p>
                      <p className="text-[10px] font-mono text-zinc-600">{p.model || "no model set"}</p>
                    </div>
                  </div>
                  <span className={cn("text-[9px] font-mono", p.enabled && p.has_key ? "text-emerald-500" : "text-zinc-700")}>
                    {p.api_mode || "chat"}
                  </span>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>

        <motion.div variants={containerVariants(0.3)} initial="hidden" animate="show"
          className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px] mb-3">Cost by Model</div>
          {cl ? (
            <div className="flex items-center justify-center py-8"><Loader2 className="w-4 h-4 animate-spin text-zinc-600" strokeWidth={1.5} /></div>
          ) : models.length === 0 ? (
            <div className="text-center py-8">
              <DollarSign className="w-6 h-6 text-zinc-700 mx-auto mb-2" strokeWidth={1} />
              <p className="text-xs text-zinc-600">No cost data yet</p>
              <p className="text-[10px] text-zinc-700 mt-1">Run a pipeline to see model cost breakdown.</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {models.slice(0, 10).map((m, i) => {
                const pct = totalCost > 0 ? (m.estimated_cost / totalCost) * 100 : 0;
                return (
                  <div key={m.model} className="flex items-center gap-3">
                    <span className="w-24 text-[10px] font-mono text-zinc-400 truncate" title={m.model}>{m.model.split("/").pop()}</span>
                    <div className="flex-1 h-5 rounded-md bg-white/[0.04] overflow-hidden">
                      <motion.div initial={{ width: 0 }} animate={{ width: `${Math.max(pct, 2)}%` }}
                        transition={{ delay: 0.3 + i * 0.04, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                        className="h-full rounded-md bg-emerald-500/30" />
                    </div>
                    <span className="w-16 text-right text-[10px] font-mono text-zinc-300">${m.estimated_cost.toFixed(2)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </motion.div>
      </div>

      <ProviderHealthSection />
    </div>
  );
}

function ProviderHealthSection() {
  const { data: healthData, isLoading } = useQuery({
    queryKey: ["provider-health"],
    queryFn: () => api.get<Record<string, { calls: number; successes: number; failures: number; total_latency_ms: number }>>("/api/health/provider-health"),
    refetchInterval: 30_000,
  });

  const models = healthData ? Object.entries(healthData).filter(([, h]) => h.calls > 0) : [];

  return (
    <motion.div variants={containerVariants(0.35)} initial="hidden" animate="show"
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] p-5 mt-6">
      <div className="flex items-center gap-2 mb-3">
        <HeartPulse className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-[0.6px]">Provider Health</span>
        <span className="text-[10px] text-zinc-600 font-mono">{models.length} active</span>
      </div>
      {isLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="w-4 h-4 animate-spin text-zinc-600" strokeWidth={1.5} /></div>
      ) : models.length === 0 ? (
        <div className="text-center py-8">
          <HeartPulse className="w-6 h-6 text-zinc-700 mx-auto mb-2" strokeWidth={1} />
          <p className="text-xs text-zinc-600">No health data yet</p>
          <p className="text-[10px] text-zinc-700 mt-1">Run some agent tasks to see provider performance metrics.</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {models.slice(0, 10).map(([model, h]) => {
            const sr = h.calls > 0 ? ((h.successes / h.calls) * 100).toFixed(0) : "0";
            const avgLatency = h.calls > 0 ? (h.total_latency_ms / h.calls / 1000).toFixed(1) : "0";
            const isHealthy = parseInt(sr) >= 80;
            return (
              <div key={model} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/[0.02] transition-colors">
                {isHealthy ? <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" strokeWidth={1.5} />
                  : <XCircle className="w-3 h-3 text-red-500 shrink-0" strokeWidth={1.5} />}
                <span className="text-[10px] font-mono text-zinc-400 w-32 truncate">{model.split("/").pop()}</span>
                <span className="text-[10px] font-mono text-zinc-600 w-16">{sr}% success</span>
                <span className="text-[10px] font-mono text-zinc-600 w-16">{avgLatency}s avg</span>
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${parseInt(sr)}%` }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className={`h-full rounded-full ${isHealthy ? "bg-emerald-500/50" : "bg-red-500/50"}`} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </motion.div>
  );
}
