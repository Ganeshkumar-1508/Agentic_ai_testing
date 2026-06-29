// Execution types for executor module

export type TestStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'skipped';

export interface TestResult {
  name: string;
  status: 'passed' | 'failed';
  durationMs: number;
  errorMessage?: string;
  errorStack?: string;
}

export interface ExecutionOptions {
  timeoutMs?: number;
  memoryLimitMb?: number;
  collectCoverage?: boolean;
  updateSnapshots?: boolean;
}

export interface ExecutionResult {
  overallStatus: 'passed' | 'failed' | 'timed-out' | 'error';
  totalTests: number;
  passedTests: number;
  failedTests: number;
  durationMs: number;
  results: TestResult[];
  errors: string[];
  coverage?: {
    lines: number;
    branches: number;
    functions: number;
    statements: number;
  };
}
