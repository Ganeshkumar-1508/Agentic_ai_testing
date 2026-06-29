"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Edit3, Trash2, Save, Bot, Code2, BookOpen, Bug, Shield, Layers, Power, PowerOff } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

type Agent = {
  name: string;
  description: string;
  model: string;
  tools: string[];
  skills: string[];
  triggers: string[];
  mode: string;
  prompt: string;
  disabled: boolean;
  temperature: number;
  max_steps: number;
};

const ICONS: Record<string, typeof Bot> = {
  "test-writer": Code2,
  "code-reviewer": Shield,
  "bug-fixer": Bug,
  "security-auditor": Shield,
  "docs-writer": BookOpen,
};

const ALL_TOOLS = [
  "read", "write", "edit", "bash", "glob", "grep",
  "web_search", "web_fetch", "execute_code", "delegate_task",
  "knowledge_graph_search", "kg_refresh", "kanban_create", "kanban_list", "kanban_update",
  "commit_and_open_pr", "attempt_heal", "todo", "question", "osv_check",
];

const EMPTY: Agent = {
  name: "", description: "", model: "", tools: ["read"], skills: [], triggers: [],
  mode: "subagent", prompt: "", disabled: false, temperature: 0.3, max_steps: 20,
};

const SPRING = { type: "spring" as const, stiffness: 100, damping: 20 };

