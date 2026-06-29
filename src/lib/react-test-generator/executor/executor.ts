import { spawn } from 'child_process';
import { join } from 'path';
import { existsSync, writeFileSync, mkdirSync, rmSync, readFileSync } from 'fs';
import { tmpdir } from 'os';
import type { ExecutionResult, TestResult, ExecutionOptions } from '@/lib/react-test-generator/types/execution';
import type { GenerationResult } from '@/lib/react-test-generator/types/generation';
import { DEFAULT_EXECUTION_OPTIONS } from '@/lib/react-test-generator/utils/constants';
import { createLogger } from '@/lib/react-test-generator/utils/logger';

const logger = createLogger('executor');

export class TestExecutor {
  /**
   * Execute generated tests in a sandboxed child process.
   * Writes the test file to a temp directory, runs vitest with JSON output,
   * parses results, and cleans up.
   */
  async execute(
    generationResult: GenerationResult,
    options?: ExecutionOptions,
  ): Promise<ExecutionResult> {
    const opts = { ...DEFAULT_EXECUTION_OPTIONS, ...options };
    const sessionDir = join(tmpdir(), `react-test-generator-${Date.now()}`);

    logger.info(`Starting test execution in ${sessionDir}`);
    const startTime = Date.now();

    try {
      // Create sandbox directory
      if (!existsSync(sessionDir)) {
        mkdirSync(sessionDir, { recursive: true });
      }

      // Write the generated test file
      const testFilePath = join(sessionDir, 'generated.test.tsx');
      writeFileSync(testFilePath, generationResult.generatedSource, 'utf-8');

      // Write a minimal vitest config for this session
      const configPath = join(sessionDir, 'vitest.config.ts');
      writeFileSync(
        configPath,
        `
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [],
    testTimeout: ${opts.timeoutMs ?? 60000},
    reporters: ['json'],
    outputFile: './test-results.json',
  },
});
`,
        'utf-8',
      );

      // Run vitest via child_process.fork
      const result = await this.runVitestInSandbox(sessionDir, opts);

      const durationMs = Date.now() - startTime;
      logger.info(
        `Execution completed in ${durationMs}ms: ${result.passedTests}/${result.totalTests} passed`,
      );

      return {
        ...result,
        durationMs,
      };
    } catch (err) {
      const durationMs = Date.now() - startTime;
      const message = err instanceof Error ? err.message : String(err);
      logger.error('Execution failed', { error: message });

      return {
        overallStatus: 'error',
        totalTests: 0,
        passedTests: 0,
        failedTests: 0,
        durationMs,
        results: [],
        errors: [message],
      };
    } finally {
      // Cleanup: remove temp files after a delay to allow async reporter flush
      setTimeout(() => {
        try {
          if (existsSync(sessionDir)) {
            rmSync(sessionDir, { recursive: true, force: true });
            logger.debug(`Cleaned up session directory: ${sessionDir}`);
          }
        } catch (cleanupErr) {
          logger.warn('Cleanup failed', cleanupErr);
        }
      }, 2000);
    }
  }

