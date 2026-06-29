# Candidate 26: Isolate all testing-specific code into a `harness/testing/` sub-package

**Strength**: Strong | **Category**: separation of concerns / domain isolation

---

## Research sources (10)

### Agent harness domain isolation patterns

1. **Hermes Agent** — Testing is NOT part of the core harness. Hermes has no `flaky_detector.py`, `coverage_gaps.py`, or `quality_score.py` at the harness root. Testing capability comes through skills and MCP servers — external to the core. https://github.com/NousResearch/hermes-agent

2. **Pantheon** — No testing-specific modules in the core. Testing is done through scheduled ingestion + skills. The core is agent loop, memory, MCP, and sources. https://github.com/r3moteBee/pantheon

3. **OpenCode** — No testing modules in the Go binary. Testing is a separate concern. https://github.com/opencode-ai/opencode

4. **Citadel** — No testing-specific core modules. Quality gates are hooks, not built-in analysis. https://github.com/SethGammon/Citadel

5. **AgentKit (inngest)** — No testing modules. Agents + networks + routers + state + tracing. Testing is a downstream concern. https://github.com/inngest/agent-kit

6. **CONTEXT.md** — The domain glossary defines agents, runs, tools, orchestrator, subagents, etc. Testing is mentioned only once ("test files TTL"). The domain model does not center on testing.

7. **CONTEXT.md — Tool Catalog** — Tools are generic primitives. `bash` runs tests but it also compiles code, installs packages, starts servers. Testing is an adapter, not the identity.

8. **Codebase audit — 20+ backend modules, 5 frontend routes, 15+ components, 8 DB tables are testing-specific** (see below)

9. **Product evolution** — The project evolved from "testing agent" (TestAI) to "general agent harness" (Harness). The testing-specific code is the remaining legacy from the testing era.

10. **Candidate 1 precedent** — Full-stack rebrand from testing to agent harness identity. This candidate is the code-level implementation of that rebrand.

---

## Codebase evidence

### Testing-specific code across the entire stack

#### Backend: 20+ modules at harness root level

| Module | Lines | Purpose | Should move to |
|---|---|---|---|
| `flaky_detector.py` | 136 | Flaky test scoring + quarantine | `testing/detectors/` |
| `flaky_auto_quarantine.py` | ~30 | Scheduled quarantine sweeps | `testing/detectors/` |
| `coverage_gaps.py` | 172 | Coverage report parsing + gap analysis | `testing/analyzers/` |
| `defect_prediction.py` | 107 | Risk scoring per module | `testing/analyzers/` |
| `quality_score.py` | 257 | Composite quality score | `testing/scorers/` |
| `quality_policy.py` | ~50 | Quality gate enforcer | `testing/gates/` |
| `risk_scoring.py` | ~30 | PR risk scoring | `testing/scorers/` |
| `rca.py` | ~200 | Root cause analysis | `testing/analyzers/` |
| `test_generator.py` | ~30 | LLM test generation | `testing/generators/` |
| `test_plan.py` | ~150 | Test plan generation | `testing/generators/` |
| `test_impact.py` | ~80 | Impact analysis | `testing/analyzers/` |
| `visual_testing.py` | ~60 | Visual diff testing | `testing/runners/` |
| `results_store.py` | ~80 | Test results persistence | `testing/storage/` |
| `daily_digest.py` | ~80 | Daily quality digest | `testing/reporting/` |
| `sprint_trends.py` | ~80 | Sprint trend analysis | `testing/reporting/` |
| `load_tester.py` | ~60 | Load testing | `testing/runners/` |
| `triage.py` | ~80 | Test triage | `testing/triage/` |
| `testai_constants.py` | ~50 | Constants | `testing/_constants.py` |
| `evidence.py` | ~100 | Evidence collection | `testing/analyzers/` |
| `tools/coverage_intelligence.py` | ~200 | Coverage tool | `testing/tools/` |
| `tools/visual_diff_tool.py` | ~300 | Visual diff tool | `testing/tools/` |
| `tools/testcases_service.py` | ~150 | Test cases service | `testing/services/` |

#### Frontend: 5 routes + 15+ components

| Route | Purpose | Should move to |
|---|---|---|
| `/test-cases` | Test case management | `(dashboard)/testing/test-cases` |
| `/flaky-tests` | Flaky test dashboard | `(dashboard)/testing/flaky-tests` |
| `/quality` | Quality dashboard | `(dashboard)/testing/quality` |
| `/visual-testing` | Visual testing | `(dashboard)/testing/visual-testing` |
| `/load-testing` | Load testing | `(dashboard)/testing/load-testing` |

Components: `FlakyScoreTrend`, `FlakyTestsTable`, `TestCaseCard`, `TestCaseGroup`, `TestPlanList`, `TestResults`, `TestResultsTable`, `TestFilterBar`, `CoverageChart`, `CoverageGapsCard`, `DefectPredictionCard`, `QualityScoreGauge`, `QualityTrendChart`, `RCACard`, `TraceabilityCard`, `SprintTrends`, `SelfHealingCard`, `DigestAttention`, `DigestChannels`, `DigestCostBar`, `DigestFailures`, `DigestHero`, `DigestInsights`, `DigestMetricRow`, `DigestTimeline`, `SessionHealthPanel`

#### Database: 8 testing-specific tables

| Table | Purpose | Prefix |
|---|---|---|
| `test_results` | Test execution results | `testing_` |
| `flaky_tests` | Flaky test tracking | `testing_` |
| `coverage_reports` | Coverage data | `testing_` |
| `test_cases` | Test case definitions | `testing_` |
| `test_plans` | Test plan definitions | `testing_` |
| `test_impact` | Test impact analysis | `testing_` |
| `requirements` | Requirements | `testing_` |
| `requirement_links` | Req-to-test mapping | `testing_` |

### The contraction

Move ALL testing-specific code into `backend/harness/testing/`:

```
backend/harness/testing/
├── __init__.py          # Exports
├── _constants.py        # Constants from testai_constants.py
├── detectors/
│   ├── flaky.py         # flaky_detector.py + flaky_auto_quarantine.py
├── analyzers/
│   ├── coverage.py      # coverage_gaps.py
│   ├── defects.py       # defect_prediction.py
│   ├── impact.py        # test_impact.py
│   ├── rca.py           # rca.py
│   └── evidence.py      # evidence.py
├── scorers/
│   ├── quality.py       # quality_score.py
│   └── risk.py          # risk_scoring.py
├── gates/
│   └── policy.py        # quality_policy.py
├── generators/
│   ├── tests.py         # test_generator.py
│   └── plans.py         # test_plan.py
├── runners/
│   ├── visual.py        # visual_testing.py
│   └── load.py          # load_tester.py
├── storage/
│   └── results.py       # results_store.py
├── reporting/
│   ├── digest.py        # daily_digest.py
│   └── sprint.py        # sprint_trends.py
├── triage/
│   └── triage.py        # triage.py
├── services/
│   └── testcases.py     # testcases_service.py
└── tools/
    ├── coverage.py      # coverage_intelligence.py
    └── visual_diff.py   # visual_diff_tool.py
```

The harness root loses 20+ testing-specific files. The frontend gets a `/testing/*` route group. The database tables get `testing_` prefix. The harness core becomes purely about agent orchestration, tool execution, memory, and event streaming — with testing as an optional module.
