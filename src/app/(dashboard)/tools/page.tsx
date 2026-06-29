"use client";

import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { CheckIcon, Cross2Icon, MagnifyingGlassIcon, UploadIcon, TrashIcon, PlusIcon } from "@radix-ui/react-icons";
import { api, apiFetch } from "@/lib/api/api-client";

interface ToolEntry {
  name: string;
  description: string;
  toolset: string;
  source: "bundled" | "user";
  capabilities: string[];
  is_async: boolean;
  enabled: boolean;
}

const TOOLSET_LABELS: Record<string, string> = {
  delegate: "Delegate",
  read: "Read",
  write: "Write",
  analyze: "Analyze",
  // C3.1: the four CodeGraph MCP tools (codegraph_explore, _node,
  // _search, _callers) are registered under toolset="intelligence"
  // in `harness/tools/codegraph_tools.py`. Without this label the
  // tools page would render them under the raw toolset name.
  intelligence: "Code Intelligence",
  core: "Core",
};

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolEntry[]>([]);
  const [bundledCount, setBundledCount] = useState(0);
  const [userCount, setUserCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [uploadStatus, setUploadStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [collapsedToolsets, setCollapsedToolsets] = useState<Record<string, boolean>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchTools = useCallback(async () => {
    try {
      const data = await api.get<{ tools: ToolEntry[]; bundled_count: number; user_count: number }>("/api/tools");
      setTools(data.tools || []);
      setBundledCount(data.bundled_count || 0);
      setUserCount(data.user_count || 0);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  const toggleTool = async (name: string, enabled: boolean) => {
    await api.post("/api/tools/toggle", { name, enabled });
    await fetchTools();
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await apiFetch("/api/tools/install", { method: "POST", body: formData });
      const data = await res.json();
      setUploadStatus({ ok: data.status === "success", msg: data.message });
      await fetchTools();
    } catch (err) {
      setUploadStatus({ ok: false, msg: String(err) });
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeTool = async (name: string) => {
    setRemoving(name);
    try {
      const data = await api.delete<{ status: string; message: string }>(`/api/tools/${name}`);
      setUploadStatus({ ok: data.status === "removed", msg: data.message });
      await fetchTools();
    } catch (err) {
      setUploadStatus({ ok: false, msg: String(err) });
    } finally { setRemoving(null); }
  };

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return tools.filter((t) => !q || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q) || t.toolset.toLowerCase().includes(q));
  }, [tools, search]);

  const grouped = useMemo(() => {
    const map: Record<string, ToolEntry[]> = {};
    for (const t of filtered) {
      const key = t.toolset || "other";
      if (!map[key]) map[key] = [];
      map[key].push(t);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  return (
    <div className="space-y-6">
      <PageHeader label={`${bundledCount} bundled · ${userCount} user-installed`} description="Browse, install, and manage agent tools" />

      {/* Status message */}
      {uploadStatus && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
          className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-xs ${uploadStatus.ok ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400" : "border-red-500/20 bg-red-500/5 text-red-400"}`}>
          {uploadStatus.ok ? <CheckIcon className="w-3.5 h-3.5" /> : <Cross2Icon className="w-3.5 h-3.5" />}
          <span className="flex-1">{uploadStatus.msg}</span>
          <button onClick={() => setUploadStatus(null)} className="text-zinc-600 hover:text-zinc-400"><Cross2Icon className="w-3 h-3" /></button>
        </motion.div>
      )}

      {/* Search + Upload bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tools by name, description, or toolset..."
            className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl pl-9 pr-3 py-2.5 text-sm text-zinc-300 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors" />
        </div>
        <input ref={fileInputRef} type="file" accept=".py,.zip,.tar.gz" className="hidden" onChange={handleUpload} />
        <button onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors active:scale-[0.98] text-sm font-medium whitespace-nowrap">
          <UploadIcon className="w-3.5 h-3.5" />
          Install Tool
        </button>
      </div>

      {/* Tools list grouped by toolset */}
      {loading ? (
        <div className="text-center py-16 text-sm text-zinc-600">Loading tools...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-sm text-zinc-600">
          {search ? "No tools match your search." : "No tools registered."}
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(([toolset, items]) => {
            const isCollapsed = collapsedToolsets[toolset] === true;
            return (
              <div key={toolset} className="bg-white/[0.02] border border-white/[0.06] rounded-2xl overflow-hidden">
                <button onClick={() => setCollapsedToolsets({ ...collapsedToolsets, [toolset]: !isCollapsed })}
                  className="flex items-center gap-2 w-full px-5 py-3 text-xs font-semibold text-zinc-500 uppercase tracking-[0.06em] hover:bg-white/[0.02] transition-colors">
                  <svg className={`w-3 h-3 transition-transform ${isCollapsed ? "" : "rotate-90"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" /></svg>
                  {TOOLSET_LABELS[toolset] || toolset}
                  <span className="ml-auto text-zinc-700 font-mono text-[10px]">{items.length}</span>
                </button>
                {!isCollapsed && (
                  <div className="divide-y divide-white/[0.04]">
                    {items.map((tool) => (
                      <div key={tool.name}
                        className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.02] transition-colors group">
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${tool.source === "user" ? "bg-amber-500/10" : "bg-emerald-500/10"}`}>
                          <span className={`text-[10px] font-bold ${tool.source === "user" ? "text-amber-400" : "text-emerald-400"}`}>{tool.name[0].toUpperCase()}</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <code className="text-sm font-medium text-zinc-200">{tool.name}</code>
                            {tool.is_async && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 font-mono">async</span>}
                          </div>
                          <p className="text-[11px] text-zinc-600 mt-0.5 truncate">{tool.description}</p>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button onClick={() => toggleTool(tool.name, !tool.enabled)}
                            className={`text-[9px] px-2 py-1 rounded-lg font-mono border transition-colors ${tool.enabled ? "bg-emerald-400/10 text-emerald-400 border-emerald-400/20" : "bg-zinc-800/50 text-zinc-600 border-zinc-700/50"}`}>
                            {tool.enabled ? "on" : "off"}
                          </button>
                          {tool.source === "user" && (
                            <button onClick={() => removeTool(tool.name)} disabled={removing === tool.name}
                              className="p-1.5 rounded-md text-zinc-700 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-30">
                              <TrashIcon className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Plugins section */}
      <PluginsSection />
    </div>
  );
}

function PluginsSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["tools-plugins"],
    queryFn: () => api.get<any>("/api/admin/plugins"),
  });
  const plugins = data?.plugins ?? [];
  if (plugins.length === 0) return null;
  return (
    <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-5">
      <div className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3">Plugins</div>
      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-8 rounded-lg shimmer-bg" />)}</div>
      ) : (
        <div className="space-y-1">
          {plugins.map((p: any, i: number) => (
            <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.02] transition-colors">
              <span className="text-[12px] font-mono text-zinc-300 flex-1">{p.name}</span>
              <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${p.enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-600"}`}>
                {p.enabled ? "active" : "inactive"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
