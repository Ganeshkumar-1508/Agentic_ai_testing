"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Container, Activity, Wifi, Trash2, Cpu, Timer, RefreshCw,
  Box, HardDrive, AlertTriangle, Server, Search, FolderTree,
  Terminal as TerminalIcon, Grid3X3, FileText, Camera, Loader2,
  Database, Archive, FileBox, Inbox,
} from "lucide-react";
import { toast } from "sonner";
import { createSandboxSnapshot } from "@/lib/services/sandbox-client";
import { api, BACKEND_URL } from "@/lib/api/api-client";

type SandboxInfo = { session_id: string; container_id?: string; container_name?: string; uptime_seconds: number; is_running: boolean };
type SandboxMetrics = { sandbox_count: number; running_count: number; avg_cpu_percent: number; memory_used_mb: number; memory_total_mb: number; disk_used_mb: number; disk_total_mb: number };
type VolumeInfo = { name: string; segment: string; created_at: string; in_use: boolean };

function KpiCard({ label, value, sub, icon: Icon }: { label: string; value: string | number; sub?: string; icon: typeof Box }) {
  return (
    <div className="bg-card border border-white/[0.06] rounded-3xl p-5 hover:border-emerald-500/10 transition-all duration-300">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] text-zinc-500 font-medium">{label}</span>
        <div className="w-7 h-7 rounded-lg bg-white/[0.03] flex items-center justify-center">
          <Icon className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
        </div>
      </div>
      <div className="text-2xl font-semibold font-mono text-zinc-100 tabular-nums tracking-tight">{value}</div>
      {sub && <div className="text-[11px] text-zinc-500 font-mono mt-1">{sub}</div>}
    </div>
  );
}

function Gauge({ value, label, color }: { value: number; label: string; color: string }) {
  const safeValue = isNaN(value) || !isFinite(value) ? 0 : Math.min(Math.max(value, 0), 100);
  const r = 58; const circ = 2 * Math.PI * r;
  const dashLen = (safeValue / 100) * circ;
  return (
    <div className="flex flex-col items-center py-7 px-4">
      <div className="relative inline-block">
        <svg width="140" height="140" viewBox="0 0 140 140" className="transform -rotate-90">
          <circle cx="70" cy="70" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" strokeLinecap="round" />
          <circle cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
            strokeDasharray={`${dashLen} ${circ}`} className="transition-all duration-1000" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold font-mono text-zinc-100 tabular-nums">{safeValue}%</span>
        </div>
      </div>
      <span className="text-[11px] text-zinc-500 font-medium mt-3 tracking-wide">{label}</span>
    </div>
  );
}

function ArtifactRow({ name, size, ext }: { name: string; size: string; ext: string }) {
  const colors: Record<string, string> = { json: "bg-emerald-500/10 text-emerald-400", html: "bg-blue-500/10 text-blue-400", md: "bg-zinc-500/10 text-zinc-400", xml: "bg-amber-500/10 text-amber-400" };
  return (
    <div className="flex items-center gap-2.5 py-2 border-b border-white/[0.03] last:border-0">
      <div className={`w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold font-mono shrink-0 ${colors[ext] || "bg-white/[0.04] text-zinc-500"}`}>{ext}</div>
      <span className="text-[12px] text-zinc-400 font-mono flex-1 truncate">{name}</span>
      <span className="text-[10px] text-zinc-600 font-mono shrink-0">{size}</span>
    </div>
  );
}

function EventRow({ type, msg, time }: { type: string; msg: string; time: string }) {
  const colors: Record<string, string> = { exec: "bg-blue-500/10 text-blue-400", pass: "bg-emerald-500/10 text-emerald-400", fail: "bg-red-500/10 text-red-400", agent: "bg-zinc-500/10 text-zinc-400" };
  return (
    <div className="flex items-start gap-2.5 py-2 border-b border-white/[0.03] last:border-0">
      <div className={`w-5 h-5 rounded-md flex items-center justify-center text-[8px] shrink-0 mt-0.5 ${colors[type] || "bg-white/[0.04] text-zinc-500"}`}>{type[0].toUpperCase()}</div>
      <span className="text-[11px] text-zinc-400 flex-1 leading-relaxed">{msg}</span>
      <span className="text-[10px] text-zinc-600 font-mono shrink-0">{time}</span>
    </div>
  );
}

