"use client";

import { useState, useEffect, useCallback } from "react";
import { usePipelineStore } from "@/stores/pipeline-store";
import { fetchWorkspaceFiles, fetchWorkspaceFileContent } from "@/lib/services/sandbox-client";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { Folder, File, FileText, FileJson, FileCode, ChevronRight, ChevronDown } from "lucide-react";

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
  expanded: boolean;
}

function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode[] = [];
  for (const p of paths) {
    const parts = p.replace(/\/$/, "").split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      let node = current.find((n) => n.name === part);
      if (!node) {
        node = { name: part, path: parts.slice(0, i + 1).join("/"), isDir: i < parts.length - 1 || p.endsWith("/"), children: [], expanded: false };
        current.push(node);
      }
      if (i < parts.length - 1) {
        current = node.children;
      }
    }
  }
  return root;
}

function FileIcon({ name, isDir }: { name: string; isDir: boolean }) {
  if (isDir) return <Folder className="w-3.5 h-3.5 text-neutral-500" strokeWidth={1.5} />;
  if (name.endsWith(".tsx") || name.endsWith(".ts")) return <FileCode className="w-3.5 h-3.5 text-blue-400" strokeWidth={1.5} />;
  if (name.endsWith(".json")) return <FileJson className="w-3.5 h-3.5 text-amber-400" strokeWidth={1.5} />;
  if (name.endsWith(".md")) return <FileText className="w-3.5 h-3.5 text-zinc-400" strokeWidth={1.5} />;
  if (name.endsWith(".html")) return <FileText className="w-3.5 h-3.5 text-zinc-400" strokeWidth={1.5} />;
  if (name.endsWith(".spec.") || name.endsWith(".test.")) return <FileCode className="w-3.5 h-3.5 text-emerald-400" strokeWidth={1.5} />;
  return <File className="w-3.5 h-3.5 text-neutral-600" strokeWidth={1.5} />;
}

export function SandboxFileTree() {
  const sessionId = usePipelineStore((s) => s.sessionId);
  const status = usePipelineStore((s) => s.status);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const loadFiles = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    const paths = await fetchWorkspaceFiles(sessionId);
    setTree(buildTree(paths));
    setLoading(false);
  }, [sessionId]);

  useEffect(() => {
    if (status === "running" && sessionId) {
      loadFiles();
      const interval = setInterval(loadFiles, 5000);
      return () => clearInterval(interval);
    }
  }, [status, sessionId, loadFiles]);

  const handleSelect = async (node: TreeNode) => {
    if (node.isDir) {
      node.expanded = !node.expanded;
      setTree([...tree]);
      return;
    }
    setSelectedPath(node.path);
    const content = await fetchWorkspaceFileContent(sessionId!, node.path);
    setPreview(content?.slice(0, 500) || "(empty)");
  };

  function renderNodes(nodes: TreeNode[], depth = 0) {
    return nodes.map((node) => (
      <div key={node.path}>
        <div
          onClick={() => handleSelect(node)}
          className={cn(
            "flex items-center gap-1.5 px-2 py-1 rounded-md cursor-pointer text-xs transition-colors",
            selectedPath === node.path ? "bg-emerald-500/10 text-emerald-300" : "text-neutral-400 hover:text-neutral-200 hover:bg-white/[0.03]",
          )}
          style={{ paddingLeft: 8 + depth * 14 }}
        >
          {node.children.length > 0 && !node.expanded && <ChevronRight className="w-3 h-3 text-neutral-600" strokeWidth={1.5} />}
          {node.children.length > 0 && node.expanded && <ChevronDown className="w-3 h-3 text-neutral-600" strokeWidth={1.5} />}
          {node.children.length === 0 && <span className="w-3" />}
          <FileIcon name={node.name} isDir={node.isDir} />
          <span className="truncate">{node.name}</span>
        </div>
        {node.isDir && node.expanded && renderNodes(node.children, depth + 1)}
      </div>
    ));
  }

  return (
    <div className="bg-surface border border-white/[0.05] rounded-3xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.04]">
        <span className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">Workspace</span>
        <span className={cn("text-[10px] font-mono", tree.length > 0 ? "text-emerald-400" : "text-neutral-600")}>
          {tree.length} items
        </span>
      </div>
      <div className="flex" style={{ minHeight: 180 }}>
        <ScrollArea className="flex-1 max-h-[280px] p-2">
          {loading && tree.length === 0 && (
            <div className="flex items-center justify-center h-24 text-[11px] text-neutral-600">Loading...</div>
          )}
          {!loading && tree.length === 0 && (
            <div className="flex items-center justify-center h-24 text-[11px] text-neutral-600">No files yet</div>
          )}
          {renderNodes(tree)}
        </ScrollArea>
        {preview && (
          <div className="w-1/2 border-l border-white/[0.04] max-h-[280px] overflow-auto">
            <div className="p-3">
              <div className="text-[10px] font-mono text-neutral-600 mb-2 truncate">{selectedPath}</div>
              <pre className="text-[10px] font-mono text-neutral-400 leading-relaxed whitespace-pre-wrap">{preview}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
