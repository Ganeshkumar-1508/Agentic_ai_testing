"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { api } from "@/lib/api/api-client";
import { cn } from "@/lib/utils";
import {
  Puzzle, Plus, Trash2, Loader2, Check, X,
  Search, ChevronDown, ChevronRight, RefreshCw, Terminal,
  Terminal as TerminalIcon, Variable, Eye, EyeOff,
} from "lucide-react";

interface MCPServerConfig {
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  transport?: string;
  timeout?: number;
  connect_timeout?: number;
  headers?: Record<string, string>;
}

interface MCPServer {
  id: string;
  name: string;
  displayName: string;
  description?: string;
  category: string;
  serverType: string;
  serverUrl?: string;
  enabled: boolean;
  config?: MCPServerConfig;
}

interface MCPTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

interface MCPConnection {
  id: string;
  name: string;
  url: string;
  connected: boolean;
  error: string | null;
  tools: MCPTool[];
}

type SortKey = "name" | "status";
type ServerType = "command" | "url";

function ArgInput({ args, onChange }: { args: string[]; onChange: (a: string[]) => void }) {
  const [val, setVal] = useState("");
  const add = () => {
    if (!val.trim()) return;
    onChange([...args, val.trim()]);
    setVal("");
  };
  return (
    <div className="space-y-1.5">
      <div className="flex gap-1.5">
        <Input value={val} onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder="Add argument..."
          className="flex-1 bg-zinc-900/80 border-zinc-800 text-xs h-7 rounded-lg font-mono focus:border-emerald-500/40" />
        <button type="button" onClick={add} disabled={!val.trim()}
          className="px-2 rounded-lg text-[10px] bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors disabled:opacity-30 active:scale-[0.95]">Add</button>
      </div>
      <div className="flex flex-wrap gap-1">
        {args.map((a, i) => (
          <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-zinc-800/60 border border-zinc-700/30 text-[10px] font-mono text-zinc-300">
            {a}
            <button type="button" onClick={() => onChange(args.filter((_, j) => j !== i))}
              className="text-zinc-600 hover:text-zinc-400 transition-colors">
              <X size={10} strokeWidth={2} />
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

function EnvInput({ entries, onChange, label }: { entries: [string, string][]; onChange: (e: [string, string][]) => void; label: string }) {
  const [k, setK] = useState("");
  const [v, setV] = useState("");
  const [showVal, setShowVal] = useState<number | null>(null);
  const add = () => {
    if (!k.trim()) return;
    onChange([...entries, [k.trim(), v]]);
    setK(""); setV("");
  };
  return (
    <div className="space-y-1.5">
      <div className="flex gap-1.5">
        <Input value={k} onChange={(e) => setK(e.target.value)}
          placeholder="Key" className="flex-1 bg-zinc-900/80 border-zinc-800 text-[10px] h-7 rounded-lg font-mono focus:border-emerald-500/40" />
        <Input value={v} onChange={(e) => setV(e.target.value)}
          placeholder="Value" className="flex-1 bg-zinc-900/80 border-zinc-800 text-[10px] h-7 rounded-lg font-mono focus:border-emerald-500/40" />
        <button type="button" onClick={add} disabled={!k.trim()}
          className="px-2 rounded-lg text-[10px] bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors disabled:opacity-30 active:scale-[0.95]">Add</button>
      </div>
      {entries.map(([key, val], i) => (
        <div key={i} className="flex items-center gap-1.5 text-[10px] font-mono">
          <span className="text-emerald-400/80">{key}</span>
          <span className="text-zinc-700">=</span>
          <span className="text-zinc-500 truncate flex-1">
            {showVal === i ? val : "••••••••"}
          </span>
          <button type="button" onClick={() => setShowVal(showVal === i ? null : i)}
            className="text-zinc-600 hover:text-zinc-400 transition-colors">
            {showVal === i ? <EyeOff size={10} strokeWidth={2} /> : <Eye size={10} strokeWidth={2} />}
          </button>
          <button type="button" onClick={() => onChange(entries.filter((_, j) => j !== i))}
            className="text-zinc-600 hover:text-red-400 transition-colors">
            <X size={10} strokeWidth={2} />
          </button>
        </div>
      ))}
    </div>
  );
}

function ServerForm({ server, onSave, onCancel }: {
  server?: Partial<MCPServer>;
  onSave: (data: any) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(server?.name || "");
  const [desc, setDesc] = useState(server?.description || "");
  const [type, setType] = useState<ServerType>(
    server?.config?.command || server?.serverType === "command" ? "command" : "url"
  );
  const [command, setCommand] = useState(server?.config?.command || (type === "command" ? server?.serverUrl || "" : ""));
  const [args, setArgs] = useState<string[]>(server?.config?.args || []);
  const [env, setEnv] = useState<[string, string][]>(
    Object.entries(server?.config?.env || {})
  );
  const [url, setUrl] = useState(server?.serverUrl || "");
  const [headers, setHeaders] = useState<[string, string][]>(
    Object.entries(server?.config?.headers || {})
  );

  const handleSave = () => {
    if (!name.trim()) return;
    if (type === "command" && !command.trim()) return;
    if (type === "url" && !url.trim()) return;

    const config: Record<string, any> = {};
    if (type === "command") {
      config.command = command.trim();
      if (args.length > 0) config.args = args;
      if (env.length > 0) {
        config.env = Object.fromEntries(env.filter(([k]) => k.trim()));
      }
    } else {
      config.headers = Object.fromEntries(headers.filter(([k]) => k.trim()));
    }

    onSave({
      name: name.trim(),
      display_name: name.trim(),
      description: desc.trim() || undefined,
      server_type: type === "command" ? "command" : "http",
      server_url: type === "command" ? command.trim() : url.trim(),
      enabled: server?.enabled ?? true,
      config: JSON.stringify(config),
    });
  };

  return (
    <div className="bg-zinc-900/30 border border-zinc-800/30 rounded-3xl p-4 space-y-2.5">
      <Input value={name} onChange={(e) => setName(e.target.value)}
        placeholder="Server name (e.g., My Custom Server)"
        className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg focus:border-emerald-500/40" />

      {/* Server type toggle */}
      <div className="flex items-center gap-1 shimmer-bg border border-zinc-800/30 rounded-lg p-0.5 w-fit">
        {(["command", "url"] as ServerType[]).map((t) => (
          <button key={t} type="button" onClick={() => setType(t)}
            className={cn("px-2.5 py-1 rounded-md text-[10px] font-medium transition-all",
              type === t ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-500 hover:text-zinc-300")}>
            {t === "command" ? "Command (stdio)" : "URL (HTTP/SSE)"}
          </button>
        ))}
      </div>

      {type === "command" ? (
        <>
          <Input value={command} onChange={(e) => setCommand(e.target.value)}
            placeholder="Command (e.g., npx, docker, python)"
            className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg font-mono focus:border-emerald-500/40" />
          <ArgInput args={args} onChange={setArgs} />
          <div className="text-[10px] text-zinc-600 font-medium tracking-wider uppercase flex items-center gap-2">
            <Variable size={11} strokeWidth={1.5} />
            Environment Variables
          </div>
          <EnvInput entries={env} onChange={setEnv} label="env" />
        </>
      ) : (
        <>
          <Input value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="URL (e.g., https://api.example.com/mcp)"
            className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg font-mono focus:border-emerald-500/40" />
          <div className="text-[10px] text-zinc-600 font-medium tracking-wider uppercase">Headers</div>
          <EnvInput entries={headers} onChange={setHeaders} label="headers" />
        </>
      )}

      <Input value={desc} onChange={(e) => setDesc(e.target.value)}
        placeholder="Description (optional)"
        className="bg-zinc-900/80 border-zinc-800 text-xs h-8 rounded-lg focus:border-emerald-500/40" />

      <div className="flex items-center gap-2">
        <Button size="sm" onClick={handleSave}
          disabled={!name.trim() || (type === "command" && !command.trim()) || (type === "url" && !url.trim())}
          className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5">
          <Check className="w-3.5 h-3.5" strokeWidth={2} />{server ? "Save" : "Add Server"}</Button>
        <Button size="sm" variant="outline" onClick={onCancel}
          className="h-8 px-3 rounded-lg text-xs border-zinc-800">Cancel</Button>
      </div>
    </div>
  );
}

export function MCPServerManager() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [connections, setConnections] = useState<MCPConnection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [toolSearch, setToolSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("name");
  const [testingId, setTestingId] = useState<string | null>(null);

  useEffect(() => { fetchAll(); }, []);

  const fetchAll = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [serversRes, connRes] = await Promise.all([
        api.get<{ servers?: MCPServer[] }>(`/api/settings/mcp`),
        api.get<{ connections?: MCPConnection[] }>(`/api/settings/mcp/connections`),
      ]);
      setServers(serversRes?.servers ?? []);
      setConnections(connRes?.connections ?? []);
    } catch {
      setLoadError("Failed to load MCP servers. Check backend connection.");
    } finally {
      setIsLoading(false);
    }
  };

  const sortedServers = useMemo(() => {
    const s = [...servers];
    if (sortBy === "name") s.sort((a, b) => a.name.localeCompare(b.name));
    return s;
  }, [servers, sortBy]);

  const getConnection = (serverName: string) =>
    connections.find((c) => c.name === serverName || c.id === serverName);

  const getAllTools = useMemo(() => {
    const tools: Array<MCPTool & { serverName: string }> = [];
    for (const conn of connections) {
      for (const tool of conn.tools) {
        tools.push({ ...tool, serverName: conn.name });
      }
    }
    return tools;
  }, [connections]);

  const filteredTools = useMemo(() => {
    if (!toolSearch) return [];
    return getAllTools.filter((t) =>
      t.name.toLowerCase().includes(toolSearch.toLowerCase()) ||
      t.description.toLowerCase().includes(toolSearch.toLowerCase()),
    );
  }, [getAllTools, toolSearch]);

  const toggleServer = async (id: string, enabled: boolean) => {
    setServers((prev) => prev.map((s) => (s.id === id ? { ...s, enabled } : s)));
    try {
      await api.patch(`/api/settings/mcp/${id}`, { enabled });
    } catch {
      setServers((prev) => prev.map((s) => (s.id === id ? { ...s, enabled: !enabled } : s)));
    }
  };

  const addServer = async (data: any) => {
    if (!data.name) return;
    try {
      const result = await api.post<{ server?: MCPServer }>(`/api/settings/mcp`, data);
      if (result?.server) {
        setServers((prev) => [...prev, result.server!]);
        setShowAddForm(false);
      }
    } catch { /* ignore */ }
  };

  const updateServer = async (id: string, data: any) => {
    try {
      await api.patch(`/api/settings/mcp/${id}`, data);
      setEditingId(null);
      await fetchAll();
    } catch { /* ignore */ }
  };

  const deleteServer = async (id: string) => {
    try {
      await api.delete(`/api/settings/mcp/${id}`);
      setServers((prev) => prev.filter((s) => s.id !== id));
    } catch { /* ignore */ }
  };

  const handleTest = async () => {
    setTestingId("all");
    await api.post(`/api/settings/mcp/reload`, {});
    await fetchAll();
    setTestingId(null);
  };

  const healthyCount = connections.filter((c) => c.connected).length;

  if (isLoading) return (
    <div className="space-y-3">
      <SkeletonBlock className="h-5 w-44" />
      {Array.from({ length: 3 }).map((_, i) => <SkeletonBlock key={i} className="h-20 w-full rounded-3xl" />)}
    </div>
  );

  if (loadError) return <ErrorState message={loadError} onRetry={fetchAll} />;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Puzzle className="w-4 h-4 text-neutral-400" strokeWidth={1.5} />
          <span className="text-sm font-medium text-neutral-200 tracking-tight">MCP Servers</span>
          <span className="text-[11px] text-neutral-600 font-mono tabular-nums">
            {servers.length} servers · {healthyCount} healthy
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {["name", "status"].map((s) => (
            <button key={s} type="button" onClick={() => setSortBy(s as SortKey)}
              className={cn("px-2 py-0.5 rounded text-[10px] font-medium transition-all capitalize",
                sortBy === s ? "bg-white/[0.08] text-neutral-300" : "text-neutral-600 hover:text-neutral-400")}>{s}</button>
          ))}
          <button type="button" onClick={handleTest} disabled={testingId === "all"}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04] transition-all">
            {testingId === "all" ? <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} /> : <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.5} />}
          </button>
        </div>
      </div>

      {/* Global tool search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-600" strokeWidth={1.5} />
        <input type="text" value={toolSearch} onChange={(e) => setToolSearch(e.target.value)}
          placeholder="Search across all discovered tools..."
          className="w-full h-8 pl-8 pr-3 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-emerald-500/40 transition-colors" />
      </div>

      {/* Global tool search results */}
      <AnimatePresence>
        {toolSearch && filteredTools.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="border border-zinc-800/30 rounded-3xl shimmer-bg overflow-hidden">
            <div className="px-3 py-2 text-[10px] text-zinc-500 font-medium uppercase tracking-wider border-b border-zinc-800/30">
              Found {filteredTools.length} tools
            </div>
            <div className="divide-y divide-zinc-800/30 max-h-48 overflow-y-auto">
              {filteredTools.slice(0, 15).map((tool) => (
                <div key={`${tool.serverName}-${tool.name}`} className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <TerminalIcon className="w-3 h-3 text-amber-400 shrink-0" strokeWidth={1.5} />
                    <span className="text-xs text-neutral-200 font-mono">{tool.name}</span>
                    <span className="text-[10px] text-neutral-600">via {tool.serverName}</span>
                  </div>
                  {tool.description && <p className="text-[10px] text-neutral-500 mt-0.5 ml-5">{tool.description}</p>}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Server list */}
      <AnimatePresence mode="popLayout">
        {sortedServers.length === 0 && !showAddForm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-12 border border-dashed border-zinc-800/50 rounded-3xl bg-zinc-900/30">
            <Puzzle className="w-8 h-8 text-neutral-600 mb-3" strokeWidth={1.2} />
            <p className="text-sm text-neutral-500 mb-1">No MCP servers configured</p>
            <p className="text-xs text-neutral-600 mb-4">Add an MCP server to extend agent capabilities</p>
            <Button onClick={() => setShowAddForm(true)}
              className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1.5">
              <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />Add Server</Button>
          </motion.div>
        )}

        {sortedServers.map((server, i) => {
          const conn = getConnection(server.name);
          const isExpanded = expandedServer === server.id;
          const isEditing = editingId === server.id;
          const isTesting = testingId === "all";
          const cfg = server.config || {};
          const hasArgs = cfg.args && cfg.args.length > 0;
          const hasEnv = cfg.env && Object.keys(cfg.env).length > 0;

          return (
            <motion.div key={server.id} layout
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 100, damping: 20, delay: i * 0.04 }}
            >
              <div className={cn("border rounded-3xl overflow-hidden transition-colors",
                isEditing ? "border-emerald-500/30 bg-zinc-900/50" : "border-zinc-800/30 shimmer-bg"
              )}>
                {/* Server header */}
                <div className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                        conn?.connected ? "bg-emerald-500/10" : conn ? "bg-red-500/10" : "bg-white/[0.03]",
                      )}>
                        <Puzzle className={cn("w-4 h-4", conn?.connected ? "text-emerald-400" : conn ? "text-red-400" : "text-neutral-500")} strokeWidth={1.5} />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-neutral-200 truncate">{server.displayName || server.name}</span>
                          <span className={cn("text-[9px] px-1.5 py-0.5 rounded font-mono",
                            server.serverType === "command"
                              ? "bg-zinc-800/60 text-zinc-500 border border-zinc-700/30"
                              : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                          )}>
                            {server.serverType === "command" ? "stdio" : "http"}
                          </span>
                          {conn && (
                            <span className={cn("relative flex w-2 h-2", conn.connected && "after:absolute after:inset-0 after:rounded-full after:bg-emerald-400/40 after:animate-ping")}>
                              <span className={cn("w-2 h-2 rounded-full", conn.connected ? "bg-emerald-400" : "bg-red-400")} />
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {conn && (
                            <>
                              <span className={cn("text-[10px] font-mono tabular-nums", conn.connected ? "text-emerald-400" : "text-red-400")}>
                                {conn.connected ? "connected" : "error"}
                              </span>
                              <span className="text-neutral-700">·</span>
                            </>
                          )}
                          <span className="text-[10px] text-neutral-600 font-mono truncate max-w-[200px]">
                            {cfg.command || server.serverUrl || "-"}
                          </span>
                          {hasArgs && (
                            <span className="text-[10px] text-zinc-600 font-mono">
                              {cfg.args?.length} arg{cfg.args!.length !== 1 ? "s" : ""}
                            </span>
                          )}
                          {hasEnv && (
                            <span className="text-[10px] text-zinc-600 font-mono">
                              {Object.keys(cfg.env!).length} env
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <button type="button" onClick={() => setEditingId(isEditing ? null : server.id)}
                        className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-all active:scale-[0.95]",
                          isEditing ? "bg-emerald-500/10 text-emerald-400" : "text-neutral-500 hover:text-neutral-300 hover:bg-white/[0.04]"
                        )}>
                        {isEditing ? <X size={12} strokeWidth={2} /> : <TerminalIcon size={12} strokeWidth={1.5} />}
                      </button>
                      <button type="button" onClick={() => deleteServer(server.id)}
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-neutral-600 hover:text-red-400 hover:bg-red-500/5 transition-all active:scale-[0.95]">
                        <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </button>
                      <Switch checked={server.enabled} onCheckedChange={(v) => toggleServer(server.id, v)} />
                    </div>
                  </div>

                  {/* Error message */}
                  <AnimatePresence>
                    {conn && !conn.connected && conn.error && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden mt-2">
                        <p className="text-[11px] text-red-400 font-mono bg-red-500/[0.04] border border-red-500/20 rounded-lg px-2.5 py-1.5">{conn.error}</p>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {/* Tool count + expand */}
                  {conn && conn.tools.length > 0 && (
                    <button type="button" onClick={() => setExpandedServer(isExpanded ? null : server.id)}
                      className="flex items-center gap-1.5 mt-2 text-[11px] text-neutral-500 hover:text-neutral-300 transition-colors">
                      {isExpanded ? <ChevronDown className="w-3 h-3" strokeWidth={1.5} /> : <ChevronRight className="w-3 h-3" strokeWidth={1.5} />}
                      {conn.tools.length} tool{conn.tools.length !== 1 ? "s" : ""} discovered
                    </button>
                  )}
                </div>

                {/* Inline edit form */}
                <AnimatePresence>
                  {isEditing && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] as const }}
                      className="overflow-hidden border-t border-zinc-800/30">
                      <div className="p-3">
                        <ServerForm
                          server={server}
                          onSave={(data) => updateServer(server.id, data)}
                          onCancel={() => setEditingId(null)}
                        />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Tool list */}
                <AnimatePresence>
                  {isExpanded && conn && conn.tools.length > 0 && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] as const }} className="overflow-hidden border-t border-zinc-800/30">
                      <div className="divide-y divide-zinc-800/30">
                        {conn.tools.map((tool) => (
                          <div key={tool.name} className="px-4 py-2.5 hover:bg-zinc-900/30 transition-colors">
                            <div className="flex items-start gap-2">
                              <Terminal className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" strokeWidth={1.5} />
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-mono text-neutral-200 font-medium">{tool.name}</span>
                                </div>
                                {tool.description && (
                                  <p className="text-[11px] text-neutral-500 mt-0.5 leading-relaxed">{tool.description}</p>
                                )}
                                {tool.inputSchema && Object.keys(tool.inputSchema).length > 0 && (
                                  <div className="flex items-center gap-1.5 mt-1">
                                    <span className="text-[10px] text-neutral-600 font-mono">args:</span>
                                    <span className="text-[10px] text-neutral-600 font-mono">
                                      {Object.keys(tool.inputSchema.properties || {}).join(", ") || "none"}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Add form */}
      <AnimatePresence>
        {showAddForm && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ServerForm onSave={addServer} onCancel={() => setShowAddForm(false)} />
          </motion.div>
        )}
      </AnimatePresence>

      {!showAddForm && sortedServers.length > 0 && (
        <Button variant="outline" onClick={() => setShowAddForm(true)}
          className="w-full h-10 border-dashed border-zinc-800/50 rounded-3xl text-xs text-zinc-500 gap-1.5 hover:text-zinc-300 transition-colors">
          <Plus className="w-4 h-4" strokeWidth={1.5} />Add MCP Server</Button>
      )}
    </div>
  );
}