"use client";

import { create } from "zustand";
import type { PipelineEvent, ToolState, ApprovalRequest } from "@/lib/types/pipeline";
import type { AgentState, LogEntry, ConsoleLine, TestResults, ResearchOutputData } from "@/lib/types/workflow";
import { createReconnectingEventSource } from "@/lib/hooks/use-event-source";
import { BACKEND_URL, api } from "@/lib/api/api-client";

/** Module-level stream controller. */
let _streamController: StreamController | null = null;

const PIPELINE_EVENT_TYPES = [
  "pipeline.started", "pipeline.cloned", "pipeline.kg_building",
  "pipeline.kg_ready", "pipeline.kg_failed", "pipeline.kg_updated",
  "pipeline.stack_detected", "pipeline.kanban_created",
  "pipeline.test_cases_generated", "pipeline.kg_test_updated",
  "pipeline.kg_fix_updated", "pipeline.autoheal.started",
  "pipeline.autoheal.completed", "pipeline.tool_audit",
  "pipeline.completed", "pipeline.failed",
  "quality.metrics_recorded", "flaky.quarantined",
  "session.started", "session.failed", "session.completed",
  "subagent.spawned", "subagent.completed", "subagent.interrupted",
  "ToolExecutionStarted", "ToolExecutionCompleted",
  "ToolProgress", "LLMCallStarted", "LLMCallCompleted",
  "TokenGenerated", "ReasoningGenerated",
];

interface StreamController {
  close: () => void;
  retry: () => void;
  readonly state: string;
  readonly retryCount: number;
}

// ── Derivation helpers (inline, no reducer file) ────────────────────

function deriveTools(events: PipelineEvent[]): ToolState[] {
  const tools: ToolState[] = [];
  for (const e of events) {
    if (e.type === "ToolExecutionStarted" || e.type === "subagent.spawned") {
      const name = e.type === "ToolExecutionStarted" ? e.tool_name : "subagent";
      const args = e.type === "ToolExecutionStarted" ? { input: e.tool_input } : { goal: (e as any).goal ?? "" };
      const existing = tools.findIndex((t) => t.name === name && t.status === "running");
      if (existing === -1) tools.push({ name, status: "running", startTime: Date.now(), args });
    } else if (e.type === "ToolExecutionCompleted" || e.type === "subagent.completed") {
      const name = e.type === "ToolExecutionCompleted" ? e.tool_name : "subagent";
      const success = e.type === "ToolExecutionCompleted" ? e.success : true;
      const output = e.type === "ToolExecutionCompleted" ? e.output_preview : undefined;
      const idx = tools.findIndex((t) => t.name === name);
      if (idx !== -1) tools[idx] = { ...tools[idx], status: success ? "completed" : "failed", endTime: Date.now(), output };
    } else if (e.type === "LLMCallStarted") {
      const name = `LLM (${e.model ?? "?"})`;
      const existing = tools.findIndex((t) => t.name === name && t.status === "running");
      if (existing === -1) tools.push({ name, status: "running", startTime: Date.now() });
    } else if (e.type === "LLMCallCompleted") {
      const name = tools.find((t) => t.status === "running" && t.name.startsWith("LLM"))?.name ?? "LLM";
      const idx = tools.findIndex((t) => t.name === name && t.status === "running");
      if (idx !== -1) tools[idx] = { ...tools[idx], status: "completed", endTime: Date.now(), output: String(e.total_tokens ?? 0) };
    }
  }
  return tools;
}

function deriveApprovals(events: PipelineEvent[]): ApprovalRequest[] {
  return events
    .filter((e): e is PipelineEvent & { type: "approval:required"; id: string; tool: string; args: Record<string, unknown> } =>
      e.type === "approval:required")
    .map((e) => ({ id: e.id, tool: e.tool, args: e.args as Record<string, unknown>, mode: "" }));
}

function deriveMetrics(events: PipelineEvent[]) {
  let promptTokens = 0, completionTokens = 0, totalTokens = 0, estimatedCost = 0;
  for (const e of events) {
    if (e.type === "metrics") {
      promptTokens += e.prompt_tokens || 0;
      completionTokens += e.completion_tokens || 0;
      totalTokens += e.total_tokens || 0;
      estimatedCost = e.estimated_cost_usd || estimatedCost;
    }
  }
  return { promptTokens, completionTokens, totalTokens, estimatedCost };
}

// ── Console messages & progress ─────────────────────────────────────

