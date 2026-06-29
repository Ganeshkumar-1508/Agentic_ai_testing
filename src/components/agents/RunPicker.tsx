"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ArrowLeft, ArrowRight, Shuffle } from "lucide-react";
import { api } from "@/lib/api/api-client";

interface RunSummary {
  id: string;
  status: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
  duration: number;
  createdAt: string;
}

interface RunPickerProps {
  runA: RunSummary | null;
  runB: RunSummary | null;
  loading?: boolean;
  onSelectA: (run: RunSummary) => void;
  onSelectB: (run: RunSummary) => void;
  onSwap: () => void;
}

export function RunPicker({ runA, runB, loading, onSelectA, onSelectB, onSwap }: RunPickerProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [openDropdown, setOpenDropdown] = useState<"A" | "B" | null>(null);

  useEffect(() => {
    (async () => {
      const json = await api.get<{ runs: any[] }>(`/api/runs?limit=50&offset=0`);
      setRuns((json?.runs ?? []).map((r: any) => ({
        id: r.id,
        status: r.status ?? "unknown",
        testCount: Number(r.testCount ?? 0),
        passedCount: Number(r.passedCount ?? 0),
        failedCount: Number(r.failedCount ?? 0),
        duration: Number(r.duration ?? 0),
        createdAt: r.createdAt ?? "",
      })));
    })();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-4 p-6 bg-surface border border-white/[0.06] rounded-[1.5rem]">
        <div className="w-48 h-16 rounded-xl shimmer-bg" />
        <div className="w-8 h-8 rounded-full shimmer-bg" />
        <div className="w-48 h-16 rounded-xl shimmer-bg" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-center gap-4 p-6 bg-surface border border-white/[0.06] rounded-[1.5rem]"
    >
      <RunSlot label="Run A" run={runA} runs={runs} isOpen={openDropdown === "A"} onToggle={() => setOpenDropdown(openDropdown === "A" ? null : "A")} onSelect={onSelectA} excludeId={runB?.id} />
      <motion.button
        onClick={onSwap}
        whileHover={{ scale: 1.1, rotate: 180 }}
        transition={{ type: "spring", stiffness: 200, damping: 15 }}
        className="w-9 h-9 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0"
      >
        <Shuffle className="w-4 h-4" strokeWidth={1.5} />
      </motion.button>
      <RunSlot label="Run B" run={runB} runs={runs} isOpen={openDropdown === "B"} onToggle={() => setOpenDropdown(openDropdown === "B" ? null : "B")} onSelect={onSelectB} excludeId={runA?.id} />
    </motion.div>
  );
}

function RunSlot({ label, run, runs, isOpen, onToggle, onSelect, excludeId }: {
  label: string; run: RunSummary | null; runs: RunSummary[]; isOpen: boolean; onToggle: () => void; onSelect: (r: RunSummary) => void; excludeId?: string;
}) {
  const filtered = runs.filter((r) => r.id !== excludeId);

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors min-w-[200px] text-left"
      >
        <div className="flex-1">
          <div className="text-[11px] text-neutral-500 uppercase tracking-wider">{label}</div>
          {run ? (
            <>
              <div className="text-sm font-mono text-neutral-200 mt-0.5">{run.id.slice(0, 8)}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className={cn("w-1.5 h-1.5 rounded-full", run.status === "completed" ? "bg-emerald-400" : run.status === "failed" ? "bg-red-400" : "bg-amber-400")} />
                <span className="text-xs text-neutral-500">{run.status} · {run.duration}s</span>
              </div>
            </>
          ) : (
            <div className="text-sm text-neutral-500 mt-0.5">Select a run...</div>
          )}
        </div>
        <ArrowLeft className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />
      </button>

      {isOpen && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute top-full left-0 right-0 mt-2 z-20 bg-surface-elevated border border-white/[0.08] rounded-xl overflow-hidden shadow-xl max-h-60 overflow-y-auto"
        >
          {filtered.length === 0 ? (
            <div className="px-4 py-3 text-sm text-neutral-500">No runs available</div>
          ) : (
            filtered.map((r) => (
              <button
                key={r.id}
                onClick={() => { onSelect(r); onToggle(); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.04] transition-colors text-left"
              >
                <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", r.status === "completed" ? "bg-emerald-400" : "bg-red-400")} />
                <span className="flex-1 text-sm font-mono text-neutral-300">{r.id.slice(0, 8)}</span>
                <span className="text-xs text-neutral-500">{r.duration}s</span>
              </button>
            ))
          )}
        </motion.div>
      )}
    </div>
  );
}
