"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Cpu, Plus, Trash2, ToggleLeft, ToggleRight, Loader2, Check, Info } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";

interface RoutingRule {
  id: string;
  task: string;
  model: string;
  description: string;
}

const TASK_OPTIONS = [
  { value: "read", label: "Read (grep, search, file reads)" },
  { value: "write", label: "Write (code gen, edits)" },
  { value: "reasoning", label: "Reasoning (architecture, planning)" },
  { value: "web", label: "Web (fetching, search)" },
  { value: "vision", label: "Vision (image analysis)" },
  { value: "chat", label: "Chat (conversation)" },
];

function RuleRow({ rule, models, onChange, onDelete }: { rule: RoutingRule; models: string[]; onChange: (r: RoutingRule) => void; onDelete: () => void }) {
  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
      className="flex items-center gap-3 rounded-xl border border-zinc-800/50 bg-zinc-900/40 p-3"
    >
      <select value={rule.task} onChange={(e) => onChange({ ...rule, task: e.target.value })}
        className="flex-1 text-xs bg-zinc-800/60 border border-zinc-700 rounded-lg px-2 py-1.5 text-zinc-300 focus:outline-none focus:border-emerald-500/40">
        {TASK_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <select value={rule.model} onChange={(e) => onChange({ ...rule, model: e.target.value })}
        className="flex-1 text-xs bg-zinc-800/60 border border-zinc-700 rounded-lg px-2 py-1.5 text-zinc-300 font-mono focus:outline-none focus:border-emerald-500/40">
        <option value="">System default</option>
        {models.map(m => <option key={m} value={m}>{m}</option>)}
      </select>
      <button onClick={onDelete} className="p-1 rounded hover:bg-zinc-800 text-zinc-600 hover:text-red-400 transition-colors"><Trash2 size={12} strokeWidth={1.5} /></button>
    </motion.div>
  );
}

export function ModelRoutingSettings() {
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [provData, routeData] = await Promise.all([
        api.get<any[]>("/api/settings/providers").catch(() => []),
        api.get<any>("/api/settings/routing-rules").catch(() => ({ rules: [], enabled: false })),
      ]);
      const modelList = (Array.isArray(provData) ? provData : [])
        .filter((p: any) => p.enabled !== false)
        .map((p: any) => p.model || p.provider || "")
        .filter(Boolean);
      setModels(modelList);
      if (routeData?.rules) setRules(routeData.rules);
      if (routeData?.enabled != null) setEnabled(routeData.enabled);
    } catch { /* defaults */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/api/settings/routing-rules", { rules, enabled });
      toast.success("Routing rules saved");
    } catch { toast.error("Failed to save"); }
    setSaving(false);
  };

  const addRule = () => {
    const used = new Set(rules.map(r => r.task));
    const next = TASK_OPTIONS.find(o => !used.has(o.value));
    if (!next) { toast.error("All task types already have rules"); return; }
    setRules([...rules, { id: Date.now().toString(), task: next.value, model: "", description: "" }]);
  };

  if (loading) return <div className="space-y-3">{[1,2].map(i => <div key={i} className="h-16 rounded-xl shimmer-bg" />)}</div>;

  const singleModel = models.length <= 1;

  return (
    <div className="space-y-6">
      {singleModel ? (
        <div className="rounded-2xl border border-amber-800/30 bg-amber-900/10 p-6 flex items-start gap-3">
          <Info size={16} className="text-amber-400 shrink-0 mt-0.5" strokeWidth={1.5} />
          <div>
            <h3 className="text-sm font-medium text-amber-300">Single Model Configured</h3>
            <p className="text-xs text-amber-400/70 mt-1">Task-aware routing requires at least 2 models. Add more models in <strong>LLM Providers</strong> to enable cost-optimized routing.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><Cpu size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
                <div><h3 className="text-sm font-medium text-zinc-200">Task-Aware Model Routing</h3><p className="text-xs text-zinc-500">Route tasks to different models based on type. 95% cost savings vs always-flag.</p></div>
              </div>
              <button onClick={() => setEnabled(!enabled)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-all ${enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-500"}`}
              >
                {enabled ? <ToggleRight size={14} strokeWidth={1.5} /> : <ToggleLeft size={14} strokeWidth={1.5} />}
                {enabled ? "Enabled" : "Disabled"}
              </button>
            </div>

            {enabled && (
              <>
                <AnimatePresence mode="popLayout">
                  {rules.map((rule) => (
                    <RuleRow key={rule.id} rule={rule} models={models} onChange={(r) => setRules(rules.map(x => x.id === rule.id ? r : x))} onDelete={() => setRules(rules.filter(r => r.id !== rule.id))} />
                  ))}
                </AnimatePresence>
                <button onClick={addRule} className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors">
                  <Plus size={12} strokeWidth={1.5} /> Add Rule
                </button>
              </>
            )}
          </div>

          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500/90 text-white hover:bg-emerald-500 disabled:opacity-40 transition-all active:scale-[0.97]"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} strokeWidth={1.5} />}
            {saving ? "Saving..." : "Save Routing Rules"}
          </button>
        </>
      )}
    </div>
  );
}
