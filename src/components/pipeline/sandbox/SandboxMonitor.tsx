"use client";

import { usePipelineStore } from "@/stores/pipeline-store";
import { destroySandbox } from "@/lib/services/sandbox-client";
import { SandboxFileTree } from "./SandboxFileTree";
import { SandboxResources } from "./SandboxResources";
import { SandboxPorts } from "./SandboxPorts";
import { SandboxDependencies } from "./SandboxDependencies";
import { SandboxTerminal } from "./SandboxTerminal";
import { SandboxTestSummary } from "./SandboxTestSummary";
import { SandboxFlakyTests } from "./SandboxFlakyTests";
import { SandboxArtifacts } from "./SandboxArtifacts";
import { motion } from "framer-motion";
import { Trash2, ExternalLink } from "lucide-react";

export function SandboxMonitor() {
  const { sessionId, status, connected, totalTokens, estimatedCost } = usePipelineStore();

  if (!sessionId || (status !== "running" && status !== "completed")) return null;

  const sectionVariants = {
    hidden: { opacity: 0, y: 16 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
  };

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      className="space-y-6"
      variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } } }}
    >
      {/* Row 1: Sandbox Header */}
      <motion.div variants={sectionVariants} className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-neutral-600"}`} />
            <span className="text-sm font-medium text-neutral-200">Sandbox</span>
          </div>
          <span className="text-[11px] font-mono text-neutral-600 bg-white/[0.03] border border-white/[0.06] rounded-md px-2 py-0.5">
            {sessionId.slice(0, 12)}
          </span>
          {status === "completed" && (
            <span className="text-[10px] text-emerald-400 font-mono bg-emerald-500/8 border border-emerald-500/12 rounded-md px-2 py-0.5">complete</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-3 text-[10px] text-neutral-500 font-mono tabular-nums bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-1.5">
            <span>{totalTokens.toLocaleString()}t</span>
            <span>${estimatedCost.toFixed(4)}</span>
          </div>
          <button
            type="button"
            onClick={() => { if (sessionId) { destroySandbox(sessionId); window.location.reload(); } }}
            className="flex items-center gap-1 text-[10px] text-red-400 bg-red-500/6 border border-red-500/10 rounded-md px-2.5 py-1.5 hover:bg-red-500/10 transition-colors"
          >
            <Trash2 className="w-3 h-3" strokeWidth={1.5} />
            Destroy
          </button>
        </div>
      </motion.div>

      {/* Row 2: 3-column bento grid */}
      <motion.div variants={sectionVariants} className="grid grid-cols-1 xl:grid-cols-[220px_1fr_260px] gap-4">
        {/* Left column */}
        <div className="flex flex-col gap-4">
          <SandboxFileTree />
          <SandboxResources />
          <SandboxPorts />
        </div>

        {/* Center */}
        <div className="flex flex-col gap-4">
          <SandboxTerminal />
          <SandboxDependencies />
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4">
          <SandboxTestSummary />
          <SandboxFlakyTests />
          <SandboxArtifacts />
        </div>
      </motion.div>
    </motion.div>
  );
}
