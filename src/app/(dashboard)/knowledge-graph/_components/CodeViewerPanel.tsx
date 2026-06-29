"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, FileText, Loader2, ExternalLink, Github, AlertCircle } from "lucide-react";
import { useEffect } from "react";
import { CodeViewer } from "./CodeViewer";
import { useFileContent } from "./use-kg";
import { cn } from "@/lib/utils";

export function CodeViewerPanel({
  graphId,
  path,
  onClose,
}: {
  graphId: string;
  path: string;
  onClose: () => void;
}) {
  const q = useFileContent(graphId, path);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const data = q.data;
  const language = data?.language ?? "text";
  const sizeBytes = data?.size_bytes ?? 0;
  const lines = data?.lines ?? 0;

  return (
    <AnimatePresence>
      <motion.div
        key="codeviewer-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div
        key="codeviewer-panel"
        initial={{ y: "100%" }}
        animate={{ y: 0 }}
        exit={{ y: "100%" }}
        transition={{
          type: "spring",
          stiffness: 140,
          damping: 22,
          mass: 0.9,
        }}
        className="fixed left-0 right-0 bottom-0 z-50 h-[68vh] bg-surface border-t border-white/[0.08] rounded-t-2xl shadow-2xl overflow-hidden flex flex-col"
        style={{ boxShadow: "0 -20px 60px rgba(0,0,0,0.5)" }}
        role="dialog"
        aria-label={`Source of ${path}`}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06]">
          <div className="w-7 h-7 rounded-md bg-emerald-500/10 border border-emerald-400/20 flex items-center justify-center">
            <FileText className="w-3.5 h-3.5 text-emerald-300" strokeWidth={1.5} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[12.5px] font-medium text-neutral-100 truncate font-mono">
              {path}
            </div>
            <div className="text-[10.5px] font-mono text-neutral-500 mt-0.5 flex items-center gap-2">
              <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06]">
                {language}
              </span>
              {data && (
                <>
                  <span>{lines.toLocaleString()} lines</span>
                  <span className="text-neutral-700">·</span>
                  <span>{formatBytes(sizeBytes)}</span>
                  {data.truncated && (
                    <>
                      <span className="text-neutral-700">·</span>
                      <span className="text-amber-400">truncated</span>
                    </>
                  )}
                </>
              )}
              {q.isFetching && !q.data && (
                <>
                  <span className="text-neutral-700">·</span>
                  <span className="flex items-center gap-1 text-emerald-300">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" strokeWidth={2} />
                    loading
                  </span>
                </>
              )}
            </div>
          </div>
          {data?.source === "missing" && data.source_url && (
            <a
              href={data.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-white/[0.04] border border-white/[0.06] text-[11px] text-neutral-300 hover:text-neutral-100 hover:border-white/[0.12] transition-colors"
            >
              <Github className="w-3 h-3" strokeWidth={1.5} />
              GitHub
              <ExternalLink className="w-2.5 h-2.5" strokeWidth={1.5} />
            </a>
          )}
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-md text-neutral-500 hover:text-neutral-200 hover:bg-white/[0.04] transition-colors"
            title="Close (Esc)"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-auto">
          {q.isError ? (
            <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center h-full">
              <AlertCircle className="w-5 h-5 text-rose-400" strokeWidth={1.5} />
              <div className="text-[12px] text-neutral-300">Could not fetch file content.</div>
              <div className="text-[11px] text-neutral-500">{(q.error as Error)?.message}</div>
            </div>
          ) : (
            <CodeViewer data={data} isLoading={q.isLoading} isError={q.isError} />
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}
