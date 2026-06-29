"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { CheckSquare, Square, Play, X, Beaker, Loader2 } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface BatchRerunProps {
  runId: string;
  tests: Array<{
    testName: string;
    status: string;
    durationMs?: number;
    error?: string;
  }>;
  requirements?: string;
}

export function BatchRerun({ runId, tests, requirements }: BatchRerunProps) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isOpen, setIsOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const failedTests = tests.filter((t) => t.status === "failed");
  const allSelected = selected.size === tests.length;
  const hasSelection = selected.size > 0;

  const toggleAll = () => {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(tests.map((t) => t.testName)));
  };

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const selectFailed = () => {
    setSelected(new Set(failedTests.map((t) => t.testName)));
  };

  const handleRerun = async () => {
    if (!hasSelection) return;
    setIsSending(true);
    try {
      const data = await api.post<{ run_id?: string }>(`/api/runs/${runId}/rerun`, {
        test_names: Array.from(selected),
        requirements: requirements ? `${requirements}\n\nRe-running: ${Array.from(selected).join(", ")}` : undefined,
      });
      if (data?.run_id) {
        toast.success(`Re-run created: ${data.run_id.slice(0, 8)}`);
        router.push(`/history/${data.run_id}`);
      }
    } catch {
      toast.error("Failed to create re-run");
    } finally {
      setIsSending(false);
    }
  };

  if (tests.length === 0) return null;

  return (
    <div className="bg-zinc-900/50 border border-white/[0.05] rounded-3xl overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 hover:bg-white/[0.01] transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <Play className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
          </div>
          <span className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">Batch Re-Run</span>
          {failedTests.length > 0 && (
            <span className="text-[10px] font-mono text-amber-400/80 px-1.5 py-0.5 rounded bg-amber-500/10">
              {failedTests.length} failed
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasSelection && (
            <span className="text-[10px] font-mono text-zinc-500">{selected.size} selected</span>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
            className="text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            {isOpen ? <X className="w-3.5 h-3.5" strokeWidth={1.5} /> : <Play className="w-3.5 h-3.5" strokeWidth={1.5} />}
          </button>
        </div>
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden border-t border-white/[0.05]"
          >
            <div className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleAll}
                  className="flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  {allSelected
                    ? <CheckSquare className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />
                    : <Square className="w-3.5 h-3.5" strokeWidth={1.5} />
                  }
                  All
                </button>
                {failedTests.length > 0 && (
                  <button
                    onClick={selectFailed}
                    className="flex items-center gap-1.5 text-[11px] text-amber-400/70 hover:text-amber-400 transition-colors"
                  >
                    <Beaker className="w-3.5 h-3.5" strokeWidth={1.5} />
                    Failed only
                  </button>
                )}
              </div>

              <div className="max-h-48 overflow-y-auto space-y-1">
                {tests.map((test) => (
                  <button
                    key={test.testName}
                    onClick={() => toggle(test.testName)}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-colors",
                      selected.has(test.testName)
                        ? "bg-emerald-500/8 text-zinc-200"
                        : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.02]",
                    )}
                  >
                    {selected.has(test.testName)
                      ? <CheckSquare className="w-3.5 h-3.5 text-emerald-400 shrink-0" strokeWidth={1.5} />
                      : <Square className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
                    }
                    <span className="truncate flex-1 text-left">{test.testName}</span>
                    <span className={cn(
                      "text-[9px] font-mono px-1 py-0.5 rounded shrink-0",
                      test.status === "passed" ? "text-emerald-400/60 bg-emerald-500/8" :
                      test.status === "failed" ? "text-red-400/60 bg-red-500/8" :
                      "text-zinc-600 bg-white/[0.03]",
                    )}>
                      {test.status}
                    </span>
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleRerun}
                  disabled={!hasSelection || isSending}
                  className={cn(
                    "flex items-center gap-1.5 px-4 h-8 rounded-xl text-xs font-semibold transition-all",
                    hasSelection && !isSending
                      ? "bg-emerald-500 hover:bg-emerald-400 text-black active:scale-[0.97]"
                      : "bg-zinc-800 text-zinc-600 cursor-not-allowed",
                  )}
                >
                  {isSending ? (
                    <Loader2 className="w-3 h-3 animate-spin" strokeWidth={2} />
                  ) : (
                    <Play className="w-3 h-3" strokeWidth={2} />
                  )}
                  Re-Run Selected
                </button>
                {hasSelection && (
                  <span className="text-[10px] text-zinc-600 font-mono">
                    {selected.size} test{selected.size > 1 ? "s" : ""}
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
