# Executor Module — Implementation Steps

## Context

- Type defs read: `execution.ts`, `generation.ts`
- Utils reviewed: `constants.ts`, `logger.ts`, `file-helpers.ts`
- Existing patterns studied from `generator/generator.ts` (import path conventions, logger usage)

## Files Created

### 1. `src/lib/react-test-generator/executor/executor.ts`

Main `TestExecutor` class with:

- **`execute()`** — entry point that creates sandbox temp dir, writes test file + vitest config, runs vitest, parses results, cleans up
- **`runVitestInSandbox()`** — forks `vitest/vitest.mjs` as child process with JSON reporter, handles SIGTERM timeout + grace period
- **`parseVitestJsonOutput()`** — primary parser for vitest JSON reporter output (handles both standard `testResults.assertionResults` and alternate flat formats)
- **`parseStdoutFallback()`** — fallback parser using stdout symbol matching (✓/×/✗/FAIL/PASS) and summary regex extraction

Key design decisions:

- ES module compatible `import { fork } from 'child_process'` style
- Uses `require.resolve('vitest/vitest.mjs')` for cross-platform vitest binary resolution
- Temp cleanup via `rmSync` in `finally` block with 2s `setTimeout` delay to allow async reporter flush
- Imports use `@/lib/react-test-generator/...` path aliases
- `import type` for type-only imports

### 2. `src/lib/react-test-generator/executor/index.ts`

Barrel export:

```ts
export { TestExecutor } from "./executor";
```

## Verification

- `npx tsc --noEmit` — no errors from executor module files
- Only pre-existing TS error: `src/lib/agent-orchestration-service.ts(384,24)` (unrelated)

## API Surface

```ts
const executor = new TestExecutor();
const result: ExecutionResult = await executor.execute(generationResult, {
  timeoutMs?: number,
  memoryLimitMb?: number,
  collectCoverage?: boolean,
  updateSnapshots?: boolean,
});
```
