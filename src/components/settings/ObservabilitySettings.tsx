"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Save, Activity, Radio, Server } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

interface ObservabilityConfig {
  otel_enabled: boolean;
  otel_endpoint: string;
  otel_protocol: string;
  otel_service_name: string;
}

export function ObservabilitySettings() {
  const { data, isLoading } = useQuery({
    queryKey: ["settings-observability"],
    queryFn: () => api.get<ObservabilityConfig>("/api/integrations/settings/observability"),
  });

  const [form, setForm] = useState<ObservabilityConfig>({
    otel_enabled: false,
    otel_endpoint: "http://localhost:4317",
    otel_protocol: "grpc",
    otel_service_name: "testai-harness",
  });

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const saveMut = useMutation({
    mutationFn: (body: ObservabilityConfig) =>
      api.put("/api/integrations/settings/observability", body),
    onSuccess: () => toast.success("Observability settings saved"),
    onError: () => toast.error("Failed to save"),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="h-24 rounded-[2rem] shimmer-bg" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Enable Toggle */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-[2rem] border border-white/[0.06] bg-white/[0.02] p-5"
      >
        <div className="flex items-center gap-4">
          <div className={cn(
            "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
            form.otel_enabled ? "bg-emerald-500/10" : "bg-white/[0.03]",
          )}>
            <Activity className={cn("w-5 h-5", form.otel_enabled ? "text-emerald-400" : "text-zinc-600")} strokeWidth={1.5} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-zinc-100">OpenTelemetry Tracing</div>
            <p className="text-xs text-zinc-600 mt-0.5">
              Export traces to an OpenTelemetry-compatible backend (Datadog, Honeycomb, Grafana Tempo, Langfuse, etc.)
            </p>
          </div>
          <button
            onClick={() => setForm((p) => ({ ...p, otel_enabled: !p.otel_enabled }))}
            className={cn(
              "relative w-10 h-5 rounded-full transition-colors",
              form.otel_enabled ? "bg-emerald-500" : "bg-zinc-700",
            )}
          >
            <span className={cn(
              "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform",
              form.otel_enabled ? "translate-x-5" : "translate-x-0",
            )} />
          </button>
        </div>
      </motion.div>

      {/* OTLP Endpoint */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="rounded-[2rem] border border-white/[0.06] bg-white/[0.02] p-5"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <Radio className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          </div>
          <div>
            <div className="text-sm font-semibold text-zinc-100">OTLP Endpoint</div>
            <p className="text-xs text-zinc-600 mt-0.5">
              gRPC endpoint for the OpenTelemetry collector (e.g., api.honeycomb.com:4317)
            </p>
          </div>
        </div>
        <input
          value={form.otel_endpoint}
          onChange={(e) => setForm((p) => ({ ...p, otel_endpoint: e.target.value }))}
          placeholder="http://localhost:4317"
          className="w-full h-10 px-3 rounded-xl bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30 font-mono transition-colors"
        />
      </motion.div>

      {/* Service Name */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-[2rem] border border-white/[0.06] bg-white/[0.02] p-5"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <Server className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          </div>
          <div>
            <div className="text-sm font-semibold text-zinc-100">Service Name</div>
            <p className="text-xs text-zinc-600 mt-0.5">Identifies this service in your observability backend</p>
          </div>
        </div>
        <input
          value={form.otel_service_name}
          onChange={(e) => setForm((p) => ({ ...p, otel_service_name: e.target.value }))}
          placeholder="testai-harness"
          className="w-full h-10 px-3 rounded-xl bg-zinc-800 border border-white/[0.06] text-xs text-zinc-300 placeholder:text-zinc-700 outline-none focus:border-emerald-500/30 font-mono transition-colors"
        />
      </motion.div>

      {/* Info card */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="rounded-[2rem] border border-zinc-800/50 bg-zinc-900/30 p-4"
      >
        <p className="text-[11px] text-zinc-600 leading-relaxed">
          Requires restart to take effect. Set <code className="text-zinc-400 bg-zinc-800 px-1 rounded">OTEL_ENABLED=true</code> environment variable
          as well, or enable above and the system will pick it up on next agent run.
          Compatible with any OTLP-gRPC backend: Datadog, Honeycomb, Grafana Tempo,
          SigNoz, Langfuse, or your own OpenTelemetry Collector.
        </p>
      </motion.div>

      {/* Save */}
      <div className="flex justify-end">
        <button
          onClick={() => saveMut.mutate(form)}
          disabled={saveMut.isPending}
          className="inline-flex items-center gap-1.5 px-4 h-9 rounded-xl bg-emerald-500/15 text-emerald-400 text-xs font-semibold hover:bg-emerald-500/25 transition-colors active:scale-[0.97] disabled:opacity-40"
        >
          <Save className="w-3.5 h-3.5" strokeWidth={2} />
          {saveMut.isPending ? "Saving…" : "Save Changes"}
        </button>
      </div>
    </div>
  );
}
