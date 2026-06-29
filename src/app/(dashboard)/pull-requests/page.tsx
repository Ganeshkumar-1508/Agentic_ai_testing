"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import { GitPullRequest, RefreshCw, Plus, X, Play, ArrowRight, CheckCircle2, AlertTriangle, Clock, Shield } from "lucide-react";
import { toast } from "sonner";

interface PR {
  id: string;
  repo_url: string | null;
  repo_provider: string;
  pr_number: number;
  title: string | null;
  description: string | null;
  author: string | null;
  status: string;
  priority: number;
  labels: string | null;
  last_test_status: string | null;
  last_test_run_at: string | null;
  risk_score: number;
  source_branch: string | null;
  target_branch: string | null;
  created_at: string;
  updated_at: string;
}

const STATUS_TONE: Record<string, { label: string; dotClass: string; textClass: string }> = {
  open: { label: "Open", dotClass: "bg-emerald-400", textClass: "text-emerald-300" },
  merged: { label: "Merged", dotClass: "bg-zinc-400", textClass: "text-zinc-300" },
  closed: { label: "Closed", dotClass: "bg-zinc-500", textClass: "text-zinc-400" },
  draft: { label: "Draft", dotClass: "bg-amber-400", textClass: "text-amber-300" },
};

const RISK_LABELS: Record<string, { label: string; className: string }> = {
  low: { label: "Low", className: "text-emerald-300" },
  med: { label: "Med", className: "text-amber-300" },
  high: { label: "High", className: "text-rose-300" },
};

