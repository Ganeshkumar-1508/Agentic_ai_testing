"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/api-client";
import { Button } from "@/components/ui/button";
import { StyledSelect } from "@/components/ui/styled-select";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Clock, Sparkles, Plus, Check, X, Loader2, GitBranch, Cpu, UserRound, GitFork } from "lucide-react";

interface BlueprintSlot {
  name: string;
  type: string;
  title: string;
  default?: any;
  enum?: string[];
  description?: string;
}

interface Blueprint {
  key: string;
  title: string;
  description: string;
  category: string;
  tags: string[];
  form_schema: {
    properties: Record<string, BlueprintSlot>;
    required: string[];
  };
}

interface WorkflowSummary {
  key: string;
  title: string;
  description: string;
  steps: number;
  tags: string[];
}

const STEP_TYPE_ICONS: Record<string, any> = {
  agent: Cpu,
  human_input: UserRound,
  router: GitFork,
};

export function BlueprintPanel() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"cron" | "workflows">("cron");
  const [selected, setSelected] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [showSuccess, setShowSuccess] = useState<string | null>(null);

  const { data: bpData, isLoading: bpLoading } = useQuery({
    queryKey: ["cron-blueprints"],
    queryFn: async () => {
      const res = await api.get<{ blueprints: Blueprint[] }>("/api/cron/blueprints");
      return res?.blueprints ?? [];
    },
  });

  const { data: wfData, isLoading: wfLoading } = useQuery({
    queryKey: ["workflows"],
    queryFn: async () => {
      const res = await api.get<{ workflows: WorkflowSummary[] }>("/api/workflows");
      return res?.workflows ?? [];
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: async ({ key, values: v }: { key: string; values: Record<string, string> }) => {
      return api.post(`/api/cron/blueprints/${key}/schedule`, { values: v });
    },
    onSuccess: () => {
      setShowSuccess(selected);
      setSelected(null);
      setValues({});
      queryClient.invalidateQueries({ queryKey: ["cron-jobs"] });
      setTimeout(() => setShowSuccess(null), 3000);
    },
  });

  const blueprints = Array.isArray(bpData) ? bpData : [];
  const workflows = Array.isArray(wfData) ? wfData : [];
  const isLoading = tab === "cron" ? bpLoading : wfLoading;

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-zinc-900/50 border border-zinc-800/30 rounded-xl p-1">
          <button onClick={() => setTab("cron")}
            className={cn("px-3 py-1.5 text-[10px] rounded-lg font-medium transition-colors",
              tab === "cron" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300")}>
            Scheduled
          </button>
          <button onClick={() => setTab("workflows")}
            className={cn("px-3 py-1.5 text-[10px] rounded-lg font-medium transition-colors",
              tab === "workflows" ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-300")}>
            <GitBranch size={10} strokeWidth={1.5} className="inline mr-1" />
            Workflows
          </button>
        </div>
        {tab === "workflows" && (
          <button onClick={() => router.push("/workflows")}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] hover:bg-emerald-500/20 transition-all active:scale-[0.97]">
            <Plus size={11} strokeWidth={1.5} />
            New Workflow
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-zinc-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading...
        </div>
      ) : tab === "cron" ? (
        <CronBlueprints
          blueprints={blueprints}
          selected={selected}
          values={values}
          showSuccess={showSuccess}
          onSelect={setSelected}
          onValuesChange={setValues}
          onSchedule={(key, v) => scheduleMutation.mutate({ key, values: v })}
          isPending={scheduleMutation.isPending}
        />
      ) : (
        <WorkflowList workflows={workflows} onNavigate={(key) => router.push(`/workflows/${key}`)} />
      )}
    </div>
  );
}

function CronBlueprints({
  blueprints, selected, values, showSuccess,
  onSelect, onValuesChange, onSchedule, isPending,
}: {
  blueprints: Blueprint[];
  selected: string | null;
  values: Record<string, string>;
  showSuccess: string | null;
  onSelect: (k: string | null) => void;
  onValuesChange: (v: Record<string, string>) => void;
  onSchedule: (key: string, v: Record<string, string>) => void;
  isPending: boolean;
}) {
  return (
    <AnimatePresence mode="popLayout">
      {blueprints.length === 0 ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center h-24 text-zinc-600 text-sm gap-2">
          <Sparkles className="w-6 h-6 opacity-30" strokeWidth={1} />
          <p>No blueprints available</p>
        </motion.div>
      ) : blueprints.map((bp, i) => (
        <motion.div key={bp.key} layout
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 100, damping: 20, delay: i * 0.04 }}
          className="border border-zinc-800/30 rounded-3xl shimmer-bg p-4 space-y-3">

          <div className="flex items-start justify-between cursor-pointer"
               onClick={() => onSelect(selected === bp.key ? null : bp.key)}>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <Sparkles className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
              </div>
              <div>
                <h3 className="text-sm font-medium text-zinc-200">{bp.title}</h3>
                <p className="text-[11px] text-zinc-500 mt-0.5">{bp.description}</p>
                <div className="flex gap-1.5 mt-2">
                  {bp.tags.map((t) => (
                    <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-md bg-zinc-800/60 text-zinc-500">{t}</span>
                  ))}
                  <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-zinc-800/60 text-zinc-500">{bp.category}</span>
                </div>
              </div>
            </div>
            <div className="text-zinc-600 text-xs mt-1">
              {selected === bp.key ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            </div>
          </div>

          {showSuccess === bp.key && (
            <div className="flex items-center gap-2 text-emerald-400 text-xs px-1 py-2">
              <Check className="w-3.5 h-3.5" /> Scheduled successfully!
            </div>
          )}

          {selected === bp.key && showSuccess !== bp.key && (
            <div className="space-y-3 pt-2 border-t border-zinc-800/20">
              {Object.entries(bp.form_schema.properties).map(([fieldName, field]) => (
                <div key={fieldName} className="space-y-1">
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">{field.title}</label>
                  {field.type === "enum" && field.enum ? (
                    <StyledSelect value={values[fieldName] ?? field.default ?? ""}
                      onChange={(e) => onValuesChange({ ...values, [fieldName]: e.target.value })}>
                      {field.enum.map((opt) => (<option key={opt} value={opt}>{opt}</option>))}
                    </StyledSelect>
                  ) : field.type === "time" ? (
                    <Input type="time" value={values[fieldName] ?? field.default ?? "08:00"}
                      onChange={(e) => onValuesChange({ ...values, [fieldName]: e.target.value })}
                      className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg font-mono" />
                  ) : (
                    <Input value={values[fieldName] ?? field.default ?? ""}
                      onChange={(e) => onValuesChange({ ...values, [fieldName]: e.target.value })}
                      placeholder={field.description || ""}
                      className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg" />
                  )}
                  {field.description && <p className="text-[9px] text-zinc-600">{field.description}</p>}
                </div>
              ))}
              <div className="flex justify-end pt-1">
                <Button onClick={() => onSchedule(bp.key, values)}
                  disabled={isPending}
                  className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5">
                  {isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Clock className="w-3.5 h-3.5" strokeWidth={1.5} />}
                  Schedule
                </Button>
              </div>
            </div>
          )}
        </motion.div>
      ))}
    </AnimatePresence>
  );
}

