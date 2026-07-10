"use client";

import { Suspense, useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, BASE_URL } from "@/lib/api/api-client";
import { toast } from "sonner";
import { useSearchParams } from "next/navigation";
import { DelegationTreeView } from "@/components/agents/DelegationTreeView";
import { PageShell } from "@/components/shared/PageShell";
import { KpiRow } from "@/components/shared/KpiRow";
import { SearchFilterBar } from "@/components/shared/SearchFilterBar";
import { TabErrorBoundary } from "@/components/shared/TabErrorBoundary";
import { BentoCard } from "@/components/shared/BentoCard";
import { RevealSection } from "@/components/shared/RevealSection";
import { GitPullRequest, Rocket, AlertTriangle, CheckCircle2, XCircle, Archive, Download, FileText, FileJson, FileType, Image, Clock } from "lucide-react";
import { SessionTimeline } from "@/components/session/SessionTimeline";
import { AgentThinkingPanel } from "@/components/agents/AgentThinkingPanel";

const rowVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as const } },
};

const springTab = { duration: 0.2, ease: [0.16, 1, 0.3, 1] as const };

type SessionRow = {
  id: string; title: string; status: string; source: "chat" | "pipeline" | "delegation" | "pr";
  goal: string; agentRole: string; depth: number; model: string;
  cost: number; tokens: number; createdAt: string; endedAt: string | null;
  testCount?: number; passedCount?: number; failedCount?: number; skippedCount?: number;
  prNumber?: number; prStatus?: string; prRiskScore?: number;
  messageCount?: number; toolCallCount?: number;
  inputTokens?: number; outputTokens?: number;
  apiCallCount?: number; parentId?: string | null;
};

type Tab = "live" | "messages" | "delegation" | "prs" | "artifacts" | "metadata" | "logs" | "timeline" | "recordings";

interface PRInfo {
  id: string; pr_number: number; title: string; status: string; priority: string;
  risk_score: number; last_test_status?: string; last_logaf_score?: number;
  total_fix_cycles?: number; files_changed: number; additions: number; deletions: number;
  source_branch?: string; repo_url?: string;
}

function SourceIcon({ source }: { source: string }) {
  const cfg: Record<string, { label: string; bg: string; text: string; icon?: React.ReactNode }> = {
    chat: { label: "C", bg: "bg-emerald-500/10", text: "text-emerald-400" },
    pipeline: { label: "P", bg: "bg-blue-500/10", text: "text-blue-400" },
    delegation: { label: "D", bg: "bg-zinc-500/10", text: "text-zinc-400" },
    pr: { label: "PR", bg: "bg-amber-500/10", text: "text-amber-400" },
  };
  const c = cfg[source] ?? cfg.delegation;
  return <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-bold font-mono", c.bg, c.text)}>{c.label}</div>;
}

function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    running: "bg-emerald-400 animate-pulse",
    ok: "bg-emerald-400",
    completed: "bg-zinc-600",
    failed: "bg-red-400",
    idle: "bg-zinc-700",
  };
  const pulse = status === "running" ? "after:absolute after:inset-[-3px] after:rounded-full after:bg-emerald-400/30 after:animate-ping" : "";
  return <span className={cn("w-1.5 h-1.5 rounded-full relative shrink-0", map[status] ?? "bg-zinc-700", pulse)} />;
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  const hue = score >= 80 ? "bg-emerald-500/10 text-emerald-400" : score >= 50 ? "bg-amber-500/10 text-amber-400" : "bg-red-500/10 text-red-400";
  return <span className={cn("text-[10px] font-semibold font-mono px-1 py-0.5 rounded", hue)}>{score}</span>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const d = new Date(dateStr).getTime();
  const sec = Math.floor((now - d) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  return `${Math.floor(hr / 24)}d`;
}

