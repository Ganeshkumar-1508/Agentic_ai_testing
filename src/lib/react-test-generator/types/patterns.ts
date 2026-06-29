// Pattern types for recognizer module

export type PatternCategory =
  | 'controlled-input'
  | 'async-data'
  | 'loading-state'
  | 'error-state'
  | 'empty-state'
  | 'compound-component'
  | 'slot-pattern'
  | 'as-child-pattern'
  | 'cva-variants'
  | 'portal-usage'
  | 'form-submission'
  | 'context-consumer'
  | 'effect-cleanup'
  | 'ref-usage'
  | 'conditional-rendering'
  | 'list-rendering';

export interface PatternMatch {
  category: PatternCategory;
  confidence: number; // 0-1
  details?: Record<string, unknown>;
}

export interface PatternRecognitionResult {
  patterns: PatternMatch[];
  componentName: string;
  summary: string[];
}
