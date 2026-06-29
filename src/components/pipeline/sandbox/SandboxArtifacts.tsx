"use client";

import { useState, useEffect, useCallback } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchSandboxArtifacts, downloadFile, downloadWorkspaceArchive } from "@/lib/services/sandbox-client";
import type { SandboxArtifact } from "@/lib/types/sandbox";
import { FileText, FileJson, FileCode, Download, Package, Archive } from "lucide-react";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function ArtifactIcon({ name }: { name: string }) {
  if (name.endsWith(".json")) return <FileJson className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />;
  if (name.endsWith(".html")) return <FileCode className="w-3.5 h-3.5 text-zinc-400" strokeWidth={1.5} />;
  if (name.endsWith(".md")) return <FileText className="w-3.5 h-3.5 text-zinc-400" strokeWidth={1.5} />;
  if (name.includes("lcov")) return <FileCode className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />;
  return <FileText className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />;
}

export function SandboxArtifacts() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [artifacts, setArtifacts] = useState<SandboxArtifact[]>([]);

  const load = useCallback(async () => {
    if (!sessionId) return;
    const data = await fetchSandboxArtifacts(sessionId);
    setArtifacts(data);
  }, [sessionId]);

  useEffect(() => {
    if ((status === "running" || status === "completed") && sessionId) {
      load();
      if (status === "running") {
        const interval = setInterval(load, 8000);
        return () => clearInterval(interval);
      }
    }
  }, [status, sessionId, load]);

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">Artifacts</div>
        {artifacts.length > 0 && (
          <button
            type="button"
            onClick={() => { if (sessionId) downloadWorkspaceArchive(sessionId); }}
            className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/6 border border-emerald-500/10 rounded-md px-2 py-1 hover:bg-emerald-500/10 transition-colors"
          >
            <Archive className="w-3 h-3" strokeWidth={1.5} />
            Download All
          </button>
        )}
      </div>
      {artifacts.length === 0 && (
        <div className="text-[11px] text-neutral-600 text-center py-4">No artifacts generated yet</div>
      )}
      <div className="space-y-1">
        {artifacts.map((a) => (
          <div key={a.path} className="flex items-center gap-2 py-1.5 text-xs border-b border-white/[0.03] last:border-0">
            <ArtifactIcon name={a.name} />
            <span className="text-neutral-400 truncate flex-1">{a.name}</span>
            <span className="text-neutral-600 font-mono text-[10px] tabular-nums">{formatSize(a.size_bytes)}</span>
            <button
              type="button"
              onClick={() => { if (sessionId) downloadFile(sessionId, a.path); }}
              className="text-emerald-400 hover:text-emerald-300 transition-colors"
            >
              <Download className="w-3 h-3" strokeWidth={1.5} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