function formatBytes(n: number): string {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "—";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function ArtifactsPanel({ sessionId }: { sessionId: string | undefined }) {
  const artifactsQ = useQuery<{ artifacts: Array<{ id: string; path: string; size_bytes: number | null; mime_type: string | null; description: string | null; created_at: string | null }> }>({
    queryKey: ["sandbox-artifacts", sessionId],
    queryFn: () => api.get(`/api/artifacts/${sessionId}`),
    enabled: !!sessionId,
    staleTime: 30_000,
  });

  return (
    <div className="bg-card border border-white/[0.06] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Artifacts</span>
        {sessionId && <span className="text-[9px] font-mono text-zinc-700">{sessionId.slice(0, 8)}</span>}
      </div>
      <div className="min-h-[120px]">
        {!sessionId ? (
          <div className="flex flex-col items-center justify-center py-6 text-zinc-700">
            <FileBox className="w-6 h-6 mb-2" strokeWidth={1} />
            <p className="text-[11px]">No sandbox selected</p>
          </div>
        ) : artifactsQ.isLoading ? (
          <div className="space-y-1.5">
            {[0, 1, 2].map(i => <div key={i} className="h-7 rounded-lg shimmer-bg" />)}
          </div>
        ) : (artifactsQ.data?.artifacts?.length ?? 0) === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 text-zinc-700">
            <Inbox className="w-6 h-6 mb-2" strokeWidth={1} />
            <p className="text-[11px]">No artifacts yet</p>
            <p className="text-[10px] text-zinc-800 mt-0.5">Run a pipeline to generate artifacts</p>
          </div>
        ) : (
          artifactsQ.data!.artifacts.slice(0, 6).map(a => {
            const name = a.path?.split(/[/\\]/).pop() ?? a.path;
            const ext = (name?.split(".").pop() ?? "").toLowerCase();
            return (
              <ArtifactRow key={a.id} name={name} size={formatBytes(a.size_bytes ?? 0)} ext={ext} />
            );
          })
        )}
      </div>
    </div>
  );
}

function EventLogPanel({ sessionId }: { sessionId: string | undefined }) {
  const [events, setEvents] = useState<Array<{ type: string; msg: string; ts: number }>>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!sessionId) { setEvents([]); return; }
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    const es = new EventSource(`${BACKEND_URL}/api/events/${sessionId}`);
    esRef.current = es;
    const push = (type: string, msg: string) =>
      setEvents(prev => [{ type, msg, ts: Date.now() }, ...prev].slice(0, 8));
    const handler = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        push(data.type ?? data.event_type ?? "event", data.label ?? data.message ?? JSON.stringify(data).slice(0, 80));
      } catch { push("event", String(e.data).slice(0, 80)); }
    };
    es.addEventListener("connected", () => push("agent", "stream connected"));
    ["tool_call", "tool_result", "agent_message", "phase_enter", "phase_complete", "error", "approval_required"].forEach(t => es.addEventListener(t, handler as EventListener));
    es.onerror = () => {};
    return () => { es.close(); esRef.current = null; };
  }, [sessionId]);

  return (
    <div className="bg-card border border-white/[0.06] rounded-3xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Event Log</span>
        {sessionId && (
          <span className="flex items-center gap-1 text-[9px] font-mono text-zinc-700">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> live
          </span>
        )}
      </div>
      <div className="min-h-[120px] max-h-[200px] overflow-y-auto">
        {!sessionId ? (
          <div className="flex flex-col items-center justify-center py-6 text-zinc-700">
            <Activity className="w-6 h-6 mb-2" strokeWidth={1} />
            <p className="text-[11px]">No sandbox selected</p>
          </div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 text-zinc-700">
            <Activity className="w-6 h-6 mb-2" strokeWidth={1} />
            <p className="text-[11px]">Waiting for events…</p>
          </div>
        ) : (
          events.map((e, i) => <EventRow key={`${e.ts}-${i}`} type={e.type} msg={e.msg} time={timeAgo(new Date(e.ts).toISOString())} />)
        )}
      </div>
    </div>
  );
}

