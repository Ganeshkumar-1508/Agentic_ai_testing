// API types for the test generation pipeline endpoints

import type { ComponentAnalysis } from './analysis';
import type { GenerationOptions, GenerationResult } from './generation';
import type { ExecutionOptions, ExecutionResult } from './execution';

export interface UploadResponse {
  sessionId: string;
  componentName: string;
  detectedExports: string[];
  fileSize: number;
}

export interface AnalyzeResponse {
  sessionId: string;
  analysis: ComponentAnalysis;
}

export interface GenerateTestsResponse {
  sessionId: string;
  generatedSource: string;
  testCount: number;
  categories: string[];
}

export interface ExecuteTestsResponse {
  sessionId: string;
  execution: ExecutionResult;
}

export interface PipelineResponse {
  sessionId: string;
  componentName: string;
  analysis: ComponentAnalysis;
  generatedSource: string;
  execution: ExecutionResult;
  warnings: string[];
}

export interface ApiError {
  error: string;
  code: 'INVALID_FILE_TYPE' | 'FILE_TOO_LARGE' | 'SYNTAX_ERROR' | 'NOT_A_REACT_COMPONENT' | 'EXECUTION_TIMEOUT' | 'INTERNAL_ERROR';
  details?: string;
}
