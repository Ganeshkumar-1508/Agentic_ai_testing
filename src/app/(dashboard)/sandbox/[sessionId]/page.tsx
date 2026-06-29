"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, Container, Wifi, Trash2, ExternalLink, Download } from "lucide-react";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxInfo, destroySandbox } from "@/lib/services/sandbox-client";
import type { SandboxInfo } from "@/lib/types/sandbox";
import { SandboxFileTree } from "@/components/pipeline/sandbox/SandboxFileTree";
import { SandboxResources } from "@/components/pipeline/sandbox/SandboxResources";
import { SandboxPorts } from "@/components/pipeline/sandbox/SandboxPorts";
import { SandboxTerminal } from "@/components/pipeline/sandbox/SandboxTerminal";
import { SandboxTestSummary } from "@/components/pipeline/sandbox/SandboxTestSummary";
import { SandboxFlakyTests } from "@/components/pipeline/sandbox/SandboxFlakyTests";
import { SandboxArtifacts } from "@/components/pipeline/sandbox/SandboxArtifacts";
import { SandboxDependencies } from "@/components/pipeline/sandbox/SandboxDependencies";
import { SandboxSnapshotPanel } from "@/components/pipeline/sandbox/SandboxSnapshotPanel";

export default function SandboxPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const { totalTokens, estimatedCost } = usePipelineStore();
  const [info, setInfo] = useState<SandboxInfo | null>(null);
  const [showDestroy, setShowDestroy] = useState(false);

  const loadInfo = useCallback(async () => {
    const data = await fetchSandboxInfo(sessionId);
    setInfo(data);
  }, [sessionId]);

  useEffect(() => {
    loadInfo();
    const interval = setInterval(loadInfo, 8000);
    return () => clearInterval(interval);
  }, [loadInfo]);

  const handleDestroy = async () => {
    const ok = await destroySandbox(sessionId);
    if (ok) router.push("/pipeline");
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/pipeline"
            className="flex items-center gap-1 text-[11px] text-neutral-500 hover:text-neutral-300 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" strokeWidth={1.5} />
            Pipeline
          </Link>
          <span className="text-neutral-600">/</span>
          <Container className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Sandbox</h1>
          <span className="text-[11px] font-mono text-neutral-500 bg-white/[0.03] border border-white/[0.06] rounded-md px-2 py-0.5">
            {sessionId.slice(0, 12)}
          </span>
          {info && (
            <span className="flex items-center gap-1.5 text-[11px] text-emerald-400 bg-emerald-500/6 border border-emerald-500/10 rounded-md px-2 py-0.5">
              <Wifi className="w-3 h-3" strokeWidth={1.5} />
              {Math.round(info.uptime_seconds / 60)}m up
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-neutral-500 font-mono tabular-nums bg-white/[0.03] border border-white/[0.06] rounded-md px-2 py-1">
            {totalTokens.toLocaleString()}t · ${estimatedCost.toFixed(4)}
          </span>
          <button
            type="button"
            onClick={() => setShowDestroy(true)}
            className="flex items-center gap-1 text-[10px] text-red-400 bg-red-500/6 border border-red-500/10 rounded-md px-2.5 py-1.5 hover:bg-red-500/10 transition-colors"
          >
            <Trash2 className="w-3 h-3" strokeWidth={1.5} />
            Destroy
          </button>
        </div>
      </div>

      {/* Resizable 3-column bento */}
      <ResizablePanelGroup direction="horizontal" className="min-h-[600px] rounded-[1.5rem] border border-white/[0.05] bg-surface overflow-hidden">
        {/* Left: Files + Resources */}
        <ResizablePanel defaultSize={20} minSize={14} maxSize={40}>
          <div className="h-full overflow-y-auto space-y-3 p-3">
            <SandboxFileTree />
            <SandboxResources />
            <SandboxPorts />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center: Terminal + Dependencies */}
        <ResizablePanel defaultSize={50} minSize={30}>
          <div className="h-full overflow-y-auto space-y-3 p-3">
            <SandboxTerminal />
            <SandboxDependencies />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right: Test Summary + Flaky + Artifacts + Snapshots */}
        <ResizablePanel defaultSize={30} minSize={18}>
          <div className="h-full overflow-y-auto space-y-3 p-3">
            <SandboxTestSummary />
            <SandboxFlakyTests />
            <SandboxArtifacts />
            <SandboxSnapshotPanel />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>

      {/* Destroy confirmation */}
      {showDestroy && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between bg-red-500/6 border border-red-500/10 rounded-xl px-5 py-3"
        >
          <span className="text-sm text-red-400">Destroy sandbox <span className="font-mono">{sessionId.slice(0, 12)}</span>? Workspace files will be preserved on disk.</span>
          <div className="flex gap-2">
            <button type="button" onClick={() => setShowDestroy(false)} className="text-[11px] text-neutral-400 px-3 py-1.5 rounded-lg border border-white/[0.06] hover:text-neutral-200 transition-colors">Cancel</button>
            <button type="button" onClick={handleDestroy} className="text-[11px] text-red-400 bg-red-500/8 border border-red-500/12 rounded-lg px-3 py-1.5 hover:bg-red-500/12 transition-colors">Confirm Destroy</button>
          </div>
        </motion.div>
      )}

      {/* Bottom bar */}
      <div className="flex items-center justify-between text-[10px] text-neutral-600 font-mono px-1">
        <div className="flex items-center gap-4">
          <span>Container: <span className="text-neutral-500">testai-{sessionId.slice(0, 12)}</span></span>
          <span>SSH: <span className="text-emerald-400">user@container:22</span></span>
        </div>
        <Link href="/pipeline" className="text-neutral-500 hover:text-neutral-300 transition-colors flex items-center gap-1">
          <ArrowLeft className="w-3 h-3" strokeWidth={1.5} />
          Back to Pipeline
        </Link>
      </div>
    </motion.div>
  );
}