const CONSOLE_MESSAGES: Record<string, (d: Record<string, unknown>) => string> = {
  "pipeline.started": () => "Pipeline started",
  "pipeline.cloned": (d) => `Repository cloned: ${String(d.workspace ?? "")}`,
  "pipeline.stack_detected": (d) => `Stack detected: ${String(d.language ?? "unknown")} / ${String(d.framework ?? "unknown")}`,
  "pipeline.test_cases_generated": (d) => `Generated ${(d as any).count ?? 0} test cases`,
  "pipeline.kg_test_updated": (d) => `KG test update #${(d as any).index ?? 0}: ${(d as any).test_name ?? "unknown"}`,
  "pipeline.kg_fix_updated": (d) => `KG fix update #${(d as any).index ?? 0}: ${(d as any).test_name ?? "unknown"}`,
  "pipeline.autoheal.started": (d) => `Autoheal started for ${(d as any).test_name ?? "unknown"}`,
  "pipeline.autoheal.completed": (d) => `Autoheal completed for ${(d as any).test_name ?? "unknown"}`,
  "pipeline.tool_audit": (d) => `Tool audit: ${Object.entries(d).filter(([, v]) => Boolean(v)).map(([k]) => k).join(", ") || "none"}`,
  "quality.metrics_recorded": (d) => `Quality: ${(d as any).pass_rate ?? 0}% pass rate`,
  "flaky.quarantined": (d) => `Quarantined ${(d as any).count ?? 0} flaky tests`,
  "orchestration.started": () => "Orchestration started — cloning repo...",
  "orchestration.completed": () => "Orchestration completed",
  "orchestration.failed": (d) => `Orchestration failed: ${(d as any).error ?? "Unknown error"}`,
  "pipeline.kg_building": () => "Building knowledge graph...",
  "pipeline.kg_ready": () => "Knowledge graph ready",
  "pipeline.kg_failed": () => "Knowledge graph build failed",
  "pipeline.kanban_created": () => "Kanban board created",
  "subagent.spawned": (d) => `Subagent spawned: ${(d as any).goal ?? ""}`,
  "subagent.completed": () => "Subagent completed",
  "subagent.thinking": () => "Subagent thinking...",
  "subagent.interrupted": () => "Subagent interrupted",
  "ToolExecutionStarted": (d) => `Tool: ${(d as any).tool_name ?? "?"}`,
  "ToolExecutionCompleted": (d) => `Tool done: ${(d as any).tool_name ?? "?"}`,
  "LLMCallStarted": (d) => `LLM call: ${(d as any).model ?? "?"}`,
  "LLMCallCompleted": () => "LLM response received",
  "kanban.updated": () => "Kanban board updated",
  "pipeline.completed": () => "Pipeline completed",
  "pipeline.failed": (d) => `Pipeline failed: ${(d as any).error ?? "Unknown error"}`,
  "session.failed": (d) => `Pipeline failed: ${(d as any).error ?? "Unknown error"}`,
  "session.completed": () => "Session completed",
};

const PROGRESS_MAP: Record<string, number> = {
  "pipeline.started": 10, "orchestration.started": 10,
  "pipeline.cloned": 20, "pipeline.stack_detected": 30,
  "pipeline.test_cases_generated": 60, "quality.metrics_recorded": 90,
  "pipeline.completed": 100, "session.completed": 100, "orchestration.completed": 100,
};

const COMPLETED_TYPES = new Set(["pipeline.completed", "session.completed", "orchestration.completed"]);
const FAILED_TYPES = new Set(["pipeline.failed", "session.failed", "orchestration.failed"]);
const STARTED_TYPES = new Set(["pipeline.started", "orchestration.started"]);

// ── Event processing ────────────────────────────────────────────────