  private runVitestInSandbox(
    sessionDir: string,
    opts: ExecutionOptions,
  ): Promise<{
    overallStatus: ExecutionResult['overallStatus'];
    totalTests: number;
    passedTests: number;
    failedTests: number;
    results: TestResult[];
    errors: string[];
  }> {
    return new Promise((resolve, reject) => {
      const timeoutMs = opts.timeoutMs ?? 60000;

      // Use npx to invoke vitest (portable across all platforms)
      const isWindows = process.platform === 'win32';
      const npxCmd = isWindows ? 'npx.cmd' : 'npx';

      const child = spawn(
        npxCmd,
        ['vitest', 'run', '--config', './vitest.config.ts', '--reporter', 'json'],
        {
          cwd: sessionDir,
          stdio: ['pipe', 'pipe', 'pipe'],
          shell: true,
          timeout: timeoutMs,
          env: {
            ...process.env,
            NODE_ENV: 'test',
            CI: 'true',
          },
        },
      );

      let stdout = '';
      let stderr = '';

      child.stdout?.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      child.stderr?.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      const timer = setTimeout(() => {
        child.kill('SIGTERM');
        resolve({
          overallStatus: 'timed-out',
          totalTests: 0,
          passedTests: 0,
          failedTests: 0,
          results: [],
          errors: ['Test execution timed out after ' + timeoutMs + 'ms'],
        });
      }, timeoutMs + 5000); // Allow 5s grace for vitest to shutdown

      child.on('close', (code) => {
        clearTimeout(timer);

        // Try to read the JSON output file
        const resultsPath = join(sessionDir, 'test-results.json');
        if (existsSync(resultsPath)) {
          try {
            const jsonContent = readFileSync(resultsPath, 'utf-8');
            const parsed = JSON.parse(jsonContent);

            const results = this.parseVitestJsonOutput(parsed);
            const passedTests = results.filter((r) => r.status === 'passed').length;
            const failedTests = results.filter((r) => r.status === 'failed').length;

            resolve({
              overallStatus: failedTests > 0 ? 'failed' : 'passed',
              totalTests: results.length,
              passedTests,
              failedTests,
              results,
              errors: results.filter((r) => r.errorMessage).map((r) => r.errorMessage!),
            });
            return;
          } catch (parseErr) {
            // Fall through to stdout parsing
          }
        }

        // Fallback: parse stdout for test results summary
        if (stdout) {
          const result = this.parseStdoutFallback(stdout, stderr);
          resolve(result);
        } else if (code === 0) {
          resolve({
            overallStatus: 'passed',
            totalTests: 1,
            passedTests: 1,
            failedTests: 0,
            results: [{ name: 'all tests', status: 'passed', durationMs: 0 }],
            errors: [],
          });
        } else {
          resolve({
            overallStatus: 'error',
            totalTests: 0,
            passedTests: 0,
            failedTests: 0,
            results: [],
            errors: stderr ? [stderr] : [`vitest exited with code ${code}`],
          });
        }
      });

      child.on('error', (err) => {
        clearTimeout(timer);
        reject(err);
      });
    });
  }

  private parseVitestJsonOutput(parsed: any): TestResult[] {
    const results: TestResult[] = [];

    try {
      // Vitest JSON reporter output structure
      const testResults = parsed?.testResults ?? [];
      for (const suite of testResults) {
        const assertionResults = suite?.assertionResults ?? [];
        for (const assertion of assertionResults) {
          results.push({
            name: assertion?.title ?? 'unknown',
            status: assertion?.status === 'passed' ? 'passed' : 'failed',
            durationMs: assertion?.duration ?? 0,
            errorMessage: assertion?.failureMessages?.[0],
            errorStack: assertion?.failureMessages?.join('\n'),
          });
        }
      }
    } catch {
      // If parsing structured output fails, return empty
    }

    // If no testResults array, try alternate vitest JSON format
    if (results.length === 0 && parsed?.numTotalTests) {
      for (let i = 0; i < (parsed.numTotalTests ?? 0); i++) {
        const test = parsed?.testResults?.[i];
        if (test) {
          results.push({
            name: test.title ?? `test #${i + 1}`,
            status: test.status === 'pass' ? 'passed' : 'failed',
            durationMs: test.duration ?? 0,
          });
        }
      }
    }

    return results;
  }

  private parseStdoutFallback(
    stdout: string,
    stderr: string,
  ): {
    overallStatus: ExecutionResult['overallStatus'];
    totalTests: number;
    passedTests: number;
    failedTests: number;
    results: TestResult[];
    errors: string[];
  } {
    const results: TestResult[] = [];
    const errors: string[] = [];

    if (stderr) {
      errors.push(stderr);
    }

    // Try to extract test names and status from standard vitest output
    const testLines = stdout.split('\n').filter((line) => line.includes('✓') || line.includes('×') || line.includes('✗') || line.includes('FAIL') || line.includes('PASS'));

    for (const line of testLines) {
      const isPass = line.includes('✓') || line.includes('PASS');
      const isFail = line.includes('×') || line.includes('✗') || line.includes('FAIL');

      // Extract test name (text after the symbol)
      const nameMatch = line.replace(/[✓×✗]/g, '').trim();

      if (nameMatch) {
        results.push({
          name: nameMatch,
          status: isPass ? 'passed' : 'failed',
          durationMs: 0,
        });
      }
    }

    const passedTests = results.filter((r) => r.status === 'passed').length;
    const failedTests = results.filter((r) => r.status === 'failed').length;

    // Check for test summary line
    const summaryMatch = stdout.match(/Tests\s+(\d+)\s+passed\s*\/\s*(\d+)\s+failed/);
    const totalMatch = stdout.match(/Tests\s+(\d+)/);

    return {
      overallStatus: failedTests > 0 ? 'failed' : passedTests > 0 ? 'passed' : 'error',
      totalTests: totalMatch ? parseInt(totalMatch[1]) : results.length,
      passedTests,
      failedTests,
      results,
      errors,
    };
  }
}
