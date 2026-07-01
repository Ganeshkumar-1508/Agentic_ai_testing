"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/api-client";
import { Plus, GitBranch, Clock, Play, Loader2, Trash2, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

interface WorkflowSummary {
  key: string;
  title: string;
  description: string;
  category: string;
  steps_count: number;
  steps: unknown[];
  tags: string[];
  schedule_template: string;
}

export default function WorkflowsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showNew, setShowNew] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newTitle, setNewTitle] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["workflows"],
    queryFn: async () => {
      const res = await api.get<{ workflows: WorkflowSummary[] }>("/api/workflows");
      return res?.workflows ?? [];
    },
  });

  const createMutation = useMutation({
    mutationFn: async (body: { key: string; title: string }) => {
      return api.post("/api/workflows", {
        ...body,
        description: "",
        category: "Workflow",
        steps: [
          {
            id: "step-1",
            label: "Task",
            type: "agent",
            prompt: "",
            mode: "sequential",
            depends_on: [],
            config: { model: null, toolsets: ["read"], timeout_sec: 300, role: "leaf" },
            branch_rules: [],
            children: [],
          },
        ],
        tags: [],
        schedule_template: "",
      });
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setShowNew(false);
      setNewKey("");
      setNewTitle("");
      router.push(`/workflows/${vars.key}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (key: string) => api.delete(`/api/workflows/${key}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workflows"] }),
  });

  const runMutation = useMutation({
    mutationFn: async (key: string) => api.post(`/api/workflows/${key}/run`, {}),
  });

  const workflows = Array.isArray(data) ? data : [];

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70" />
            <span className="text-xs font-mono text-zinc-600">/workflows</span>
          </div>
          <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100">Workflows</h1>
          <p className="text-sm text-zinc-600 mt-1">Multi-step agent pipelines with visual canvas</p>
        </div>
        <button onClick={() => setShowNew(!showNew)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-all active:scale-[0.97]">
          <Plus size={14} strokeWidth={1.5} />
          New Workflow
        </button>
      </div>

      {showNew && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-zinc-800/40 bg-zinc-900/30 p-4 space-y-3">
          <input value={newKey} onChange={(e) => setNewKey(e.target.value.replace(/\s+/g, "-").toLowerCase())}
            placeholder="workflow-key"
            className="w-full bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 font-mono" />
          <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Workflow Title"
            className="w-full bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowNew(false)}
              className="px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Cancel</button>
            <button onClick={() => createMutation.mutate({ key: newKey, title: newTitle })}
              disabled={!newKey || createMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-all active:scale-[0.97] disabled:opacity-40">
              {createMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : "Create"}
            </button>
          </div>
        </motion.div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-32 rounded-xl border border-zinc-800/30 bg-zinc-900/20 shimmer" />
          ))}
        </div>
      ) : workflows.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-zinc-600 gap-3">
          <GitBranch size={24} strokeWidth={1} className="text-zinc-700" />
          <p className="text-sm">No workflows yet</p>
          <p className="text-xs text-zinc-700">Create a workflow to define multi-step agent pipelines</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {workflows.map((wf, i) => (
            <motion.div key={wf.key} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className="group rounded-xl border border-zinc-800/40 bg-zinc-900/20 p-4 space-y-3 hover:border-zinc-700/50 transition-all cursor-pointer"
              onClick={() => router.push(`/workflows/${wf.key}`)}>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0">
                    <GitBranch size={14} className="text-indigo-400" strokeWidth={1.5} />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-medium text-zinc-200 truncate">{wf.title}</h3>
                    <p className="text-[10px] text-zinc-600 font-mono truncate">{wf.key}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={(e) => { e.stopPropagation(); runMutation.mutate(wf.key); }}
                    className="w-7 h-7 rounded-lg bg-zinc-800/40 flex items-center justify-center text-zinc-500 hover:text-emerald-400 transition-colors"
                    title="Run now">
                    <Play size={11} strokeWidth={1.5} />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(wf.key); }}
                    className="w-7 h-7 rounded-lg bg-zinc-800/40 flex items-center justify-center text-zinc-500 hover:text-red-400 transition-colors"
                    title="Delete">
                    <Trash2 size={11} strokeWidth={1.5} />
                  </button>
                </div>
              </div>
              {wf.description && (
                <p className="text-[11px] text-zinc-600 line-clamp-2">{wf.description}</p>
              )}
              <div className="flex items-center gap-2 text-[10px] text-zinc-600">
                  <span className="flex items-center gap-1">
                    <FileText size={10} strokeWidth={1.5} />
                    {wf.steps_count ?? 0} steps
                  </span>
                {wf.schedule_template && (
                  <span className="flex items-center gap-1">
                    <Clock size={10} strokeWidth={1.5} />
                    {wf.schedule_template}
                  </span>
                )}
                {wf.tags?.map((t) => (
                  <span key={t} className="px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-500">{t}</span>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