function processEvent(
  eventType: string,
  dataObj: Record<string, unknown>,
  addEvent: (ev: PipelineEvent) => void,
) {
  const ev = (
    STARTED_TYPES.has(eventType) ? { type: "pipeline:start" as const } :
    COMPLETED_TYPES.has(eventType) ? { type: "done" as const } :
    FAILED_TYPES.has(eventType) ? { type: "error" as const, message: String((dataObj as any).error ?? "Unknown error") } :
    eventType === "quality.metrics_recorded" ? { type: "metrics" as const, prompt_tokens: Number((dataObj as any).tokens ?? 0), completion_tokens: 0, total_tokens: Number((dataObj as any).tokens ?? 0), estimated_cost_usd: 0 } :
    eventType === "subagent.spawned" ? { type: "subagent.spawned" as const, goal: String((dataObj as any).goal ?? ""), subagent_id: String((dataObj as any).subagent_id ?? "") } :
    eventType === "subagent.completed" ? { type: "subagent.completed" as const, subagent_id: String((dataObj as any).subagent_id ?? "") } :
    eventType === "subagent.thinking" ? { type: "reasoning" as const, content: String((dataObj as any).thought ?? "") } :
    eventType === "subagent.interrupted" ? { type: "error" as const, message: "Subagent interrupted" } :
    eventType === "ToolExecutionStarted" ? { type: "ToolExecutionStarted" as const, tool_name: String((dataObj as any).tool_name ?? "tool"), tool_input: String((dataObj as any).tool_input ?? ""), trace_id: String((dataObj as any).trace_id ?? "") } :
    eventType === "ToolExecutionCompleted" ? { type: "ToolExecutionCompleted" as const, tool_name: String((dataObj as any).tool_name ?? "tool"), success: Boolean((dataObj as any).success ?? true), output_preview: String((dataObj as any).output_preview ?? "") } :
    eventType === "LLMCallStarted" ? { type: "LLMCallStarted" as const, model: String((dataObj as any).model ?? "?"), call_id: String((dataObj as any).call_id ?? "") } :
    eventType === "LLMCallCompleted" ? { type: "LLMCallCompleted" as const, total_tokens: Number((dataObj as any).total_tokens ?? 0) } :
    eventType === "TokenGenerated" ? { type: "token" as const, content: String((dataObj as any).content ?? "") } :
    eventType === "ReasoningGenerated" ? { type: "reasoning" as const, content: String((dataObj as any).content ?? "") } :
    eventType === "ToolProgress" ? { type: "ToolProgress" as const, tool_name: String((dataObj as any).tool_name ?? "tool"), content: String((dataObj as any).content ?? "").slice(0, 200) } :
    null
  );
  if (ev) { try { addEvent(ev as PipelineEvent); } catch {} }
}

// ── Store ───────────────────────────────────────────────────────────

function initialState() {
  return {
    connected: false,
    runId: null as string | null,
    mode: "auto" as string,
    sessionId: null as string | null,
    requirements: "",
    status: "idle" as "idle" | "running" | "completed" | "failed",
    startTime: null as number | null,
    endTime: null as number | null,
    events: [] as PipelineEvent[],
    tools: [] as ToolState[],
    approvals: [] as ApprovalRequest[],
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0,
    estimatedCost: 0,
    agentStates: [] as AgentState[],
    agentExecutionDetails: [] as any[],
    workflowProgress: 0,
    activityLog: [] as LogEntry[],
    agentStreamOutputs: {} as Record<string, string[]>,
    testResults: null as TestResults | null,
    consoleLines: [] as ConsoleLine[],
    researchOutput: null as ResearchOutputData | null,
    logDirPath: null as string | null,
    pipelineOutput: "",
  };
}

interface PipelineStore extends ReturnType<typeof initialState> {
  approveRequest: (id: string) => void;
  denyRequest: (id: string) => void;
  setConnected: (connected: boolean) => void;
  setRunId: (runId: string | null) => void;
  setMode: (mode: string) => void;
  setStatus: (status: PipelineStore["status"]) => void;
  setRequirements: (req: string) => void;
  startRun: () => void;
  endRun: () => void;
  reset: () => void;
  addEvent: (event: PipelineEvent) => void;
  startWorkflow: (requirements: string, files?: File[], githubRepo?: string, repoProvider?: string) => Promise<{ workflowId: string; runId: string | null }>;
  connectToWorkflow: (workflowId: string, streamEndpoint?: string) => void;
  disconnect: () => void;
}

const handleEvent = (dataObj: Record<string, unknown>, type: string, set: (fn: (prev: PipelineStore) => Partial<PipelineStore>) => void, get: () => PipelineStore) => {
  const ctx = { sessionId: get().sessionId, addEvent: (ev: PipelineEvent) => { try { get().addEvent(ev); } catch {} } };
  processEvent(type, dataObj, ctx.addEvent);

  // Derive state from events
  const events = get().events;
  const updates: Partial<PipelineStore> = {};
  const msgFn = CONSOLE_MESSAGES[type];
  if (msgFn) updates.consoleLines = [...get().consoleLines, { text: msgFn(dataObj), type: FAILED_TYPES.has(type) ? "stderr" : "system" }];
  if (PROGRESS_MAP[type] !== undefined) updates.workflowProgress = PROGRESS_MAP[type];
  if (COMPLETED_TYPES.has(type)) { updates.status = "completed"; updates.connected = false; }
  if (FAILED_TYPES.has(type)) { updates.status = "failed"; updates.connected = false; }
  if (STARTED_TYPES.has(type)) updates.status = "running";
  updates.tools = deriveTools(events);
  updates.approvals = deriveApprovals(events);
  const m = deriveMetrics(events);
  updates.promptTokens = m.promptTokens;
  updates.completionTokens = m.completionTokens;
  updates.totalTokens = m.totalTokens;
  updates.estimatedCost = m.estimatedCost;
  set(() => updates);
};

