"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Puzzle, Package, Plug, Power, PowerOff, Trash2, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import { useState } from "react";

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
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.get<{ plugins: PluginInfo[]; total: number }>("/api/ops/plugins"),
    refetchInterval: 30_000,
  });

  const enableMut = useMutation({
    mutationFn: (name: string) => api.post(`/api/ops/plugins/${name}/enable`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["plugins"] }); toast.success("Plugin enabled"); },
    onError: () => toast.error("Failed to enable plugin"),
  });

  const disableMut = useMutation({
    mutationFn: (name: string) => api.post(`/api/ops/plugins/${name}/disable`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["plugins"] }); toast.success("Plugin disabled"); },
    onError: () => toast.error("Failed to disable plugin"),
  });

  const uninstallMut = useMutation({
    mutationFn: (name: string) => api.delete(`/api/ops/plugins/${name}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["plugins"] }); toast.success("Plugin uninstalled"); },
    onError: () => toast.error("Failed to uninstall plugin"),
  });

  const plugins = data?.plugins ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center">
          <Puzzle size={16} className="text-zinc-400" strokeWidth={1.5} />
        </div>
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Plugins</h3>
          <p className="text-xs text-zinc-500">{data?.total ?? 0} plugin(s) discovered</p>
        </div>
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
                <div className="flex items-center gap-3 cursor-pointer flex-1" onClick={() => setExpanded(expanded === plugin.name ? null : plugin.name)}>
                  <div className="w-9 h-9 rounded-xl bg-zinc-800/50 flex items-center justify-center">
                    <Plug size={16} className={cn("text-zinc-400", plugin.source === "bundled" ? "text-emerald-400" : "text-zinc-400")} strokeWidth={1.5} />
                  </div>
                  <div className="flex-1">
                    <h4 className="text-sm font-medium text-zinc-200">{plugin.name}</h4>
                    <p className="text-xs text-zinc-500">{plugin.description || "No description"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500 font-mono border border-zinc-700/30">{plugin.version || "-"}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-900/30 text-indigo-400 font-mono border border-indigo-800/30">{plugin.source}</span>
                    {expanded === plugin.name ? <ChevronDown size={12} className="text-zinc-500" /> : <ChevronRight size={12} className="text-zinc-500" />}
                  </div>
                </div>
              </div>

              <AnimatePresence>
                {expanded === plugin.name && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden space-y-3">
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
                    <div className="flex gap-2 pt-1">
                      <button onClick={() => enableMut.mutate(plugin.name)} className="px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors flex items-center gap-1.5">
                        <Power size={11} strokeWidth={1.5} /> Enable
                      </button>
                      <button onClick={() => disableMut.mutate(plugin.name)} className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors flex items-center gap-1.5">
                        <PowerOff size={11} strokeWidth={1.5} /> Disable
                      </button>
                      {plugin.source !== "bundled" && (
                        <button onClick={() => { if (confirm(`Uninstall plugin "${plugin.name}"?`)) uninstallMut.mutate(plugin.name); }}
                          className="px-3 py-1.5 text-xs rounded-lg bg-red-900/20 text-red-400 hover:bg-red-900/40 transition-colors flex items-center gap-1.5 ml-auto">
                          <Trash2 size={11} strokeWidth={1.5} /> Uninstall
                        </button>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
