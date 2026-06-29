"use client";

import { useState, useEffect, useCallback } from "react";
import { FileExplorer, type FileTreeNode } from "@/components/shared/FileExplorer";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, apiFetch } from "@/lib/api/api-client";

// ─── Prism setup for syntax highlighting ─────────────────────────────────────

interface LogExplorerProps {
  runId: string | null;
  className?: string;
}

function getLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  const langMap: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    py: "python",
    json: "json",
    md: "markdown",
    txt: "plaintext",
    yaml: "yaml",
    yml: "yaml",
    log: "plaintext",
    html: "html",
    css: "css",
  };
  return langMap[ext || ""] || "plaintext";
}

export function LogExplorer({ runId, className }: LogExplorerProps) {
  const [fileTree, setFileTree] = useState<FileTreeNode | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingContent, setIsLoadingContent] = useState(false);

  // Fetch file tree when runId changes
  useEffect(() => {
    if (!runId) {
      setFileTree(null);
      setSelectedFile(null);
      setFileContent(null);
      return;
    }

    setIsLoading(true);
    api.get<{ tree?: any }>(`/api/runs/${runId}/logs`)
      .then((data) => {
        setFileTree(data?.tree || null);
      })
      .catch(() => setFileTree(null))
      .finally(() => setIsLoading(false));
  }, [runId]);

  // Fetch file content when a file is selected
  const handleFileSelect = useCallback(async (path: string) => {
    if (!runId) return;
    setSelectedFile(path);
    setIsLoadingContent(true);
    try {
      const res = await apiFetch(`/api/runs/${runId}/logs/${encodeURIComponent(path)}`);
      if (res.ok) {
        const text = await res.text();
        setFileContent(text);
      } else {
        setFileContent("// Error loading file content");
      }
    } catch {
      setFileContent("// Error loading file content");
    } finally {
      setIsLoadingContent(false);
    }
  }, [runId]);

  if (!runId) {
    return (
      <div className={cn("flex items-center justify-center py-12 text-xs text-neutral-600", className)}>
        No run selected
      </div>
    );
  }

  return (
    <div className={cn("grid grid-cols-[280px_1fr] gap-0 border border-white/[0.05] rounded-[1.5rem] overflow-hidden", className)}>
      {/* Left: File Explorer */}
      <div className="bg-surface border-r border-white/[0.05] max-h-[500px] overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-4 h-4 animate-spin text-neutral-500" />
          </div>
        ) : (
          <FileExplorer
            tree={fileTree}
            onFileSelect={handleFileSelect}
            selectedFile={selectedFile || undefined}
          />
        )}
      </div>

      {/* Right: File Content */}
      <div className="bg-surface flex flex-col max-h-[500px]">
        {selectedFile && (
          <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.05]">
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />
              <span className="text-xs text-neutral-400 font-mono">{selectedFile}</span>
              <span className="text-[10px] text-neutral-600 bg-white/[0.03] px-1.5 py-0.5 rounded">
                {getLanguageFromPath(selectedFile)}
              </span>
            </div>
            <button
              type="button"
              onClick={() => { setSelectedFile(null); setFileContent(null); }}
              className="text-neutral-500 hover:text-neutral-300"
            >
              <X className="w-3.5 h-3.5" strokeWidth={1.5} />
            </button>
          </div>
        )}

        <ScrollArea className="flex-1">
          {isLoadingContent ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-4 h-4 animate-spin text-neutral-500" />
            </div>
          ) : fileContent ? (
            <pre className="p-4 text-xs font-mono text-neutral-300 leading-6 whitespace-pre-wrap break-all">
              {fileContent}
            </pre>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
              <FileText className="w-8 h-8 text-neutral-600 mb-2" strokeWidth={1.2} />
              <p className="text-xs text-neutral-500">
                Select a file from the explorer to view its contents
              </p>
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}
