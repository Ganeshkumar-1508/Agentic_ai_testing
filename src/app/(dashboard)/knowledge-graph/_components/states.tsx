"use client";

import { motion } from "framer-motion";
import { Network, FileText, AlertTriangle, Check, Loader2 } from "lucide-react";
import { SectionCard } from "./mini-ui";

export function CanvasLoadingState() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-background/72 backdrop-blur-sm">
      <div className="w-full max-w-[280px] rounded-3xl border border-white/[0.06] bg-zinc-950/82 p-4 shadow-[0_24px_80px_rgba(0,0,0,0.28)]">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-emerald-400/16 bg-emerald-500/10">
            <Loader2 className="h-5 w-5 animate-spin text-emerald-300/80" strokeWidth={1.6} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium text-neutral-200">Loading graph snapshot</p>
            <p className="text-[10px] font-mono text-neutral-500">Hydrating nodes, edges, and metadata…</p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <div className="shimmer-bg h-16 rounded-2xl" />
          <div className="shimmer-bg h-16 rounded-2xl" />
          <div className="shimmer-bg h-16 rounded-2xl" />
        </div>
      </div>
    </motion.div>
  );
}

export function CanvasEmptyState() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="rounded-3xl border border-white/[0.06] bg-zinc-950/76 px-8 py-7 shadow-[0_24px_80px_rgba(0,0,0,0.24)] backdrop-blur-md">
        <Network className="mx-auto h-10 w-10 text-neutral-700" strokeWidth={1.2} />
        <div className="mt-3 space-y-1">
          <p className="text-[14px] font-medium text-neutral-200">No knowledge graph available</p>
          <p className="max-w-[320px] text-[11px] leading-6 text-neutral-500">Run the coordinator agent to clone the repo and build the initial knowledge graph snapshot.</p>
        </div>
      </div>
    </motion.div>
  );
}

export function CanvasNoNodesState() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="rounded-3xl border border-white/[0.06] bg-zinc-950/76 px-8 py-7 shadow-[0_24px_80px_rgba(0,0,0,0.24)] backdrop-blur-md">
        <FileText className="mx-auto h-8 w-8 text-neutral-700" strokeWidth={1.2} />
        <div className="mt-3 space-y-1">
          <p className="text-[14px] font-medium text-neutral-200">Graph contains no nodes</p>
          <p className="max-w-[320px] text-[11px] leading-6 text-neutral-500">The selected snapshot loaded correctly, but it does not yet expose symbol-level data.</p>
        </div>
      </div>
    </motion.div>
  );
}

export function CanvasErrorState({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/84 text-center backdrop-blur-sm">
      <AlertTriangle className="h-8 w-8 text-rose-300/80" strokeWidth={1.5} />
      <div className="space-y-1">
        <p className="text-[14px] font-medium text-rose-200">Graph request failed</p>
        <p className="max-w-md text-[11px] font-mono text-neutral-500">{message ?? "Unable to fetch graph data from the backend contract."}</p>
      </div>
      <button type="button" onClick={onRetry}
        className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-[11px] font-medium text-rose-200 transition-colors hover:bg-rose-500/14">
        Retry request
      </button>
    </motion.div>
  );
}

export function EmptyStage({ isLoading, hasGraphs, onSelectFirst }: { isLoading: boolean; hasGraphs: boolean; onSelectFirst: () => void }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center bg-[radial-gradient(circle_at_30%_30%,rgba(52,211,153,0.06),transparent_24%),#0a0a0f] px-6">
      <div className="w-full max-w-lg rounded-3xl border border-white/[0.06] bg-surface/88 p-8 text-center shadow-[0_20px_80px_rgba(0,0,0,0.35)] backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-400/20 bg-emerald-500/10">
          {isLoading ? <Loader2 className="h-6 w-6 animate-spin text-emerald-300" strokeWidth={1.6} /> : <Network className="h-6 w-6 text-emerald-300" strokeWidth={1.6} />}
        </div>
        <h3 className="mt-4 text-[18px] font-semibold text-neutral-100">
          {isLoading ? "Loading graph inventory" : "Choose a graph snapshot"}
        </h3>
        <p className="mt-2 text-[12px] leading-6 text-neutral-500">
          {hasGraphs ? "The left graph rail has been collapsed. Use the top-bar switcher to move between snapshots." : "No indexed knowledge graphs are available yet. Once the backend creates a snapshot, it will appear in the top-bar selector."}
        </p>
        {hasGraphs ? (
          <button type="button" onClick={onSelectFirst}
            className="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-2 text-[12px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/16">
            Open latest graph
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function SelectionGuidanceState({ title, body }: { title: string; body: string }) {
  return (
    <SectionCard className="border-dashed">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-xl border border-white/[0.06] bg-white/[0.03]">
          <Check className="h-4 w-4 text-neutral-500" strokeWidth={1.7} />
        </div>
        <div>
          <div className="text-[12px] font-medium text-neutral-100">{title}</div>
          <p className="mt-1 text-[11px] leading-6 text-neutral-500">{body}</p>
        </div>
      </div>
    </SectionCard>
  );
}

export function RailSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="rounded-2xl border border-white/[0.05] bg-white/[0.02] p-4">
          <div className="shimmer-bg h-3 w-24 rounded" />
          <div className="mt-3 shimmer-bg h-4 w-3/4 rounded" />
          <div className="mt-2 shimmer-bg h-3 w-full rounded" />
          <div className="mt-1.5 shimmer-bg h-3 w-4/5 rounded" />
        </div>
      ))}
    </div>
  );
}
