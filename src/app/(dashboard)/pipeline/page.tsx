"use client";

import { useState, useEffect, useRef, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Play, Square, History, Settings2, Code2, Activity, FileText,
  CheckCircle2, XCircle, Zap, Shield, BarChart3, Bug, Globe, Layers,
} from "lucide-react";
import { KanbanBoardSection } from "@/components/pipeline/KanbanBoardSection";
import { SkillsPanel } from "@/components/pipeline/SkillsPanel";
import { EventStream } from "@/components/pipeline/EventStream";
import { usePipelineStore } from "@/stores/pipeline-store";
import { api } from "@/lib/api/api-client";

const MODES = ["auto", "ask", "custom"] as const;
const DEFAULT_QUICK_CHIPS = ["Generate tests for auth API", "Test payment flow edge cases", "E2E: user registration", "API: rate limiting tests"];
const TEST_TYPES = [
  { id: "unit", label: "Unit", icon: Code2 },
  { id: "integration", label: "Integration", icon: Layers },
  { id: "e2e", label: "E2E", icon: Globe },
  { id: "security", label: "Security", icon: Shield },
  { id: "performance", label: "Performance", icon: BarChart3 },
];

function PipelinePageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const startupRef = useRef(false);
  const {
    status: workflowStatus,
    sessionId: workflowId,
    testResults: liveTestResults,
    startWorkflow,
    connectToWorkflow,
    disconnect,
  } = usePipelineStore();
  const [requirements, setRequirements] = useState("");
  const [pipelineMode, setPipelineMode] = useState<"quick" | "orchestrate">("quick");
  const [repoUrl, setRepoUrl] = useState("");
  const [mode, setMode] = useState<string>("auto");
  const [selectedTestTypes, setSelectedTestTypes] = useState<string[]>(["e2e"]);
  const [showHistory, setShowHistory] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [historySessions, setHistorySessions] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [tokenUsage, setTokenUsage] = useState({ tokens: 0, cost: 0 });
  const [_boardId, _setBoardId] = useState<string | null>(null);

  const status = workflowStatus;
  const sessionId = workflowId;
  const testResults = liveTestResults ?? { total: 0, passed: 0, failed: 0, skipped: 0, duration: 0 };

  // Derive quick chips from recent pipeline goals
  const quickChips = (() => {
    const recentGoals = historySessions
      .filter((s: any) => s.goal && s.goal.length > 10)
      .map((s: any) => s.goal)
      .filter((g: string, i: number, a: string[]) => a.indexOf(g) === i)
      .slice(0, 3);
    return recentGoals.length >= 2 ? recentGoals : DEFAULT_QUICK_CHIPS;
  })();

  useEffect(() => {
    api.get<{ sessions?: any[] }>(`/api/pipeline-activity/recent?limit=20`)
      .then((d) => setHistorySessions(d.sessions || []))
      .catch(() => {});
    api.get<{ templates?: any[] }>(`/api/pipeline-templates`)
      .then((d) => setTemplates(d.templates || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (startupRef.current) return;
    startupRef.current = true;

    try {
      const seededRequirements = sessionStorage.getItem("pipeline_requirements");
      const autorun = sessionStorage.getItem("pipeline_autorun");
      const requestedSessionId = searchParams.get("session_id");

      if (seededRequirements?.trim()) {
        setRequirements(seededRequirements.trim());
      }

      if (requestedSessionId) {
        connectToWorkflow(requestedSessionId);
        return;
      }

      if (seededRequirements?.trim() && autorun === "1") {
        sessionStorage.removeItem("pipeline_autorun");
        void startWorkflow(seededRequirements.trim())
          .then(() => toast.success("Pipeline started"))
          .catch(() => toast.error("Failed to start pipeline"));
      }
    } catch {
      // Ignore storage hydration errors
    }
  }, [connectToWorkflow, searchParams, startWorkflow]);

  const startPipeline = useCallback(async () => {
    if (!requirements.trim()) return;
    try {
      sessionStorage.setItem("pipeline_requirements", requirements.trim());
      _setBoardId(null);
      setTokenUsage({ tokens: 0, cost: 0 });

      if (pipelineMode === "orchestrate" && repoUrl.trim()) {
        const fullUrl = repoUrl.trim().startsWith("http") ? repoUrl.trim() : `https://github.com/${repoUrl.trim()}`;
        // C08 Q7 step 2: route through the canonical `POST /api/jobs`
        // surface (same as the store's quick-test path). The previous
        // `POST /api/delegate` endpoint was hard-deleted.
        const { toJobSpecFromPipelineQuickTest } = await import("@/lib/adapters/job-spec");
        const spec = toJobSpecFromPipelineQuickTest({
          requirements: requirements.trim(),
          repo_url: fullUrl,
          mode: "auto",
          test_types: selectedTestTypes,
        });
        // Tier 2 = supervised: orchestrator does the work, kanban review
        // posts the diff. Tier 1 (autonomous) would auto-merge.
        spec.tier = 2;
        const data = await api.post<{ spec_id?: string; session_id?: string }>(`/api/jobs`, spec);
        const sessionId = data?.spec_id || data?.session_id;
        if (!sessionId) throw new Error("Backend did not return a session id");
        connectToWorkflow(sessionId);
      } else {
        await startWorkflow(requirements.trim());
      }
      toast.success(pipelineMode === "orchestrate" ? "Orchestration started" : "Pipeline started");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to start pipeline");
    }
  }, [requirements, repoUrl, pipelineMode, startWorkflow, connectToWorkflow]);

  const stopPipeline = useCallback(async () => {
    if (sessionId) await api.post(`/api/delegate/${sessionId}/cancel`, {}).catch(() => {});
    disconnect();
  }, [disconnect, sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setTokenUsage({ tokens: 0, cost: 0 });
      return;
    }

    const syncCost = () => {
      api.get<{ models?: Array<{ input_tokens?: number; output_tokens?: number; cache_read_tokens?: number }>; total_cost?: number }>(`/api/cost/session/${sessionId}`)
        .then((d) => {
          const tokens = (d.models || []).reduce((sum, model) => {
            return sum + Number(model.input_tokens || 0) + Number(model.output_tokens || 0) + Number(model.cache_read_tokens || 0);
          }, 0);
          setTokenUsage({
            tokens,
            cost: Number(d.total_cost || 0),
          });
        })
        .catch(() => {});
    };

    syncCost();
    const interval = setInterval(syncCost, 5000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const loadSession = useCallback((sid: string) => {
    setShowHistory(false);
    router.push(`/pipeline?session_id=${sid}`);
  }, [router]);

  useEffect(() => {
    if (!sessionId) return;
    const discoverBoard = () => {
      api.get<{ boards?: Array<{ id: string; name?: string; config?: { source?: string } }> }>(`/api/kanban/boards`)
        .then((d) => {
          const boards = d.boards || [];
          const match = boards.find((b) =>
            b.name?.toLowerCase().includes(sessionId.slice(0, 8)) ||
            b.config?.source === "orchestrator"
          );
          if (match) _setBoardId(match.id);
        })
        .catch(() => {});
    };
    discoverBoard();
    const interval = setInterval(discoverBoard, 8000);
    return () => clearInterval(interval);
  }, [sessionId]);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">

      {/* === 1. PAGE HEADER + KPIs === */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-medium tracking-tighter text-zinc-100 leading-none">Pipeline</h1>
          <p className="text-sm text-zinc-500 mt-2 max-w-[540px] leading-relaxed">Generate and execute tests using AI agents</p>
        </div>
        <div className="flex items-center gap-2.5">
          <button onClick={() => setShowHistory(!showHistory)}
            className={`flex items-center gap-2 px-4 py-2 rounded-[0.75rem] text-[13px] font-medium border transition-all ${
              showHistory ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-white/[0.03] text-zinc-400 border-white/[0.06] hover:bg-white/[0.05]"
            }`}>
            <History className="w-4 h-4" strokeWidth={1.5} /> History
          </button>
          <button onClick={() => setShowConfig(!showConfig)}
            className="flex items-center gap-2 px-4 py-2 rounded-[0.75rem] text-[13px] font-medium border border-white/[0.06] bg-white/[0.03] text-zinc-400 hover:bg-white/[0.05] transition-all">
            <Settings2 className="w-4 h-4" strokeWidth={1.5} /> Config
          </button>
          <button onClick={status === "running" ? stopPipeline : startPipeline}
            disabled={status === "running" ? false : !requirements.trim()}
            className="flex items-center gap-2 px-5 py-2 rounded-[0.75rem] text-[13px] font-semibold bg-emerald-500 text-zinc-950 hover:bg-emerald-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-[0.98]">
            {status === "running" ? <><Square className="w-4 h-4" strokeWidth={2} /> Stop</> : <><Play className="w-4 h-4" strokeWidth={2} /> Run</>}
          </button>
        </div>
      </div>

      {/* KPI Row — pure data, no cards */}
      <div className="border-t border-white/[0.06]">
        <div className="grid grid-cols-1 md:grid-cols-4 divide-x divide-white/[0.06]">
          {[
            { label: "Tests", value: testResults.total, sub: `${testResults.passed} passed / ${testResults.failed} failed` },
            { label: "Tokens Used", value: tokenUsage.tokens.toLocaleString(), sub: `~$${tokenUsage.cost.toFixed(4)}` },
            { label: "Status", value: status === "running" ? "Running" : status === "completed" ? "Completed" : "Idle", sub: status === "running" ? "Agent active" : "Ready" },
            { label: "Pipeline", value: pipelineMode === "orchestrate" ? "Orchestrate" : "Quick Test", sub: pipelineMode === "orchestrate" ? "Repo-driven" : "Standard" },
          ].map((kpi, i) => (
            <div key={i} className="py-5 px-6 first:pl-0 last:pr-0">
              <div className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5">{kpi.label}</div>
              <div className="text-[28px] font-semibold font-mono text-zinc-100 tabular-nums flex items-center gap-2 leading-none">
                {kpi.value}
                {kpi.label === "Status" && status === "running" && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
              </div>
              <div className="text-[11px] text-zinc-600 font-mono mt-2">{kpi.sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* === 2. PIPELINE MODE TOGGLE === */}
      <div className="flex items-center gap-3">
        <div className="flex bg-card border border-white/[0.06] rounded-full p-0.5 gap-0.5">
          <button onClick={() => setPipelineMode("quick")}
            className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-all flex items-center gap-1.5 ${
              pipelineMode === "quick" ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-400 hover:text-zinc-300"
            }`}>
            <Zap className="w-3.5 h-3.5" strokeWidth={1.5} />
            Quick Test
          </button>
          <button onClick={() => setPipelineMode("orchestrate")}
            className={`px-4 py-1.5 rounded-full text-[12px] font-medium transition-all flex items-center gap-1.5 ${
              pipelineMode === "orchestrate" ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-400 hover:text-zinc-300"
            }`}>
            <Layers className="w-3.5 h-3.5" strokeWidth={1.5} />
            Orchestrate
          </button>
        </div>
        <span className="text-[11px] text-zinc-600">
          {pipelineMode === "quick" ? "Generate and run tests from a description" : "Analyze a repo, triage issues, and auto-fix"}
        </span>
      </div>

      {/* === 3. REPO URL INPUT (orchestrate mode) === */}
      {pipelineMode === "orchestrate" && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
          <div>
            <label className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5 block">Repository URL</label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-600" strokeWidth={1.5} />
                <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo or owner/repo"
                  className="w-full pl-10 pr-3 py-2.5 text-[13px] bg-card border border-white/[0.06] rounded-xl text-zinc-300 placeholder:text-zinc-700 focus:outline-none focus:border-emerald-500/30 font-mono" />
              </div>
            </div>
            <p className="text-[10px] text-zinc-700 mt-1.5">Supports GitHub, GitLab, and Bitbucket repositories</p>
          </div>
        </motion.div>
      )}

      {/* === 4. REQUIREMENTS INPUT === */}
      <div>
        <label className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-1.5 block">Requirements</label>
        <textarea value={requirements} onChange={e => setRequirements(e.target.value)}
          placeholder={pipelineMode === "quick" ? "Describe what you want to test, e.g. 'Generate tests for user authentication API including login, registration, password reset, and edge cases'" : "Describe what to focus on, e.g. 'Fix all open bugs and add tests for the auth module'"}
          className="w-full min-h-[100px] bg-card border border-white/[0.06] rounded-xl p-5 text-[14px] text-zinc-100 placeholder:text-zinc-600 resize-y focus:outline-none focus:border-emerald-500/30 focus:ring-2 focus:ring-emerald-500/10 transition-all leading-relaxed" />
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-2 flex-wrap">
            {pipelineMode === "quick" ? (quickChips).map((chip, i) => (
              <button key={i} onClick={() => setRequirements(chip)}
                className="px-3 py-1.5 rounded-full text-[11px] font-medium border border-white/[0.06] text-zinc-400 hover:text-emerald-400 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-all">
                {chip}
              </button>
            )) : (
              <button onClick={() => setRequirements("Fix all open issues and add tests for the main functionality")}
                className="px-3 py-1.5 rounded-full text-[11px] font-medium border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/10 transition-all">
                Fix open issues
              </button>
            )}
          </div>
          <span className="text-[11px] text-zinc-600 font-mono flex items-center gap-1.5">
            <kbd className="px-1.5 py-0.5 rounded border border-white/[0.06] bg-white/[0.03] text-[10px]">Ctrl</kbd>
            <span>+</span>
            <kbd className="px-1.5 py-0.5 rounded border border-white/[0.06] bg-white/[0.03] text-[10px]">Enter</kbd>
            <span>to run</span>
          </span>
        </div>
      </div>

      {/* === 4b. TEST TYPE CHIPS === */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[11px] text-zinc-600">Test types:</span>
        {TEST_TYPES.map((tt) => {
          const Icon = tt.icon;
          const active = selectedTestTypes.includes(tt.id);
          return (
            <button key={tt.id}
              onClick={() => setSelectedTestTypes(prev => active ? prev.filter(t => t !== tt.id) : [...prev, tt.id])}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium border transition-all ${
                active ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "border-white/[0.06] text-zinc-400 hover:text-zinc-300 hover:border-white/[0.12]"
              }`}>
                <Icon className="w-3 h-3" strokeWidth={1.5} />
                {tt.label}
            </button>
          );
        })}
        <span className="text-[11px] text-zinc-600 font-mono flex items-center gap-1.5 ml-auto">
          <kbd className="px-1.5 py-0.5 rounded border border-white/[0.06] bg-white/[0.03] text-[10px]">Ctrl</kbd>
          <span>+</span>
          <kbd className="px-1.5 py-0.5 rounded border border-white/[0.06] bg-white/[0.03] text-[10px]">Enter</kbd>
          <span>to run</span>
        </span>
      </div>

      {/* === 4c. FILE UPLOAD AREA === */}
      <div className="border border-dashed border-white/[0.06] rounded-xl p-4 flex items-center justify-center gap-3 text-[12px] text-zinc-500 hover:border-emerald-500/20 hover:bg-emerald-500/5 transition-all cursor-pointer">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Drop source files here or <span className="text-emerald-400 font-medium">browse</span> to upload for context-aware test generation
      </div>

      {/* === 3. MODE SELECTOR BAR === */}
      <div className="flex items-center gap-5">
        <div className="flex bg-card border border-white/[0.06] rounded-full p-1 gap-0.5">
          {MODES.map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-all flex items-center gap-1.5 ${
                mode === m ? "bg-emerald-500 text-zinc-950 font-semibold" : "text-zinc-400 hover:text-zinc-300"
              }`}>
              {m === mode && <span className="w-1.5 h-1.5 rounded-full bg-zinc-950" />}
              {m === "auto" ? "Auto" : m === "ask" ? "Ask" : "Custom"}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-zinc-600 font-mono">
          {mode === "auto" ? "Full autonomy — orchestrator selects agents" :
           mode === "ask" ? "Read-only — research and questions" :
           "Manual tool permissions"}
        </span>
        <div className="flex items-center gap-2 ml-auto">
          <button onClick={() => setShowConfig(!showConfig)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium border transition-all ${
              showConfig ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "border-white/[0.06] text-zinc-500 hover:text-zinc-300 hover:border-white/[0.12]"
            }`}>
            <Settings2 className="w-3 h-3" strokeWidth={1.5} /> Advanced Config
          </button>
          <button onClick={status === "running" ? stopPipeline : startPipeline}
            disabled={status === "running" ? false : !requirements.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-emerald-500 text-zinc-950 hover:bg-emerald-400 disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-[0.98]">
            {status === "running" ? <><Square className="w-3 h-3" strokeWidth={2} /> Stop</> : <><Play className="w-3 h-3" strokeWidth={2} /> Run with Options</>}
          </button>
          <div className="flex items-center gap-3 text-[12px] font-mono text-zinc-500">
            {status === "running" && (
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Agent active
              </span>
            )}
            <span className="flex items-center gap-1">
              <BarChart3 className="w-3.5 h-3.5" strokeWidth={1.5} />
              {tokenUsage.tokens.toLocaleString()}t
            </span>
            <span className="flex items-center gap-1">
              <Activity className="w-3.5 h-3.5" strokeWidth={1.5} />
              ${tokenUsage.cost.toFixed(4)}
            </span>
          </div>
        </div>
      </div>

      {/* === 4. HISTORY PANEL (collapsible) === */}
      <AnimatePresence>
        {showHistory && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="border border-white/[0.06] rounded-[1.5rem] max-h-[400px] overflow-y-auto">
              {historySessions.length === 0 ? (
                <div className="p-8 text-center text-[13px] text-zinc-600">No past sessions</div>
              ) : historySessions.map((s: any) => (
                <div key={s.session_id} onClick={() => loadSession(s.session_id)}
                  className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-3 px-5 py-3 border-b border-white/[0.04] last:border-0 cursor-pointer hover:bg-white/[0.02] transition-colors group">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${s.status === "running" ? "bg-emerald-400 animate-pulse" : s.status === "completed" ? "bg-emerald-400" : s.status === "failed" ? "bg-red-400" : "bg-zinc-600"}`} />
                  <div className="min-w-0">
                    <div className="text-[13px] text-zinc-200 truncate">{(s.goal || s.requirements || "")?.slice(0, 80) || "No description"}</div>
                    <div className="text-[11px] text-zinc-600 font-mono mt-0.5 flex items-center gap-2">
                      <span>{s.session_id?.slice(0, 12)}</span>
                      {s.repo_url && <span className="text-zinc-700 truncate max-w-[200px]">{s.repo_url.split("/").slice(-2).join("/")}</span>}
                    </div>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider shrink-0 ${s.mode === "orchestrate" ? "bg-amber-500/10 text-amber-400" : "bg-emerald-500/10 text-emerald-400"}`}>{s.mode || "auto"}</span>
                  <span className="text-[11px] text-zinc-600 font-mono whitespace-nowrap shrink-0">{s.created_at?.slice(11, 16) || "-"}</span>
                  {s.status === "running" && (
                    <button onClick={(e) => { e.stopPropagation(); connectToWorkflow(s.session_id); }}
                      className="px-2.5 py-1 rounded-lg text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors shrink-0 opacity-0 group-hover:opacity-100">
                      Reconnect
                    </button>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* === 5. MAIN CONTENT GRID (Skills + Templates + Config) === */}
      {status === "idle" && (
        <div className="grid grid-cols-[280px_1fr] gap-6">
          <div className="space-y-4">
            <SkillsPanel />
          </div>
          <div className="space-y-4">
            {/* Templates Gallery */}
            <div>
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-4 block">Templates</span>
              {templates.length === 0 ? (
                <div className="text-center py-12 text-[13px] text-zinc-600 border border-dashed border-white/[0.06] rounded-[1.5rem]">
                  <FileText className="w-8 h-8 mx-auto mb-2 text-zinc-700" strokeWidth={1} />
                  <p>No templates yet</p>
                  <p className="text-[11px] text-zinc-600 mt-1">Templates can be added via the API or Settings page</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {templates.slice(0, 5).map((t, i) => (
                    <div key={i} className="border border-white/[0.06] rounded-[1.5rem] p-6 hover:border-emerald-500/10 hover:translate-y-[-2px] transition-all cursor-pointer group">
                      <div className="text-[14px] font-semibold text-zinc-200">{t.name || t.id}</div>
                      <div className="text-[12px] text-zinc-500 mt-1.5 leading-relaxed">{(t.description || "").slice(0, 60)}</div>
                      {t.tags && t.tags.length > 0 && (
                        <div className="flex gap-1.5 mt-3 flex-wrap">
                          {t.tags.slice(0, 3).map((tag: string, j: number) => (
                            <span key={j} className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">{tag}</span>
                          ))}
                        </div>
                      )}
                      <div className="mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={() => setRequirements(t.requirements || t.description || "")} className="text-[11px] text-emerald-400 hover:text-emerald-300 transition-colors">Use template</button>
                      </div>
                    </div>
                  ))}
                  <div className="border border-dashed border-white/[0.06] rounded-[1.5rem] p-6 flex flex-col items-center justify-center min-h-[140px] hover:border-emerald-500 hover:bg-emerald-500/5 transition-all cursor-pointer">
                    <Code2 className="w-6 h-6 text-zinc-600 mb-2" strokeWidth={1.5} />
                    <span className="text-[13px] text-zinc-500 font-medium">Add Template</span>
                  </div>
                </div>
              )}
            </div>

            {/* Advanced Config (collapsible) */}
            {showConfig && (
              <div>
                <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-4 block">Advanced Configuration</span>
                <div className="border border-white/[0.06] rounded-[1.5rem] p-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[{ l: "Timeout (s)", v: "600" }, { l: "Max Retries", v: "3" }, { l: "Parallelism", v: "1" }, { l: "Model", v: "deepseek-v4-flash" }].map((f, i) => (
                      <div key={i} className="flex flex-col gap-1">
                        <label className="text-[11px] font-medium text-zinc-500">{f.l}</label>
                        <input defaultValue={f.v} className="px-2.5 py-1.5 bg-card border border-white/[0.06] rounded-lg text-[13px] text-zinc-300 focus:outline-none focus:border-emerald-500/30" />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* === 6. KANBAN BOARD SECTION === */}
      {status === "running" && <KanbanBoardSection boardId={_boardId} sessionId={sessionId} />}

      {/* === 7. LIVE EXECUTION DASHBOARD === */}
      {status === "running" && (
        <>
          <EventStream />

          {/* Test Results + Queue */}
          <div className="grid grid-cols-[1fr_1fr] gap-6">
            <div className="bg-card border border-white/[0.06] rounded-xl p-5">
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3 block">Test Results</span>
              <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden mb-3 flex">
                <div className="bg-emerald-400 h-full transition-all duration-700" style={{ width: `${testResults.total > 0 ? (testResults.passed / testResults.total) * 100 : 0}%` }} />
                <div className="bg-red-400 h-full transition-all duration-700" style={{ width: `${testResults.total > 0 ? (testResults.failed / testResults.total) * 100 : 0}%` }} />
              </div>
              <div className="flex gap-4 text-[12px] font-mono">
                <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> {testResults.passed} passed</span>
                <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-red-400" /> {testResults.failed} failed</span>
              </div>
              <div className="mt-3 divide-y divide-white/[0.03]">
                  <div className="py-3 text-[12px] text-zinc-600">Test evidence appears in the event stream above as the pipeline runs.</div>
              </div>
              {testResults.failed > 0 && (
                <div className="mt-3 pt-3 border-t border-white/[0.06]">
                  <div className="flex items-center gap-2 text-[12px] text-amber-400">
                    <Bug className="w-3.5 h-3.5" strokeWidth={1.5} /> Autoheal is driven by backend stream evidence for failing tests
                  </div>
                </div>
              )}
            </div>

            {/* Approval Queue */}
            <div className="bg-card border border-white/[0.06] rounded-xl p-5">
              <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider mb-3 block">Approval Queue</span>
              <div className="space-y-2">
                <div className="bg-card border border-white/[0.06] rounded-lg p-4 text-[12px] text-zinc-500 leading-relaxed">
                  <div className="flex items-center gap-2 mb-2">
                    <Shield className="w-4 h-4 text-blue-400" strokeWidth={1.5} />
                    <span className="text-zinc-300 font-medium">Live approval state</span>
                  </div>
                  Approval-required tool calls will appear here only if emitted by the active delegate stream. No synthetic approval placeholders are shown.
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* === 7. PIPELINE SUMMARY === */}
      {status === "completed" && (
        <div className="flex items-center gap-4 px-5 py-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <CheckCircle2 className="w-9 h-9 text-emerald-400 shrink-0" strokeWidth={1.5} />
          <div className="flex-1">
            <div className="text-[15px] font-semibold text-zinc-100">Pipeline completed</div>
            <div className="text-[12px] text-zinc-500 mt-0.5 font-mono">{testResults.total} tests, {testResults.passed} passed, {testResults.failed} failed</div>
          </div>
          <button onClick={disconnect} className="px-4 py-2 rounded-lg text-[12px] font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors">New Run</button>
        </div>
      )}

      {status === "failed" && (
        <div className="flex items-center gap-4 px-5 py-4 rounded-xl bg-red-500/10 border border-red-500/20">
          <XCircle className="w-9 h-9 text-red-400 shrink-0" strokeWidth={1.5} />
          <div className="flex-1">
            <div className="text-[15px] font-semibold text-zinc-100">Pipeline failed</div>
            <div className="text-[12px] text-zinc-500 mt-0.5">Check logs for details</div>
          </div>
          <button onClick={disconnect} className="px-4 py-2 rounded-lg text-[12px] font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700 transition-colors">Retry</button>
        </div>
      )}
    </motion.div>
  );
}

export default function PipelinePage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] flex items-center justify-center text-zinc-600">Loading...</div>}>
      <PipelinePageInner />
    </Suspense>
  );
}
