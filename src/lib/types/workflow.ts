export type AgentTypeV2 =
  | "research"
  | "env_setup"
  | "requirements_analyst"
  | "task_decomposer"
  | "test_generator"
  | "test_data_generator"
  | "test_runner"
  | "reporter";

export interface AgentState {
  id: string;
  name: string;
  type: AgentTypeV2;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  currentTask: string | null;
  output?: unknown;
  error?: string;
  logPath?: string;
}

export interface LogEntry {
  id: string;
  agentId: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface ConsoleLine {
  text: string;
  type: "stdout" | "stderr" | "system";
  agentId?: string;
  timestamp?: string;
}

export interface TestResults {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  duration: number;
  executionResults?: Array<{
    testName: string;
    testType: string;
    passed: number;
    failed: number;
    skipped: number;
    duration: number;
    output: string;
    tests: Array<{
      name: string;
      status: string;
      duration: number;
      error?: string;
      retryCount?: number;
      healedByAgent?: boolean;
      isQuarantined?: boolean;
    }>;
  }>;
}

export interface ResearchOutputData {
  projectSummary: string;
  techStack: Record<string, unknown>;
  aiPatterns: Array<{
    name: string;
    detected: boolean;
    confidence: string;
    frameworks: string[];
    files?: string[];
  }>;
  environment: Record<string, unknown>;
  recommendedFocus: string[];
}
