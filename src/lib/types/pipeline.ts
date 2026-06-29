"use client";

/**
 * Pipeline event types — aligned with backend StreamEvent types.
 *
 * Backend emits: ToolExecutionStarted, ToolExecutionCompleted,
 * LLMCallStarted, LLMCallCompleted, etc.
 *
 * We use these directly instead of mapping to internal types.
 * This eliminates the pipeline-event-reducer mapping layer.
 */
export type PipelineEvent =
  | { type: "token"; content: string }
  | { type: "reasoning"; content: string }
  | { type: "tool_calls"; calls: ToolCall[] }
  | { type: "tool_result"; name: string; result: string }
  | { type: "ToolExecutionStarted"; tool_name: string; tool_input: string; trace_id: string; agent_id?: string; session_id?: string }
  | { type: "ToolExecutionCompleted"; tool_name: string; success: boolean; output_preview?: string; trace_id?: string; agent_id?: string; session_id?: string }
  | { type: "ToolProgress"; tool_name: string; content: string; kind?: string }
  | { type: "LLMCallStarted"; model?: string; call_id?: string; round?: number }
  | { type: "LLMCallCompleted"; total_tokens?: number; prompt_tokens?: number; completion_tokens?: number; model?: string }
  | { type: "subagent.spawned"; goal?: string; subagent_id?: string }
  | { type: "subagent.completed"; subagent_id?: string }
  | { type: "subagent.thinking"; thought?: string }
  | { type: "subagent.interrupted"; subagent_id?: string }
  | { type: "approval:required"; id: string; tool: string; args: Record<string, unknown> }
  | { type: "metrics"; prompt_tokens: number; completion_tokens: number; total_tokens: number; estimated_cost_usd: number }
  | { type: "done"; content?: string }
  | { type: "error"; message: string }
  | { type: "mode"; mode: string }
  | { type: "pipeline:start"; session_id?: string; workspace?: string }
  | { type: "phase:enter"; phase: PhaseName; label: string; run_id?: string }
  | { type: "phase:progress"; phase: PhaseName; percent: number; message?: string; cost?: number; tokens?: number }
  | { type: "phase:complete"; phase: PhaseName; status: "passed" | "failed" | "skipped"; duration_s?: number }
  | { type: "phase:skip"; phase: PhaseName; reason: string };

export type PhaseName = "enter" | "analyze" | "setup" | "work" | "review" | "publish" | "persist";

export interface PhaseState {
  name: PhaseName;
  label: string;
  status: "pending" | "running" | "passed" | "failed" | "skipped";
  percent: number;
  message?: string;
  cost?: number;
  tokens?: number;
  duration_s?: number;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface ToolState {
  name: string;
  status: "running" | "completed" | "failed" | "pending";
  startTime?: number;
  endTime?: number;
  args?: Record<string, unknown>;
  output?: string;
  error?: string;
}

export interface ApprovalRequest {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  mode: string;
}

export interface AgentExecutionDetail {
  id: string;
  name: string;
  type: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  currentTask: string | null;
  currentTool: string | null;
  toolCalls: ToolState[];
  reasoning: string[];
  streamOutput: string[];
  output: unknown;
  error?: string;
  startedAt?: string;
  endedAt?: string;
}

export interface GroupedError {
  signature: string;
  type: string;
  message: string;
  count: number;
  occurrences: Array<{
    testName?: string;
    file?: string;
    line?: number;
    message: string;
  }>;
  firstSeen?: string;
  lastSeen?: string;
  severity: "error" | "warning" | "info";
}
