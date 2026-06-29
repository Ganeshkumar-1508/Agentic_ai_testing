"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/api-client";
import {
  FileText, Upload, Github, Gitlab as GitlabIcon, GitBranch,
  Check, ChevronRight, ChevronLeft, Play, Sparkles, ArrowRight,
  FileCode, ListChecks, FileUp, Eye, Zap, Loader2, AlertCircle,
  Plus, Search, Trash2, Link2,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface Requirement {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  source: string;
  created_at: string;
  updated_at: string;
}

interface CoverageInfo {
  test_count: number;
  passed_count: number;
  has_gap: boolean;
  gap_type: string;
}

// ── Step Definitions ──

interface StepDef { num: number; label: string; icon: typeof FileText; }

const STEPS: StepDef[] = [
  { num: 1, label: "Describe", icon: FileText },
  { num: 2, label: "Configure", icon: FileUp },
  { num: 3, label: "Review", icon: Eye },
  { num: 4, label: "Generate", icon: Zap },
];

const TEST_TYPE_LABELS: Record<string, string> = {
  api: "API Tests", ui: "UI/E2E Tests", unit: "Unit Tests",
  performance: "Performance", security: "Security",
};

type RepoProvider = 'github' | 'gitlab' | 'bitbucket';

const REPO_PROVIDERS = [
  { id: 'github' as RepoProvider, label: 'GitHub', icon: Github, placeholder: 'owner/repo or https://github.com/owner/repo', color: 'text-zinc-100' },
  { id: 'gitlab' as RepoProvider, label: 'GitLab', icon: GitlabIcon, placeholder: 'owner/repo or https://gitlab.com/owner/repo', color: 'text-zinc-400' },
  { id: 'bitbucket' as RepoProvider, label: 'Bitbucket', icon: GitBranch, placeholder: 'owner/repo or https://bitbucket.org/owner/repo', color: 'text-blue-400' },
];

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-zinc-800 text-zinc-500",
  active: "bg-emerald-400/10 text-emerald-400",
  completed: "bg-blue-400/10 text-blue-400",
  deprecated: "bg-red-400/10 text-red-400",
};

const PRIORITY_BADGE: Record<string, string> = {
  high: "bg-red-400/10 text-red-400",
  medium: "bg-amber-400/10 text-amber-400",
  low: "bg-emerald-400/10 text-emerald-400",
};

