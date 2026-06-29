"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Plus, Trash2, ArrowRight, UserCheck, Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api/api-client";
import { toast } from "sonner";

interface EscalationRule {
  id: string;
  trigger: string;
  condition: string;
  action: "ask" | "escalate" | "auto-retry";
  target: string;
}

const TRIGGER_OPTIONS = [
  { value: "tool_failure", label: "Tool fails 3x consecutively" },
  { value: "cost_exceeded", label: "Session cost exceeds limit" },
  { value: "unknown_domain", label: "Unknown domain detected" },
  { value: "high_risk_action", label: "High-risk action detected" },
  { value: "low_confidence", label: "Agent confidence below threshold" },
];

const TARGET_OPTIONS = [
  { value: "user", label: "Current user" },
  { value: "admin", label: "Admin / on-call" },
  { value: "slack", label: "Slack channel" },
  { value: "email", label: "Email notification" },
];

function RuleCard({ rule, onDelete, onChange }: { rule: EscalationRule; onDelete: () => void; onChange: (r: EscalationRule) => void }) {
  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
      className="flex items-start gap-3 rounded-xl border border-zinc-800/50 bg-zinc-900/40 p-4"
    >
      <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center shrink-0"><AlertTriangle size={14} className="text-amber-400" strokeWidth={1.5} /></div>
      <div className="flex-1 grid grid-cols-1 sm:grid-cols-4 gap-3">
        <select value={rule.trigger} onChange={(e) => onChange({ ...rule, trigger: e.target.value })}
          className="text-xs bg-zinc-800/60 border border-zinc-700 rounded-lg px-2 py-1.5 text-zinc-300 focus:outline-none focus:border-emerald-500/40">
          {TRIGGER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <ArrowRight size={14} className="text-zinc-600 self-center mx-auto" strokeWidth={1.5} />
        <select value={rule.action} onChange={(e) => onChange({ ...rule, action: e.target.value as any })}
          className="text-xs bg-zinc-800/60 border border-zinc-700 rounded-lg px-2 py-1.5 text-zinc-300 focus:outline-none focus:border-emerald-500/40">
          <option value="ask">Ask user</option>
          <option value="escalate">Escalate</option>
          <option value="auto-retry">Auto-retry</option>
        </select>
        <select value={rule.target} onChange={(e) => onChange({ ...rule, target: e.target.value })}
          className="text-xs bg-zinc-800/60 border border-zinc-700 rounded-lg px-2 py-1.5 text-zinc-300 focus:outline-none focus:border-emerald-500/40">
          {TARGET_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <button onClick={onDelete} className="p-1 rounded hover:bg-zinc-800 text-zinc-600 hover:text-red-400 transition-colors"><Trash2 size={12} strokeWidth={1.5} /></button>
    </motion.div>
  );
}

export function EscalationPolicySettings() {
  const [rules, setRules] = useState<EscalationRule[]>([]);
  const [timeoutSec, setTimeoutSec] = useState(300);
  const [autoResolve, setAutoResolve] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<any>("/api/settings/escalation");
      if (data?.rules) setRules(data.rules);
      if (data?.timeout_seconds != null) setTimeoutSec(data.timeout_seconds);
      if (data?.auto_resolve != null) setAutoResolve(data.auto_resolve);
    } catch { /* use defaults */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/api/settings/escalation", { rules, timeout_seconds: timeoutSec, auto_resolve: autoResolve });
      toast.success("Escalation policy saved");
    } catch { toast.error("Failed to save"); }
    setSaving(false);
  };

  const addRule = () => {
    setRules([...rules, { id: Date.now().toString(), trigger: "tool_failure", condition: "", action: "ask", target: "user" }]);
  };

  if (loading) return <div className="space-y-3">{[1,2].map(i => <div key={i} className="h-16 rounded-xl shimmer-bg" />)}</div>;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><UserCheck size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
          <div><h3 className="text-sm font-medium text-zinc-200">Escalation Rules</h3><p className="text-xs text-zinc-500">Define when agents should ask for human help</p></div>
        </div>

        <AnimatePresence mode="popLayout">
          {rules.map((rule) => (
            <RuleCard key={rule.id} rule={rule} onDelete={() => setRules(rules.filter(r => r.id !== rule.id))} onChange={(r) => setRules(rules.map(x => x.id === rule.id ? r : x))} />
          ))}
        </AnimatePresence>

        <button onClick={addRule} className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors">
          <Plus size={12} strokeWidth={1.5} /> Add Rule
        </button>
      </div>

      <div className="rounded-2xl border border-zinc-800/50 bg-zinc-900/40 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/50 flex items-center justify-center"><AlertTriangle size={16} className="text-zinc-400" strokeWidth={1.5} /></div>
          <div><h3 className="text-sm font-medium text-zinc-200">Timeout & Auto-Resolve</h3><p className="text-xs text-zinc-500">What happens when a human doesn't respond</p></div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-400">Timeout after</span>
          <input type="number" value={timeoutSec} onChange={(e) => setTimeoutSec(parseInt(e.target.value) || 300)} min="10" max="3600"
            className="w-20 bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 font-mono text-center focus:outline-none focus:border-emerald-500/40" />
          <span className="text-xs text-zinc-400">seconds</span>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={autoResolve} onChange={(e) => setAutoResolve(e.target.checked)}
            className="rounded border-zinc-700 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/20" />
          <span className="text-xs text-zinc-400">Auto-resolve with safest default action on timeout</span>
        </label>
      </div>

      <button onClick={save} disabled={saving}
        className="inline-flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500/90 text-white hover:bg-emerald-500 disabled:opacity-40 transition-all active:scale-[0.97]"
      >
        {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} strokeWidth={1.5} />}
        {saving ? "Saving..." : "Save Policy"}
      </button>
    </div>
  );
}
