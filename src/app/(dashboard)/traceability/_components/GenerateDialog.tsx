"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useGenerateTests, useRequirements } from "./use-traceability";
import { cn } from "@/lib/utils";

export function GenerateDialog({
  open,
  onClose,
  selectedRequirementIds,
}: {
  open: boolean;
  onClose: () => void;
  selectedRequirementIds?: string[];
}) {
  const reqs = useRequirements();
  const generate = useGenerateTests();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [goal, setGoal] = useState("");

  useEffect(() => {
    if (open) {
      setSelected(new Set(selectedRequirementIds ?? []));
      setGoal("");
    }
  }, [open, selectedRequirementIds]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const allRequirements = reqs.data?.requirements ?? [];
  const submitting = generate.isPending;

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const onSubmit = () => {
    if (selected.size === 0) return;
    generate.mutate(
      { requirement_ids: Array.from(selected) },
      {
        onSettled: () => onClose(),
      }
    );
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 20 }}
            transition={{ type: "spring", stiffness: 140, damping: 22 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
          >
            <div
              className="w-full max-w-xl bg-surface border border-white/[0.08] rounded-2xl p-6 pointer-events-auto flex flex-col max-h-[80vh]"
              style={{ boxShadow: "0 20px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)" }}
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider flex items-center gap-1.5">
                    <Sparkles className="w-3 h-3 text-emerald-400" strokeWidth={1.5} />
                    LLM Generate
                  </div>
                  <h2 className="text-lg font-semibold text-neutral-100 mt-0.5">Generate tests from requirements</h2>
                </div>
                <button
                  onClick={onClose}
                  className="w-8 h-8 flex items-center justify-center rounded-md text-neutral-500 hover:text-neutral-200 hover:bg-white/[0.04] transition-colors"
                >
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>

              <div className="mb-4">
                <div className="text-[11px] font-medium text-neutral-300 mb-1.5">Goal hint <span className="text-neutral-600 font-normal">— optional, biases generation</span></div>
                <input
                  type="text"
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="e.g. focus on security and edge cases"
                  className="w-full"
                />
              </div>

              <div className="text-[11px] font-medium text-neutral-300 mb-2">
                Requirements <span className="text-neutral-600 font-normal">— {selected.size} selected</span>
              </div>

              <div className="flex-1 overflow-y-auto rounded-lg border border-white/[0.04] divide-y divide-white/[0.04]">
                {allRequirements.length === 0 ? (
                  <div className="p-6 text-center text-[12px] text-neutral-500">
                    No requirements exist. Add one first.
                  </div>
                ) : (
                  allRequirements.map((r) => {
                    const isSel = selected.has(r.id);
                    return (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => toggle(r.id)}
                        className={cn(
                          "w-full text-left px-3 py-2.5 flex items-center gap-3 transition-colors",
                          isSel ? "bg-emerald-500/[0.04]" : "hover:bg-white/[0.025]"
                        )}
                      >
                        <span
                          className={cn(
                            "w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors",
                            isSel ? "bg-emerald-500/30 border-emerald-400" : "border-white/[0.1]"
                          )}
                        >
                          {isSel && <CheckCircle2 className="w-3 h-3 text-emerald-300" strokeWidth={2.5} />}
                        </span>
                        <span className="flex-1 min-w-0 text-[12.5px] text-neutral-200 truncate">{r.title}</span>
                        <span className="text-[10px] font-mono text-neutral-600 uppercase tracking-wider shrink-0">
                          {r.priority}
                        </span>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="flex items-center justify-between mt-5">
                <div className="text-[10.5px] font-mono text-neutral-600">
                  {selected.size === 0 ? "Select at least one requirement" : `${selected.size} will be processed`}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onClose}
                    className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium text-neutral-400 hover:text-neutral-200 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={onSubmit}
                    disabled={selected.size === 0 || submitting}
                    className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
                  >
                    {submitting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                    ) : (
                      <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />
                    )}
                    {submitting ? "Generating…" : "Generate tests"}
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
