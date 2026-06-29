# Candidate 20: Remove or relocate the 1,100-line test generator subsystem from the agent harness lib

**Strength**: Worth exploring | **Category**: legacy code / testing-era leftover

---

## Research sources (10)

### Agent harness frontend library patterns

1. **Pantheon (web-based)** — Frontend is a Vite + React dashboard. No test generator in the lib. The frontend is for monitoring and configuration only. https://github.com/r3moteBee/pantheon

2. **OpenHands (web-based)** — Frontend has `features/`, `providers/`, `shared/`, `ui/` components. No embedded test generator. Agent-related tooling is in the backend. https://github.com/All-Hands-AI/OpenHands

3. **Hermes Agent (web-based gateway)** — Frontend TUI with skills and memory. No test generation in the UI layer. Agent capabilities are in the backend. https://github.com/NousResearch/hermes-agent

4. **a0 Agent Harness** — Web UI has 3 surfaces: Dashboard, Config Panel, State Store. No test generation. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

5. **OpenCode** — TUI-based frontend. No embedded test generator. https://github.com/opencode-ai/opencode

6. **Citadel** — Frontend is a `/cost` and `/dashboard` console. No test generator. https://github.com/SethGammon/Citadel

7. **Awesome Harness Engineering — Harness taxonomy** — The harness field organizes into: Context/Memory, Guardrails/Safety, Specs/Workflow, Evals/Observability, Runtimes/Harnesses. A test generator is part of the harness evaluation layer, not the frontend library. https://github.com/Jiaaqiliu/Awesome-Harness-Engineering

8. **Candidate 4 precedent** — The backend had 13 orphaned testing-specific modules (C4). The frontend has its own testing-era leftover: `react-test-generator/` in `src/lib/`.

9. **Codebase audit — `react-test-generator` ~1,100 lines, 15 files, 1 consumer** (see below)

10. **CONTEXT.md — Tool Catalog** — Tools are defined in the backend harness, not in the frontend lib. A test generator should be a backend tool, not a frontend library.

---

## Codebase evidence

### The frontend's testing-era leftover

```
src/lib/react-test-generator/        (~1,100 lines, 15 files)
├── analyzer/
│   ├── analyzer.ts                  (452 lines)
│   └── index.ts                     (1 line)
├── executor/
│   ├── executor.ts                  (272 lines)
│   └── index.ts                     (1 line)
├── generator/
│   ├── generator.ts                 (138 lines)
│   ├── index.ts                     (2 lines)
│   ├── mock-builder.ts             (43 lines)
│   └── templates.ts                (175 lines)
├── recognizer/
│   ├── index.ts                     (1 line)
│   └── recognizer.ts               (207 lines)
├── types/
│   ├── analysis.ts                  (81 lines)
│   ├── api.ts                       (37 lines)
│   ├── execution.ts                 (30 lines)
│   ├── generation.ts                (46 lines)
│   └── patterns.ts                  (28 lines)
├── utils/
│   ├── constants.ts                (40 lines)
│   ├── file-helpers.ts             (45 lines)
│   ├── index.ts                     (3 lines)
│   └── logger.ts                    (29 lines)
├── index.ts                         (11 lines)
└── pipeline.ts                      (173 lines)
```

### Consumer count: 1

Only one file imports from `react-test-generator`:
- `src/app/api/testcases/component/pipeline/route.ts` — a single API route

This is a complete test generation pipeline (analyze → recognize patterns → generate tests → execute) sitting in the frontend lib directory. It's from the testing era of the project. It consumes ~1,100 lines of frontend bundle and adds complexity to `src/lib/` for a single API route.

### The deletion test

Delete `src/lib/react-test-generator/`. One API route (`src/app/api/testcases/component/pipeline/route.ts`) breaks. Move that route's logic to a backend endpoint. The frontend lib drops from ~3,500 lines to ~2,400 lines — a 31% reduction. The 15 files reduce to 0.

### The contraction

Option A: **Delete** — Move the test generation logic to the backend (as a harness tool similar to the existing `test_generator.py`). Remove `react-test-generator/` from the frontend entirely. The API route becomes a thin proxy to the backend.

Option B: **Preserve as-is** — Keep it in place but document that it's a legacy subsystem not related to the agent harness core. Add a README to `react-test-generator/` explaining its purpose and that it's a testing-era leftover.
