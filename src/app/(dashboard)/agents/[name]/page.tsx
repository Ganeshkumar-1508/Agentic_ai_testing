"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  ArrowLeft, Save, RotateCcw, Clock, GitBranch,
  FileText, Cpu, Wrench, BookOpen, Hash, AlertCircle,
  ChevronDown, ChevronRight, CheckCircle2, XCircle,
} from "lucide-react";

interface AgentData {
  name: string; description: string; model: string; tools: string[];
  skills: string[]; triggers: string[]; prompt: string;
  temperature: number; max_steps: number; disabled: boolean;
}

interface Version {
  id: number; version: number; message: string; created_at: string;
}

function formatTime(iso: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

const springProps = { type: "spring" as const, stiffness: 200, damping: 24 };

export default function AgentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const name = params?.name as string;

  const [tab, setTab] = useState<"config" | "versions">("config");
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<AgentData | null>(null);
  const [versionMsg, setVersionMsg] = useState("");
  const [diffV1, setDiffV1] = useState<number | null>(null);
  const [diffV2, setDiffV2] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["agent", name],
    queryFn: async () => {
      const res = await api.get<{ agent: AgentData }>(`/api/agents/${name}`);
      return res?.agent;
    },
  });

  const { data: versionsData } = useQuery({
    queryKey: ["agent-versions", name],
    queryFn: async () => {
      const res = await api.get<{ versions: Version[] }>(`/api/agents/${name}/versions`);
      return res?.versions ?? [];
    },
    enabled: tab === "versions",
  });

  const { data: diffData } = useQuery({
    queryKey: ["agent-diff", name, diffV1, diffV2],
    queryFn: async () => {
      if (!diffV1 || !diffV2) return null;
      const res = await api.get<any>(`/api/agents/${name}/diff?v1=${diffV1}&v2=${diffV2}`);
      return res;
    },
    enabled: diffV1 !== null && diffV2 !== null,
  });

  const saveMutation = useMutation({
    mutationFn: async (body: any) => api.put(`/api/agents/${name}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent", name] });
      queryClient.invalidateQueries({ queryKey: ["agent-versions", name] });
      setEditing(false);
      toast.success("Agent saved");
    },
    onError: () => toast.error("Failed to save"),
  });

  const restoreMutation = useMutation({
    mutationFn: async (version: number) => api.post(`/api/agents/${name}/restore/${version}`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent", name] });
      queryClient.invalidateQueries({ queryKey: ["agent-versions", name] });
      toast.success("Version restored");
    },
  });

  const agent = data;
  const versions = versionsData ?? [];

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="h-8 w-48 shimmer-bg rounded mb-4" />
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-16 rounded-xl shimmer-bg" />)}</div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex flex-col items-center py-20 text-zinc-600 gap-3">
          <AlertCircle size={24} strokeWidth={1} className="text-zinc-700" />
          <p className="text-sm">Agent not found</p>
          <button onClick={() => router.push("/agents")} className="text-xs text-emerald-400 hover:underline">Back to agents</button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => router.push("/agents")}
          className="w-7 h-7 rounded-lg bg-zinc-800/40 flex items-center justify-center text-zinc-500 hover:text-zinc-300 transition-colors">
          <ArrowLeft size={13} strokeWidth={1.5} />
        </button>
        <div className="flex-1">
          <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100">{agent.name}</h1>
          <p className="text-sm text-zinc-600">{agent.description || "No description"}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-zinc-900/50 border border-zinc-800/30 rounded-xl p-1 w-fit">
        {(["config", "versions"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("px-3 py-1.5 text-[10px] rounded-lg font-medium transition-colors",
              tab === t ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300")}>
            {t === "config" ? "Configuration" : `Versions (${versions.length})`}
          </button>
        ))}
      </div>

      {tab === "config" && (
        <ConfigTab agent={agent} editing={editing} onEdit={() => setEditing(true)}
          onCancel={() => setEditing(false)}
          onSave={(data) => saveMutation.mutate({ ...data, version_message: versionMsg })}
          versionMsg={versionMsg} onVersionMsgChange={setVersionMsg}
          isPending={saveMutation.isPending} />
      )}

      {tab === "versions" && (
        <VersionsTab versions={versions} name={name}
          diffV1={diffV1} diffV2={diffV2}
          diffData={diffData}
          onSelectV1={(v) => setDiffV1(v)}
          onSelectV2={(v) => setDiffV2(v)}
          onRestore={(v) => { if (confirm(`Restore v${v}?`)) restoreMutation.mutate(v); }} />
      )}
    </div>
  );
}

function ConfigTab({
  agent, editing, onEdit, onCancel, onSave, versionMsg, onVersionMsgChange, isPending,
}: {
  agent: AgentData; editing: boolean; onEdit: () => void; onCancel: () => void;
  onSave: (d: AgentData) => void; versionMsg: string; onVersionMsgChange: (v: string) => void;
  isPending: boolean;
}) {
  const [form, setForm] = useState<AgentData>({ ...agent });
  const [toolsInput, setToolsInput] = useState(agent.tools.join(", "));
  const [skillsInput, setSkillsInput] = useState(agent.skills.join(", "));

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryCard icon={Cpu} label="Model" value={agent.model || "default"} />
        <SummaryCard icon={Wrench} label="Tools" value={`${agent.tools.length}`} />
        <SummaryCard icon={BookOpen} label="Skills" value={`${agent.skills.length}`} />
        <SummaryCard icon={Hash} label="Triggers" value={`${agent.triggers.length}`} />
      </div>

      {/* Prompt */}
      <div className="rounded-xl border border-zinc-800/40 bg-zinc-900/20 p-4 space-y-2">
        <span className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider">System Prompt</span>
        {editing ? (
          <textarea value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })}
            className="w-full h-32 bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-300 font-mono outline-none focus:border-emerald-500/40 resize-y" />
        ) : (
          <p className="text-xs text-zinc-500 font-mono whitespace-pre-wrap line-clamp-6 leading-relaxed">
            {agent.prompt || "(empty)"}
          </p>
        )}
      </div>

      {/* Fields */}
      {editing && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-zinc-800/40 bg-zinc-900/20 p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-zinc-600 font-medium">Model</label>
              <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}
                className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 outline-none focus:border-emerald-500/40 font-mono" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-zinc-600 font-medium">Temperature</label>
              <input type="number" step="0.1" min="0" max="2" value={form.temperature}
                onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) || 0 })}
                className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 outline-none focus:border-emerald-500/40" />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-600 font-medium">Tools (comma-separated)</label>
            <input value={toolsInput} onChange={(e) => setToolsInput(e.target.value)}
              onBlur={() => setForm({ ...form, tools: toolsInput.split(",").map(s => s.trim()).filter(Boolean) })}
              className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 outline-none focus:border-emerald-500/40 font-mono" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-600 font-medium">Skills (comma-separated)</label>
            <input value={skillsInput} onChange={(e) => setSkillsInput(e.target.value)}
              onBlur={() => setForm({ ...form, skills: skillsInput.split(",").map(s => s.trim()).filter(Boolean) })}
              className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 outline-none focus:border-emerald-500/40 font-mono" />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] text-zinc-600 font-medium">Version message (optional)</label>
            <input value={versionMsg} onChange={(e) => onVersionMsgChange(e.target.value)}
              placeholder="e.g. Added web research tools"
              className="w-full bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-300 placeholder-zinc-700 outline-none focus:border-emerald-500/40" />
          </div>
        </motion.div>
      )}

      {editing ? (
        <div className="flex items-center gap-2">
          <button onClick={() => onSave(form)}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs hover:bg-emerald-500/20 transition-all active:scale-[0.97]">
            {isPending ? <span className="w-3 h-3 rounded-full border-2 border-emerald-400/30 border-t-emerald-400 animate-spin" /> : <Save size={11} strokeWidth={1.5} />}
            Save as Version
          </button>
          <button onClick={onCancel}
            className="px-3 py-1.5 rounded-lg text-xs text-zinc-600 hover:text-zinc-400 transition-colors">Cancel</button>
        </div>
      ) : (
        <button onClick={onEdit}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800/40 text-zinc-400 text-xs hover:bg-zinc-800/60 transition-all active:scale-[0.97]">
          <Save size={11} strokeWidth={1.5} /> Edit
        </button>
      )}
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-800/40 bg-zinc-900/20 p-3 space-y-1">
      <div className="flex items-center gap-1.5 text-[10px] text-zinc-600">
        <Icon size={11} strokeWidth={1.5} />
        {label}
      </div>
      <span className="text-sm font-medium text-zinc-200 font-mono truncate block">{value}</span>
    </div>
  );
}

function VersionsTab({
  versions, name, diffV1, diffV2, diffData, onSelectV1, onSelectV2, onRestore,
}: {
  versions: Version[]; name: string;
  diffV1: number | null; diffV2: number | null; diffData: any;
  onSelectV1: (v: number) => void; onSelectV2: (v: number) => void;
  onRestore: (v: number) => void;
}) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="space-y-4">
      {/* Diff selector */}
      <div className="flex items-center gap-2 text-[10px] text-zinc-600">
        <span>Compare:</span>
        <select value={diffV1 ?? ""} onChange={(e) => onSelectV1(e.target.value ? parseInt(e.target.value) : 0)}
          className="bg-zinc-800/50 border border-zinc-700 rounded px-2 py-1 text-zinc-300 outline-none text-[10px]">
          <option value="">v1</option>
          {versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
        </select>
        <span>vs</span>
        <select value={diffV2 ?? ""} onChange={(e) => onSelectV2(e.target.value ? parseInt(e.target.value) : 0)}
          className="bg-zinc-800/50 border border-zinc-700 rounded px-2 py-1 text-zinc-300 outline-none text-[10px]">
          <option value="">v2</option>
          {versions.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
        </select>
      </div>

      {/* Diff result */}
      {diffData?.diffs && Object.keys(diffData.diffs).length > 0 && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-2">
          <span className="text-[10px] font-medium text-amber-400 uppercase tracking-wider">Changes</span>
          {Object.entries(diffData.diffs).map(([field, val]: [string, any]) => (
            <div key={field} className="text-[11px] space-y-0.5">
              <span className="text-zinc-400 font-medium">{field}:</span>
              <div className="flex items-start gap-2 font-mono pl-3">
                <span className="text-red-400/70 line-through">{JSON.stringify(val.old)}</span>
                <span className="text-emerald-400/70">{JSON.stringify(val.new)}</span>
              </div>
            </div>
          ))}
        </motion.div>
      )}

      {versions.length === 0 ? (
        <div className="flex flex-col items-center py-12 text-zinc-600 gap-2">
          <Clock size={20} strokeWidth={1} className="text-zinc-700" />
          <p className="text-xs">No versions saved yet</p>
          <p className="text-[10px] text-zinc-700">Save the agent to create the first version snapshot</p>
        </div>
      ) : (
        <div className="space-y-1">
          {versions.map((v, i) => (
            <motion.div key={v.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ ...springProps, delay: i * 0.02 }}
              className="group flex items-start gap-3 px-4 py-2.5 rounded-xl border border-zinc-800/30 bg-zinc-900/20 hover:border-zinc-700/40 transition-all cursor-pointer"
              onClick={() => setExpanded(expanded === v.version ? null : v.version)}>
              <div className="w-6 h-6 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <GitBranch size={11} className="text-indigo-400" strokeWidth={1.5} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-medium text-zinc-300 font-mono">v{v.version}</span>
                  <span className="text-[10px] text-zinc-600">{v.message || `Version ${v.version}`}</span>
                  <span className="ml-auto text-[9px] text-zinc-700 font-mono">{formatTime(v.created_at)}</span>
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={(e) => { e.stopPropagation(); onRestore(v.version); }}
                  className="w-6 h-6 rounded flex items-center justify-center text-zinc-600 hover:text-emerald-400 transition-colors" title="Restore">
                  <RotateCcw size={10} strokeWidth={1.5} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
