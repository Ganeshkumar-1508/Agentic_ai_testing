"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { HeartPulse, Cpu, Plug, Activity, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api/api-client";


function PulseDot({ active }: { active: boolean }) {
  return (
    <span className="relative inline-flex ml-auto">
      <span className={`w-1.5 h-1.5 rounded-full ${active ? "bg-emerald-400/80" : "bg-zinc-700"}`} />
      {active && <span className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-emerald-400/30 animate-ping" />}
    </span>
  );
}

export function HealthPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "health", "providers"],
    queryFn: async () => {
      const [providers, connections, modesResp] = await Promise.all([
        api.get<any>(`/api/settings/providers`),
        api.get<{ connections?: any[] }>(`/api/settings/mcp/connections`),
        api.get<{ modes?: any[] }>(`/api/modes`).catch(() => ({ modes: [] })),
      ]);
      return {
        providers: Array.isArray(providers) ? providers : [],
        connections: connections?.connections ?? [],
        modes: modesResp?.modes ?? [],
      };
    },
    refetchInterval: 30_000,
  });

  const testMutation = useMutation({
    mutationFn: async (provider: string) => {
      await api.post(`/api/settings/providers/test-connection`, { provider, api_key: "", base_url: "", model: "" });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "health"] }),
  });

  const providers = data?.providers ?? [];
  const connections = data?.connections ?? [];
  const modes = data?.modes ?? [];
  const configuredCount = providers.filter((p: any) => p.has_key).length;
  const connectedCount = connections.filter((c: any) => c.connected).length;

  const kpis = [
    { label: "Providers", value: `${configuredCount}/${providers.length}`, icon: Cpu, desc: "with valid keys", delay: 0 },
    { label: "MCP Servers", value: `${connectedCount}`, icon: Plug, desc: "active connections", delay: 0.05 },
    { label: "Backend", value: "Healthy", icon: HeartPulse, desc: "API responding", delay: 0.1 },
    { label: "Modes", value: String(modes.length || 5), icon: Activity, desc: modes.length > 0 ? modes.join("/").slice(0, 40) : "auto/ask/debug", delay: 0.15 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-zinc-100 tracking-tight">System Health</h2>
        <p className="text-sm text-zinc-500 mt-1">Provider status, MCP connections, and backend health</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_1fr_1fr] gap-4">
        {kpis.map((k) => (
          <motion.div key={k.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: k.delay, ease: [0.16, 1, 0.3, 1] }}
            className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 hover:border-zinc-700/50 transition-colors">
            <div className="flex items-center justify-between mb-3">
              <k.icon size={14} className="text-zinc-500" strokeWidth={1.5} />
              <PulseDot active={true} />
            </div>
            <div className="text-2xl font-semibold tracking-tight text-zinc-100">{k.value}</div>
            <div className="text-xs text-zinc-600 mt-1">{k.desc}</div>
          </motion.div>
        ))}
      </div>

      <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-800/30 flex items-center justify-between">
          <p className="text-xs text-zinc-500 tracking-wider uppercase">LLM Providers</p>
          <button onClick={() => testMutation.mutate("all")} className="text-[10px] px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.97]">
            Test All
          </button>
        </div>
        <div className="divide-y divide-zinc-800/20">
          {providers.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-zinc-600">No providers configured</div>
          )}
          {providers.map((p: any, i: number) => (
            <div key={p.provider} className="flex items-center justify-between px-5 py-3 hover:bg-zinc-900/30 transition-colors">
              <div className="flex items-center gap-3">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/60" />
                <span className="text-sm text-zinc-300">{p.provider}</span>
                <span className="text-xs text-zinc-500 font-mono">{p.model}</span>
              </div>
              <div className="flex items-center gap-3">
                {p.base_url && <span className="text-xs text-zinc-600 font-mono hidden md:inline max-w-[160px] truncate">{p.base_url}</span>}
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${p.has_key ? "bg-emerald-500/10 text-emerald-400/80" : "bg-zinc-800/50 text-zinc-500"}`}>
                  {p.has_key ? "Active" : "No Key"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-800/30">
          <p className="text-xs text-zinc-500 tracking-wider uppercase">MCP Connections</p>
        </div>
        <div className="divide-y divide-zinc-800/20">
          {connections.length === 0 && (
            <div className="px-5 py-4 text-sm text-zinc-600">No MCP servers configured</div>
          )}
          {connections.map((c: any) => (
            <div key={c.id} className="flex items-center justify-between px-5 py-3 hover:bg-zinc-900/30 transition-colors">
              <div className="flex items-center gap-3">
                <PulseDot active={c.connected} />
                <span className="text-sm text-zinc-300">{c.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-zinc-500">{c.tools?.length ?? 0} tools</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${c.connected ? "bg-emerald-500/10 text-emerald-400/80" : "bg-red-500/10 text-red-400/80"}`}>
                  {c.connected ? "Connected" : "Disconnected"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
