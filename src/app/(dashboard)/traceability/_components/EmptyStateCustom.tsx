"use client";

import { motion } from "framer-motion";
import { GitBranch, Beaker, Sparkles, Plus, AlertCircle } from "lucide-react";

export function TraceabilityEmptyState({
  onAdd,
  onGenerate,
}: {
  onAdd: () => void;
  onGenerate: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] as const }}
      className="bg-surface border border-white/[0.06] rounded-[1.5rem] card-glow relative overflow-hidden"
      style={{ minHeight: 540 }}
    >
      <div className="absolute inset-0 pointer-events-none opacity-[0.04]">
        <GhostGraph />
      </div>

      <div className="relative z-10 flex flex-col items-center justify-center text-center px-6 py-20">
        <div className="flex items-center gap-3 mb-6">
          <GhostNode icon={GitBranch} tone="indigo" />
          <GhostConnector />
          <GhostNode icon={Beaker} tone="emerald" />
          <GhostConnector />
          <GhostNode icon={AlertCircle} tone="rose" dashed />
        </div>

        <div className="text-[10.5px] font-mono text-neutral-600 uppercase tracking-wider mb-2">
          Traceability graph
        </div>
        <h3 className="text-2xl font-semibold text-neutral-100 tracking-tight mb-2">
          No requirements yet
        </h3>
        <p className="text-[13px] text-neutral-500 max-w-md leading-relaxed mb-7">
          Build a chain from <span className="text-zinc-300">requirements</span> through{" "}
          <span className="text-emerald-300">tests</span> to{" "}
          <span className="text-rose-300">defects</span>. Add one manually, or generate them with the LLM.
        </p>

        <div className="flex items-center gap-3">
          <button
            onClick={onGenerate}
            className="px-4 py-2 rounded-lg text-[13px] font-medium text-emerald-300 bg-emerald-500/10 border border-emerald-500/25 hover:bg-emerald-500/15 hover:border-emerald-500/35 transition-colors flex items-center gap-2"
          >
            <Sparkles className="w-3.5 h-3.5" strokeWidth={1.5} />
            Generate from goal
          </button>
          <button
            onClick={onAdd}
            className="px-4 py-2 rounded-lg text-[13px] font-medium text-neutral-100 bg-white/[0.06] border border-white/[0.08] hover:bg-white/[0.09] transition-colors flex items-center gap-2"
          >
            <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
            Add manually
          </button>
        </div>

        <div className="mt-10 grid grid-cols-3 gap-3 max-w-2xl w-full">
          <HintCard
            tone="indigo"
            label="1. Add requirement"
            description="Describe the user-visible behavior you want to verify."
          />
          <HintCard
            tone="emerald"
            label="2. Link tests"
            description="Auto-generate 5 test cases from the description, or link existing ones."
          />
          <HintCard
            tone="rose"
            label="3. Track defects"
            description="Failing tests surface as defects on the right rail of the graph."
          />
        </div>
      </div>
    </motion.div>
  );
}

function GhostNode({
  icon: Icon,
  tone,
  dashed = false,
}: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  tone: "indigo" | "emerald" | "rose";
  dashed?: boolean;
}) {
  const toneClass = {
    indigo: "border-zinc-400/30 bg-zinc-500/[0.08] text-zinc-300",
    emerald: "border-emerald-400/30 bg-emerald-500/[0.08] text-emerald-300",
    rose: "border-rose-400/30 bg-rose-500/[0.06] text-rose-300",
  }[tone];
  return (
    <div
      className={`w-16 h-12 rounded-lg border flex items-center justify-center ${toneClass} ${
        dashed ? "border-dashed" : ""
      }`}
    >
      <Icon className="w-4 h-4" strokeWidth={1.5} />
    </div>
  );
}

function GhostConnector() {
  return (
    <div className="w-10 h-px bg-white/[0.08]" />
  );
}

function HintCard({
  tone,
  label,
  description,
}: {
  tone: "indigo" | "emerald" | "rose";
  label: string;
  description: string;
}) {
  const dotClass = {
    indigo: "bg-zinc-400",
    emerald: "bg-emerald-400",
    rose: "bg-rose-400",
  }[tone];
  return (
    <div className="text-left p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
        <span className="text-[10.5px] font-mono text-neutral-500 uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-[11.5px] text-neutral-400 leading-relaxed">{description}</p>
    </div>
  );
}

function GhostGraph() {
  return (
    <svg width="100%" height="100%" viewBox="0 0 800 500" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="ghost-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="rgba(255,255,255,0.04)" />
          <stop offset="0.5" stopColor="rgba(255,255,255,0.12)" />
          <stop offset="1" stopColor="rgba(255,255,255,0.04)" />
        </linearGradient>
      </defs>
      {Array.from({ length: 6 }).map((_, row) =>
        Array.from({ length: 8 }).map((_, col) => {
          const x = col * 110 + 40;
          const y = row * 80 + 40;
          return <circle key={`${row}-${col}`} cx={x} cy={y} r={1} fill="rgba(255,255,255,0.06)" />;
        })
      )}
      <line x1="100" y1="120" x2="350" y2="120" stroke="url(#ghost-line)" strokeWidth={1} />
      <line x1="100" y1="120" x2="350" y2="240" stroke="url(#ghost-line)" strokeWidth={1} />
      <line x1="100" y1="240" x2="350" y2="240" stroke="url(#ghost-line)" strokeWidth={1} />
      <line x1="450" y1="180" x2="700" y2="180" stroke="url(#ghost-line)" strokeWidth={1} strokeDasharray="4 3" />
    </svg>
  );
}