function SavedFilterDropdown({ onLoad }: { onLoad: (search: string, source: string, status: string) => void }) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["saved-filters"],
    queryFn: () => api.get<{ filters?: any[] }>("/api/saved-filters"),
    staleTime: 30_000,
  });
  const filters = data?.filters ?? [];
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="text-[10px] px-2 py-1 rounded text-zinc-500 hover:text-zinc-300 border border-white/[0.06] transition-colors flex items-center gap-1">
        Saved Filters {filters.length > 0 && <span className="text-zinc-700 font-mono">({filters.length})</span>}
      </button>
      {open && (
          <div className="absolute top-full left-0 mt-1 z-50 bg-surface-elevated border border-white/[0.06] rounded-xl shadow-lg overflow-hidden min-w-[180px]">
          {filters.length === 0 ? (
            <div className="px-3 py-2 text-[10px] text-zinc-600">No saved filters</div>
          ) : filters.map((f: any) => (
            <button key={f.id} onClick={() => {
              try {
                const d = JSON.parse(f.filter_data || "{}");
                onLoad(d.search || "", d.source || "", d.status || "");
              } catch {}
              setOpen(false);
            }}
              className="flex items-center gap-2 w-full px-3 py-2 text-left text-[11px] text-zinc-400 hover:bg-white/[0.03] transition-colors">
              <span>{f.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SessionsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState("");
  const [filterSource, setFilterSource] = useState(searchParams?.get("source") || "");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterAgentRole, setFilterAgentRole] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState<Tab>("messages");
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const [selectedForTree, setSelectedForTree] = useState<string | null>(null);

  const { data: overview } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => api.get<any>("/api/dashboard/overview"),
    refetchInterval: 30_000,
  });

  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [prs, setPrs] = useState<PRInfo[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingPrs, setLoadingPrs] = useState(false);
  const [sessionPrs, setSessionPrs] = useState<PRInfo[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const sessionPath = search.trim()
        ? `/api/sessions/search?q=${encodeURIComponent(search.trim())}`
        : "/api/sessions?limit=50";
      const [sessData, prData] = await Promise.all([
        api.get<{ sessions?: unknown[] }>(sessionPath).catch(() => ({ sessions: [] })),
        api.get<{ prs?: PRInfo[] }>("/api/prs").catch(() => ({ prs: [] })),
      ]);
      const raw: any[] = sessData?.sessions ?? [];
      const mapped: SessionRow[] = raw.map((s: any) => ({
        id: s.session_id || s.id,
        title: s.goal?.slice(0, 80) || s.title || (s.session_id || s.id || "").slice(0, 12),
        status: s.status === "ok" ? "completed" : s.status || "completed",
        source: s.source === "pipeline" || s.source === "api" ? "pipeline" : s.source === "delegation" ? "delegation" : "chat",
        goal: s.goal || "",
        agentRole: s.agent_role || "",
        depth: s.depth ?? 0,
        model: s.model || "",
        cost: s.cost ?? s.estimated_cost_usd ?? 0,
        tokens: s.tokens ?? 0,
        createdAt: s.created_at || s.createdAt || "",
        endedAt: s.ended_at || null,
        messageCount: s.message_count ?? 0,
        toolCallCount: s.tool_call_count ?? 0,
        inputTokens: s.input_tokens ?? 0,
        outputTokens: s.output_tokens ?? 0,
        apiCallCount: s.api_call_count ?? 0,
        parentId: s.parent_session_id ?? null,
      }));
      const prRows: SessionRow[] = (prData?.prs ?? []).map((pr: any) => ({
        id: pr.id,
        title: `#${pr.pr_number} ${pr.title}`.slice(0, 80),
        status: pr.status === "open" ? "running" : pr.status === "merged" ? "completed" : "failed",
        source: "pr" as const,
        goal: pr.title || "",
        agentRole: "pr",
        depth: 0,
        model: "",
        cost: 0,
        tokens: 0,
        createdAt: pr.created_at || "",
        endedAt: null,
        prNumber: pr.pr_number,
        prStatus: pr.status,
        prRiskScore: pr.risk_score,
      }));
      const combined = [...mapped, ...prRows];
      combined.sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime());
      setSessions(combined);
      setPrs(prData?.prs ?? []);
    } catch (e) {
      toast.error("Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (!selectedId) { setSessionPrs([]); setArtifacts([]); return; }
    setLoadingPrs(true);
    api.get<{ prs?: PRInfo[] }>(`/api/prs?session_id=${encodeURIComponent(selectedId)}`)
      .then((d) => setSessionPrs(d?.prs || []))
      .catch(() => setSessionPrs([]))
      .finally(() => setLoadingPrs(false));
    setLoadingArtifacts(true);
    api.get<{ artifacts?: any[] }>(`/api/artifacts/${encodeURIComponent(selectedId)}`)
      .then((d) => setArtifacts(d?.artifacts || []))
      .catch(() => setArtifacts([]))
      .finally(() => setLoadingArtifacts(false));
  }, [selectedId]);

  const detailQ = useQuery({
    queryKey: ["session-detail", selectedId],
    queryFn: async () => {
      if (!selectedId) return null;
      return api.get<any>(`/api/sessions/${encodeURIComponent(selectedId)}`);
    },
    enabled: !!selectedId,
  });

  const eventsQ = useQuery({
    queryKey: ["session-events", selectedId],
    queryFn: async () => {
      if (!selectedId) return { events: [] };
      return api.get<{ events?: any[] }>(`/api/sessions/${encodeURIComponent(selectedId)}/events?limit=200`);
    },
    enabled: !!selectedId,
    refetchInterval: 10_000,
  });

  const agentRoles = [...new Set(sessions.map((s) => s.agentRole).filter(Boolean))];
  const filtered = sessions.filter((s) => {
    if (filterSource && s.source !== filterSource) return false;
    if (filterStatus && s.status !== filterStatus) return false;
    if (filterAgentRole && s.agentRole !== filterAgentRole) return false;
    return true;
  });

  const handleSelect = (id: string) => {
    setSelectedId(selectedId === id ? null : id);
    setSelectedTab("messages");
  };

  const handleResume = (id: string) => router.push(`/chat?thread_id=${encodeURIComponent(id)}`);
  const handleExport = (id: string) => { window.open(`${BASE_URL}/api/sessions/${encodeURIComponent(id)}/export`, "_blank"); toast.success("Exported"); };
  const handleDelete = async (id: string, source: string) => {
    if (source !== "chat") return;
    if (!confirm("Delete this session?")) return;
    await api.delete(`/api/sessions/${encodeURIComponent(id)}`);
    setSessions((p) => p.filter((s) => s.id !== id));
  };

  const toggleCompare = (id: string) => {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <PageShell
      title="Sessions"
      description="Browse, search, and inspect agent runs and pipeline executions"
      actions={
        <>
          <AnimatePresence>
            {compareIds.size > 1 && (
              <motion.button initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} transition={springTab}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg bg-white/[0.04] text-zinc-200 border border-white/[0.08] transition-colors hover:bg-white/[0.06]">
                Compare <span className="ml-0.5 bg-emerald-400/20 px-1 rounded text-[10px]">{compareIds.size}</span>
              </motion.button>
            )}
          </AnimatePresence>
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg bg-white/[0.03] border border-white/[0.06] text-zinc-500 hover:text-zinc-300 transition-colors"
            onClick={() => { fetchData(); toast.success("Refreshed"); }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            Refresh
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-lg bg-white/[0.03] border border-white/[0.06] text-zinc-500 hover:text-zinc-300 transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Export
          </button>
        </>
      }
      sections={[
        {
          title: "Overview",
          children: (
            <RevealSection>
              <BentoCard label="Session Overview" description="Aggregate session metrics across all sources" padding="sm">
                <KpiRow items={[
                  { label: "Total Sessions", value: sessions.length, sub: `+${overview?.pipeline_runs_24h ?? 0} last 24h` },
                  { label: "Active Now", value: overview?.active_agents ?? 0, sub: `${overview?.pipeline_status?.running ?? 0} agents`, pulse: (overview?.active_agents ?? 0) > 0 },
                  { label: "Today", value: overview?.pipeline_runs_24h ?? 0, sub: `${overview?.tests_24h?.passed ?? 0} passed` },
                  { label: "Avg Cost", value: `$${((sessions.reduce((s, x) => s + x.cost, 0) / (sessions.length || 1))).toFixed(4)}`, sub: `~${Math.round(sessions.reduce((s, x) => s + x.tokens, 0) / (sessions.length || 1))} tok avg` },
                ]} />
              </BentoCard>
            </RevealSection>
          ),
        },
        {
          title: "Filters",
          children: (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <SavedFilterDropdown onLoad={(s, st, r) => { setSearch(s); setFilterSource(st || ""); setFilterStatus(r || ""); }} />
                <button onClick={async () => {
                  const name = prompt("Save current filter as:");
                  if (!name) return;
                  await api.post("/api/saved-filters", { name, filter_data: JSON.stringify({ search, source: filterSource, status: filterStatus }) });
                  toast.success("Filter saved");
                }} className="text-[10px] px-2 py-1 rounded text-zinc-500 hover:text-zinc-300 border border-white/[0.06] transition-colors">+ Save</button>
              </div>
              <SearchFilterBar
                search={search} onSearchChange={setSearch} searchPlaceholder="Search sessions..."
                sourceFilters={[{ v: "", l: "All" }, { v: "chat", l: "Chat" }, { v: "pipeline", l: "Pipeline" }, { v: "delegation", l: "Delegation" }, { v: "pr", l: "Pull Requests" }].map(o => ({ value: o.v, label: o.l }))}
                sourceValue={filterSource} onSourceChange={setFilterSource}
                selects={[
                  {
                    value: filterStatus, onChange: setFilterStatus, placeholder: "Status",
                    options: [{ value: "completed", label: "Completed" }, { value: "running", label: "Running" }, { value: "failed", label: "Failed" }],
                  },
                  ...(agentRoles.length > 0 ? [{
                    value: filterAgentRole, onChange: setFilterAgentRole, placeholder: "Agent Role",
                    options: agentRoles.map(r => ({ value: r, label: r })),
                  }] : []),
                ]}
              />
            </div>
          ),
        },
        {
          title: "Sessions",
          children: (
            <RevealSection>
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4 items-stretch">
              <div className="space-y-0.5">
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="h-16 rounded-xl shimmer-bg border border-white/[0.04]" />
                  ))
                ) : filtered.length === 0 ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-16 text-zinc-600">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="opacity-30 mb-3"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    <p className="text-sm">{search ? "No sessions match" : "No sessions yet"}</p>
                  </motion.div>
                ) : (
                  filtered.map((s, i) => (
                    <div key={s.id}>
                      <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.015, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                        onClick={() => handleSelect(s.id)}
                        className={cn("flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all border",
                          selectedId === s.id ? "bg-white/[0.03] border-white/[0.08]" : "hover:bg-white/[0.02] border-transparent")}>
                        <span onClick={(e) => { e.stopPropagation(); toggleCompare(s.id); }}
                          className={cn("w-4 h-4 rounded border shrink-0 flex items-center justify-center transition-colors cursor-pointer",
                            compareIds.has(s.id) ? "bg-emerald-400 border-emerald-400" : "border-zinc-700 hover:border-zinc-500")}>
                          {compareIds.has(s.id) && (<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>)}
                        </span>
                        <SourceIcon source={s.source} />
                        <StatusDot status={s.status} />
                        <ScoreBadge score={s.cost > 0 ? Math.min(99, Math.round(s.tokens / (s.cost * 100) / 100)) : null} />
                        <div className="min-w-0 flex-1">
                          <div className="text-[13px] font-medium text-zinc-200 truncate">{s.title}</div>
                          <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-zinc-600 flex-wrap">
                            <span className={cn("px-1 py-0.5 rounded text-[9px] font-medium uppercase",
                              s.source === "chat" ? "bg-emerald-500/10 text-emerald-400" :
                              s.source === "pipeline" ? "bg-blue-500/10 text-blue-400" :
                              s.source === "pr" ? "bg-amber-500/10 text-amber-400" : "bg-zinc-500/10 text-zinc-400")}>{s.source}</span>
                            {s.prNumber && <span className="text-amber-400 font-mono text-[9px]">#{s.prNumber}</span>}
                            {s.prRiskScore && s.prRiskScore > 0 && <span className="text-zinc-700 text-[9px]">risk {s.prRiskScore}</span>}
                            {s.model && <span className="px-1 py-0.5 rounded bg-white/[0.04] text-zinc-600">{s.model}</span>}
                            {(s.messageCount ?? 0) > 0 && <span className="text-zinc-700 text-[9px]">{s.messageCount} msgs</span>}
                            {(s.toolCallCount ?? 0) > 0 && <span className="text-zinc-700 text-[9px]">{s.toolCallCount} tools</span>}
                            <span>${s.cost.toFixed(4)}</span>
                            <span>{s.tokens.toLocaleString()} tok</span>
                            {s.depth > 0 && <span>depth {s.depth}</span>}
                            {s.agentRole && <span className="text-zinc-700">{s.agentRole}</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {s.source === "chat" && (
                            <>
                              <button onClick={(e) => { e.stopPropagation(); handleResume(s.id); }}
                                className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-600 hover:text-zinc-200 hover:bg-white/[0.06] transition-colors" title="Resume">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                              </button>
                              <button onClick={(e) => { e.stopPropagation(); handleExport(s.id); }}
                                className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-600 hover:text-zinc-200 hover:bg-white/[0.06] transition-colors" title="Export">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                              </button>
                              <button onClick={(e) => { e.stopPropagation(); setSelectedForTree(selectedForTree === s.id ? null : s.id); }}
                                className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-colors", selectedForTree === s.id ? "text-zinc-100 bg-white/[0.08]" : "text-zinc-600 hover:text-zinc-200 hover:bg-white/[0.06]")} title="Delegation tree">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>
                              </button>
                            </>
                          )}
                          {s.source === "pr" ? (
                            <button onClick={(e) => {
                              e.stopPropagation();
                              const pr = prs.find((p) => p.id === s.id);
                              const url = pr?.repo_url || (s.prNumber ? `https://github.com/pulls?q=is%3Apr+${s.prNumber}` : null);
                              if (url) window.open(url, "_blank", "noopener,noreferrer");
                            }}
                              disabled={!prs.find((p) => p.id === s.id)?.repo_url && !s.prNumber}
                              className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-colors",
                                (prs.find((p) => p.id === s.id)?.repo_url || s.prNumber)
                                  ? "text-amber-600 hover:text-amber-400 hover:bg-amber-500/10"
                                  : "text-zinc-800 cursor-not-allowed")}
                              title="View PR">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 15l-6-6-6 6"/></svg>
                            </button>
                          ) : (
                            <button onClick={(e) => { e.stopPropagation(); handleDelete(s.id, s.source); }}
                              className="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors" title="Delete">
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            </button>
                          )}
                        </div>
                        <div className="text-[10px] font-mono text-zinc-700 shrink-0 min-w-[42px] text-right">
                          {s.createdAt ? timeAgo(s.createdAt) : ""}
                        </div>
                      </motion.div>
                      <AnimatePresence>
                        {selectedForTree === s.id && (
                          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden pl-14 pr-3">
                            <div className="pb-3"><DelegationTreeView sessionId={s.id} /></div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  ))
                )}
              </div>

              <AnimatePresence>
                {selectedId && (
                  <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={springTab}
                    className="bg-surface border border-white/[0.06] rounded-[2rem] overflow-hidden sticky top-4">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
                      <div className="flex items-center gap-2 min-w-0">
                        <StatusDot status={filtered.find((s) => s.id === selectedId)?.status ?? ""} />
                        <span className="text-[12px] font-semibold text-zinc-100 truncate font-mono">{selectedId.slice(0, 16)}</span>
                      </div>
                      <button onClick={() => setSelectedId(null)} className="w-6 h-6 rounded flex items-center justify-center text-zinc-600 hover:text-zinc-400 transition-colors">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                      </button>
                    </div>

                    <div className="flex gap-0 px-3 pt-2 bg-white/[0.01] border-b border-white/[0.06]">
                      {(["live", "messages", "delegation", "prs", "artifacts", "metadata", "logs", "timeline", "recordings"] as Tab[]).map((t) => (
                        <button key={t} onClick={() => setSelectedTab(t)}
                          className={cn("px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider transition-colors -mb-px border-b-2",
                            selectedTab === t ? "border-emerald-400 text-zinc-100" : "border-transparent text-zinc-600 hover:text-zinc-400")}>{t}</button>
                      ))}
                    </div>

                    <div className="p-4 max-h-[480px] overflow-y-auto space-y-3 text-[12px]">
                      <TabErrorBoundary tab="live">
                        {selectedTab === "live" && <AgentThinkingPanel sessionId={selectedId} />}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="messages">
                        {selectedTab === "messages" && (
                          eventsQ.isLoading ? (
                            <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 rounded-lg shimmer-bg" />)}</div>
                          ) : (() => {
                            const events = eventsQ.data?.events ?? [];
                            if (events.length === 0) {
                              return <p className="text-zinc-600">No messages captured for this session yet.</p>;
                            }
                            return events.slice(0, 20).map((ev: any, i: number) => {
                              const isUser = ev.type === "user_message" || ev.type === "user" || ev.payload?.role === "user";
                              const isAssistant = ev.type === "assistant_message" || ev.type === "assistant" || ev.type === "llmcall.completed" || ev.type === "LLMCallCompleted" || ev.payload?.role === "assistant";
                              const isTool = ev.type === "tool.execution.started" || ev.type === "tool.execution.completed" || ev.type === "ToolExecutionStarted" || ev.type === "ToolExecutionCompleted" || ev.type === "tool_call" || ev.type === "tool_result" || ev.payload?.tool_name;
                              const toolName = ev.payload?.tool_name || ev.payload?.name;
                              const text = ev.payload?.content ?? ev.payload?.text ?? ev.payload?.message ?? (typeof ev.payload === "string" ? ev.payload : "");
                              return (
                                <div key={ev.id ?? i} className="flex gap-2.5">
                                  <div className={cn("w-6 h-6 rounded-lg flex items-center justify-center text-[9px] font-bold shrink-0",
                                    isUser ? "bg-white/[0.05] text-zinc-500" :
                                    isTool ? "bg-amber-500/10 text-amber-400" :
                                    "bg-emerald-500/10 text-emerald-400")}>
                                    {isUser ? "U" : isTool ? "T" : "A"}
                                  </div>
                                  <div className="min-w-0">
                                    <div className="text-[10px] text-zinc-600 font-medium">
                                      {isUser ? "User" : isTool ? `Tool: ${toolName ?? "?"}` : "Assistant"}
                                    </div>
                                    <p className={cn("text-[12px] leading-relaxed mt-0.5",
                                      isTool ? "text-zinc-600 font-mono text-[11px]" : "text-zinc-400"
                                    )}>{String(text || "").slice(0, 300) || "—"}</p>
                                  </div>
                                </div>
                              );
                            });
                          })()
                        )}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="delegation">
                        {selectedTab === "delegation" && <DelegationTreeView sessionId={selectedId} />}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="prs">
                        {selectedTab === "prs" && (
                          loadingPrs ? (
                            <div className="space-y-2">{Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-16 rounded-lg shimmer-bg" />)}</div>
                          ) : sessionPrs.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
                              <GitPullRequest className="w-8 h-8 opacity-30 mb-2" strokeWidth={1} />
                              <p className="text-[12px]">No pull requests for this session</p>
                            </div>
                          ) : sessionPrs.map((pr) => (
                            <div key={pr.id} className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 space-y-3">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <GitPullRequest className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />
                                  <span className="text-[13px] font-semibold text-zinc-200">#{pr.pr_number}</span>
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                                    pr.status === "open" ? "bg-emerald-500/10 text-emerald-400" :
                                    pr.status === "merged" ? "bg-blue-500/10 text-blue-400" :
                                    "bg-zinc-800 text-zinc-600"
                                  }`}>{pr.status}</span>
                                </div>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                                  pr.priority === "high" ? "bg-red-500/10 text-red-400" :
                                  pr.priority === "medium" ? "bg-amber-500/10 text-amber-400" :
                                  "bg-emerald-500/10 text-emerald-400"
                                }`}>{pr.priority}</span>
                              </div>
                              <p className="text-[12px] text-zinc-300">{pr.title}</p>
                              {pr.source_branch && (
                                <p className="text-[10px] text-zinc-600 font-mono">{pr.source_branch}</p>
                              )}
                              <div className="grid grid-cols-3 gap-2 text-center">
                                <div className="bg-white/[0.02] rounded-lg p-2">
                                  <div className="text-[14px] font-semibold font-mono text-zinc-100">{pr.files_changed}</div>
                                  <div className="text-[9px] text-zinc-600">Files</div>
                                </div>
                                <div className="bg-white/[0.02] rounded-lg p-2">
                                  <div className="text-[14px] font-semibold font-mono text-emerald-400">+{pr.additions}</div>
                                  <div className="text-[9px] text-zinc-600">Added</div>
                                </div>
                                <div className="bg-white/[0.02] rounded-lg p-2">
                                  <div className="text-[14px] font-semibold font-mono text-red-400">-{pr.deletions}</div>
                                  <div className="text-[9px] text-zinc-600">Deleted</div>
                                </div>
                              </div>
                              {pr.last_test_status && (
                                <div className="flex items-center gap-2 text-[11px]">
                                  <span className={`flex items-center gap-1 ${
                                    pr.last_test_status === "passed" ? "text-emerald-400" : "text-red-400"
                                  }`}>
                                    {pr.last_test_status === "passed" ? <CheckCircle2 className="w-3 h-3" strokeWidth={1.5} /> : <XCircle className="w-3 h-3" strokeWidth={1.5} />}
                                    {pr.last_test_status}
                                  </span>
                                  {pr.last_logaf_score !== undefined && (
                                    <span className="text-zinc-600">LOGAF: {pr.last_logaf_score}</span>
                                  )}
                                </div>
                              )}
                            </div>
                          ))
                        )}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="artifacts">
                        {selectedTab === "artifacts" && (
                          loadingArtifacts ? (
                            <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 rounded-lg shimmer-bg" />)}</div>
                          ) : artifacts.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
                              <Archive className="w-8 h-8 opacity-30 mb-2" strokeWidth={1} />
                              <p className="text-[12px]">No artifacts for this session</p>
                            </div>
                          ) : (
                            <div className="space-y-1">
                              {artifacts.map((a: any) => (
                                <div key={a.id} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.02] transition-colors border border-transparent hover:border-white/[0.06]">
                                  <div className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center shrink-0">
                                    {a.mime_type?.startsWith("image/") ? <Image className="w-4 h-4 text-zinc-400" strokeWidth={1.5} /> :
                                     a.mime_type?.includes("json") ? <FileJson className="w-4 h-4 text-zinc-400" strokeWidth={1.5} /> :
                                     a.mime_type?.includes("html") ? <FileType className="w-4 h-4 text-zinc-400" strokeWidth={1.5} /> :
                                     <FileText className="w-4 h-4 text-zinc-400" strokeWidth={1.5} />}
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="text-[12px] font-medium text-zinc-300 truncate">{a.path?.split("/").pop() || a.id}</div>
                                    <div className="text-[10px] text-zinc-600 font-mono">
                                      {formatBytes(a.size_bytes)} · {a.mime_type || "unknown"}
                                    </div>
                                  </div>
                                  {a.session_id && (
                                    <span className="text-[9px] text-zinc-700 font-mono truncate max-w-[80px]">{a.session_id.slice(0, 8)}</span>
                                  )}
                                  {a.id && (
                                    <a href={`${BASE_URL}/api/artifacts/${a.id}/download`} target="_blank" rel="noopener noreferrer"
                                      className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-zinc-600 hover:text-zinc-400 hover:bg-white/[0.04] transition-colors">
                                      <Download className="w-3 h-3" strokeWidth={1.5} />
                                    </a>
                                  )}
                                </div>
                              ))}
                            </div>
                          )
                        )}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="metadata">
                        {selectedTab === "metadata" && detailQ.data && (
                          <div className="space-y-2 divide-y divide-white/[0.04]">
                            {[
                              { l: "Session ID", v: detailQ.data.id },
                              { l: "Source", v: detailQ.data.source },
                              { l: "Status", v: detailQ.data.status },
                              { l: "Model", v: detailQ.data.model || "\u2014" },
                              { l: "Provider", v: detailQ.data.provider || "\u2014" },
                              { l: "Agent Role", v: detailQ.data.agent_role || "\u2014" },
                              { l: "Depth", v: String(detailQ.data.depth ?? 0) },
                              { l: "Cost", v: `$${(detailQ.data.estimated_cost_usd ?? detailQ.data.total_cost ?? 0).toFixed(4)}` },
                              { l: "Tokens", v: (detailQ.data.total_tokens ?? 0).toLocaleString() },
                              { l: "Created", v: detailQ.data.created_at ? new Date(detailQ.data.created_at).toLocaleString() : "\u2014" },
                              { l: "Ended", v: detailQ.data.ended_at ? new Date(detailQ.data.ended_at).toLocaleString() : "\u2014" },
                              { l: "End Reason", v: detailQ.data.end_reason || "\u2014" },
                            ].map((r) => (
                              <div key={r.l} className="flex items-center justify-between py-1.5 text-[11px]">
                                <span className="text-zinc-600">{r.l}</span>
                                <span className="text-zinc-300 font-mono text-[10px] truncate max-w-[200px] text-right">{String(r.v ?? "\u2014")}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="logs">
                        {selectedTab === "logs" && (
                          (() => {
                            const toolEvents = (eventsQ.data?.events ?? []).filter(
                              (e: any) => e.type === "tool.execution.started" || e.type === "tool.execution.completed" || e.type === "ToolExecutionStarted" || e.type === "ToolExecutionCompleted" || e.type === "tool_call" || e.type === "tool_result" || e.payload?.tool_name
                            );
                            if (eventsQ.isLoading) {
                              return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-8 rounded-lg shimmer-bg" />)}</div>;
                            }
                            if (toolEvents.length === 0) {
                              return <p className="text-zinc-600">No tool logs for this session.</p>;
                            }
                            return (
                              <div className="space-y-1">
                                {toolEvents.slice(0, 20).map((ev: any, i: number) => (
                                  <div key={ev.id ?? i} className="flex gap-2 text-[11px] font-mono py-1 border-b border-white/[0.03] last:border-0">
                                    <span className="text-zinc-700 w-20 shrink-0 truncate">
                                      {ev.createdAt ? new Date(ev.createdAt).toLocaleTimeString() : `#${i + 1}`}
                                    </span>
                                    <span className="text-blue-400 shrink-0">{ev.type ?? "tool"}</span>
                                    <span className="text-zinc-500 truncate">
                                      {ev.payload?.tool_name ?? ev.payload?.name ?? ev.type ?? "—"}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            );
                          })()
                        )}
                      </TabErrorBoundary>

                      <TabErrorBoundary tab="recordings">
                        {selectedTab === "recordings" && <RecordingsSection />}
                      </TabErrorBoundary>
                      <TabErrorBoundary tab="timeline">
                        {selectedTab === "timeline" && <SessionTimeline sessionId={selectedId} />}
                      </TabErrorBoundary>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            </RevealSection>
          ),
        },
      ]}
    />
  );
}

function RecordingsSection() {
  const [recordings, setRecordings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get<{ recordings?: any[] }>("/api/sessions/recordings")
      .then((d) => setRecordings(d?.recordings || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 rounded-lg shimmer-bg" />)}</div>;
  if (recordings.length === 0) return <div className="text-center py-8 text-[12px] text-zinc-600">No session recordings yet</div>;

  return (
    <div className="space-y-1">
      {recordings.map((r: any) => (
        <div key={r.session_id} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.02] transition-colors">
          <div className="flex-1 min-w-0">
            <div className="text-[12px] text-zinc-300 font-mono truncate">{r.session_id}</div>
            <div className="text-[10px] text-zinc-600">
              {(r.size_bytes / 1024).toFixed(1)} KB · {r.created_at ? new Date(r.created_at * 1000).toLocaleString() : "—"}
            </div>
          </div>
          {r.session_id && (
            <a href={`${BASE_URL}/api/sessions/recordings/${r.session_id}/download`} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-zinc-600 hover:text-zinc-400 hover:bg-white/[0.04] transition-colors">
              <Download className="w-3 h-3" strokeWidth={1.5} />
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

export default function SessionsPage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] flex items-center justify-center bg-background"><div className="flex items-center gap-3 text-zinc-600"><Clock className="w-4 h-4 animate-spin" strokeWidth={1.5} /><span className="text-sm">Loading sessions...</span></div></div>}>
      <SessionsPageInner />
    </Suspense>
  );
}