export default function RequirementsPage() {
  const router = useRouter();
  const [reqs, setReqs] = useState<Requirement[]>([]);
  const [coverage, setCoverage] = useState<Record<string, CoverageInfo>>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sidebarView, setSidebarView] = useState<"list" | "detail">("list");
  const [editingReq, setEditingReq] = useState<Requirement | null>(null);
  const [editForm, setEditForm] = useState({ title: "", description: "", priority: "medium" });
  const [showNewForm, setShowNewForm] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "matrix">("list");
  const [matrixData, setMatrixData] = useState<any[]>([]);
  const [showGenerate, setShowGenerate] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [linkInput, setLinkInput] = useState("");

  // Session state for pipeline flow
  const [currentStep, setCurrentStep] = useState(1);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [repoUrl, setRepoUrl] = useState<string>("");
  const [repoProvider, setRepoProvider] = useState<RepoProvider>("github");
  const [selectedTestTypes, setSelectedTestTypes] = useState<string[]>(["api"]);
  const [language, setLanguage] = useState<string>("");
  const [framework, setFramework] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchReqs = useCallback(async () => {
    try {
      const [reqsRes, gapsRes] = await Promise.all([
        api.get("/api/traceability/requirements"),
        api.get("/api/traceability/coverage-gaps"),
      ]);
      setReqs((reqsRes as any)?.requirements ?? []);
      const gapMap: Record<string, CoverageInfo> = {};
      for (const g of ((gapsRes as any)?.gaps ?? [])) {
        gapMap[g.requirement_id] = g;
      }
      setCoverage(gapMap);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchReqs(); }, [fetchReqs]);

  const createReq = async () => {
    if (!editForm.title.trim()) return;
    try {
      await api.post("/api/traceability/requirements", { title: editForm.title.trim(), description: editForm.description, priority: editForm.priority });
      setEditForm({ title: "", description: "", priority: "medium" });
      setShowNewForm(false);
      await fetchReqs();
    } catch { /* ignore */ }
  };

  const deleteReq = async (id: string) => {
    try {
      await api.post("/api/traceability/requirements/delete", { id });
      await fetchReqs();
    } catch { /* ignore */ }
  };

  const fetchMatrix = useCallback(async () => {
    try {
      const res = await api.get("/api/traceability/matrix");
      setMatrixData((res as any)?.matrix ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (viewMode === "matrix") fetchMatrix(); }, [viewMode, fetchMatrix]);

  const handleGenerate = async (reqId: string, reqTitle: string) => {
    setGenerating(true);
    try {
      await api.post("/api/traceability/generate", { requirement_id: reqId, title: reqTitle });
      setShowGenerate(false);
    } catch { /* ignore */ }
    setGenerating(false);
  };

  const handleLink = async (reqId: string, testCaseId: string) => {
    try {
      await api.post("/api/traceability/link", { requirement_id: reqId, test_case_id: testCaseId });
      setLinkInput("");
      await fetchReqs();
    } catch { /* ignore */ }
  };

  const filtered = search.trim()
    ? reqs.filter((r) => r.title.toLowerCase().includes(search.toLowerCase()))
    : reqs;

  const kpiStats = [
    { label: "Total", value: reqs.length, sub: `${reqs.filter(r => r.status === "active").length} active, ${reqs.filter(r => r.status === "draft").length} draft`, color: "text-zinc-100" },
    { label: "Coverage", value: `${reqs.length > 0 ? Math.round((reqs.filter(r => coverage[r.id]?.test_count > 0).length / reqs.length) * 100) : 0}%`, sub: `${reqs.filter(r => coverage[r.id]?.test_count > 0).length} of ${reqs.length} covered by tests`, color: "text-emerald-400" },
    { label: "Coverage Gaps", value: reqs.filter(r => coverage[r.id]?.has_gap || coverage[r.id]?.test_count === 0).length, sub: `${reqs.filter(r => coverage[r.id]?.test_count === 0).length} no tests`, color: "text-amber-400" },
    { label: "High Risk", value: reqs.filter(r => r.priority === "high" || r.priority === "critical").length, sub: "critical + high priority", color: "text-red-400" },
    { label: "Linked Tests", value: reqs.reduce((s, r) => s + (coverage[r.id]?.test_count ?? 0), 0), sub: `${reqs.length > 0 ? (reqs.reduce((s, r) => s + (coverage[r.id]?.test_count ?? 0), 0) / reqs.length).toFixed(1) : 0} avg tests per requirement`, color: "text-blue-400" },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Requirements" route="/requirements" label={`${reqs.length} total`}
        description="Manage requirements, link test cases, and run test generation pipelines"
        actions={
          <div className="flex items-center gap-2">
            <button onClick={() => setViewMode(viewMode === "list" ? "matrix" : "list")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${viewMode === "matrix" ? "bg-emerald-500/15 text-emerald-400" : "bg-white/[0.04] text-zinc-500 hover:text-zinc-300"}`}>
              <ListChecks className="w-3 h-3" strokeWidth={1.5} />
              {viewMode === "matrix" ? "List" : "Matrix"}
            </button>
          </div>
        }
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {kpiStats.map((kpi, i) => (
          <div key={i} className="rounded-[2rem] p-4 card-glow">
            <div className="text-[10px] font-medium text-zinc-600 uppercase tracking-wider mb-1">{kpi.label}</div>
            <div className={`text-2xl font-semibold font-mono tracking-tight ${kpi.color}`}>{kpi.value}</div>
            <div className="text-[10px] text-zinc-600 mt-1">{kpi.sub}</div>
          </div>
        ))}
      </div>

      {viewMode === "matrix" ? (
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.05] text-zinc-500">
                  <th className="text-left py-2.5 px-4 font-medium">Requirement</th>
                  <th className="text-left py-2.5 px-3 font-medium">Priority</th>
                  <th className="text-right py-2.5 px-3 font-medium">Tests</th>
                  <th className="text-right py-2.5 px-3 font-medium">Passed</th>
                  <th className="text-center py-2.5 px-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {matrixData.length === 0 ? (
                  <tr><td colSpan={5} className="text-center py-8 text-zinc-700">No traceability data available</td></tr>
                ) : matrixData.map((row: any) => (
                  <tr key={row.requirement_id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="py-2.5 px-4 text-zinc-300 font-medium">{row.title}</td>
                    <td className="py-2.5 px-3">
                      <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${PRIORITY_BADGE[row.priority] || "text-zinc-600"}`}>{row.priority}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-zinc-400 font-mono">{row.test_count}</td>
                    <td className="py-2.5 px-3 text-right font-mono">
                      <span className={row.passed_count === row.test_count && row.test_count > 0 ? "text-emerald-400" : "text-amber-400"}>
                        {row.passed_count}/{row.test_count}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {row.test_count === 0 ? (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-400/10 text-red-400 font-mono">No tests</span>
                      ) : row.passed_count < row.test_count ? (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-400/10 text-amber-400 font-mono">Gap</span>
                      ) : (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-400/10 text-emerald-400 font-mono">Covered</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
      <div className="flex gap-6">
        {/* Left: Requirements List */}
        <div className="w-72 shrink-0 space-y-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-600" strokeWidth={1.5} />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..."
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg pl-7 pr-2.5 py-1.5 text-xs text-zinc-300 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
            </div>
            <button onClick={() => { setShowNewForm(!showNewForm); setEditingReq(null); }}
              className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors active:scale-[0.95]">
              <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
            </button>
          </div>

          <div className="space-y-1 max-h-[600px] overflow-y-auto">
            <AnimatePresence>
              {showNewForm && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                  <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-3 space-y-2">
                    <input value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                      placeholder="Requirement title..." autoFocus
                      className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40" />
                    <textarea value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      placeholder="Description..." rows={2}
                      className="w-full bg-white/[0.05] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-emerald-500/40 resize-none" />
                    <div className="flex gap-2">
                      <select value={editForm.priority} onChange={(e) => setEditForm({ ...editForm, priority: e.target.value })}
                        className="flex-1 bg-white/[0.05] border border-white/[0.08] rounded-lg px-2 py-1 text-[10px] text-zinc-300 outline-none">
                        <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
                      </select>
                      <button onClick={createReq} disabled={!editForm.title.trim()}
                        className="px-3 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors text-[11px] disabled:opacity-40">Add</button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {loading ? (
              <div className="text-center py-8 text-xs text-zinc-600">Loading...</div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-8 text-xs text-zinc-700">
                <FileText className="w-5 h-5 mx-auto mb-2 text-zinc-800" strokeWidth={1} />
                {search ? "No matches" : "No requirements yet"}
              </div>
            ) : (
              filtered.map((req) => {
                const cov = coverage[req.id];
                return (
                  <motion.div key={req.id} layout
                    className="group flex items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-white/[0.03] transition-colors cursor-pointer border border-transparent hover:border-white/[0.06]"
                    onClick={() => { setEditingReq(req); setSidebarView("detail"); }}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-medium text-zinc-200 truncate">{req.title}</span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${PRIORITY_BADGE[req.priority] || "text-zinc-600"}`}>{req.priority}</span>
                        {cov && (
                          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${cov.has_gap ? "bg-amber-400/10 text-amber-400" : "bg-emerald-400/10 text-emerald-400"}`}>
                            {cov.has_gap ? `${cov.passed_count}/${cov.test_count}` : `${cov.test_count} tests`}
                          </span>
                        )}
                      </div>
                    </div>
                    <button onClick={(e) => { e.stopPropagation(); deleteReq(req.id); }}
                      className="p-1 rounded text-zinc-700 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100">
                      <Trash2 className="w-3 h-3" strokeWidth={1.5} />
                    </button>
                  </motion.div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Detail / Pipeline */}
        <div className="flex-1 min-w-0">
          {editingReq && (
            <div className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <input value={editingReq.title}
                  onChange={(e) => setEditingReq({ ...editingReq, title: e.target.value })}
                  className="text-lg font-semibold text-zinc-100 bg-transparent border-b border-transparent hover:border-zinc-700 focus:border-emerald-500/40 outline-none transition-colors flex-1" />
                <div className="flex items-center gap-2">
                  <select value={editingReq.status}
                    onChange={(e) => setEditingReq({ ...editingReq, status: e.target.value })}
                    className="bg-white/[0.05] border border-white/[0.08] rounded-lg px-2 py-1 text-[10px] text-zinc-300 outline-none">
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                    <option value="completed">Completed</option>
                    <option value="deprecated">Deprecated</option>
                  </select>
                  <Button size="sm" variant="outline" onClick={async () => {
                    await api.post("/api/traceability/requirements", { id: editingReq.id, title: editingReq.title, status: editingReq.status });
                    setEditingReq(null);
                    setSidebarView("list");
                    await fetchReqs();
                  }}>Save</Button>
                </div>
              </div>
              {editingReq.description && (
                <p className="text-sm text-zinc-500">{editingReq.description}</p>
              )}

              {/* Coverage Info */}
              {coverage[editingReq.id] && (
                <div className="flex gap-4 text-xs">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400" /> {coverage[editingReq.id].passed_count} passing</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-zinc-700" /> {coverage[editingReq.id].test_count} total tests</span>
                  {coverage[editingReq.id].has_gap && (
                    <span className="text-amber-400">Coverage gap detected</span>
                  )}
                </div>
              )}

              <div className="flex items-center gap-2 pt-2">
                <Button size="sm" onClick={() => setShowGenerate(true)} className="text-xs">
                  <Zap className="w-3 h-3 mr-1" strokeWidth={1.5} /> Generate Tests
                </Button>
                <div className="flex items-center gap-1 flex-1">
                  <Input
                    value={linkInput}
                    onChange={(e) => setLinkInput(e.target.value)}
                    placeholder="Link test case ID..."
                    className="h-7 text-[10px]"
                  />
                  <Button size="sm" variant="outline" onClick={() => handleLink(editingReq.id, linkInput)} disabled={!linkInput.trim()} className="text-xs">
                    <Link2 className="w-3 h-3" strokeWidth={1.5} /> Link
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Pipeline Launcher (original workflow) */}
          <div className="mt-4 bg-white/[0.02] border border-white/[0.06] rounded-2xl p-5 space-y-4">
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Run Test Pipeline</h3>
            <p className="text-xs text-zinc-600">Choose a requirement above or enter requirements directly to generate and execute tests.</p>
            <Textarea placeholder="Describe what you want to test..." className="min-h-[80px]" />
            <div className="flex items-center gap-3">
              <Button><Play className="w-3.5 h-3.5 mr-1.5" strokeWidth={1.5} /> Run Pipeline</Button>
              <Button variant="outline"><Upload className="w-3.5 h-3.5 mr-1.5" strokeWidth={1.5} /> Upload Files</Button>
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Generate Tests Modal */}
      {showGenerate && editingReq && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/60"
          onClick={() => setShowGenerate(false)}>
          <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 w-[420px] space-y-4"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-zinc-100">Generate Tests</h3>
            <p className="text-xs text-zinc-500">Generate tests for: <span className="text-zinc-300">{editingReq.title}</span></p>
            <div className="flex gap-2">
              <Button onClick={() => handleGenerate(editingReq.id, editingReq.title)} disabled={generating} className="flex-1">
                {generating ? <Loader2 className="w-3 h-3 animate-spin" strokeWidth={1.5} /> : <Zap className="w-3 h-3" strokeWidth={1.5} />}
                {generating ? "Generating..." : "Generate Tests"}
              </Button>
              <Button variant="outline" onClick={() => setShowGenerate(false)}>Cancel</Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}