function riskBucket(score: number): "low" | "med" | "high" {
  if (score >= 70) return "high";
  if (score >= 40) return "med";
  return "low";
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "now";
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`;
  return `${Math.floor(ms / 86_400_000)}d`;
}

const SPRING = { type: "spring" as const, stiffness: 100, damping: 20 };
const CUBIC = [0.16, 1, 0.3, 1] as const;

function PulsingDot({ className }: { className: string }) {
  return (
    <span className="relative inline-flex h-1.5 w-1.5">
      <motion.span
        animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        className={cn("absolute inline-flex h-full w-full rounded-full opacity-60", className)}
      />
      <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", className)} />
    </span>
  );
}

export default function PullRequestsPage() {
  const queryClient = useQueryClient();
  const [repoFilter, setRepoFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [syncFormOpen, setSyncFormOpen] = useState(false);
  const [syncForm, setSyncForm] = useState({ repo_url: "", token: "" });

  const { data: prsResp, isLoading } = useQuery<{ prs: PR[] }>({
    queryKey: ["prs"],
    queryFn: () => api.get("/api/prs"),
    refetchInterval: 30_000,
  });

  const syncMut = useMutation({
    mutationFn: async (body: { repo_url: string; token: string }) => {
      return api.post<{ count?: number; error?: string }>("/api/prs/sync", {
        repo_url: body.repo_url,
        token: body.token,
        provider: "github",
      });
    },
    onSuccess: (data) => { toast.success(`Synced ${data?.count ?? "?"} PRs`); setSyncFormOpen(false); setSyncForm({ repo_url: "", token: "" }); queryClient.invalidateQueries({ queryKey: ["prs"] }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const runMut = useMutation({
    mutationFn: async (prId: string) => {
      return api.post<{ run_id?: string; error?: string }>(`/api/prs/${prId}/run`, {});
    },
    onSuccess: (data) => { toast.success(`Pipeline started: ${data?.run_id?.slice(0, 8) ?? "?"}`); queryClient.invalidateQueries({ queryKey: ["prs"] }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const autoFixMut = useMutation({
    mutationFn: async (prId: string) => {
      return api.post<{ error?: string }>(`/api/prs/${prId}/auto-fix`, {});
    },
    onSuccess: () => { toast.success("Auto-fix started"); queryClient.invalidateQueries({ queryKey: ["prs"] }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const prs = prsResp?.prs ?? [];

  const repos = useMemo(() => {
    const set = new Set<string>();
    prs.forEach((p) => { if (p.repo_url) set.add(p.repo_url); });
    return Array.from(set).sort();
  }, [prs]);

  const filtered = useMemo(() => {
    return prs.filter((p) => {
      if (repoFilter !== "all" && p.repo_url !== repoFilter) return false;
      if (statusFilter !== "all" && p.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!(p.title ?? "").toLowerCase().includes(q) && !String(p.pr_number).includes(q)) return false;
      }
      return true;
    });
  }, [prs, repoFilter, statusFilter, search]);

  const selected = prs.find((p) => p.id === selectedId) ?? null;

  const stats = useMemo(() => ({
    total: prs.length,
    open: prs.filter((p) => p.status === "open").length,
    highRisk: prs.filter((p) => p.risk_score >= 70).length,
    needsTest: prs.filter((p) => p.status === "open" && !p.last_test_status).length,
  }), [prs]);

  return (
    <div className="max-w-7xl mx-auto px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.18em] mb-2">Infrastructure / Pull Requests</div>
          <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100 leading-none">Synced PRs</h1>
          <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Pull requests pulled from connected GitHub repos. Click a row to see test history, run on demand, or trigger auto-fix.</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <motion.button whileTap={{ scale: 0.97 }} onClick={() => queryClient.invalidateQueries({ queryKey: ["prs"] })}
            className="flex items-center gap-1.5 h-9 px-3.5 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05] text-zinc-300 text-xs font-medium transition-colors">
            <RefreshCw className="w-3.5 h-3.5" strokeWidth={1.5} /> Refresh
          </motion.button>
          <motion.button whileTap={{ scale: 0.97 }} onClick={() => setSyncFormOpen(!syncFormOpen)}
            className="flex items-center gap-1.5 h-9 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-zinc-950 text-xs font-semibold transition-colors">
            <Plus className="w-3.5 h-3.5" strokeWidth={2} /> Sync from GitHub
          </motion.button>
        </div>
      </div>

      {/* Stats — divide-y strip, not boxed cards (skill rule 4: anti-card-overuse) */}
      <div className="flex items-stretch border-y border-white/[0.06] divide-x divide-white/[0.06]">
        {[
          { label: "Total", value: stats.total, accent: false },
          { label: "Open", value: stats.open, accent: true },
          { label: "High Risk", value: stats.highRisk, accent: false, tone: "high" },
          { label: "Needs Test", value: stats.needsTest, accent: false, tone: "warn" },
        ].map((s) => (
          <div key={s.label} className="flex-1 px-6 py-5 flex items-baseline gap-3">
            <span className="text-[10px] font-mono text-zinc-600 uppercase tracking-[0.14em]">{s.label}</span>
            <motion.span key={s.value} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}
              className={cn("text-2xl font-mono tabular-nums tracking-tight",
                s.tone === "high" && s.value > 0 ? "text-rose-300" :
                s.tone === "warn" && s.value > 0 ? "text-amber-300" :
                s.accent ? "text-emerald-300" : "text-zinc-100")}>
              {s.value}
            </motion.span>
          </div>
        ))}
      </div>

      {/* Sync form */}
      <AnimatePresence>
        {syncFormOpen && (
          <motion.section initial={{ opacity: 0, y: -8, height: 0 }} animate={{ opacity: 1, y: 0, height: "auto" }} exit={{ opacity: 0, y: -8, height: 0 }} transition={SPRING}
            className="overflow-hidden">
            <div className="bg-white/[0.015] border border-white/[0.06] rounded-3xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-sm font-medium text-zinc-200">Sync PRs from GitHub</h2>
                  <p className="text-[11px] text-zinc-600 mt-0.5">Pulls open PRs from the repo and indexes them in the tracker.</p>
                </div>
                <button onClick={() => setSyncFormOpen(false)} className="text-zinc-600 hover:text-zinc-300 transition-colors">
                  <X className="w-3.5 h-3.5" strokeWidth={1.5} />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-[1fr_280px_auto] gap-3">
                <input value={syncForm.repo_url} onChange={(e) => setSyncForm({ ...syncForm, repo_url: e.target.value })}
                  placeholder="https://github.com/owner/repo"
                  className="h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors font-mono" />
                <input value={syncForm.token} onChange={(e) => setSyncForm({ ...syncForm, token: e.target.value })}
                  type="password" placeholder="GitHub PAT (private repos)"
                  className="h-10 rounded-xl bg-white/[0.03] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 transition-colors font-mono" />
                <motion.button whileTap={{ scale: 0.97 }} onClick={() => syncMut.mutate(syncForm)} disabled={!syncForm.repo_url.trim() || syncMut.isPending}
                  className="h-10 px-5 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-950 text-xs font-semibold transition-colors flex items-center justify-center gap-1.5">
                  {syncMut.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" strokeWidth={2} /> : <RefreshCw className="w-3.5 h-3.5" strokeWidth={2} />}
                  {syncMut.isPending ? "Syncing" : "Sync"}
                </motion.button>
              </div>
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {/* Filters — slim strip, not boxed */}
      <div className="flex items-center gap-3 flex-wrap">
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by title or PR number…"
          className="flex-1 min-w-[240px] h-9 rounded-xl bg-white/[0.02] border border-white/[0.06] px-3.5 text-[12px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-white/[0.12] transition-colors" />
        <select value={repoFilter} onChange={(e) => setRepoFilter(e.target.value)}
          className="h-9 px-3 rounded-xl bg-white/[0.02] border border-white/[0.06] text-[12px] text-zinc-400 outline-none focus:border-white/[0.12] transition-colors cursor-pointer">
          <option value="all">All repos · {repos.length}</option>
          {repos.map((r) => <option key={r} value={r}>{r.replace("https://github.com/", "")}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 px-3 rounded-xl bg-white/[0.02] border border-white/[0.06] text-[12px] text-zinc-400 outline-none focus:border-white/[0.12] transition-colors cursor-pointer">
          {["all", "open", "merged", "closed", "draft"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* PR list */}
      <section>
        {isLoading ? (
          <div className="space-y-px">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-16 border-b border-white/[0.04] flex items-center gap-4 px-4">
                <div className="h-3 w-48 rounded shimmer-bg" />
                <div className="h-3 w-24 rounded shimmer-bg ml-auto" />
                <div className="h-3 w-16 rounded shimmer-bg" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={SPRING}
            className="py-20 text-center">
            <motion.div animate={{ y: [0, -3, 0] }} transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
              className="w-12 h-12 mx-auto rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4">
              <GitPullRequest className="w-5 h-5 text-zinc-600" strokeWidth={1.2} />
            </motion.div>
            <h3 className="text-sm font-medium text-zinc-200">{prs.length === 0 ? "No PRs synced yet" : "No PRs match the filters"}</h3>
            <p className="text-xs text-zinc-600 mt-1.5 max-w-xs mx-auto">
              {prs.length === 0 ? "Connect a GitHub repo to see open pull requests indexed here." : "Try clearing the search or filters above."}
            </p>
            {prs.length === 0 && (
              <motion.button whileTap={{ scale: 0.97 }} onClick={() => setSyncFormOpen(true)}
                className="mt-5 h-9 px-4 rounded-xl bg-emerald-500/10 text-emerald-300 text-xs font-medium hover:bg-emerald-500/20 transition-colors inline-flex items-center gap-1.5">
                <Plus className="w-3.5 h-3.5" strokeWidth={1.5} /> Sync your first repo
              </motion.button>
            )}
          </motion.div>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {filtered.map((p, i) => {
              const tone = STATUS_TONE[p.status] ?? STATUS_TONE.open;
              const risk = riskBucket(p.risk_score ?? 0);
              const isHigh = risk === "high";
              return (
                <motion.div key={p.id} layout="position" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ ...SPRING, delay: Math.min(i * 0.02, 0.4) }}
                  onClick={() => setSelectedId(selectedId === p.id ? null : p.id)}
                  className={cn("group grid grid-cols-[1fr_140px_80px_72px_120px_auto] gap-4 items-center px-4 py-3.5 cursor-pointer transition-colors",
                    selectedId === p.id ? "bg-white/[0.03]" : "hover:bg-white/[0.02]",
                    isHigh && "relative")}>
                  {isHigh && <span className="absolute left-0 top-0 bottom-0 w-px bg-rose-500/50" />}
                  <div className="flex items-center gap-2.5 min-w-0">
                    {p.status === "open" ? <PulsingDot className={tone.dotClass} /> : <span className={cn("w-1.5 h-1.5 rounded-full", tone.dotClass)} />}
                    <div className="min-w-0">
                      <div className="text-[13px] text-zinc-100 truncate font-medium" title={p.title ?? ""}>{p.title ?? "(untitled)"}</div>
                      <div className="text-[10.5px] font-mono text-zinc-600 mt-0.5 flex items-center gap-1.5">
                        <span className="text-zinc-500">#{p.pr_number}</span>
                        {p.author && <><span className="text-zinc-700">·</span><span>{p.author}</span></>}
                        {p.source_branch && p.target_branch && (
                          <><span className="text-zinc-700">·</span><span className="text-zinc-500">{p.source_branch} → {p.target_branch}</span></>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="text-[10.5px] font-mono text-zinc-500 truncate" title={p.repo_url ?? ""}>{(p.repo_url ?? "").replace("https://github.com/", "")}</div>
                  <div className={cn("text-[10px] font-mono", tone.textClass)}>{tone.label}</div>
                  <div className={cn("text-[10px] font-mono tabular-nums", RISK_LABELS[risk].className)}>{Math.round(p.risk_score ?? 0)}</div>
                  <div className="text-[10px] font-mono text-zinc-500">{relativeTime(p.updated_at)} ago</div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                    <motion.button whileTap={{ scale: 0.95 }} onClick={() => runMut.mutate(p.id)} disabled={runMut.isPending}
                      className="h-7 px-2.5 rounded-lg bg-emerald-500/10 text-emerald-300 text-[10.5px] font-medium hover:bg-emerald-500/20 transition-colors disabled:opacity-40 flex items-center gap-1">
                      <Play className="w-2.5 h-2.5" strokeWidth={2} /> Run
                    </motion.button>
                    <motion.button whileTap={{ scale: 0.95 }} onClick={() => autoFixMut.mutate(p.id)} disabled={autoFixMut.isPending}
                      className="h-7 px-2.5 rounded-lg bg-white/[0.04] text-zinc-300 text-[10.5px] font-medium hover:bg-white/[0.08] transition-colors disabled:opacity-40 flex items-center gap-1">
                      <Shield className="w-2.5 h-2.5" strokeWidth={1.5} /> Fix
                    </motion.button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </section>

      {/* Detail drawer */}
      <AnimatePresence>
        {selected && (
          <motion.aside initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }} transition={SPRING}
            className="fixed right-6 bottom-6 w-[420px] bg-card border border-white/[0.08] rounded-3xl shadow-[0_24px_48px_-12px_rgba(0,0,0,0.6)] z-50 overflow-hidden">
            <div className="p-6 space-y-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[10px] font-mono text-zinc-600 mb-1">#{selected.pr_number} · {selected.status}</div>
                  <h2 className="text-[15px] font-medium text-zinc-100 leading-snug">{selected.title ?? "(untitled)"}</h2>
                </div>
                <button onClick={() => setSelectedId(null)} className="text-zinc-600 hover:text-zinc-300 transition-colors shrink-0">
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>
              {selected.description && <p className="text-[11.5px] text-zinc-400 leading-relaxed line-clamp-4">{selected.description}</p>}
              <div className="divide-y divide-white/[0.04] text-[11.5px]">
                <Row label="Author" value={selected.author ?? "—"} />
                <Row label="Risk" value={`${Math.round(selected.risk_score ?? 0)} · ${RISK_LABELS[riskBucket(selected.risk_score ?? 0)].label}`} />
                <Row label="Branch" value={selected.source_branch && selected.target_branch ? `${selected.source_branch} → ${selected.target_branch}` : "—"} mono />
                <Row label="Last test" value={selected.last_test_status ?? "never"} />
                <Row label="Updated" value={`${relativeTime(selected.updated_at)} ago`} />
              </div>
              <div className="flex gap-2">
                <motion.button whileTap={{ scale: 0.97 }} onClick={() => runMut.mutate(selected.id)} disabled={runMut.isPending}
                  className="flex-1 h-9 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-zinc-950 text-[12px] font-semibold transition-colors flex items-center justify-center gap-1.5">
                  <Play className="w-3 h-3" strokeWidth={2} /> Run tests
                </motion.button>
                <motion.button whileTap={{ scale: 0.97 }} onClick={() => autoFixMut.mutate(selected.id)} disabled={autoFixMut.isPending}
                  className="flex-1 h-9 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] disabled:opacity-40 text-zinc-200 text-[12px] font-semibold transition-colors flex items-center justify-center gap-1.5">
                  <Shield className="w-3 h-3" strokeWidth={1.5} /> Auto-fix
                </motion.button>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-zinc-600">{label}</span>
      <span className={cn("text-zinc-200", mono && "font-mono text-[10.5px]")}>{value}</span>
    </div>
  );
}