function WorkflowList({ workflows, onNavigate }: { workflows: WorkflowSummary[]; onNavigate: (key: string) => void }) {
  if (workflows.length === 0) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        className="flex flex-col items-center justify-center py-12 text-zinc-600 gap-2">
        <GitBranch size={20} strokeWidth={1} className="text-zinc-700" />
        <p className="text-sm">No workflows yet</p>
        <p className="text-xs text-zinc-700">Create a workflow to define multi-step agent pipelines</p>
      </motion.div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3">
      {workflows.map((wf, i) => (
        <motion.div key={wf.key} layout
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 100, damping: 20, delay: i * 0.04 }}
          onClick={() => onNavigate(wf.key)}
          className="border border-zinc-800/30 rounded-2xl p-3.5 space-y-2.5 cursor-pointer hover:border-zinc-700/50 transition-all group">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0">
                <GitBranch size={12} className="text-indigo-400" strokeWidth={1.5} />
              </div>
              <div className="min-w-0">
                <h3 className="text-[13px] font-medium text-zinc-200 truncate">{wf.title}</h3>
                <p className="text-[10px] text-zinc-600 font-mono truncate">{wf.key}</p>
              </div>
            </div>
            <div className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] text-zinc-600">
              Edit &rarr;
            </div>
          </div>
          {wf.description && (
            <p className="text-[11px] text-zinc-600 line-clamp-2">{wf.description}</p>
          )}
          <div className="flex items-center gap-2 text-[10px] text-zinc-600">
            <span>{wf.steps || 0} steps</span>
            {wf.tags?.map((t) => (
              <span key={t} className="px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-500">{t}</span>
            ))}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
