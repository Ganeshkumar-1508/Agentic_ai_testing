"use client";

import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { StyledSelect } from "@/components/ui/styled-select";
import { Clock, Play, Plus, Trash2, X, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api/api-client";

const NL_SCHEDULE_PRESETS = [
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Every 30 minutes", cron: "*/30 * * * *" },
  { label: "Every 15 minutes", cron: "*/15 * * * *" },
  { label: "Daily at midnight", cron: "0 0 * * *" },
  { label: "Daily at 9 AM", cron: "0 9 * * *" },
  { label: "Weekdays at 9 AM", cron: "0 9 * * 1-5" },
  { label: "Weekdays at 5 PM", cron: "0 17 * * 1-5" },
  { label: "Weekly on Monday", cron: "0 9 * * 1" },
  { label: "First of month", cron: "0 9 1 * *" },
];

const NL_PATTERNS: [RegExp, string | ((m: RegExpMatchArray) => string)][] = [
  [/every (\d+) minutes?/i, (m: RegExpMatchArray) => `*/${m[1]} * * * *`],
  [/every (\d+) hours?/i, (m: RegExpMatchArray) => `0 */${m[1]} * * *`],
  [/every hour/i, "0 * * * *"],
  [/every (\d+) days?/i, (m: RegExpMatchArray) => `0 0 */${m[1]} * *`],
  [/daily at (\d+)\s*(am|pm)/i, (m: RegExpMatchArray) => {
    let h = parseInt(m[1]); const ampm = m[2].toLowerCase();
    if (ampm === "pm" && h !== 12) h += 12;
    if (ampm === "am" && h === 12) h = 0;
    return `0 ${h} * * *`;
  }],
  [/weekdays at (\d+)\s*(am|pm)/i, (m: RegExpMatchArray) => {
    let h = parseInt(m[1]); const ampm = m[2].toLowerCase();
    if (ampm === "pm" && h !== 12) h += 12;
    if (ampm === "am" && h === 12) h = 0;
    return `0 ${h} * * 1-5`;
  }],
  [/weekly on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)/i, () => "0 9 * * 1"],
  [/every weekday/i, "0 9 * * 1-5"],
  [/midnight/i, "0 0 * * *"],
  [/hourly/i, "0 * * * *"],
];

function nlToCron(input: string): string {
  const trimmed = input.trim().toLowerCase();
  if (!trimmed) return "";
  for (const [pattern, replacement] of NL_PATTERNS) {
    if (typeof replacement === "string") {
      if (pattern.test(trimmed)) return replacement;
    } else {
      const match = trimmed.match(pattern);
      if (match) return replacement(match);
    }
  }
  return "";
}

