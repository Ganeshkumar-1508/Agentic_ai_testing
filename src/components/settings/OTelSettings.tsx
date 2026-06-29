"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Activity, CheckCircle2, XCircle, Loader2, Save,
  Radio, Wifi, WifiOff,
} from "lucide-react";

export function OTelSettings() {
  const [endpoint, setEndpoint] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["otel-status"],
    queryFn: async () => {
      const res = await api.get<{
        enabled: boolean; available: boolean; endpoint: string;
        service_name: string; span_counts: Record<string, number>;
        last_span_at: string | null;
      }>("/api/observability/status");
      return res;
    },
    refetchInterval: 10_000,
  });

  if (data && !loaded) {
    setEndpoint(data.endpoint);
    setServiceName(data.service_name);
    setEnabled(data.enabled);
    setLoaded(true);
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      await api.post("/api/settings/otel", {
        endpoint, service_name: serviceName, enabled,
      });
    },
    onSuccess: () => toast.success("OTEL settings saved (restart required)"),
    onError: () => toast.error("Failed to save"),
  });

  const isLive = data?.available && data?.enabled;
  const spanCount = data?.span_counts
    ? Object.values(data.span_counts).reduce((a: number, b: number) => a + b, 0)
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-zinc-800/40 flex items-center justify-center">
          <Activity size={13} className="text-zinc-400" strokeWidth={1.5} />
        </div>
        <div>
          <div className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">OpenTelemetry</div>
          <p className="text-[11px] text-zinc-600 mt-0.5">Export traces to Jaeger, Grafana, Aspire, or any OTLP-compatible backend</p>
        </div>
      </div>

      {/* Connection status */}
      <div className={cn("rounded-xl border p-4 space-y-2",
        isLive ? "border-emerald-500/20 bg-emerald-500/5" : "border-zinc-800/30 bg-zinc-900/20")}>
        <div className="flex items-center gap-2">
          {isLoading ? (
            <Loader2 size={12} className="animate-spin text-zinc-600" />
          ) : isLive ? (
            <Wifi size={14} className="text-emerald-400" strokeWidth={1.5} />
          ) : (
            <WifiOff size={14} className="text-zinc-500" strokeWidth={1.5} />
          )}
          <span className={cn("text-[11px] font-medium",
            isLive ? "text-emerald-400" : "text-zinc-500")}>
            {isLive ? "Connected" : data?.enabled ? "Not connected (check endpoint)" : "Disabled"}
          </span>
          {spanCount > 0 && (
            <span className="text-[10px] text-zinc-600 font-mono ml-auto">{spanCount} spans</span>
          )}
        </div>
        {data?.last_span_at && (
          <p className="text-[9px] text-zinc-700 font-mono">Last span: {new Date(data.last_span_at).toLocaleString()}</p>
        )}
        {data?.span_counts && Object.keys(data.span_counts).length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {Object.entries(data.span_counts).map(([op, count]) => (
              <span key={op} className="text-[8px] px-1.5 py-0.5 rounded bg-zinc-800/50 text-zinc-500 font-mono">
                {op}: {count}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Config form */}
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <button onClick={() => setEnabled(!enabled)}
            className={cn("relative w-9 h-5 rounded-full transition-colors",
              enabled ? "bg-emerald-500" : "bg-zinc-700")}>
            <span className={cn("absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform",
              enabled ? "translate-x-4" : "translate-x-0")} />
          </button>
          <span className="text-[11px] text-zinc-400">OpenTelemetry export</span>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-zinc-600 font-medium">OTLP Endpoint</label>
          <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)}
            placeholder="http://localhost:4317"
            className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-[11px] text-zinc-300 font-mono placeholder-zinc-700 outline-none focus:border-emerald-500/40" />
          <p className="text-[9px] text-zinc-700">gRPC default: :4317, HTTP default: :4318</p>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-zinc-600 font-medium">Service Name</label>
          <input value={serviceName} onChange={(e) => setServiceName(e.target.value)}
            placeholder="testai-harness"
            className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-[11px] text-zinc-300 font-mono placeholder-zinc-700 outline-none focus:border-emerald-500/40" />
        </div>

        <button onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] hover:bg-emerald-500/20 transition-all active:scale-[0.97] disabled:opacity-40">
          {saveMut.isPending ? <Loader2 size={10} className="animate-spin" /> : <Save size={10} strokeWidth={1.5} />}
          Save
        </button>
      </div>

      {/* Quick reference */}
      <div className="rounded-xl border border-zinc-800/30 bg-zinc-900/20 p-4 space-y-2">
        <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">Quick Start</span>
        <div className="text-[10px] text-zinc-600 font-mono space-y-1">
          <p><span className="text-zinc-500"># Jaeger (Docker)</span></p>
          <p className="text-zinc-500">docker run -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one</p>
          <p className="mt-2"><span className="text-zinc-500"># Grafana / Aspire</span></p>
          <p className="text-zinc-500">docker run -p 18888:18888 mcr.microsoft.com/dotnet/aspire-dashboard:latest</p>
          <p className="mt-2"><span className="text-zinc-500"># Set endpoint to:</span></p>
          <p className="text-zinc-500">http://host.docker.internal:4317 (from container)</p>
        </div>
      </div>
    </div>
  );
}