export default function SandboxPage() {
  const router = useRouter();
  const [sandboxes, setSandboxes] = useState<SandboxInfo[]>([]);
  const [execContainers, setExecContainers] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<SandboxMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [ttlMinutes, setTtlMinutes] = useState(30);
  const [sandboxFilter, setSandboxFilter] = useState<"all" | "running" | "idle">("all");
  const [activeTab, setActiveTab] = useState<"overview" | "workspace" | "terminal" | "volumes">("overview");
  const [selectedSandbox, setSelectedSandbox] = useState<string | null>(null);
  const [liveLogs, setLiveLogs] = useState<string[]>([]);
  const [snapshotting, setSnapshotting] = useState<string | null>(null);
  const [volumes, setVolumes] = useState<VolumeInfo[]>([]);
  const [volumesLoading, setVolumesLoading] = useState(false);
  const [destroyingVolume, setDestroyingVolume] = useState<string | null>(null);
  const [reapAfterHours, setReapAfterHours] = useState<number>(168);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // PTY WebSocket for interactive terminal
  const wsRef = useRef<WebSocket | null>(null);
  const termBufferRef = useRef<string>("");
  const termInputRef = useRef<HTMLInputElement>(null);
  const [ptyConnected, setPtyConnected] = useState(false);
  const [ptyLines, setPtyLines] = useState<string[]>([]);

  // Connect PTY WebSocket when terminal tab + sandbox selected
  const connectPty = useCallback(() => {
    if (!selectedSandbox) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${BACKEND_URL.replace("http", "ws")}/api/sandbox/${encodeURIComponent(selectedSandbox)}/pty`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setPtyConnected(true);
      setPtyLines((prev) => [...prev, `> Connected to ${selectedSandbox.slice(0, 12)}`]);
      termInputRef.current?.focus();
    };

    ws.onmessage = (event) => {
      const data = typeof event.data === "string"
        ? event.data
        : new TextDecoder().decode(event.data);
      termBufferRef.current += data;
      const parts = termBufferRef.current.split("\n");
      termBufferRef.current = parts.pop() || "";
      const newLines = parts.filter(Boolean);
      if (newLines.length > 0) {
        setPtyLines((prev) => [...prev.slice(-499), ...newLines]);
      }
    };

    ws.onclose = () => {
      setPtyConnected(false);
      setPtyLines((prev) => [...prev, "> Disconnected"]);
    };

    ws.onerror = () => setPtyConnected(false);

    wsRef.current = ws;
  }, [selectedSandbox]);

  const disconnectPty = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setPtyConnected(false);
  }, []);

  // Auto-connect PTY when sandbox selected + terminal tab active
  useEffect(() => {
    if (activeTab === "terminal" && selectedSandbox) {
      connectPty();
    }
    return () => disconnectPty();
  }, [activeTab, selectedSandbox, connectPty, disconnectPty]);

  // PTY keystroke handling
  const handlePtyKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const keyMap: Record<string, string> = {
      Enter: "\r", Backspace: "\x7f", Tab: "\t",
      ArrowUp: "\x1b[A", ArrowDown: "\x1b[B",
      ArrowRight: "\x1b[C", ArrowLeft: "\x1b[D",
      Home: "\x1b[H", End: "\x1b[F",
    };

    if (e.key === "c" && e.ctrlKey) { e.preventDefault(); wsRef.current.send(new TextEncoder().encode("\x03")); return; }
    if (e.key === "d" && e.ctrlKey) { e.preventDefault(); wsRef.current.send(new TextEncoder().encode("\x04")); return; }
    if (e.key === "l" && e.ctrlKey) { e.preventDefault(); wsRef.current.send(new TextEncoder().encode("\x0c")); return; }

    if (keyMap[e.key]) {
      e.preventDefault();
      wsRef.current.send(new TextEncoder().encode(keyMap[e.key]));
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      wsRef.current.send(new TextEncoder().encode(e.key));
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      const [sb, exec, met] = await Promise.all([
        api.get<{ sandboxes: any[] }>(`/api/sandbox/list`).catch(() => ({ sandboxes: [] })),
        api.get<{ containers: any[] }>(`/api/sandbox/exec-containers`).catch(() => ({ containers: [] })),
        api.get<any>(`/api/sandbox/metrics`).catch(() => null),
      ]);
      setSandboxes(sb.sandboxes || []);
      setExecContainers(exec.containers || []);
      if (met) setMetrics(met);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); const i = setInterval(loadData, 8000); return () => clearInterval(i); }, [loadData]);

  const loadVolumes = useCallback(async () => {
    setVolumesLoading(true);
    try {
      const j = await api.get<{ volumes?: any[]; reap_after_hours?: number }>(`/api/sandbox/volumes`).catch(() => ({ volumes: [], reap_after_hours: 168 }));
      setVolumes(j.volumes || []);
      if (typeof j.reap_after_hours === "number") setReapAfterHours(j.reap_after_hours);
    } catch {
      setVolumes([]);
    }
    setVolumesLoading(false);
  }, []);

  useEffect(() => {
    if (activeTab !== "volumes") return;
    loadVolumes();
    const i = setInterval(loadVolumes, 12000);
    return () => clearInterval(i);
  }, [activeTab, loadVolumes]);

  const handleDestroyVolume = async (name: string) => {
    if (destroyingVolume) return;
    setDestroyingVolume(name);
    try {
      const j = await api.delete<{ error?: string }>(`/api/sandbox/volumes/${encodeURIComponent(name)}`).catch(() => ({ error: "destroy failed" }));
      if (j.error) {
        toast.error(j.error || "Destroy failed");
      } else {
        toast.success(`Volume ${name.slice(0, 28)}… destroyed`);
        setVolumes(p => p.filter(v => v.name !== name));
      }
    } catch (e) {
      toast.error(`Destroy failed: ${e instanceof Error ? e.message : String(e)}`);
    }
    setDestroyingVolume(null);
  };

  const handleDestroy = async (sid: string) => {
    await api.delete(`/api/sandbox/${sid}`);
    setSandboxes(p => p.filter(s => s.session_id !== sid));
  };
  const handleReap = async () => { await api.post(`/api/sandbox/exec-containers/reap`, {}); loadData(); };
  const handleSnapshot = async (sid: string) => {
    setSnapshotting(sid);
    try {
      const result = await createSandboxSnapshot(sid, "");
      if (result?.snapshot_id) {
        toast.success(`Snapshot saved: ${result.snapshot_id.slice(0, 24)}…`);
      } else {
        toast.error("Snapshot failed");
      }
    } catch (e) {
      toast.error(`Snapshot failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSnapshotting(null);
    }
  };

  const allContainers = [...sandboxes, ...execContainers];
  const running = allContainers.filter(c => c.is_running).length;
  const idle = allContainers.filter(c => !c.is_running).length;
  const m = metrics;
  const filtered = allContainers.filter(c => {
    if (sandboxFilter === "running") return c.is_running;
    if (sandboxFilter === "idle") return !c.is_running;
    return true;
  });

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">

      {/* === TOP BAR === */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[13px] text-zinc-500">Monitor</span>
          <span className="text-[10px] text-zinc-700">/</span>
          <span className="text-[13px] text-zinc-100 font-semibold">Sandbox Environments</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.05]">
            <Timer className="w-3 h-3 text-zinc-500" strokeWidth={1.5} />
            <select value={ttlMinutes} onChange={e => setTtlMinutes(Number(e.target.value))}
              className="bg-transparent text-[11px] text-zinc-400 outline-none cursor-pointer font-mono">
              <option value={5}>5m TTL</option>
              <option value={15}>15m TTL</option>
              <option value={30}>30m TTL</option>
              <option value={60}>1h TTL</option>
              <option value={0}>No cleanup</option>
            </select>
          </div>
          <button onClick={handleReap} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] text-zinc-500 hover:text-zinc-300 bg-white/[0.03] border border-white/[0.05] transition-colors">
            <RefreshCw className="w-3 h-3" strokeWidth={1.5} /> Reap
          </button>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/15">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] text-emerald-400 font-medium">Live</span>
          </div>
        </div>
      </div>

      {/* === SECTION 1: KPI STRIP (6 cards) === */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard label="Active Sandboxes" value={running} icon={Server} sub={`${allContainers.length} total`} />
        <KpiCard label="Total Containers" value={allContainers.length} icon={Box} sub={`${idle} idle`} />
        <KpiCard label="Avg CPU" value={m ? `${m.avg_cpu_percent ?? 0}%` : "-"} icon={Cpu} sub="across sandboxes" />
        <KpiCard label="Memory Used" value={m ? `${((m.memory_used_mb ?? 0) / 1024).toFixed(1)} GB` : "-"} icon={HardDrive} sub={m ? `of ${((m.memory_total_mb ?? 0) / 1024).toFixed(1)} GB` : ""} />
        <KpiCard label="Disk Used" value={m ? `${((m.disk_used_mb ?? 0) / 1024).toFixed(1)} GB` : "-"} icon={HardDrive} sub={m ? `of ${((m.disk_total_mb ?? 0) / 1024).toFixed(1)} GB` : ""} />
        <KpiCard label="Sandboxes" value={allContainers.length} icon={Server} sub={`${running} running / ${idle} idle`} />
      </div>

      {/* === SECTION 2: STATUS BAR === */}
      <div className="flex items-center gap-6 flex-wrap px-5 py-3 bg-white/[0.02] border border-white/[0.06] rounded-xl text-[12px] text-zinc-500">
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> {running} running
        </span>
        <span className="w-px h-4 bg-white/[0.06]" />
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-500" /> {idle} idle
        </span>
        <span className="w-px h-4 bg-white/[0.06]" />
        <span className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} /> Docker: healthy
        </span>
        <span className="w-px h-4 bg-white/[0.06]" />
        <span className="flex items-center gap-1.5">
          <Timer className="w-3.5 h-3.5" strokeWidth={1.5} /> Auto-reap: {ttlMinutes > 0 ? `${ttlMinutes}m` : "off"}
        </span>
      </div>

      {/* === SECTION 3: RESOURCE GAUGES === */}
      {m && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-card border border-white/[0.06] rounded-3xl overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-4 pb-0">
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">CPU Usage</span>
            </div>
            <Gauge value={Math.min(m.avg_cpu_percent, 100)} label="avg across sandboxes" color="#f59e0b" />
          </div>
          <div className="bg-card border border-white/[0.06] rounded-3xl overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-4 pb-0">
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Memory Usage</span>
            </div>
            <Gauge value={m.memory_total_mb > 0 ? Math.round((m.memory_used_mb / m.memory_total_mb) * 100) : 0} label="avg across sandboxes" color="#3b82f6" />
          </div>
          <div className="bg-card border border-white/[0.06] rounded-3xl overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-4 pb-0">
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Disk Usage</span>
            </div>
            <Gauge value={m.disk_total_mb > 0 ? Math.round((m.disk_used_mb / m.disk_total_mb) * 100) : 0} label="across sandboxes" color="#34d399" />
          </div>
        </div>
      )}

      {/* === SECTION 4: SANDBOX TABS === */}
      {(
        <>
          <div className="flex gap-0.5 bg-white/[0.02] rounded-xl p-0.5">
            {([
              { id: "overview" as const, label: "Overview", icon: Grid3X3, show: allContainers.length > 0 },
              { id: "workspace" as const, label: "Workspace", icon: FolderTree, show: allContainers.length > 0 },
              { id: "terminal" as const, label: "Terminal", icon: TerminalIcon, show: allContainers.length > 0 },
              { id: "volumes" as const, label: "Volumes", icon: Database, show: true },
            ] as const).filter(t => t.show).map(tab => {
              const Icon = tab.icon;
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-[12px] font-medium transition-all duration-200 ${
                    activeTab === tab.id ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.03]"
                  }`}>
                  <Icon className="w-3.5 h-3.5" strokeWidth={1.5} /> {tab.label}
                </button>
              );
            })}
          </div>

          {/* === OVERVIEW TAB === */}
          {activeTab === "overview" && (
            <div className="space-y-3">
              {/* Sandbox List + Port Map */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <div className="bg-card border border-white/[0.06] rounded-3xl overflow-hidden">
                  <div className="flex items-center justify-between px-5 pt-4 pb-0">
                    <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Sandbox List</span>
                    <div className="flex gap-1 bg-white/[0.02] rounded-lg p-0.5">
                      {(["all", "running", "idle"] as const).map(f => (
                        <button key={f} onClick={() => setSandboxFilter(f)}
                          className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-colors ${
                            sandboxFilter === f ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-600 hover:text-zinc-400"
                          }`}>{f.charAt(0).toUpperCase() + f.slice(1)}</button>
                      ))}
                    </div>
                  </div>
                  <div className="px-5 pb-4 pt-3 overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
                          <th className="pb-2 pr-3">Name</th>
                          <th className="pb-2 pr-3">Status</th>
                          <th className="pb-2 pr-3">Uptime</th>
                          <th className="pb-2 pr-3">Image</th>
                          <th className="pb-2">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.slice(0, 10).map(c => (
                          <tr key={c.session_id}
                            onClick={() => { setSelectedSandbox(c.session_id); setActiveTab("terminal"); }}
                            className={`text-[12px] border-t border-white/[0.03] cursor-pointer transition-colors ${
                              selectedSandbox === c.session_id
                                ? "bg-emerald-500/5 text-emerald-300"
                                : "text-zinc-400 hover:bg-emerald-500/3"
                            }`}>
                            <td className="py-2.5 pr-3 font-mono text-zinc-300">{(c.container_name || `sb-${c.session_id?.slice(0, 8)}`).slice(0, 24)}</td>
                            <td className="py-2.5 pr-3">
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                                c.is_running ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-500/10 text-zinc-500"
                              }`}>{c.is_running ? "running" : "stopped"}</span>
                            </td>
                            <td className="py-2.5 pr-3 font-mono text-zinc-500">{Math.round(c.uptime_seconds / 60)}m</td>
                            <td className="py-2.5 pr-3 font-mono text-zinc-600 text-[10px]">python-nodejs</td>
                            <td className="py-2.5">
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={e => { e.stopPropagation(); handleSnapshot(c.session_id); }}
                                  disabled={snapshotting === c.session_id}
                                  title="Snapshot sandbox"
                                  className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors disabled:opacity-30"
                                >
                                  {snapshotting === c.session_id ? (
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                  ) : (
                                    <Camera className="w-3 h-3" strokeWidth={1.5} />
                                  )}
                                </button>
                                <button onClick={e => { e.stopPropagation(); handleDestroy(c.session_id); }}
                                  className="text-[10px] text-zinc-600 hover:text-red-400 transition-colors"
                                >
                                  <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Port Map */}
                <div className="bg-card border border-white/[0.06] rounded-3xl p-5">
                  <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Active Port Map</span>
                  <div className="mt-4 space-y-3">
                    {filtered.slice(0, 3).map(c => (
                      <div key={c.session_id}>
                        <div className="text-[10px] text-zinc-600 font-mono mb-2 font-semibold uppercase tracking-wider">{c.session_id?.slice(0, 12)}</div>
                        <div className="flex items-center gap-3 py-1.5 border-b border-white/[0.03] last:border-0">
                          <span className="text-[13px] font-bold font-mono text-emerald-400 min-w-[50px]">3000</span>
                          <span className="text-[11px] text-zinc-600">&rarr;</span>
                          <span className="text-[12px] font-mono text-blue-400">localhost:3000</span>
                          <span className="ml-auto text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-semibold uppercase tracking-wider">preview</span>
                        </div>
                      </div>
                    ))}
                    {filtered.length === 0 && <p className="text-[12px] text-zinc-600 text-center py-4">No ports exposed</p>}
                  </div>
                </div>
              </div>

              {/* Artifacts + Flaky Tests + Events (3-col) */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <ArtifactsPanel sessionId={filtered[0]?.session_id} />
                <EventLogPanel sessionId={filtered[0]?.session_id} />
                <div className="bg-card border border-white/[0.06] rounded-3xl p-5">
                  <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Flaky Tests</span>
                  <div className="mt-3 text-center py-6">
                    <AlertTriangle className="w-8 h-8 mx-auto text-zinc-700 mb-2" strokeWidth={1} />
                    <p className="text-[12px] text-zinc-600">No flaky tests detected</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Workspace Tab */}
          {activeTab === "workspace" && (
            <div className="bg-card border border-white/[0.06] rounded-3xl p-6 min-h-[300px] flex items-center justify-center">
              <div className="text-center text-zinc-600">
                <FolderTree className="w-10 h-10 mx-auto mb-3" strokeWidth={1} />
                <p className="text-sm">Select a sandbox row to view workspace</p>
              </div>
            </div>
          )}

          {/* Terminal Tab — PTY WebSocket interactive terminal */}
          {activeTab === "terminal" && (
            <div className="bg-zinc-950 border border-white/[0.06] rounded-2xl overflow-hidden min-h-[400px] flex flex-col shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_20px_40px_-15px_rgba(0,0,0,0.3)]">
              <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-900/80 border-b border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/40" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/40" />
                  <span className="text-[10px] text-zinc-600 font-mono ml-2">
                    {selectedSandbox ? selectedSandbox.slice(0, 12) : "no sandbox"}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-mono">
                  {selectedSandbox ? (
                    ptyConnected ? (
                      <span className="text-emerald-400/60">pty live</span>
                    ) : (
                      <span className="text-zinc-600">connecting...</span>
                    )
                  ) : (
                    <span className="text-zinc-700">select a sandbox</span>
                  )}
                </div>
              </div>
              <div className="flex-1 p-4 overflow-y-auto font-mono text-[12px] leading-[1.7] max-h-[560px]">
                {!selectedSandbox ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center space-y-1">
                      <TerminalIcon className="w-8 h-8 mx-auto mb-2 text-zinc-700" strokeWidth={1} />
                      <p className="text-xs text-zinc-600">Select a sandbox to open terminal</p>
                    </div>
                  </div>
                ) : ptyLines.length === 0 ? (
                  <div className="text-zinc-600 text-xs">Initializing PTY session...</div>
                ) : (
                  ptyLines.map((line, i) => (
                    <div key={i} className="text-zinc-400 whitespace-pre-wrap break-all py-[1px]">
                      {line}
                    </div>
                  ))
                )}
                <div ref={logsEndRef} />
              </div>
              {/* PTY input */}
              {selectedSandbox && (
                <div className="px-4 pb-3 border-t border-white/[0.04]">
                  <input
                    ref={termInputRef}
                    type="text"
                    autoFocus
                    onKeyDown={handlePtyKeyDown}
                    className="w-full bg-transparent outline-none text-zinc-300 text-[12px] font-mono caret-emerald-400"
                    placeholder={ptyConnected ? "Type here..." : "Connecting..."}
                    disabled={!ptyConnected}
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="off"
                    spellCheck={false}
                  />
                </div>
              )}
            </div>
          )}

          {/* === VOLUMES TAB === */}
          {activeTab === "volumes" && (
            <motion.div
              key="volumes"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 220, damping: 26 }}
              className="bg-card border border-white/[0.06] rounded-3xl overflow-hidden"
            >
              <div className="flex items-center justify-between px-5 pt-4 pb-3">
                <div className="flex items-center gap-2">
                  <Archive className="w-3.5 h-3.5 text-zinc-500" strokeWidth={1.5} />
                  <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Workspace Volumes</span>
                  <span className="text-[10px] font-mono text-zinc-600">testai-ws-*</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-600 font-mono">
                    {volumesLoading ? "scanning..." : `${volumes.length} volume${volumes.length === 1 ? "" : "s"}`}
                  </span>
                  <span className="text-[10px] text-zinc-700 font-mono">reap after {reapAfterHours}h idle</span>
                </div>
              </div>

              {/* Skeleton */}
              {volumesLoading && volumes.length === 0 && (
                <div className="px-5 pb-5 space-y-2">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="h-12 rounded-lg shimmer-bg" style={{ animationDelay: `${i * 80}ms` }} />
                  ))}
                </div>
              )}

              {/* Empty state */}
              {!volumesLoading && volumes.length === 0 && (
                <div className="px-5 pb-8 pt-2 flex flex-col items-center text-center">
                  <Database className="w-8 h-8 text-zinc-700 mb-2" strokeWidth={1} />
                  <p className="text-[12px] text-zinc-400 font-medium">No workspace volumes</p>
                  <p className="text-[11px] text-zinc-600 mt-1 max-w-[40ch]">
                    Volumes appear here once a pipeline runs. Each repo gets its own volume, reused across sessions.
                  </p>
                </div>
              )}

              {/* List — divide-y, no card chrome (data density 4) */}
              {volumes.length > 0 && (
                <div className="border-t border-white/[0.06]">
                  <AnimatePresence initial={false}>
                    {volumes.map((v, idx) => {
                      const isDestroying = destroyingVolume === v.name;
                      const seg = v.segment || "default";
                      const repoish = seg.replace(/_/g, "/").replace(/^https?\/+/, "");
                      return (
                        <motion.div
                          key={v.name}
                          layout
                          initial={{ opacity: 0, x: -4 }}
                          animate={{ opacity: isDestroying ? 0.4 : 1, x: 0, scale: isDestroying ? 0.99 : 1 }}
                          exit={{ opacity: 0, x: 8, transition: { duration: 0.18 } }}
                          transition={{ type: "spring", stiffness: 240, damping: 28, delay: idx * 0.02 }}
                          className="flex items-center gap-3 px-5 py-3 border-b border-white/[0.04] last:border-b-0 hover:bg-white/[0.02] transition-colors duration-150"
                        >
                          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${v.in_use ? "bg-emerald-400 animate-pulse" : "bg-zinc-700"}`} />
                          <div className="flex-1 min-w-0">
                            <div className="text-[12px] font-mono text-zinc-200 truncate" title={v.name}>
                              {repoish || v.name}
                            </div>
                            <div className="text-[10px] font-mono text-zinc-600 truncate" title={v.name}>
                              {v.name}
                            </div>
                          </div>
                          <div className="text-right shrink-0 hidden md:block">
                            <div className="text-[10px] font-mono text-zinc-500">
                              {v.created_at ? new Date(v.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}
                            </div>
                            <div className="text-[10px] font-mono text-zinc-700">
                              {v.created_at ? new Date(v.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : ""}
                            </div>
                          </div>
                          <span className={`text-[10px] font-mono px-2 py-0.5 rounded uppercase tracking-wider shrink-0 ${
                            v.in_use ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-500/10 text-zinc-500"
                          }`}>
                            {v.in_use ? "in use" : "idle"}
                          </span>
                          <button
                            onClick={() => handleDestroyVolume(v.name)}
                            disabled={v.in_use || isDestroying || !!destroyingVolume}
                            title={v.in_use ? "In use by a running container" : "Destroy this volume"}
                             className="shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-red-500/10 active:scale-[0.97] active:translate-y-px transition-all duration-150 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-zinc-600"
                          >
                            {isDestroying ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.5} />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
                            )}
                          </button>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
              )}

              <div className="px-5 py-2.5 border-t border-white/[0.04] text-[10px] font-mono text-zinc-700 flex items-center justify-between">
                <span>Reaper sweeps every cycle · in-use volumes are skipped</span>
                <button
                  onClick={loadVolumes}
                  className="flex items-center gap-1 text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <RefreshCw className="w-3 h-3" strokeWidth={1.5} /> refresh
                </button>
              </div>
            </motion.div>
          )}
        </>
      )}

      {/* Loading */}
      {loading && <div className="grid grid-cols-3 gap-3">{[1,2,3,4,5,6].map(i => <div key={i} className="h-28 rounded-[2.5rem] shimmer-bg" />)}</div>}

      {/* Empty */}
      {!loading && allContainers.length === 0 && !(activeTab === "volumes" && volumes.length > 0) && (
        <div className="flex flex-col items-center justify-center min-h-[40vh] text-center">
          <Server className="w-12 h-12 text-zinc-700 mb-4" strokeWidth={1} />
          <p className="text-zinc-400 text-sm font-medium">No active containers</p>
          <p className="text-zinc-600 text-xs mt-1">Run a pipeline to create a sandbox environment</p>
          <Link href="/pipeline" className="mt-5 text-[12px] text-emerald-400 bg-emerald-500/8 border border-emerald-500/12 rounded-lg px-4 py-2 hover:bg-emerald-500/12 transition-colors">Go to Pipeline</Link>
        </div>
      )}
    </motion.div>
  );
}
