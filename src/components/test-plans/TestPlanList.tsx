"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ClipboardList, Eye, Tag, FileCode, ChevronRight, ChevronDown, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";

/** TestPlan shape — the server side projects the dataclass
 * (harness/test_plan.py:TestPlan) to JSON via the
 * `_plan_to_dict` helper in `routers/test_plans.py`. The
 * `invariants` field is the most useful projection (each
 * Invariant projects to a dict with id, description, target,
 * category, risk). */
interface TestPlanSummary {
  plan_id: string;
  run_id: string;
  spec_id: string;
  repo_url: string;
  repo_sha: string;
  framework: string;
  invariants: Array<{
    id: string;
    description: string;
    target: string;
    category: string;
    risk: string;
  }>;
  files: string[];
  risk: "low" | "medium" | "high";
  requires_browser: boolean;
  intent_hash: string;
  created_at: string | null;
}

const RISK_STYLES: Record<string, string> = {
  low: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  high: "text-red-400 bg-red-500/10 border-red-500/20",
};

const CATEGORY_STYLES: Record<string, string> = {
  "happy-path": "text-zinc-300 bg-zinc-500/8",
  "edge-case": "text-zinc-300 bg-zinc-500/8",
  "regression": "text-amber-300 bg-amber-500/8",
  "security": "text-red-300 bg-red-500/8",
  "performance": "text-emerald-300 bg-emerald-500/8",
};

function shortHash(h: string): string {
  return h ? h.slice(0, 10) : "";
}

function shortRepo(url: string): string {
  if (!url) return "";
  const cleaned = url.replace(/^https?:\/\//, "").replace(/\.git$/, "");
  const parts = cleaned.split("/");
  return parts.slice(-2).join("/");
}

/** TestPlanList — a small "recent TestPlans" surface for the
 * test-cases page. Renders a horizontal scroll of plan cards;
 * clicking one opens a slide-over with the invariants + a button
 * to surface the planner role body.
 *
 * Per C2.1: TestPlan is the durable handoff between explore and
 * test-generation. The frontend surfacing here is a thin read
 * layer; the actual planner is a subagent the orchestrator
 * invokes (follow-up).
 */
export function TestPlanList() {
  const [plans, setPlans] = useState<TestPlanSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<TestPlanSummary | null>(null);
  const [plannerPrompt, setPlannerPrompt] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ plans?: TestPlanSummary[] }>("/api/test-plans?limit=10");
      setPlans(data?.plans ?? []);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const loadPrompt = useCallback(async () => {
    if (plannerPrompt !== null) {
      setShowPrompt((s) => !s);
      return;
    }
    try {
      const data = await api.get<{ prompt?: string }>("/api/test-plans/prompt");
      setPlannerPrompt(data?.prompt ?? "");
      setShowPrompt(true);
    } catch {
      toast.error("Could not load planner role");
    }
  }, [plannerPrompt]);

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-3.5 h-3.5 text-zinc-400" strokeWidth={1.5} />
          <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
            Test Plans
          </span>
          <span className="text-[10px] font-mono text-neutral-700">
            {plans.length} recent
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={loadPrompt}
            className="flex items-center gap-1 text-[10px] text-neutral-500 hover:text-zinc-300 bg-white/[0.02] border border-white/[0.05] rounded-md px-2 py-1 transition-colors"
            title="Toggle planner role body"
          >
            {showPrompt ? <ChevronDown className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            Planner role
          </button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {showPrompt && plannerPrompt !== null && (
          <motion.pre
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="text-[10px] text-neutral-400 font-mono leading-relaxed bg-white/[0.02] border border-white/[0.04] rounded-md p-3 max-h-48 overflow-y-auto mb-3 whitespace-pre-wrap"
          >
            {plannerPrompt || "(planner role body is empty)"}
          </motion.pre>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="flex items-center gap-2 text-[11px] text-neutral-600 py-2">
          <Loader2 className="w-3 h-3 animate-spin" />
          Loading TestPlans…
        </div>
      ) : plans.length === 0 ? (
        <div className="text-[11px] text-neutral-600 text-center py-3">
          No TestPlans yet. The C2.1 planner subagent will produce them during the
          explore phase of a run.
        </div>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {plans.map((p) => (
            <button
              key={p.plan_id}
              type="button"
              onClick={() => setSelected(p)}
              className={cn(
                "shrink-0 w-[280px] text-left bg-white/[0.02] border border-white/[0.05] rounded-xl p-3 transition-colors",
                "hover:border-zinc-500/30 hover:bg-zinc-500/4",
                selected?.plan_id === p.plan_id && "border-zinc-500/40 bg-zinc-500/5",
              )}
            >
              <div className="flex items-center gap-1.5 mb-1.5">
                <FileCode className="w-3 h-3 text-zinc-300" strokeWidth={1.5} />
                <span className="text-[12px] font-medium text-neutral-200 truncate">
                  {p.framework}
                </span>
                <span
                  className={cn(
                    "text-[9px] px-1.5 py-0.5 rounded font-mono uppercase",
                    RISK_STYLES[p.risk] || RISK_STYLES.medium,
                  )}
                >
                  {p.risk}
                </span>
                {p.requires_browser && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded font-mono bg-blue-500/8 text-blue-300">
                    browser
                  </span>
                )}
              </div>
              <div className="text-[10px] text-neutral-500 font-mono truncate mb-1">
                {shortRepo(p.repo_url)}
              </div>
              <div className="flex items-center gap-3 text-[10px] text-neutral-600">
                <span className="flex items-center gap-1">
                  <Tag className="w-2.5 h-2.5" strokeWidth={1.5} />
                  {p.invariants.length} invariants
                </span>
                <span className="font-mono">…{shortHash(p.intent_hash)}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="mt-3 border-t border-white/[0.04] pt-3"
          >
            <div className="flex items-center gap-2 mb-2">
              <ChevronRight className="w-3 h-3 text-zinc-400" strokeWidth={1.5} />
              <span className="text-[11px] font-medium text-neutral-300">
                {selected.framework}
                <span className="text-neutral-600"> · </span>
                <span className="text-neutral-500 font-mono text-[10px]">
                  {shortRepo(selected.repo_url)} @ {selected.repo_sha.slice(0, 7)}
                </span>
              </span>
            </div>
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {selected.invariants.length === 0 ? (
                <div className="text-[11px] text-neutral-600 italic">No invariants on this plan.</div>
              ) : (
                selected.invariants.map((inv) => (
                  <div
                    key={inv.id}
                    className="flex items-start gap-2 text-[11px] py-1.5 border-b border-white/[0.03] last:border-0"
                  >
                    <span
                      className={cn(
                        "shrink-0 text-[9px] px-1.5 py-0.5 rounded font-mono uppercase",
                        CATEGORY_STYLES[inv.category] || CATEGORY_STYLES["happy-path"],
                      )}
                    >
                      {inv.category}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-neutral-300">{inv.description}</div>
                      <div className="text-[10px] text-neutral-600 font-mono truncate">
                        {inv.target}
                      </div>
                    </div>
                    <span
                      className={cn(
                        "shrink-0 text-[9px] px-1.5 py-0.5 rounded font-mono uppercase",
                        RISK_STYLES[inv.risk] || RISK_STYLES.medium,
                      )}
                    >
                      {inv.risk}
                    </span>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
