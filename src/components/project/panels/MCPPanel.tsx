"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Plug, Wifi, WifiOff } from "lucide-react";
import { api } from "@/lib/api/api-client";

export function MCPPanel() {
  const { data: serversData } = useQuery({
    queryKey: ["settings", "mcp"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/mcp`))?? {};
    },
  });
  const { data: connectionsData } = useQuery({
    queryKey: ["settings", "mcp", "connections"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/mcp/connections`))?? {};
    },
  });

  const servers = (serversData as any)?.servers ?? [];
  const connections = (connectionsData as any)?.connections ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-medium text-zinc-100 tracking-tight">MCP Servers</h2>
        <p className="text-sm text-zinc-500 mt-1">Browse and manage tools from connected MCP servers</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Configured Servers */}
        <div className="shimmer-bg border border-zinc-800/30 rounded-3xl p-5 space-y-3">
          <h3 className="text-sm font-medium text-zinc-300 tracking-tight">Configured Servers</h3>
          {servers.length === 0 ? (
            <p className="text-xs text-zinc-600">No MCP servers configured</p>
          ) : (
            <div className="divide-y divide-zinc-800/20">
              {servers.map((s: any) => (
                <div key={s.id} className="flex items-center justify-between py-2.5">
                  <div className="flex items-center gap-2">
                    {s.enabled ? <Wifi size={14} className="text-emerald-400/80" strokeWidth={1.5} /> : <WifiOff size={14} className="text-zinc-600" strokeWidth={1.5} />}
                    <span className="text-sm text-zinc-300">{s.displayName || s.name}</span>
                  </div>
                  <span className="text-[10px] text-zinc-600">{s.category}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Active Connections */}
        <div className="shimmer-bg border border-zinc-800/30 rounded-3xl p-5 space-y-3">
          <h3 className="text-sm font-medium text-zinc-300 tracking-tight">Active Connections</h3>
          {connections.length === 0 ? (
            <p className="text-xs text-zinc-600">No active connections</p>
          ) : (
            <div className="divide-y divide-zinc-800/20">
              {connections.map((c: any) => (
                <div key={c.id} className="py-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-300">{c.name}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${c.connected ? "bg-emerald-500/10 text-emerald-400/80" : "bg-red-500/10 text-red-400/80"}`}>
                      {c.connected ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-600 mt-1">{c.tools?.length ?? 0} tools available</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