export const usePipelineStore = create<PipelineStore>()((set, get) => ({
  ...initialState(),

  setConnected: (connected) => set({ connected }),
  setRunId: (runId) => set({ runId }),
  setMode: (mode) => set({ mode }),
  setStatus: (status) => set({ status }),
  setRequirements: (requirements) => set({ requirements }),

  startRun: () => set({ ...initialState(), status: "running", startTime: Date.now() }),
  endRun: () => set({ status: "completed", endTime: Date.now(), connected: false }),
  reset: () => set(initialState()),

  approveRequest: (id) => set((state) => ({ approvals: state.approvals.filter((a) => a.id !== id) })),
  denyRequest: (id) => set((state) => ({ approvals: state.approvals.filter((a) => a.id !== id) })),

  addEvent: (event) => {
    const state = get();
    const events = [...state.events, event].slice(-2000);
    const updates: Partial<PipelineStore> = { events };
    switch (event.type) {
      case "done": updates.status = "completed"; updates.endTime = Date.now(); updates.tools = deriveTools(events); break;
      case "error": updates.status = "failed"; updates.endTime = Date.now(); break;
      case "mode": updates.mode = event.mode; break;
      case "pipeline:start": updates.status = "running"; updates.startTime = Date.now(); updates.sessionId = event.session_id ?? state.sessionId; break;
    }
    updates.tools = deriveTools(events);
    updates.approvals = deriveApprovals(events);
    const m = deriveMetrics(events);
    updates.promptTokens = m.promptTokens;
    updates.completionTokens = m.completionTokens;
    updates.totalTokens = m.totalTokens;
    updates.estimatedCost = m.estimatedCost;
  set(updates as Partial<PipelineStore>);
  },

  disconnect: () => {
    _streamController?.close();
    _streamController = null;
    set((prev) => ({ ...initialState(), status: prev.status === "running" ? "idle" as const : prev.status }));
  },

  connectToWorkflow: (workflowId: string, streamEndpoint?: string) => {
    _streamController?.close();
    const endpoint = streamEndpoint || `/api/delegate/${workflowId}/stream`;
    const url = endpoint.startsWith("http") ? endpoint : `${BACKEND_URL}${endpoint}`;
    set({ ...initialState(), sessionId: workflowId, runId: workflowId, connected: true, status: "running", consoleLines: [{ text: `Session ${workflowId.slice(0, 8)} connected`, type: "system" }] });

    const controller = createReconnectingEventSource(url, {
      eventTypes: PIPELINE_EVENT_TYPES,
      onEvent: (type, data) => {
        const payload = (data ?? {}) as Record<string, unknown>;
        const dataObj = (payload && typeof payload === "object" && "data" in payload) ? (payload.data as Record<string, unknown>) : payload;
        handleEvent(dataObj, type, set, get);
      },
      onError: () => { set((prev) => ({ consoleLines: [...prev.consoleLines, { text: "Stream connection lost, retrying...", type: "stderr" as const }] })); },
    });
    _streamController = controller;
  },

  startWorkflow: async (requirements: string, files?: File[], githubRepo?: string, repoProvider?: string) => {
    _streamController?.close();
    _streamController = null;
    set({ ...initialState(), status: "running", requirements, startTime: Date.now(), consoleLines: [{ text: "Starting pipeline...", type: "system" }] });

    const payload: Record<string, unknown> = { project_id: `project-${Date.now()}`, requirements };
    if (githubRepo) { payload.repo_url = githubRepo; payload.repo_provider = repoProvider || "github"; }
    if (files && files.length > 0) {
      const fileContents: Record<string, string> = {};
      for (const file of files) fileContents[file.name] = await file.text();
      payload.file_contents = fileContents;
    }

    try {
      const { toJobSpecFromPipelineQuickTest } = await import("@/lib/adapters/job-spec");
      const spec = toJobSpecFromPipelineQuickTest(payload);
      const result = await api.post<{ run_id?: string; error?: string; detail?: string }>("/api/jobs", spec);
      if (!result.run_id) {
        const msg = result.error || result.detail || "Failed to start job";
        set((prev) => ({ ...prev, status: "failed", consoleLines: [...prev.consoleLines, { text: `Pipeline failed: ${msg}`, type: "stderr" as const }] }));
        throw new Error(msg);
      }
      const runId = result.run_id;
      get().connectToWorkflow(runId, `/api/delegate/${runId}/stream`);
      return { workflowId: runId, runId };
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown error";
      set((prev) => ({ ...prev, status: "failed", consoleLines: [...prev.consoleLines, { text: `Error: ${message}`, type: "stderr" as const }] }));
      throw error;
    }
  },
}));
