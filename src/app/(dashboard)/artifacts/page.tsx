"use client";

import { useMemo, useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, BACKEND_URL } from "@/lib/api/api-client";
import {
  FolderTree, Folder, FolderOpen, FileText, FileCode, FileJson,
  FileImage, FileArchive, Download, Trash2, RefreshCw, ChevronRight,
  ChevronDown, Search, Loader2, Eye, X, AlertTriangle, Box,
  Server, Inbox, FileBox, ExternalLink,
} from "lucide-react";

type SandboxSession = {
  session_id: string;
  container_id?: string;
  container_name?: string;
  created_at?: number | string;
  is_running?: boolean;
  repo_url?: string;
  goal?: string;
  status?: string;
};

type TreeNode = {
  path: string;
  name: string;
  is_dir: boolean;
};

type FileContent = {
  path: string;
  size_bytes: number;
  truncated: boolean;
  is_text: boolean;
  content: string;
  encoding?: string;
};

const TEXT_EXTS = new Set([
  "txt", "md", "json", "yaml", "yml", "toml", "log", "csv", "tsv",
  "py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "rb", "go", "rs",
  "java", "kt", "swift", "c", "h", "hpp", "cpp", "cc", "cs", "php",
  "sh", "bash", "html", "htm", "xml", "css", "scss", "sass", "less",
  "sql", "vue", "svelte", "lua", "pl", "r", "dart", "erb", "haml",
  "slim", "ini", "cfg", "env",
]);

const TEXT_NAMES = new Set([
  "dockerfile", "makefile", "gemfile", "rakefile", "readme", "license",
  "changelog", "contributing", ".gitignore", ".gitattributes",
]);

