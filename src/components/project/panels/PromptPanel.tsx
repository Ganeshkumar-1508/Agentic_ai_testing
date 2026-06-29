"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Terminal, FileCode2, History, Plus, X, Check, Play, Diff } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { StyledSelect } from "@/components/ui/styled-select";
import { api } from "@/lib/api/api-client";

export function PromptPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ content: "", model: "" });
  const [playgroundInput, setPlaygroundInput] = useState("");
  const [playgroundModel, setPlaygroundModel] = useState("");
  const [compareId, setCompareId] = useState<string | null>(null);

  const { data: providers } = useQuery({
    queryKey: ["settings", "providers"],
    queryFn: async () => {
      return (await api.get<any[]>(`/api/settings/providers`))?? [];
    },
  });

  const modelOptions = (providers || []).flatMap((p: any) => {
    const model = p.model || "";
    return model ? [{ label: `${p.provider} / ${model}`, value: `${p.provider}/${model}` }] : [];
  });

  const { data: promptsData, isLoading } = useQuery({
    queryKey: ["settings", "prompts"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/prompts`))?? {};
    },
  });

  const { data: activeData } = useQuery({
    queryKey: ["settings", "prompts", "active"],
    queryFn: async () => {
      return (await api.get<any>(`/api/settings/prompts/active`))?? {};
    },
  });

  const prompts = (promptsData as any)?.prompts ?? [];
  const activePrompt = activeData?.prompt;

  const createPrompt = useMutation({
    mutationFn: async () => {
      await api.post("/api/settings/prompts", { content: form.content, name: "system", model: form.model });
    },
    onSuccess: () => { setShowForm(false); setForm({ content: "", model: "" }); queryClient.invalidateQueries({ queryKey: ["settings", "prompts"] }); },
  });

  const rollbackPrompt = useMutation({
    mutationFn: async (id: string) => { await api.post(`/api/settings/prompts/${id}/rollback`); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings", "prompts"] }),
  });

  const playground = useMutation({
    mutationFn: async () => {
      return api.post<any>("/api/settings/prompts/playground", { content: playgroundInput, model: playgroundModel });
    },
  });

  const activeContent = activePrompt?.content || "";
  const comparePrompt = compareId ? prompts.find((p: any) => p.id === compareId) : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-zinc-100">Prompt Playground</h2>
          <p className="text-sm text-zinc-500 mt-1">Edit, test, and version-control agent prompts</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.98]">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {showForm ? "Cancel" : "New Version"}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCode2 className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
              <h3 className="text-sm font-medium text-zinc-200">Active Prompt</h3>
            </div>
            {activePrompt && <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-emerald-500/10 text-emerald-400">v{activePrompt.version}</span>}
          </div>
          <pre className="text-xs text-zinc-400 font-mono bg-zinc-900/60 rounded-lg p-4 max-h-[250px] overflow-y-auto whitespace-pre-wrap">{activeContent || "No active prompt"}</pre>
        </div>

        {comparePrompt && (
          <div className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Diff className="w-4 h-4 text-amber-400" strokeWidth={1.5} />
                <h3 className="text-sm font-medium text-zinc-200">v{comparePrompt.version}</h3>
              </div>
              <button onClick={() => setCompareId(null)} className="text-[10px] text-zinc-500 hover:text-zinc-300">Close</button>
            </div>
            <pre className="text-xs text-zinc-400 font-mono bg-amber-500/[0.03] border border-amber-500/15 rounded-lg p-4 max-h-[250px] overflow-y-auto whitespace-pre-wrap">{comparePrompt.content}</pre>
          </div>
        )}
      </div>

      <div className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-medium text-zinc-300">Test Prompt</h3>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
          <div className="space-y-3">
            <textarea value={playgroundInput} onChange={(e) => setPlaygroundInput(e.target.value)} rows={5} placeholder="Enter a test prompt..." className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 resize-none" />
            <div className="flex items-center gap-2">
              <StyledSelect value={playgroundModel} onChange={(e) => setPlaygroundModel(e.target.value)} className="flex-1 text-xs font-mono">
                <option value="" className="bg-zinc-900">Select a model...</option>
                {modelOptions.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-zinc-900">{opt.label}</option>
                ))}
              </StyledSelect>
              <button onClick={() => playground.mutate()} disabled={!playgroundInput || playground.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98] shrink-0">
                <Play className="w-3.5 h-3.5" strokeWidth={1.5} />
                {playground.isPending ? "Running..." : "Run"}
              </button>
            </div>
          </div>
          <div className="bg-zinc-900/60 rounded-lg p-4 min-h-[120px] max-h-[200px] overflow-y-auto">
            {playground.data ? (
              <div className="space-y-2">
                <div className="flex items-center gap-3 text-[10px] text-zinc-500">
                  <span className="text-emerald-400">{playground.data.status}</span>
                  <span>{playground.data.latencyMs}ms</span>
                  <span>{playground.data.tokens} tokens</span>
                  <span className="font-mono">{playground.data.model}</span>
                </div>
                <pre className="text-xs text-zinc-300 font-mono whitespace-pre-wrap">{playground.data.response}</pre>
              </div>
            ) : (
              <p className="text-xs text-zinc-600">Output will appear here...</p>
            )}
          </div>
        </div>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">Model</label>
                <StyledSelect value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
                  <option value="" className="bg-zinc-900">Default</option>
                  {modelOptions.map((opt) => (
                    <option key={opt.value} value={opt.value} className="bg-zinc-900">{opt.label}</option>
                  ))}
                </StyledSelect>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400">System Prompt</label>
                <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} rows={8} placeholder="Enter system prompt..." className="w-full bg-zinc-900/80 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 font-mono leading-relaxed outline-none focus:border-emerald-500/40 resize-none" />
              </div>
              <div className="flex justify-end">
                <button onClick={() => createPrompt.mutate()} disabled={!form.content || createPrompt.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98]">
                  {createPrompt.isPending ? "Saving..." : <><Check className="w-3.5 h-3.5" strokeWidth={1.5} /> Save & Activate</>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="shimmer-bg border border-zinc-800/30 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />
          <h3 className="text-sm font-medium text-zinc-300">Version History</h3>
        </div>
        {prompts.length === 0 && !isLoading && <p className="text-xs text-zinc-600">No prompt versions saved</p>}
        <div className="space-y-2">
          {prompts.map((p: any) => (
            <div key={p.id} className="flex items-center justify-between py-2 border-b border-zinc-800/20 last:border-0 text-xs">
              <div className="flex items-center gap-3">
                <span className="font-mono text-zinc-400">v{p.version}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${p.status === "active" ? "bg-emerald-500/10 text-emerald-400" : p.status === "archived" ? "bg-zinc-800/50 text-zinc-500" : "bg-blue-500/10 text-blue-400"}`}>{p.status}</span>
                <span className="text-zinc-600">{p.createdAt?.slice(0, 10)}</span>
              </div>
              <div className="flex items-center gap-2">
                {p.status !== "active" && (
                  <button onClick={() => { setCompareId(p.id); }} className="text-zinc-500 hover:text-amber-400 transition-colors">Diff</button>
                )}
                {p.status === "archived" && (
                  <button onClick={() => rollbackPrompt.mutate(p.id)} className="text-zinc-500 hover:text-emerald-400 transition-colors">Rollback</button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