export function CronPanel() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", prompt: "", scheduleType: "interval", scheduleExpr: "*/30 * * * *", nlInput: "" });
  const cronPreview = useMemo(() => {
    if (form.scheduleType === "nl" && form.nlInput) {
      const converted = nlToCron(form.nlInput);
      return converted || "Could not parse — try a preset below";
    }
    return form.scheduleExpr;
  }, [form.scheduleType, form.nlInput, form.scheduleExpr]);

  const { data, isLoading } = useQuery({
    queryKey: ["cron-jobs"],
    queryFn: async () => {
      const res = await api.get("/api/cron-jobs");
      return res ?? {};
    },
  });

  const jobs = (data as any)?.jobs ?? [];

  const createJob = useMutation({
    mutationFn: async () => {
      await api.post("/api/cron-jobs", { name: form.name, prompt: form.prompt, schedule_type: form.scheduleType, schedule_expr: form.scheduleExpr });
    },
    onSuccess: () => { setShowForm(false); setForm({ name: "", prompt: "", scheduleType: "nl", scheduleExpr: "*/30 * * * *", nlInput: "" }); queryClient.invalidateQueries({ queryKey: ["cron-jobs"] }); },
  });

  const deleteJob = useMutation({
    mutationFn: async (jobId: string) => { await api.delete(`/api/cron-jobs/${jobId}`); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cron-jobs"] }),
  });

  const runNow = useMutation({
    mutationFn: async (jobId: string) => { await api.post(`/api/cron-jobs/${jobId}/run`, {}); },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-neutral-100">Scheduled Pipelines</h2>
          <p className="text-sm text-neutral-500 mt-1">Run pipelines on a recurring schedule</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.98]">
          {showForm ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />}
          {showForm ? "Cancel" : "Add Job"}
        </button>
      </div>

      <AnimatePresence>
        {showForm && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Name</label>
                  <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Daily Regression" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-neutral-400">Schedule Type</label>
                  <StyledSelect value={form.scheduleType} onChange={(e) => setForm({ ...form, scheduleType: e.target.value })}>
                    <option value="nl" className="bg-surface">Natural Language</option>
                    <option value="interval" className="bg-surface">Interval</option>
                    <option value="cron" className="bg-surface">Cron</option>
                  </StyledSelect>
                </div>
                {form.scheduleType === "nl" ? (
                  <div className="space-y-3 col-span-2">
                    <div className="space-y-1.5">
                      <label className="text-xs text-neutral-400">Describe the schedule</label>
                      <input value={form.nlInput} onChange={(e) => setForm({ ...form, nlInput: e.target.value, scheduleExpr: nlToCron(e.target.value) || form.scheduleExpr })} placeholder="e.g. every weekday at 9 AM" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50" />
                      <p className="text-[10px] text-neutral-600">Try: "daily at midnight", "every 30 minutes", "weekdays at 5 PM", "hourly"</p>
                    </div>
                    {form.nlInput && cronPreview && typeof cronPreview === "string" && cronPreview.startsWith("0") && (
                      <p className="text-[10px] font-mono text-emerald-500">Cron: <span className="text-emerald-400">{cronPreview}</span></p>
                    )}
                    {form.nlInput && cronPreview === "Could not parse — try a preset below" && (
                      <p className="text-[10px] text-amber-500">{cronPreview}</p>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      {NL_SCHEDULE_PRESETS.map((preset) => (
                        <button key={preset.cron} onClick={() => setForm({ ...form, nlInput: preset.label, scheduleExpr: preset.cron })} className="text-[10px] px-2 py-1 rounded-md bg-zinc-800/50 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50 transition-colors border border-zinc-700/30">
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1.5 col-span-2">
                    <label className="text-xs text-neutral-400">Cron Expression</label>
                    <input value={form.scheduleExpr} onChange={(e) => setForm({ ...form, scheduleExpr: e.target.value })} placeholder="*/30 * * * *" className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 font-mono focus:outline-none focus:border-emerald-500/50" />
                  </div>
                )}
                <div className="space-y-1.5 col-span-2">
                  <label className="text-xs text-neutral-400">Prompt</label>
                  <textarea value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} rows={3} placeholder="Enter the pipeline prompt to run..." className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500/50 resize-none" />
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={() => createJob.mutate()} disabled={!form.name || !form.prompt || createJob.isPending} className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg bg-emerald-500 text-white hover:bg-emerald-400 transition-colors disabled:opacity-40 active:scale-[0.98]">
                  {createJob.isPending ? "Saving..." : <><Check className="w-3.5 h-3.5" strokeWidth={1.5} /> Create Job</>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {jobs.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-48 text-neutral-600 text-sm gap-3">
          <Clock className="w-10 h-10 opacity-30" strokeWidth={1} />
          <p>No cron jobs configured. Click "Add Job" to create one.</p>
        </div>
      )}

      <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06]">
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Schedule</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">State</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500">Last Run</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-neutral-500">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j: any) => (
                <tr key={j.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="px-4 py-3 text-sm text-neutral-300">{j.name}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-mono text-neutral-400 bg-white/[0.04] px-2 py-0.5 rounded">{j.schedule_expr || "—"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${j.state === "running" ? "bg-blue-500/10 text-blue-400" : j.state === "scheduled" ? "bg-emerald-500/10 text-emerald-400" : "bg-neutral-500/10 text-neutral-500"}`}>{j.state || "idle"}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-500">{j.last_run_at ? new Date(j.last_run_at).toLocaleDateString() : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button onClick={() => runNow.mutate(j.id)} className="p-1.5 rounded-lg hover:bg-white/[0.06] text-neutral-500 hover:text-emerald-400 transition-colors active:scale-[0.98]">
                        <Play className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </button>
                      <button onClick={() => deleteJob.mutate(j.id)} className="p-1.5 rounded-lg hover:bg-white/[0.06] text-neutral-500 hover:text-red-400 transition-colors active:scale-[0.98]">
                        <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
