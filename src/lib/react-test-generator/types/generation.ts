// Generation types for generator module

import type { ComponentAnalysis } from './analysis';
import type { PatternRecognitionResult } from './patterns';

export type TestCategory =
  | 'render'
  | 'props'
  | 'state'
  | 'events'
  | 'async'
  | 'edge-cases'
  | 'accessibility'
  | 'snapshot'
  | 'integration';

export interface TestCaseTemplate {
  category: TestCategory;
  name: string;
  description: string;
  template: string;
  requiredFindings: string[];
  priority: number;
}

export interface GeneratedTest {
  category: TestCategory;
  name: string;
  content: string;
  description: string;
}

export interface MockDefinition {
  moduleName: string;
  mockPath: string;
  mockImplementation: string;
}

export interface GenerationOptions {
  categories?: TestCategory[];
  includeSnapshot?: boolean;
  mockConfig?: Record<string, unknown>;
  additionalContext?: string;
}

export interface GenerationResult {
  generatedSource: string;
  testCount: number;
  categories: TestCategory[];
  specs: GeneratedTest[];
  mocks: MockDefinition[];
  coverageEstimated: number;
}
