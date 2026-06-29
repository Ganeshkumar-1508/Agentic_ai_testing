"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, Save, Sparkles, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { Requirement, Priority, ReqStatus } from "./types";
import { PRIORITY_TONE, REQ_STATUS_TONE } from "./constants";
import { useCreateRequirement, useUpdateRequirement, useGenerateTests } from "./use-traceability";

const PRIORITIES: Priority[] = ["high", "medium", "low"];
const STATUSES: ReqStatus[] = ["active", "draft", "archived"];

export function RequirementForm({
  open,
  onClose,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  initial: Requirement | null;
}) {
  const createMut = useCreateRequirement();
  const updateMut = useUpdateRequirement();
  const generateMut = useGenerateTests();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [status, setStatus] = useState<ReqStatus>("active");
  const [generateAfter, setGenerateAfter] = useState(true);

  useEffect(() => {
    if (initial) {
      setTitle(initial.title);
      setDescription(initial.description ?? "");
      setPriority(initial.priority);
      setStatus(initial.status);
    } else {
      setTitle("");
      setDescription("");
      setPriority("medium");
      setStatus("active");
      setGenerateAfter(true);
    }
  }, [initial, open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const submitting = createMut.isPending || updateMut.isPending || generateMut.isPending;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    if (initial) {
      updateMut.mutate(
        { id: initial.id, title, status },
        {
          onSuccess: () => {
            onClose();
          },
        }
      );
      return;
    }

    createMut.mutate(
      { title, description, priority },
      {
        onSuccess: ({ requirement }) => {
          if (generateAfter) {
            generateMut.mutate({ requirement_ids: [requirement.id] }, {
              onSettled: () => onClose(),
            });
          } else {
            onClose();
          }
        },
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
            <form
              onSubmit={onSubmit}
              className="w-full max-w-lg bg-surface border border-white/[0.08] rounded-2xl p-6 pointer-events-auto"
              style={{ boxShadow: "0 20px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04)" }}
            >
              <div className="flex items-center justify-between mb-5">
                <div>
                  <div className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider">
                    {initial ? "Edit" : "New"} requirement
                  </div>
                  <h2 className="text-lg font-semibold text-neutral-100 mt-0.5">
                    {initial ? "Update details" : "Add to traceability graph"}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="w-8 h-8 flex items-center justify-center rounded-md text-neutral-500 hover:text-neutral-200 hover:bg-white/[0.04] transition-colors"
                >
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>

              <div className="space-y-4">
                <Field label="Title" required>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Users can reset their password via email"
                    className="w-full"
                    autoFocus
                  />
                </Field>

                <Field label="Description" hint="Optional context — what does 'done' look like?">
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Acceptance criteria, edge cases, references…"
                    rows={3}
                    className="w-full resize-none"
                  />
                </Field>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Priority">
                    <div className="flex items-center gap-1">
                      {PRIORITIES.map((p) => {
                        const tone = PRIORITY_TONE[p];
                        const active = priority === p;
                        return (
                          <button
                            key={p}
                            type="button"
                            onClick={() => setPriority(p)}
                            className={cn(
                              "flex-1 px-2.5 py-1.5 rounded-md text-[11px] font-medium uppercase tracking-wider transition-all border",
                              active
                                ? "bg-white/[0.06] border-white/[0.12] text-neutral-200"
                                : "bg-transparent border-white/[0.05] text-neutral-500 hover:text-neutral-300"
                            )}
                          >
                            <span className="flex items-center justify-center gap-1.5">
                              <span className={cn("w-1 h-1 rounded-full", tone.dot)} />
                              {tone.label}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </Field>

                  <Field label="Status">
                    <div className="flex items-center gap-1">
                      {STATUSES.map((s) => {
                        const tone = REQ_STATUS_TONE[s];
                        const active = status === s;
                        return (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setStatus(s)}
                            className={cn(
                              "flex-1 px-2.5 py-1.5 rounded-md text-[11px] font-medium uppercase tracking-wider transition-all border",
                              active
                                ? "bg-white/[0.06] border-white/[0.12] text-neutral-200"
                                : "bg-transparent border-white/[0.05] text-neutral-500 hover:text-neutral-300"
                            )}
                          >
                            <span className="flex items-center justify-center gap-1.5">
                              <span className={cn("w-1 h-1 rounded-full", tone.dot)} />
                              {tone.label}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </Field>
                </div>

                {!initial && (
                  <label className="flex items-start gap-2.5 p-3 rounded-lg bg-emerald-500/[0.04] border border-emerald-500/15 cursor-pointer hover:bg-emerald-500/[0.06] transition-colors">
                    <input
                      type="checkbox"
                      checked={generateAfter}
                      onChange={(e) => setGenerateAfter(e.target.checked)}
                      className="mt-0.5 accent-emerald-500"
                    />
                    <div>
                      <div className="text-[12.5px] text-neutral-200 font-medium flex items-center gap-1.5">
                        <Sparkles className="w-3 h-3 text-emerald-400" strokeWidth={1.5} />
                        Auto-generate tests with the LLM
                      </div>
                      <div className="text-[11px] text-neutral-500 mt-0.5">
                        Creates 5 test cases and links them to this requirement.
                      </div>
                    </div>
                  </label>
                )}
              </div>

              <div className="flex items-center justify-end gap-2 mt-6">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium text-neutral-400 hover:text-neutral-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!title.trim() || submitting}
                  className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
                >
                  {submitting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                  ) : initial ? (
                    <Save className="w-3.5 h-3.5" strokeWidth={1.5} />
                  ) : (
                    <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />
                  )}
                  {initial ? "Save changes" : generateAfter ? "Create + generate" : "Create requirement"}
                </button>
              </div>
            </form>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="flex items-center gap-1 mb-1.5">
        <span className="text-[11px] font-medium text-neutral-300">{label}</span>
        {required && <span className="text-rose-400 text-[11px]">*</span>}
        {hint && <span className="text-[10.5px] font-mono text-neutral-600 ml-1">— {hint}</span>}
      </label>
      {children}
    </div>
  );
}