export function AgentsSettings() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Agent | null>(null);
  const [isNew, setIsNew] = useState(false);

  const { data: resp, isLoading, error } = useQuery<{ agents: Agent[] }>({
    queryKey: ["agents"],
    queryFn: () => api.get("/api/agents"),
  });

  const saveMut = useMutation({
    mutationFn: async (agent: Agent) => {
      const res = await api.put<unknown>(`/api/agents/${encodeURIComponent(agent.name)}`, agent);
      return res;
    },
    onSuccess: () => {
      toast.success("Agent saved");
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setEditing(null);
      setIsNew(false);
    },
    onError: (e: Error) => toast.error(e?.message ?? "Save failed"),
  });

  const deleteMut = useMutation({
    mutationFn: async (name: string) => { await api.delete(`/api/agents/${encodeURIComponent(name)}`); },
    onSuccess: () => {
      toast.success("Agent deleted");
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (e: Error) => toast.error(e?.message ?? "Delete failed"),
  });

  const agents = resp?.agents ?? [];
  const toggleTool = (t: string) => {
    if (!editing) return;
    setEditing({ ...editing, tools: editing.tools.includes(t) ? editing.tools.filter((x) => x !== t) : [...editing.tools, t] });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight text-zinc-100">Subagent Definitions</h2>
          <p className="text-sm text-zinc-500 mt-1">Subagents used by the orchestrator for fan-out work. Each one is a discrete role with its own toolset and system prompt.</p>
        </div>
        <motion.button whileTap={{ scale: 0.97 }}
          onClick={() => { setEditing({ ...EMPTY, name: `agent-${agents.length + 1}` }); setIsNew(true); }}
          className="h-9 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-xs font-semibold transition-colors flex items-center gap-1.5 shrink-0">
          <Plus className="w-3.5 h-3.5" strokeWidth={2} /> New Agent
        </motion.button>
      </div>

      {/* Strip */}
      <div className="flex items-stretch border-y border-white/[0.06] divide-x divide-white/[0.06]">
        {[
          { label: "Total", value: agents.length },
          { label: "Active", value: agents.filter((a) => !a.disabled).length },
          { label: "Disabled", value: agents.filter((a) => a.disabled).length },
        ].map((s) => (
          <div key={s.label} className="flex-1 px-6 py-4 flex items-baseline gap-3">
            <span className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.14em]">{s.label}</span>
            <motion.span key={s.value} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}
              className="text-2xl font-mono tabular-nums tracking-tight text-zinc-100">{s.value}</motion.span>
          </div>
        ))}
      </div>

      {/* List */}
      <section>
        {isLoading ? (
          <div className="space-y-px">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-16 border-b border-white/[0.04] flex items-center gap-4 px-4">
                <div className="w-8 h-8 rounded-lg shimmer-bg" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-40 rounded shimmer-bg" />
                  <div className="h-2.5 w-64 rounded shimmer-bg" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="py-16 text-center">
            <p className="text-sm text-rose-300">Failed to load agents: {(error as Error).message}</p>
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ["agents"] })}
              className="mt-3 text-xs text-zinc-500 hover:text-zinc-300 underline underline-offset-4">Retry</button>
          </div>
        ) : agents.length === 0 ? (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={SPRING} className="py-20 text-center">
            <motion.div animate={{ y: [0, -3, 0] }} transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
              className="w-12 h-12 mx-auto rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4">
              <Bot className="w-5 h-5 text-zinc-600" strokeWidth={1.2} />
            </motion.div>
            <h3 className="text-sm font-medium text-zinc-200">No subagents yet</h3>
            <p className="text-xs text-zinc-600 mt-1.5 max-w-xs mx-auto">Define a subagent to give the orchestrator a specialized worker it can delegate to.</p>
          </motion.div>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {agents.map((a, i) => {
              const Icon = ICONS[a.name] || Bot;
              return (
                <motion.div key={a.name} layout="position" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ ...SPRING, delay: Math.min(i * 0.025, 0.3) }}
                  className={cn("group grid grid-cols-[40px_1fr_auto_140px] gap-4 items-center px-4 py-3.5 transition-colors hover:bg-white/[0.02]",
                    a.disabled && "opacity-50")}>
                  <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center border",
                    a.disabled ? "bg-zinc-500/10 border-zinc-500/15" : "bg-emerald-500/10 border-emerald-500/15")}>
                    <Icon className={cn("w-3.5 h-3.5", a.disabled ? "text-zinc-500" : "text-emerald-300")} strokeWidth={1.5} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] text-zinc-100 font-medium">{a.name}</span>
                      <span className={cn("text-[9px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider",
                        a.mode === "primary" ? "bg-zinc-500/10 text-zinc-300" : "bg-white/[0.04] text-zinc-500")}>{a.mode}</span>
                    </div>
                    <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{a.description || "No description"}</p>
                  </div>
                  <div className="flex flex-wrap gap-1 justify-end max-w-[280px]">
                    {a.tools.slice(0, 4).map((t) => (
                      <span key={t} className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-500 border border-white/[0.04]">{t}</span>
                    ))}
                    {a.tools.length > 4 && <span className="text-[9.5px] font-mono text-zinc-600">+{a.tools.length - 4}</span>}
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <motion.button whileTap={{ scale: 0.95 }}
                      onClick={() => { setEditing({ ...a }); setIsNew(false); }}
                      className="h-7 w-7 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.06] transition-colors flex items-center justify-center" title="Edit">
                      <Edit3 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </motion.button>
                    <motion.button whileTap={{ scale: 0.95 }}
                      onClick={() => deleteMut.mutate(a.name)}
                      className="h-7 w-7 rounded-lg text-zinc-500 hover:text-rose-300 hover:bg-rose-500/10 transition-colors flex items-center justify-center" title="Delete">
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                    </motion.button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </section>

      {/* Edit modal */}
      <AnimatePresence>
        {editing && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={SPRING}
            className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/60 backdrop-blur-sm p-4" onClick={() => setEditing(null)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }} transition={SPRING}
              className="w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-card border border-white/[0.08] rounded-3xl shadow-[0_24px_48px_-12px_rgba(0,0,0,0.6)]"
              onClick={(e) => e.stopPropagation()}>
              <div className="sticky top-0 bg-card/95 backdrop-blur-sm px-6 py-4 border-b border-white/[0.06] flex items-center justify-between z-10">
                <div>
                  <h3 className="text-[15px] font-medium text-zinc-100">{isNew ? "New agent" : `Edit · ${editing.name}`}</h3>
                  <p className="text-[11px] text-zinc-600 mt-0.5">Subagent role used by the orchestrator</p>
                </div>
                <button onClick={() => setEditing(null)} className="w-8 h-8 rounded-lg text-zinc-600 hover:text-zinc-300 hover:bg-white/[0.05] transition-colors flex items-center justify-center">
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>
              <div className="p-6 space-y-5">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="sm:col-span-2">
                    <Label>Name</Label>
                    <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                      className="w-full h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors font-mono" />
                  </div>
                  <div>
                    <Label>Mode</Label>
                    <select value={editing.mode} onChange={(e) => setEditing({ ...editing, mode: e.target.value })}
                      className="w-full h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3 text-[12px] text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors cursor-pointer">
                      <option value="subagent">subagent</option>
                      <option value="primary">primary</option>
                    </select>
                  </div>
                </div>
                <div>
                  <Label>Description</Label>
                  <input value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                    className="w-full h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <Label>Model (optional, overrides default)</Label>
                    <input value={editing.model} onChange={(e) => setEditing({ ...editing, model: e.target.value })}
                      placeholder="leave empty to use the default"
                      className="w-full h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors font-mono" />
                  </div>
                  <div>
                    <Label>Triggers (comma-separated)</Label>
                    <input value={editing.triggers.join(", ")} onChange={(e) => setEditing({ ...editing, triggers: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                      placeholder="review, audit, security"
                      className="w-full h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors" />
                  </div>
                </div>
                <div>
                  <Label>Tools ({editing.tools.length} selected)</Label>
                  <div className="flex flex-wrap gap-1.5 p-3 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                    {ALL_TOOLS.map((t) => (
                      <motion.button key={t} whileTap={{ scale: 0.94 }} onClick={() => toggleTool(t)}
                        className={cn("h-7 px-2.5 rounded-lg text-[10px] font-mono font-medium transition-colors",
                          editing.tools.includes(t)
                            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25"
                            : "bg-white/[0.03] text-zinc-500 border border-white/[0.04] hover:text-zinc-300")}>
                        {t}
                      </motion.button>
                    ))}
                  </div>
                </div>
                <div>
                  <Label>System prompt</Label>
                  <textarea value={editing.prompt} onChange={(e) => setEditing({ ...editing, prompt: e.target.value })} rows={6}
                    className="w-full rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 py-2.5 text-[12px] text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors font-mono leading-relaxed resize-y" />
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
                  <button onClick={() => setEditing({ ...editing, disabled: !editing.disabled })}
                    className="flex items-center gap-2.5 group">
                    <span className={cn("relative inline-flex h-5 w-9 rounded-full transition-colors",
                      editing.disabled ? "bg-zinc-700" : "bg-emerald-500")}>
                      <motion.span layout
                        className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white"
                        animate={{ x: editing.disabled ? 0 : 16 }} transition={SPRING} />
                    </span>
                    <span className="flex items-center gap-1.5 text-[11.5px] text-zinc-400">
                      {editing.disabled ? <PowerOff className="w-3 h-3" strokeWidth={1.5} /> : <Power className="w-3 h-3" strokeWidth={1.5} />}
                      {editing.disabled ? "Disabled" : "Enabled"}
                    </span>
                  </button>
                </div>
              </div>
              <div className="sticky bottom-0 bg-card/95 backdrop-blur-sm px-6 py-4 border-t border-white/[0.06] flex gap-2">
                <motion.button whileTap={{ scale: 0.97 }} onClick={() => saveMut.mutate(editing)} disabled={saveMut.isPending || !editing.name}
                  className="flex-1 h-10 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-zinc-950 text-[12px] font-semibold transition-colors flex items-center justify-center gap-1.5">
                  {saveMut.isPending ? <span className="w-3.5 h-3.5 border-2 border-zinc-950 border-t-transparent rounded-full animate-spin" /> : <Save className="w-3.5 h-3.5" strokeWidth={2} />}
                  {saveMut.isPending ? "Saving" : "Save agent"}
                </motion.button>
                <motion.button whileTap={{ scale: 0.97 }} onClick={() => setEditing(null)}
                  className="h-10 px-5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-zinc-300 text-[12px] font-semibold transition-colors">
                  Cancel
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.12em] block mb-1.5">{children}</label>;
}
