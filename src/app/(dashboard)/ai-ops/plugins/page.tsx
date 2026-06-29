"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { StatsCard } from "@/components/shared/StatsCard";
import { PulseDot } from "@/components/ai-ops/PulseDot";
import { Puzzle, Workflow, Wrench, Package, Plus, Search } from "lucide-react";
import { api } from "@/lib/api/api-client";

type Plugin = {
  name: string;
  version: string;
  description: string;
  author: string;
  source: string;
  requires_env: string[];
  provides_tools: string[];
  provides_hooks: string[];
  kind: string;
  path: string;
};

type HookInfo = {
  name: string;
  handler_count: number;
  handler_names: string[];
};

type HookCategories = Record<string, HookInfo[]>;

function sourceBadge(source: string) {
  const colors: Record<string, string> = {
    bundled: "bg-emerald-500/10 text-emerald-400/80",
    user: "bg-zinc-500/10 text-zinc-400/80",
    project: "bg-amber-500/10 text-amber-400/80",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${colors[source] ?? "bg-zinc-800 text-zinc-500"}`}>
      {source}
    </span>
  );
}

function hookColor(hookName: string): string {
  const agentLoop = ["pre_llm_call", "post_llm_call", "pre_tool_call", "post_tool_call", "on_session_start", "on_session_end"];
  const transform = ["transform_llm_output", "transform_tool_result", "transform_terminal_output"];
  const subagent = ["subagent_stop", "pre_approval_request", "post_approval_response"];
  if (agentLoop.includes(hookName)) return "bg-emerald-500/10 text-emerald-400/80 border-emerald-500/20";
  if (transform.includes(hookName)) return "bg-zinc-500/10 text-zinc-400/80 border-zinc-500/20";
  if (subagent.includes(hookName)) return "bg-rose-500/10 text-rose-400/80 border-rose-500/20";
  return "bg-zinc-800 text-zinc-500";
}

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [hookData, setHookData] = useState<HookCategories | null>(null);
  const [totalHooks, setTotalHooks] = useState(0);
  const [totalHandlers, setTotalHandlers] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [plugData, hookData] = await Promise.all([
          api.get<{ plugins?: Plugin[] }>("/api/ops/plugins"),
          api.get<{ categories?: HookCategories; total_hooks?: number; total_handlers?: number }>("/api/ops/plugins/hooks"),
        ]);
        setPlugins(plugData?.plugins ?? []);
        setHookData(hookData?.categories ?? null);
        setTotalHooks(hookData?.total_hooks ?? 0);
        setTotalHandlers(hookData?.total_handlers ?? 0);
      } catch {
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const activePlugins = plugins.filter((p) => p.source !== "project" || true).length;
  const toolsFromPlugins = plugins.reduce((sum, p) => sum + p.provides_tools.length, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard icon={<Package size={16} />} label="Active Plugins" value={plugins.length} sub={`${plugins.filter((p) => p.source === "bundled").length} bundled`} delay={0.05} />
        <StatsCard icon={<Workflow size={16} />} label="Hooks Registered" value={totalHooks} sub={`${totalHandlers} total handlers`} delay={0.1} />
        <StatsCard icon={<Wrench size={16} />} label="Tools Added" value={toolsFromPlugins} sub="from plugin registration" delay={0.15} />
        <StatsCard icon={<Puzzle size={16} />} label="Hook Categories" value={hookData ? Object.keys(hookData).length : 0} sub="agent loop, transform, subagent" delay={0.2} />
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4">
            {[0, 1].map((i) => <div key={i} className="h-32 rounded-2xl shimmer-bg border border-zinc-800/30" />)}
          </motion.div>
        ) : (
          <motion.div key="content" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="space-y-6">
            {/* Installed Plugins */}
            <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-sm font-medium text-zinc-100">Installed Plugins</h2>
                <div className="flex gap-2">
                  <button className="px-3 py-1.5 text-xs rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors inline-flex items-center gap-1.5">
                    <Search size={10} strokeWidth={1.5} /> Discover
                  </button>
                  <button className="px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors inline-flex items-center gap-1.5">
                    <Plus size={10} strokeWidth={1.5} /> Install
                  </button>
                </div>
              </div>

              {plugins.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-zinc-600">
                  <Package size={28} className="opacity-20 mb-2" strokeWidth={1} />
                  <p className="text-sm">No plugins installed</p>
                  <p className="text-xs mt-1">Drop a plugin.yaml + __init__.py into backend/plugins/</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {plugins.map((p) => {
                    const initial = p.name.charAt(0).toUpperCase();
                    return (
                      <div key={p.name} className="flex items-center gap-4 p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.03] transition-colors">
                        <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center text-sm font-bold text-black shrink-0">
                          {initial}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-zinc-100">{p.name}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 font-mono">v{p.version || "?"}</span>
                            {sourceBadge(p.source)}
                          </div>
                          <p className="text-xs text-zinc-500 mt-0.5 truncate">{p.description || "No description"}</p>
                          <div className="flex gap-3 mt-1.5 text-[10px] flex-wrap">
                            {p.provides_tools.length > 0 && (
                              <span className="text-zinc-600 font-mono">Tools: {p.provides_tools.join(", ") || "(none)"}</span>
                            )}
                            {p.provides_hooks.length > 0 && (
                              <span className="text-zinc-600 font-mono">Hooks: {p.provides_hooks.join(", ")}</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <PulseDot color="bg-emerald-400" />
                          <span className="text-[10px] text-emerald-400/80 font-mono">Active</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Hook Visualization + Sources */}
            <div className="grid grid-cols-1 md:grid-cols-[3fr_2fr] gap-6">
              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <h2 className="text-sm font-medium text-zinc-100 mb-5">Hook Visualization</h2>
                {!hookData || Object.keys(hookData).length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-24 text-zinc-600">
                    <p className="text-xs">No hooks registered</p>
                  </div>
                ) : (
                  <div className="space-y-5">
                    {Object.entries(hookData).map(([category, hooks]) => (
                      <div key={category}>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">{category}</span>
                          <span className="text-[10px] text-zinc-600 font-mono">{hooks.length} hooks</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {hooks.map((h) => (
                            <span
                              key={h.name}
                              className={`px-2 py-1 text-[10px] rounded-md border font-mono ${hookColor(h.name)}`}
                            >
                              {h.name}
                              {h.handler_count > 0 && (
                                <span className="ml-1 opacity-60">({h.handler_count})</span>
                              )}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800/50 rounded-2xl p-6">
                <h2 className="text-sm font-medium text-zinc-100 mb-5">Plugin Sources</h2>
                <div className="space-y-3">
                  {[
                    { label: "Bundled", path: "backend/plugins/", icon: "B", color: "bg-emerald-500/10 text-emerald-400", count: plugins.filter((p) => p.source === "bundled").length },
                    { label: "User", path: "~/.testai/plugins/", icon: "U", color: "bg-zinc-500/10 text-zinc-400", count: plugins.filter((p) => p.source === "user").length },
                    { label: "Project", path: ".testai/plugins/", icon: "P", color: "bg-zinc-600/30 text-zinc-500", count: plugins.filter((p) => p.source === "project").length },
                  ].map((src) => (
                    <div key={src.label} className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02]">
                      <div className="flex items-center gap-3">
                        <span className={`w-7 h-7 rounded-lg ${src.color} flex items-center justify-center text-xs font-bold`}>{src.icon}</span>
                        <div>
                          <span className="text-sm text-zinc-100">{src.label}</span>
                          <span className="text-[10px] text-zinc-500 block font-mono">{src.path}</span>
                        </div>
                      </div>
                      <span className="text-xs text-zinc-500 font-mono">{src.count} plugin{src.count !== 1 ? "s" : ""}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-4 p-3 rounded-xl bg-zinc-900/50 border border-zinc-800">
                  <p className="text-[10px] font-mono text-zinc-500">Discovery Order: Bundled &gt; Config &gt; User &gt; Project. Later sources override on name collision.</p>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
