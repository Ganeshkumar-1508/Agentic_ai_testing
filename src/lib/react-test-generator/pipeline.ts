import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { Analyzer } from '@/lib/react-test-generator/analyzer/analyzer';
import { PatternRecognizer } from '@/lib/react-test-generator/recognizer/recognizer';
import { TestGenerator } from '@/lib/react-test-generator/generator/generator';
import { TestExecutor } from '@/lib/react-test-generator/executor/executor';
import { createSessionDir, writeComponentFile, cleanSessionDir, inferComponentName, validateFileType, validateFileSize } from '@/lib/react-test-generator/utils/file-helpers';
import { createLogger } from '@/lib/react-test-generator/utils/logger';
import type { ComponentAnalysis } from '@/lib/react-test-generator/types/analysis';
import type { PatternRecognitionResult } from '@/lib/react-test-generator/types/patterns';
import type { GenerationResult, TestCategory } from '@/lib/react-test-generator/types/generation';
import type { ExecutionResult } from '@/lib/react-test-generator/types/execution';

const logger = createLogger('pipeline');

export interface PipelineSession {
  sessionId: string;
  sessionDir: string;
  componentName: string;
  analysis: ComponentAnalysis | null;
  patterns: PatternRecognitionResult | null;
  generation: GenerationResult | null;
  execution: ExecutionResult | null;
}

export class TestPipeline {
  private analyzer = new Analyzer();
  private recognizer = new PatternRecognizer();
  private generator = new TestGenerator();
  private executor = new TestExecutor();

  private sessions = new Map<string, PipelineSession>();

  /**
   * Step 1: Upload a component file and create a session
   */
  upload(filename: string, content: string): { sessionId: string; componentName: string } {
    logger.info(`Pipeline upload: ${filename}`);

    if (!validateFileType(filename)) {
      throw { error: 'Invalid file type. Allowed: .tsx, .jsx, .ts, .js', code: 'INVALID_FILE_TYPE' };
    }

    if (!validateFileSize(content)) {
      throw { error: 'File too large. Maximum: 500KB', code: 'FILE_TOO_LARGE' };
    }

    const sessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const baseDir = join(tmpdir(), 'react-test-generator-sessions');
    const sessionDir = createSessionDir(sessionId, baseDir);
    writeComponentFile(sessionDir, filename, content);

    const componentName = inferComponentName(filename);

    this.sessions.set(sessionId, {
      sessionId,
      sessionDir,
      componentName,
      analysis: null,
      patterns: null,
      generation: null,
      execution: null,
    });

    logger.info(`Session created: ${sessionId} for ${componentName}`);
    return { sessionId, componentName };
  }

  /**
   * Step 2: Analyze the uploaded component
   */
  analyze(sessionId: string): { analysis: ComponentAnalysis; patterns: PatternRecognitionResult } {
    const session = this.getSession(sessionId);
    logger.info(`Pipeline analyze: ${session.componentName}`);

    const files = readdirSync(session.sessionDir);
    const componentFile = files.find(
      f => f.endsWith('.tsx') || f.endsWith('.jsx') || f.endsWith('.ts') || f.endsWith('.js')
    );

    if (!componentFile) {
      throw { error: 'No component file found in session', code: 'INTERNAL_ERROR' };
    }

    const sourceCode = readFileSync(join(session.sessionDir, componentFile), 'utf-8');

    // Run analysis
    const analysis = this.analyzer.analyze(sourceCode, componentFile);
    session.analysis = analysis;

    // Run pattern recognition
    const patterns = this.recognizer.recognize(analysis);
    session.patterns = patterns;

    logger.info(
      `Analysis complete: ${analysis.props.length} props, ${patterns.patterns.length} patterns`
    );
    return { analysis, patterns };
  }

  /**
   * Step 3: Generate tests
   */
  generate(
    sessionId: string,
    options?: { categories?: string[]; includeSnapshot?: boolean }
  ): GenerationResult {
    const session = this.getSession(sessionId);

    if (!session.analysis || !session.patterns) {
      throw { error: 'Component not yet analyzed. Call analyze first.', code: 'INTERNAL_ERROR' };
    }

    logger.info(`Pipeline generate: ${session.componentName}`);
    const generation = this.generator.generate(session.analysis, session.patterns, {
      categories: options?.categories as TestCategory[] | undefined,
      includeSnapshot: options?.includeSnapshot,
    });

    session.generation = generation;
    logger.info(`Generated ${generation.testCount} tests`);
    return generation;
  }

  /**
   * Step 4: Execute generated tests
   */
  async execute(
    sessionId: string,
    options?: { timeoutMs?: number }
  ): Promise<ExecutionResult> {
    const session = this.getSession(sessionId);

    if (!session.generation) {
      throw { error: 'Tests not yet generated. Call generate first.', code: 'INTERNAL_ERROR' };
    }

    logger.info(`Pipeline execute: ${session.componentName}`);
    const execution = await this.executor.execute(session.generation, {
      timeoutMs: options?.timeoutMs,
    });

    session.execution = execution;

    logger.info(`Execution complete: ${execution.passedTests}/${execution.totalTests} passed`);
    return execution;
  }

  /**
   * Run the full pipeline: upload -> analyze -> generate -> execute
   */
  async runFullPipeline(
    filename: string,
    content: string,
    options?: { categories?: string[]; includeSnapshot?: boolean; timeoutMs?: number }
  ): Promise<{
    sessionId: string;
    componentName: string;
    analysis: ComponentAnalysis;
    patterns: PatternRecognitionResult;
    generation: GenerationResult;
    execution: ExecutionResult;
  }> {
    const { sessionId, componentName } = this.upload(filename, content);
    const { analysis, patterns } = this.analyze(sessionId);
    const generation = this.generate(sessionId, options);
    const execution = await this.execute(sessionId, options);

    return {
      sessionId,
      componentName,
      analysis,
      patterns,
      generation,
      execution,
    };
  }

  /**
   * Clean up a session
   */
  cleanup(sessionId: string): void {
    const session = this.sessions.get(sessionId);
    if (session) {
      cleanSessionDir(session.sessionDir);
      this.sessions.delete(sessionId);
      logger.info(`Session cleaned up: ${sessionId}`);
    }
  }

  /**
   * Get a session by ID, throwing if not found
   */
  private getSession(sessionId: string): PipelineSession {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw { error: `Session not found: ${sessionId}`, code: 'INTERNAL_ERROR' };
    }
    return session;
  }
}

// Singleton
export const testPipeline = new TestPipeline();
