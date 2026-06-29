"use client";

import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LogExplorer } from "@/components/agents/LogExplorer";
import { RunComparison } from "@/components/agents/RunComparison";
import { TestResultsTable } from "@/components/pipeline/TestResultsTable";
import { generatePipelineReport } from "@/lib/generate-pipeline-report";
import { CostMeter } from "@/components/pipeline/CostMeter";
import { ModelTokensPanel } from "@/components/pipeline/ModelTokensPanel";
import { GroupedErrors } from "@/components/pipeline/GroupedErrors";
import { RunArtifactBrowser } from "@/components/pipeline/RunArtifactBrowser";
import { SessionReplay } from "@/components/pipeline/SessionReplay";
import { BatchRerun } from "@/components/pipeline/BatchRerun";
import { groupErrors } from "@/lib/error-grouping";
import { useEventSource } from "@/lib/hooks/use-event-source";
import { api, BACKEND_URL } from "@/lib/api/api-client";

import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { SkeletonBlock } from "@/components/shared/LoadingSkeleton";
import { ReasoningBlock } from "@/components/shared/ReasoningBlock";
import { ToolCallCard } from "@/components/shared/ToolCallCard";
import { StackTrace } from "@/components/shared/StackTrace";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  Beaker,
  Github,
  GitlabIcon as GitLab,
  GitBranch,
  CheckCircle,
  XCircle,
  Clock,
  Play,
  Calendar,
  Globe,
  Loader2,
  GitCompare,
  MessageSquare,
  FileDown,
  PauseCircle,
  StopCircle,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface RunDetail {
  id: string;
  workflowId: string;
  repoUrl?: string | null;
  repoProvider?: string | null;
  requirements?: string | null;
  status: string;
  testCount: number;
  passedCount: number;
  failedCount: number;
  skippedCount: number;
  duration: number;
  techStack?: string | null;
  aiPatterns?: string | null;
  researchReport?: string | null;
  createdAt: string;
  completedAt?: string | null;
  logDirPath?: string | null;
  costUsd?: number;
  budgetCap?: number;
  tokenCount?: number;
  repos?: string[];
  multiRepo?: boolean;
  phases?: Array<{
    name: string;
    status: string;
    percent: number;
    message?: string;
    costUsd?: number;
    tokens?: number;
    durationS?: number;
  }>;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

function formatDate(dateStr: string) {
  try {
    return new Date(dateStr).toLocaleString("en-US", {
      year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return dateStr; }
}

function ProviderIcon({ provider }: { provider?: string | null }) {
  switch (provider) {
    case "github": return <Github className="w-4 h-4" strokeWidth={1.5} />;
    case "gitlab": return <GitLab className="w-4 h-4" strokeWidth={1.5} />;
    case "bitbucket": return <GitBranch className="w-4 h-4" strokeWidth={1.5} />;
    default: return <Globe className="w-4 h-4" strokeWidth={1.5} />;
  }
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function RunDetailPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;

  const [run, setRun] = useState<RunDetail | null>(null);
  const [tests, setTests] = useState<any[]>([]);
  const [testsLoading, setTestsLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [pipelineEvents, setPipelineEvents] = useState<any[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [coverageReports, setCoverageReports] = useState<any[]>([]);
  // Q11-D: interrupt / pause / cancel / fork UI state
  const [showForkPrompt, setShowForkPrompt] = useState(false);
  const [forkGoal, setForkGoal] = useState("");
  const [actionPending, setActionPending] = useState<string | null>(null);
  // The `isRunLive` flag is declared later in this component
  // (line ~288) with the canonical definition; we reuse it here
  // for the action buttons.

  // ── Coordinator agent stages (moved before early returns for React hooks rules) ──
  const stageOrder = ["bootstrap", "explore", "coordinate", "execute", "verify"];
  const stageLabels: Record<string, string> = {
    bootstrap: "Bootstrap", explore: "Explore", coordinate: "Coordinate",
    execute: "Execute", verify: "Verify",
  };

  // ── State + SSE for live runs (must be before early returns) ──
  const [liveStages, setLiveStages] = useState<{ name: string; label: string; status: string; percent: number; message?: string }[]>([]);
  const [liveCost, setLiveCost] = useState(0);
  const [liveTokens, setLiveTokens] = useState({ total: 0, prompt: 0, completion: 0 });
  const [liveBreakdown, setLiveBreakdown] = useState({ llm: 0, sandbox: 0, tools: 0 });
  const isRunLive = run?.status === "running" || run?.status === "pending";

  // SSE for live runs
  useEventSource({
    url: isRunLive ? `${BACKEND_URL}/api/delegate/${runId}/stream` : null,
    eventTypes: ["stage:start", "stage:progress", "stage:complete", "metrics", "cost:snapshot"],
    onEvent: (type, data) => {
      const d = data as any;
      if (type.startsWith("stage:") && d?.stage) {
        setLiveStages((prev) => {
          const existing = prev.findIndex((p) => p.name === d.stage);
          const entry = {
            name: d.stage,
            label: stageLabels[d.stage] ?? d.label ?? d.stage,
            status: type === "stage:complete" ? (d.status ?? "passed") : "running",
            percent: d.percent ?? 0,
            message: d.message,
          };
          if (existing >= 0) {
            const next = [...prev];
            next[existing] = entry;
            return next;
          }
          return [...prev, entry];
        });
      }
      if (type === "metrics") {
        setLiveCost((d.estimated_cost_usd ?? 0));
        setLiveTokens((prev) => ({
          total: prev.total + (d.total_tokens ?? 0),
          prompt: prev.prompt + (d.prompt_tokens ?? 0),
          completion: prev.completion + (d.completion_tokens ?? 0),
        }));
      }
      if (type === "cost:snapshot") {
        setLiveCost(d.total ?? 0);
        setLiveBreakdown({ llm: d.llm ?? 0, sandbox: d.sandbox ?? 0, tools: d.tools ?? 0 });
        if (d.tokens) setLiveTokens(d.tokens);
      }
    },
  });

  // ── Derived state (useMemo must be before early returns per React hooks rules) ──
  const derivedStages = useMemo(() => {
    if (liveStages.length > 0) return liveStages;

    const apiPhases = (run as any)?.phases;
    if (apiPhases && Array.isArray(apiPhases) && apiPhases.length > 0) {
      return stageOrder.map((name) => {
        const found = apiPhases.find((p: any) => p.name === name);
        return { name, label: stageLabels[name], status: found?.status ?? "pending", percent: found?.percent ?? 0 };
      });
    }
    return stageOrder.map((name) => ({ name, label: stageLabels[name], status: "pending" as const, percent: 0 }));
  }, [liveStages]);

  const groupedErrors = useMemo(() => {
    const failures = (tests ?? []).filter((t: any) => t.status === "failed" || t.error).map((t: any) => ({
      testName: t.testName,
      file: t.file,
      line: t.line,
      message: t.error || `${t.testName} failed`,
      timestamp: t.timestamp,
    }));
    return groupErrors(failures);
  }, [tests]);

  async function callDelegateAction(action: "interrupt" | "pause" | "cancel"): Promise<void> {
    if (!runId) return;
    setActionPending(action);
    try {
      const body = await api.post<{ detail?: string }>(`/api/delegate/${runId}/${action}`, {});
      if (body?.detail) {
        toast.error(`Action failed: ${body.detail}`);
        return;
      }
      toast.success(`Run ${action} requested`);
      // Re-fetch run status to reflect the action
      setTimeout(() => fetchRun(), 500);
    } catch (e) {
      toast.error(`Action error: ${(e as Error).message}`);
    } finally {
      setActionPending(null);
    }
  }

  async function callFork(): Promise<void> {
    if (!runId || !forkGoal.trim()) return;
    setActionPending("fork");
    try {
      const body = await api.post<{ detail?: string; new_session_id?: string }>(`/api/delegate/${runId}/fork`, { new_goal: forkGoal.trim() });
      if (body?.detail) {
        toast.error(`Fork failed: ${body.detail}`);
        return;
      }
      toast.success(`Forked: new session ${body?.new_session_id?.slice(0, 8) || "?"}`);
      setShowForkPrompt(false);
      setForkGoal("");
      // Navigate to the new session so the operator can watch it
      if (body?.new_session_id) router.push(`/history/${body.new_session_id}`);
    } catch (e) {
      toast.error(`Fork error: ${(e as Error).message}`);
    } finally {
      setActionPending(null);
    }
  }

  useEffect(() => {
    fetchRun();
  }, [runId]);

  const fetchRun = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [runRes, testsRes, eventsData, covRes] = await Promise.all([
        api.get<{ run?: any }>(`/api/runs/${runId}`),
        api.get<{ tests?: any[] }>(`/api/runs/${runId}/test-results`),
        api.get<{ events?: any[] }>(`/api/runs/${runId}/events`).catch(() => ({ events: [] })),
        api.get<any>(`/api/coverage/history?limit=20`).catch(() => ({})),
      ]);
      if (!runRes) throw new Error("Failed to fetch run");
      setRun(runRes?.run ?? null);
      setTests(testsRes?.tests ?? []);
      setPipelineEvents(eventsData?.events ?? []);
      const reports = ((covRes as any)?.reports ?? []).filter((r: any) => r.runId === runId);
      setCoverageReports(reports);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  };

  const handleReRunAll = () => {
    if (!run) return;
    sessionStorage.setItem("pipeline_requirements", run.requirements || "");
    router.push("/pipeline");
  };

  const handleOpenInChat = () => {
    if (!run?.requirements) return;
    sessionStorage.setItem("agent_prompt", run.requirements);
    router.push("/chat");
  };

  const handleDownloadReport = async () => {
    try {
      const [eventsData, testsRes] = await Promise.all([
        api.get<{ events?: any[] }>(`/api/runs/${runId}/events`),
        api.get<{ tests?: any[] }>(`/api/runs/${runId}/test-results`),
      ]);
      const html = generatePipelineReport(
        run as any,
        eventsData?.events ?? [],
        (testsRes?.tests ?? []) as any[],
      );
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pipeline-report-${runId.slice(0, 8)}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to generate report");
    }
  };

  // ── Loading ────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-6">
        <SkeletonBlock className="h-8 w-64" />
        <SkeletonBlock className="h-48 w-full rounded-[1.5rem]" />
        <SkeletonBlock className="h-64 w-full rounded-[1.5rem]" />
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="space-y-6">
        <Button
          variant="ghost"
          onClick={() => router.back()}
          className="gap-2 text-neutral-400"
        >
          <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
          Back
        </Button>
        <ErrorState message={error || "Run not found"} onRetry={fetchRun} />
      </div>
    );
  }

  const passRate = run.testCount > 0
    ? Math.round((run.passedCount / run.testCount) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.back()}
          className="w-8 h-8 text-neutral-500"
        >
          <ArrowLeft className="w-4 h-4" strokeWidth={1.5} />
        </Button>
        <PageHeader
          title={run.repoUrl || "Manual Run"}
          description={`Started ${formatDate(run.createdAt)}`}
            actions={
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={handleOpenInChat}
                className="rounded-xl gap-2 border-white/[0.08] text-xs"
              >
                <MessageSquare className="w-3.5 h-3.5" strokeWidth={1.5} />
                Chat
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCompareId(compareId ? null : runId)}
                className="rounded-xl gap-2 border-white/[0.08] text-xs"
              >
                <GitCompare className="w-3.5 h-3.5" strokeWidth={1.5} />
                {compareId ? "Close Compare" : "Compare"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleDownloadReport}
                className="rounded-xl gap-2 border-white/[0.08] text-xs active:scale-[0.97]"
              >
                <FileDown className="w-3.5 h-3.5" strokeWidth={1.5} />
                Report
              </Button>
              <Button
                size="sm"
                onClick={handleReRunAll}
                className="rounded-xl gap-2 bg-emerald-500 hover:bg-emerald-400 text-xs active:scale-[0.98]"
              >
                <Play className="w-3.5 h-3.5" strokeWidth={2} />
                Re-run
              </Button>
              {/* Q11-D: interrupt / pause / cancel / fork. Visible
                  only while the run is live (not yet completed /
                  failed / cancelled). Each button calls a backend
                  endpoint already wired in
                  `delegate.py:243,279,318,336,374`. */}
              {isRunLive && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => callDelegateAction("interrupt")}
                    disabled={actionPending !== null}
                    className="rounded-xl gap-2 border-white/[0.08] text-xs"
                  >
                    <StopCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
                    {actionPending === "interrupt" ? "Interrupting…" : "Interrupt"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => callDelegateAction("pause")}
                    disabled={actionPending !== null}
                    className="rounded-xl gap-2 border-white/[0.08] text-xs"
                  >
                    <PauseCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
                    {actionPending === "pause" ? "Pausing…" : "Pause"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => callDelegateAction("cancel")}
                    disabled={actionPending !== null}
                    className="rounded-xl gap-2 border-white/[0.08] text-xs text-red-400 hover:text-red-300"
                  >
                    <XCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
                    {actionPending === "cancel" ? "Cancelling…" : "Cancel"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowForkPrompt(true)}
                    disabled={actionPending !== null}
                    className="rounded-xl gap-2 border-white/[0.08] text-xs"
                  >
                    <GitBranch className="w-3.5 h-3.5" strokeWidth={1.5} />
                    Fork
                  </Button>
                </>
              )}
            </div>
          }
        />

        {/* Q11-D: Fork prompt modal. Shown when the operator clicks
            the Fork button. Asks for the new goal (the new session
            inherits the source's repo/branch/context but not the
            prompt). The form is intentionally minimal: a text
            input + a submit + cancel. No new state lives here
            besides what's already in the page. */}
        {showForkPrompt && (
          <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
            <div className="bg-surface border border-white/[0.08] rounded-2xl p-6 max-w-xl w-full">
              <h2 className="text-lg font-semibold mb-1">Fork this run</h2>
              <p className="text-xs text-zinc-500 mb-4">
                Creates a new session that points to this one as its parent.
                The new run inherits the repo, branch, and explored context,
                but you can redirect the work with a new goal.
              </p>
              <textarea
                value={forkGoal}
                onChange={(e) => setForkGoal(e.target.value)}
                placeholder="New goal for the forked run…"
                className="w-full h-32 px-3 py-2 rounded-xl bg-white/[0.04] border border-white/[0.08] text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
                autoFocus
              />
              <div className="flex items-center justify-end gap-2 mt-4">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => { setShowForkPrompt(false); setForkGoal(""); }}
                  className="rounded-xl text-xs"
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={() => void callFork()}
                  disabled={!forkGoal.trim() || actionPending === "fork"}
                  className="rounded-xl gap-2 bg-emerald-500 hover:bg-emerald-400 text-xs"
                >
                  <GitBranch className="w-3.5 h-3.5" strokeWidth={2} />
                  {actionPending === "fork" ? "Forking…" : "Fork"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Stage Progress + Cost */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          {derivedStages.length > 0 && (
            <div className="bg-surface border border-white/[0.05] rounded-3xl p-5">
              <div className="flex items-center gap-4">
                {derivedStages.map((s, i) => (
                  <div key={s.name} className="flex items-center gap-2 flex-1">
                    {i > 0 && <div className="h-px flex-1 bg-white/[0.06]" />}
                    <div className={cn(
                      "flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-all",
                      s.status === "running" ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20" :
                      s.status === "passed" ? "bg-emerald-500/10 text-emerald-400" :
                      s.status === "failed" ? "bg-red-500/10 text-red-400" :
                      "bg-white/[0.03] text-zinc-600"
                    )}>
                      {s.status === "running" && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />}
                      {s.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div>
          {(liveCost > 0 || (run as any)?.costUsd > 0) && (
            <CostMeter
              currentCost={liveCost || ((run as any)?.costUsd ?? 0)}
              budgetCap={(run as any)?.budgetCap ?? (run as any)?.budget_cap ?? 5.00}
              breakdown={Object.values(liveBreakdown).some(v => v > 0) ? liveBreakdown : undefined}
              tokens={liveTokens.total > 0 ? liveTokens : undefined}
              isLive={isRunLive}
            />
          )}
          {/* C7.1: OTel GenAI semconv panel. Projects the run's
              trace events to `gen_ai.request.model`,
              `gen_ai.usage.input_tokens`,
              `gen_ai.usage.output_tokens`, `gen_ai.provider.name`
              and renders a per-model breakdown. The trace events
              come from `/api/runs/{runId}/trace-events` (legacy
              event_data payload keys `model`, `prompt_tokens`,
              `completion_tokens` are also accepted for back-compat). */}
          <div className="mt-3">
            <ModelTokensPanel runId={runId} />
          </div>
        </div>
      </div>

      {/* Summary card */}
      <div className="bg-surface border border-white/[0.05] rounded-3xl p-6">
        <div className="flex items-start gap-4 mb-6">
          <div
            className={cn(
              "w-14 h-14 rounded-2xl flex items-center justify-center shrink-0",
              run.status === "completed" ? "bg-emerald-500/10" :
              run.status === "failed" ? "bg-red-500/10" : "bg-amber-500/10",
            )}
          >
            {run.status === "completed" ? (
              <CheckCircle className="w-7 h-7 text-emerald-400" strokeWidth={1.5} />
            ) : run.status === "failed" ? (
              <XCircle className="w-7 h-7 text-red-400" strokeWidth={1.5} />
            ) : (
              <Clock className="w-7 h-7 text-amber-400" strokeWidth={1.5} />
            )}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <ProviderIcon provider={run.repoProvider} />
              <span className="text-lg font-semibold text-zinc-100">{run.repoUrl || "Manual"}</span>
              <Badge
                variant="outline"
                className={cn(
                  "text-xs px-2 py-0.5 rounded font-medium",
                  run.status === "completed" ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/5" :
                  run.status === "failed" ? "text-red-400 border-red-500/30 bg-red-500/5" :
                  "text-amber-400 border-amber-500/30 bg-amber-500/5",
                )}
              >
                {run.status}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-neutral-500">
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" strokeWidth={1.5} />
                {formatDate(run.createdAt)}
              </span>
              {run.completedAt && (
                <span>Completed {formatDate(run.completedAt)}</span>
              )}
            </div>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem] p-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Beaker className="w-4 h-4 text-emerald-400" strokeWidth={1.5} />
            </div>
            <div className="text-2xl font-semibold text-zinc-100">{run.testCount}</div>
            <div className="text-xs text-neutral-500">Total Tests</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem] p-4 text-center">
            <div className="text-2xl font-semibold text-emerald-400">{run.passedCount}</div>
            <div className="text-xs text-neutral-500">Passed</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem] p-4 text-center">
            <div className="text-2xl font-semibold text-red-400">{run.failedCount}</div>
            <div className="text-xs text-neutral-500">Failed</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem] p-4 text-center">
            <div className="text-2xl font-semibold text-zinc-100">{passRate}%</div>
            <div className="text-xs text-neutral-500">Pass Rate</div>
          </div>
        </div>

        {/* Duration */}
        <div className="text-xs text-neutral-500">
          Duration: {formatDuration(run.duration)}
        </div>
      </div>

      {/* Error Grouping */}
      {groupedErrors.length > 0 && (
        <GroupedErrors groups={groupedErrors} />
      )}

      {/* Test Results */}
      {tests.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-3">Test Results</h3>
          <TestResultsTable tests={tests.map((t: any) => ({
            testName: t.testName,
            status: t.status,
            durationMs: t.durationMs,
            error: t.error,
            healed: t.healedByAgent,
          }))} loading={isLoading} />
        </div>
      )}

      {/* Batch Re-Run */}
      {tests.length > 0 && (
        <BatchRerun
          runId={runId}
          tests={tests.map((t: any) => ({
            testName: t.testName,
            status: t.status,
            durationMs: t.durationMs,
            error: t.error,
          }))}
          requirements={(run as any)?.requirements}
        />
      )}

      {/* Session Replay */}
      {pipelineEvents.length > 0 && (
        <SessionReplay
          events={pipelineEvents.map((e: any) => ({
            type: e.type,
            data: e.data,
            createdAt: e.createdAt,
          }))}
        />
      )}

      {/* Artifact Browser */}
      {tests.length > 0 && (
        <RunArtifactBrowser
          testResults={tests.map((t: any) => ({
            testName: t.testName,
            status: t.status,
            error: t.error,
            durationMs: t.durationMs,
          }))}
          coverageReports={coverageReports}
          logs={pipelineEvents.map((e: any) => ({
            type: e.type,
            data: e.data,
            createdAt: e.createdAt,
          }))}
        />
      )}

      {/* Log Explorer */}
      <div>
        <h3 className="text-sm font-semibold text-zinc-100 mb-3">Run Artifacts & Logs</h3>
        <LogExplorer runId={runId} />
      </div>

      {/* Pipeline Event Replay */}
      {pipelineEvents.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-3">Pipeline Events</h3>
          <div className="space-y-2">
            {pipelineEvents.map((ev, i) => {
              const d = ev.data || {};
              switch (ev.type) {
                case "reasoning":
                  return (
                    <ReasoningBlock
                      key={i}
                      content={typeof d.content === "string" ? d.content : JSON.stringify(d)}
                    />
                  );
                case "ToolExecutionStarted":
                case "ToolExecutionCompleted":
                case "tool_calls":
                case "tool_result":
                  return (
                    <ToolCallCard
                      key={i}
                      name={d.tool_name || d.name || d.calls?.[0]?.function?.name || "tool"}
                      status={d.success ? "completed" : d.type === "ToolExecutionStarted" ? "running" : "completed"}
                      durationMs={d.duration_ms || undefined}
                      args={d.arguments || d.args || undefined}
                      result={d.output || d.result || undefined}
                    />
                  );
                case "error": {
                  const errMsg = d.message || "Unknown error";
                  const isTrace = errMsg.includes("Traceback") || errMsg.includes("    at ") || /^\w*(Error|TypeError)/.test(errMsg);
                  return (
                    <div key={i}>
                      {isTrace ? (
                        <StackTrace trace={errMsg} />
                      ) : (
                        <div className="flex items-start gap-2.5 px-3.5 py-2.5 rounded-xl border border-red-500/15 bg-red-500/[0.04]">
                          <div className="flex-1">
                            <p className="text-xs font-medium text-red-400">Pipeline Error</p>
                            <p className="text-[11px] text-red-400/70 font-mono mt-0.5">{errMsg}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                }
                case "done":
                  return (
                    <div key={i} className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl border border-emerald-500/10 bg-emerald-500/[0.03]">
                      <span className="text-xs font-medium text-emerald-400">Pipeline completed</span>
                    </div>
                  );
                case "metrics":
                  return (
                    <div key={i} className="flex items-center gap-2 px-3 py-1.5">
                      <span className="text-[10px] text-neutral-500 font-mono tabular-nums">
                        {d.total_tokens ? `${(d.total_tokens / 1000).toFixed(1)}k tokens` : ""}
                        {d.estimated_cost_usd ? ` · $${d.estimated_cost_usd.toFixed(4)}` : ""}
                      </span>
                    </div>
                  );
                default:
                  return null;
              }
            })}
          </div>
        </div>
      )}

      {/* Compare run selector */}
      <AnimatePresence>
        {compareId && !compareId.match(/^[a-f0-9-]+$/i) && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden border border-white/[0.06] rounded-3xl bg-surface p-4">
            <div className="flex items-end gap-3">
              <div className="flex-1 space-y-1">
                <label className="text-[10px] text-neutral-500 uppercase tracking-wider font-medium">Compare with run ID</label>
                <input type="text" value={compareId === runId ? "" : compareId}
                  onChange={(e) => setCompareId(e.target.value)}
                  placeholder="Paste a run ID to compare..."
                  className="w-full h-8 px-3 rounded-lg bg-white/[0.02] border border-white/[0.08] text-xs text-neutral-300 placeholder:text-neutral-600 outline-none focus:border-emerald-500/30 font-mono transition-colors" />
              </div>
              <button type="button" onClick={() => { setCompareId(runId); }}
                className="h-8 px-4 rounded-lg text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold active:scale-[0.95] transition-all">
                Compare
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Comparison section */}
      <div className={cn("space-y-4", compareId && compareId !== runId ? "" : "hidden")}>
        <RunComparison
          runId={runId}
          compareId={compareId && compareId !== runId ? compareId : null}
          onClose={() => setCompareId(null)}
        />
      </div>
    </div>
  );
}