function formatBytes(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function fileBadge(name: string): { label: string; color: string; icon: React.ReactNode } {
  const ext = (name.split(".").pop() ?? "").toLowerCase();
  const lname = name.toLowerCase();
  if (ext === "json" || ext === "yaml" || ext === "yml" || ext === "toml")
    return { label: ext.toUpperCase(), color: "bg-amber-500/15 text-amber-400 border-amber-500/20", icon: <FileJson className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  if (["png", "jpg", "jpeg", "gif", "svg", "webp", "ico"].includes(ext))
    return { label: ext.toUpperCase(), color: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20", icon: <FileImage className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  if (["zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar"].includes(ext))
    return { label: ext.toUpperCase(), color: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20", icon: <FileArchive className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  if (ext === "html" || ext === "htm")
    return { label: "HTML", color: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20", icon: <FileCode className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  if (["py", "js", "ts", "tsx", "jsx", "rb", "go", "rs", "java", "sh"].includes(ext))
    return { label: ext.toUpperCase(), color: "bg-blue-500/15 text-blue-400 border-blue-500/20", icon: <FileCode className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  if (TEXT_NAMES.has(lname))
    return { label: lname.toUpperCase(), color: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20", icon: <FileText className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  if (TEXT_EXTS.has(ext) || ext === "")
    return { label: ext ? ext.toUpperCase() : "FILE", color: "bg-blue-500/15 text-blue-400 border-blue-500/20", icon: <FileText className="w-3.5 h-3.5" strokeWidth={1.5} /> };
  return { label: ext.toUpperCase() || "BIN", color: "bg-zinc-500/15 text-zinc-400 border-zinc-500/20", icon: <FileArchive className="w-3.5 h-3.5" strokeWidth={1.5} /> };
}

function isPreviewable(name: string): boolean {
  const ext = (name.split(".").pop() ?? "").toLowerCase();
  const lname = name.toLowerCase();
  return TEXT_EXTS.has(ext) || TEXT_NAMES.has(lname);
}

export default function ArtifactsPage() {
  const qc = useQueryClient();
  const [sessionId, setSessionId] = useState<string>("");
  const [currentPath, setCurrentPath] = useState<string>("/");
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set(["", "/repo"]));
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [depth, setDepth] = useState(4);

  const sessionsQ = useQuery<{ sessions: SandboxSession[]; count: number }>({
    queryKey: ["artifacts-sessions"],
    queryFn: () => api.get<{ sessions: SandboxSession[]; count: number }>("/api/artifacts/sessions"),
    refetchInterval: 15_000,
  });

  // Auto-select first session once loaded
  useEffect(() => {
    if (!sessionId && sessionsQ.data?.sessions?.length) {
      setSessionId(sessionsQ.data.sessions[0].session_id);
    }
  }, [sessionId, sessionsQ.data]);

  const treeQ = useQuery<{ nodes: TreeNode[]; path: string; count: number }>({
    queryKey: ["artifacts-tree", sessionId, currentPath, depth, showHidden],
    queryFn: () => api.get<{ nodes: TreeNode[]; path: string; count: number }>(
      `/api/artifacts/${sessionId}/tree?path=${encodeURIComponent(currentPath)}&depth=${depth}&show_hidden=${showHidden}`,
    ),
    enabled: !!sessionId,
    staleTime: 10_000,
  });

  const fileQ = useQuery<FileContent>({
    queryKey: ["artifact-file", sessionId, selectedFile],
    queryFn: () => api.get<FileContent>(
      `/api/artifacts/${sessionId}/file-content?path=${encodeURIComponent(selectedFile ?? "")}&max_bytes=262144`,
    ),
    enabled: !!sessionId && !!selectedFile,
    staleTime: 30_000,
  });

  const deleteMut = useMutation({
    mutationFn: async (path: string) => {
      const r = await fetch(`${BACKEND_URL}/api/artifacts/${sessionId}/file?path=${encodeURIComponent(path)}`, {
        method: "DELETE",
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t || `HTTP ${r.status}`);
      }
      return r.json();
    },
    onSuccess: (_d, path) => {
      toast.success(`Deleted ${path.split("/").pop()}`);
      qc.invalidateQueries({ queryKey: ["artifacts-tree", sessionId] });
      if (selectedFile === path) setSelectedFile(null);
    },
    onError: (e: Error) => toast.error(`Delete failed: ${e.message}`),
  });

  const selectedSession = useMemo(
    () => sessionsQ.data?.sessions?.find(s => s.session_id === sessionId),
    [sessionsQ.data, sessionId],
  );

  const nodes = useMemo(() => {
    const raw = treeQ.data?.nodes ?? [];
    if (!filter) return raw;
    const q = filter.toLowerCase();
    return raw.filter(n => n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q));
  }, [treeQ.data, filter]);

  const toggleDir = useCallback((p: string) => {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }, []);

  const handlePick = useCallback((node: TreeNode) => {
    if (node.is_dir) {
      const next = node.path === "" ? "/" : `/${node.path}`;
      setCurrentPath(next);
      setExpandedDirs(prev => new Set([...prev, node.path]));
    } else {
      setSelectedFile(node.path);
    }
  }, []);

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ["artifacts-tree", sessionId] });
    qc.invalidateQueries({ queryKey: ["artifacts-sessions"] });
  };

  const downloadFile = (path: string) => {
    const url = `${BACKEND_URL}/api/artifacts/${sessionId}/download?path=${encodeURIComponent(path)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = path.split("/").pop() ?? "file";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const downloadArchive = () => {
    const url = `${BACKEND_URL}/api/sandbox/workspace/${sessionId}/archive`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `sandbox-${sessionId.slice(0, 12)}.tar.gz`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const breadcrumbs = useMemo(() => {
    if (currentPath === "/" || currentPath === "") return [{ label: "workspace", path: "/" }];
    const parts = currentPath.split("/").filter(Boolean);
    const crumbs: { label: string; path: string }[] = [{ label: "workspace", path: "/" }];
    let acc = "";
    for (const p of parts) {
      acc += `/${p}`;
      crumbs.push({ label: p, path: acc });
    }
    return crumbs;
  }, [currentPath]);

  const sessions = sessionsQ.data?.sessions ?? [];
  const totalNodes = treeQ.data?.count ?? 0;
  const selectedName = selectedFile?.split("/").pop() ?? null;

  return (
    <div className="max-w-7xl mx-auto px-8 pt-6 pb-12">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.1em] mb-1">Infrastructure</div>
          <h1 className="text-[22px] font-medium tracking-tighter leading-none text-zinc-100">Workspace Browser</h1>
          <p className="text-[13px] text-zinc-500 mt-0.5">Browse files in the per-session sandbox container</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHidden(v => !v)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] border transition-colors ${
              showHidden
                ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                : "bg-white/[0.03] text-zinc-500 border-white/[0.06] hover:text-zinc-300"
            }`}
            title="Show hidden files (.*)"
          >
            {showHidden ? <Eye className="w-3 h-3" strokeWidth={1.5} /> : <X className="w-3 h-3" strokeWidth={1.5} />}
            hidden
          </button>
          <select
            value={depth}
            onChange={e => setDepth(Number(e.target.value))}
            className="bg-white/[0.03] border border-white/[0.06] text-zinc-400 text-[11px] rounded-lg px-2 py-1.5 outline-none"
            title="Tree depth"
          >
            <option value={2}>depth 2</option>
            <option value={3}>depth 3</option>
            <option value={4}>depth 4</option>
            <option value={6}>depth 6</option>
            <option value={8}>depth 8</option>
          </select>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] text-zinc-500 hover:text-zinc-300 bg-white/[0.03] border border-white/[0.06] transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${treeQ.isFetching ? "animate-spin" : ""}`} strokeWidth={1.5} /> refresh
          </button>
          {sessionId && (
            <button
              onClick={downloadArchive}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] text-emerald-400 hover:text-emerald-300 bg-emerald-500/8 border border-emerald-500/15 transition-colors"
            >
              <Download className="w-3 h-3" strokeWidth={1.5} /> .tar.gz
            </button>
          )}
        </div>
      </motion.div>

      {/* === Session selector === */}
      <div className="bg-surface border border-white/[0.06] rounded-2xl p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <label className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">Sandbox Session</label>
          {sessionsQ.isError && (
            <span className="text-[10px] text-red-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" strokeWidth={1.5} /> failed to load
            </span>
          )}
        </div>

        {sessionsQ.isLoading ? (
          <div className="space-y-2">
            {[0, 1].map(i => <div key={i} className="h-10 rounded-lg shimmer-bg" />)}
          </div>
        ) : sessionsQ.isError ? (
          <div className="flex flex-col items-center py-4 text-zinc-600">
            <AlertTriangle className="w-5 h-5 mb-1 text-red-400" strokeWidth={1.5} />
            <p className="text-[12px] text-red-400">Backend error</p>
            <p className="text-[10px] text-zinc-700 mt-0.5">{(sessionsQ.error as Error)?.message ?? "unknown"}</p>
            <button onClick={() => sessionsQ.refetch()} className="mt-2 text-[10px] text-emerald-400 hover:underline">retry</button>
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center py-4 text-zinc-600">
            <Server className="w-5 h-5 mb-1" strokeWidth={1.5} />
            <p className="text-[12px] text-zinc-500">No sandbox containers running</p>
            <p className="text-[10px] text-zinc-700 mt-0.5">Run a pipeline to create one</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {sessions.map(s => {
              const active = s.session_id === sessionId;
              return (
                <button
                  key={s.session_id}
                  onClick={() => { setSessionId(s.session_id); setCurrentPath("/"); setSelectedFile(null); }}
                  className={`text-left p-3 rounded-xl border transition-all ${
                    active
                      ? "bg-emerald-500/8 border-emerald-500/20 shadow-[0_0_0_1px_rgba(16,185,129,0.15)]"
                      : "bg-white/[0.02] border-white/[0.04] hover:border-white/[0.08] hover:bg-white/[0.04]"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Box className={`w-3.5 h-3.5 shrink-0 ${active ? "text-emerald-400" : "text-zinc-500"}`} strokeWidth={1.5} />
                    <span className="font-mono text-[12px] text-zinc-200 truncate">{s.session_id.slice(0, 16)}</span>
                    <span className={`ml-auto inline-flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                      s.is_running ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-500/10 text-zinc-500"
                    }`}>
                      <span className={`w-1 h-1 rounded-full ${s.is_running ? "bg-emerald-400 animate-pulse" : "bg-zinc-500"}`} />
                      {s.is_running ? "running" : "stopped"}
                    </span>
                  </div>
                  {s.repo_url ? (
                    <div className="text-[10px] text-zinc-500 font-mono truncate" title={s.repo_url}>
                      {s.repo_url.replace(/^https?:\/\//, "").replace(/\.git$/, "")}
                    </div>
                  ) : (
                    <div className="text-[10px] text-zinc-700 font-mono truncate">{s.goal?.slice(0, 60) ?? "—"}</div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* === Main split: tree + preview === */}
      {sessionId ? (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Tree panel */}
          <div className="lg:col-span-2 bg-surface border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col min-h-[560px]">
            <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <FolderTree className="w-3.5 h-3.5 text-zinc-500 shrink-0" strokeWidth={1.5} />
                <span className="text-[11px] font-semibold text-zinc-200 uppercase tracking-wider shrink-0">Files</span>
                <span className="text-[10px] font-mono text-zinc-700 ml-1">{totalNodes} entries</span>
              </div>
              <div className="relative shrink-0">
                <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600" strokeWidth={1.5} />
                <input
                  value={filter}
                  onChange={e => setFilter(e.target.value)}
                  placeholder="filter…"
                  className="bg-white/[0.03] border border-white/[0.06] text-zinc-300 text-[11px] pl-7 pr-2 py-1 rounded-md outline-none w-32 focus:w-44 transition-all"
                />
              </div>
            </div>

            {/* Breadcrumbs */}
            <div className="px-4 py-2 border-b border-white/[0.06] flex items-center gap-1 text-[11px] text-zinc-500 overflow-x-auto whitespace-nowrap">
              {breadcrumbs.map((b, i) => (
                <span key={b.path} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="w-3 h-3 text-zinc-700 shrink-0" strokeWidth={1.5} />}
                  <button
                    onClick={() => setCurrentPath(b.path)}
                    className="hover:text-zinc-200 font-mono transition-colors"
                  >
                    {b.label}
                  </button>
                </span>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto py-1">
              {treeQ.isLoading ? (
                <div className="space-y-1 p-2">
                  {[0, 1, 2, 3, 4, 5, 6].map(i => (
                    <div key={i} className="h-7 rounded-md shimmer-bg" style={{ animationDelay: `${i * 50}ms` }} />
                  ))}
                </div>
              ) : treeQ.isError ? (
                <div className="flex flex-col items-center py-10 text-zinc-600">
                  <AlertTriangle className="w-5 h-5 mb-2 text-red-400" strokeWidth={1.5} />
                  <p className="text-[12px] text-red-400">Failed to read workspace</p>
                  <p className="text-[10px] text-zinc-700 mt-1 max-w-[40ch] text-center">{(treeQ.error as Error)?.message ?? "unknown"}</p>
                  <button onClick={() => treeQ.refetch()} className="mt-2 text-[10px] text-emerald-400 hover:underline">retry</button>
                </div>
              ) : nodes.length === 0 ? (
                <div className="flex flex-col items-center py-10 text-zinc-700">
                  <Inbox className="w-6 h-6 mb-2" strokeWidth={1} />
                  <p className="text-[12px]">No entries in {currentPath}</p>
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {nodes.map((n, i) => {
                    const isSelected = !n.is_dir && selectedFile === n.path;
                    return (
                      <motion.button
                        key={`${n.path}-${i}`}
                        layout
                        initial={{ opacity: 0, x: -4 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.12, delay: Math.min(i * 0.008, 0.2) }}
                        onClick={() => handlePick(n)}
                        className={`w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-white/[0.04] transition-colors ${
                          isSelected ? "bg-emerald-500/10 text-emerald-300" : "text-zinc-300"
                        }`}
                      >
                        {n.is_dir ? (
                          <Folder className="w-3.5 h-3.5 text-amber-400/80 shrink-0" strokeWidth={1.5} />
                        ) : (
                          <span className="shrink-0 text-zinc-500">{fileBadge(n.name).icon}</span>
                        )}
                        <span className="text-[12px] font-mono truncate flex-1">{n.name || "/workspace"}</span>
                        {n.is_dir && (
                          <ChevronRight className="w-3 h-3 text-zinc-700 shrink-0" strokeWidth={1.5} />
                        )}
                      </motion.button>
                    );
                  })}
                </AnimatePresence>
              )}
            </div>
          </div>

          {/* Preview panel */}
          <div className="lg:col-span-3 bg-surface border border-white/[0.06] rounded-2xl overflow-hidden flex flex-col min-h-[560px]">
            <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0 flex-1">
                {selectedFile ? (
                  <>
                    <span className="shrink-0 text-zinc-400">{fileBadge(selectedName ?? "").icon}</span>
                    <span className="text-[12px] font-mono text-zinc-200 truncate" title={selectedFile}>{selectedFile}</span>
                    <span className="text-[10px] font-mono text-zinc-700 shrink-0 ml-1">{formatBytes(fileQ.data?.size_bytes)}</span>
                  </>
                ) : (
                  <>
                    <FileBox className="w-3.5 h-3.5 text-zinc-600" strokeWidth={1.5} />
                    <span className="text-[11px] text-zinc-600">Select a file to preview</span>
                  </>
                )}
              </div>
              {selectedFile && (
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => downloadFile(selectedFile)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-medium text-emerald-400 hover:bg-emerald-500/10 border border-emerald-500/15 transition-colors"
                  >
                    <Download className="w-3 h-3" strokeWidth={1.5} /> download
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Delete ${selectedName}? This cannot be undone.`)) {
                        deleteMut.mutate(selectedFile);
                      }
                    }}
                    disabled={deleteMut.isPending}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-medium text-red-400 hover:bg-red-500/10 border border-red-500/15 transition-colors disabled:opacity-30"
                  >
                    {deleteMut.isPending ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.5} /> : <Trash2 className="w-3 h-3" strokeWidth={1.5} />}
                    delete
                  </button>
                </div>
              )}
            </div>
            <div className="flex-1 overflow-auto bg-zinc-950/40">
              {!selectedFile ? (
                <div className="flex flex-col items-center justify-center h-full text-zinc-700 py-20">
                  <FileBox className="w-10 h-10 mb-3" strokeWidth={1} />
                  <p className="text-[13px] text-zinc-500">Pick a file from the tree to preview</p>
                  <p className="text-[11px] text-zinc-700 mt-1 max-w-[36ch] text-center">
                    Text files preview inline. Binary files (images, archives) download directly.
                  </p>
                </div>
              ) : fileQ.isLoading ? (
                <div className="flex items-center justify-center h-full py-20">
                  <Loader2 className="w-4 h-4 animate-spin text-zinc-600" strokeWidth={1.5} />
                </div>
              ) : fileQ.isError ? (
                <div className="flex flex-col items-center justify-center h-full py-20 text-zinc-600">
                  <AlertTriangle className="w-5 h-5 mb-2 text-red-400" strokeWidth={1.5} />
                  <p className="text-[12px] text-red-400">Failed to read file</p>
                  <p className="text-[10px] text-zinc-700 mt-1">{(fileQ.error as Error)?.message ?? "unknown"}</p>
                </div>
              ) : fileQ.data?.is_text ? (
                <pre className="p-4 text-[12px] font-mono text-zinc-300 leading-relaxed whitespace-pre-wrap break-words">
                  {fileQ.data.content}
                  {fileQ.data.truncated && (
                    <span className="text-amber-400 text-[10px] block mt-2">
                      … truncated, file is {formatBytes(fileQ.data.size_bytes)} total
                    </span>
                  )}
                </pre>
              ) : (
                <div className="flex flex-col items-center justify-center h-full py-20 text-zinc-600">
                  <FileArchive className="w-8 h-8 mb-2" strokeWidth={1.5} />
                  <p className="text-[12px] text-zinc-400">Binary file · {formatBytes(fileQ.data?.size_bytes)}</p>
                  <p className="text-[10px] text-zinc-700 mt-1">Preview not available for binary content</p>
                  <button
                    onClick={() => downloadFile(selectedFile)}
                    className="mt-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/15 transition-colors"
                  >
                    <Download className="w-3 h-3" strokeWidth={1.5} /> download instead
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-surface border border-white/[0.06] rounded-2xl p-12 text-center">
          <FolderTree className="w-10 h-10 text-zinc-700 mx-auto mb-3" strokeWidth={1} />
          <p className="text-[13px] text-zinc-500">Select a sandbox session above to browse its workspace</p>
          <p className="text-[11px] text-zinc-700 mt-1">Each session gets a Docker container with the cloned repo at <code className="font-mono text-zinc-500">/workspace/repo</code></p>
        </div>
      )}
    </div>
  );
}
