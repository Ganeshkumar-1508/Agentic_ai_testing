"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Puzzle, Package, Plug, Power, PowerOff, ExternalLink } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface PluginInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  source: string;
  requires_env: string[];
  provides_tools: string[];
  provides_hooks: string[];
  kind: string;
}

export function PluginManagerSettings() {
  const { data, isLoading } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.get<{ plugins: PluginInfo[]; total: number }>("/api/ops/plugins"),
    refetchInterval: 30_000,
  });

  const plugins = data?.plugins ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><Puzzle size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
        <div><h3 className="text-sm font-medium text-zinc-200">Plugins</h3><p className="text-xs text-zinc-500">{data?.total ?? 0} plugin(s) discovered</p></div>
      </div>

      {isLoading ? (
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-24 rounded-xl shimmer-bg" />)}</div>
      ) : plugins.length === 0 ? (
        <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-12 text-center">
          <Package size={32} className="mx-auto text-zinc-700 mb-3" strokeWidth={1} />
          <p className="text-sm text-zinc-500">No plugins found</p>
          <p className="text-xs text-zinc-700 mt-1">Install plugins to ~/.testai/plugins/&lt;name&gt;/ with a plugin.yaml manifest</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {plugins.map((plugin, i) => (
            <motion.div key={plugin.name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
              className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-5 space-y-3"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-zinc-800/50 flex items-center justify-center"><Plug size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
                  <div>
                    <h4 className="text-sm font-medium text-zinc-200">{plugin.name}</h4>
                    <p className="text-xs text-zinc-500">{plugin.description || "No description"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500 font-mono border border-zinc-700/30">{plugin.version || "-"}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/30 text-indigo-400 font-mono border border-indigo-800/30">{plugin.source}</span>
                </div>
              </div>

              <div className="flex flex-wrap gap-4 text-[11px] text-zinc-600">
                {plugin.author && <span>By {plugin.author}</span>}
                {plugin.kind && <span>Kind: {plugin.kind}</span>}
                {plugin.provides_tools?.length ? <span>{plugin.provides_tools.length} tool(s)</span> : null}
                {plugin.provides_hooks?.length ? <span>{plugin.provides_hooks.length} hook(s)</span> : null}
              </div>

              {plugin.requires_env?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {plugin.requires_env.map((env) => (
                    <span key={env} className="text-[10px] px-2 py-0.5 rounded-md bg-amber-900/20 text-amber-500 font-mono border border-amber-800/20">{env}</span>
                  ))}
                </div>
              ) : null}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
