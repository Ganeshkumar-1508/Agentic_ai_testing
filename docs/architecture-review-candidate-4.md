# Candidate 4: Consolidate 13 orphaned quality/testing modules into a `harness/eval/` sub-package

**Strength**: Worth exploring | **Category**: module organization / pattern duplication

---

## Research sources (10)

### Harness engineering module structure patterns

1. **Awesome Harness Engineering (walkinglabs + Jiaaqiliu)** — 883 entities across agent infrastructure. The field organizes into: Foundations → Context/Memory → Guardrails/Safety → Specs/Workflow → **Evals/Observability** → Runtimes/Harnesses → MCP. Quality and testing are a sub-domain of Evals/Observability, not a parallel top-level concern. https://github.com/walkinglabs/awesome-harness-engineering

2. **Microsoft Agentic Harness Architecture** — Observability is a single pipeline with structured spans (`agent.turn`, `agent.tool_call`, `rag.retrieve`, `knowledge.query`). Quality metrics are emitted as custom metrics (`harness.agent.tokens`, `harness.tools.invocations`) from within the harness instrumentation — not from separate quality modules. https://mckruz.github.io/microsoft-agentic-harness/architecture/05-observability.html

3. **Learn Harness Engineering — Lecture 11** — "Create a trace for each harness session, a span for each task." Quality is measured through structured observability (traces, metrics, logs), not through parallel quality-scoring modules. https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/

4. **Martinfowler/Thoughtworks — "Assessing internal quality while coding with an agent"** — Quality checks move into the loop (inside the harness event system), not as external after-the-fact analysis. https://martinfowler.com/articles/exploring-gen-ai/ccmenu-quality.html

5. **OpenAI — "Testing Agent Skills Systematically with Evals"** — Testing is done through evals, which are part of the observability/evaluation layer. The eval system is a sub-domain, not a top-level parallel structure. https://developers.openai.com/blog/eval-skills/

6. **OpenHands — Agent Canvas architecture** — All quality signals come through the agent event stream, not through separate quality modules. https://github.com/All-Hands-AI/OpenHands

7. **paddo.dev — Agent Harnesses: DIY to Product** — "The harness automates execution, not decisions. Which features to build, whether code is correct, when to ship — these remain human responsibilities." Quality assessment is a judgment layer inside the harness, not a separate module tree. https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

8. **htek.dev — 8 Harnesses Compared** — No production harness has standalone "coverage_gaps.py" or "flaky_detector.py" at the harness root. Quality signals come from the observability pipeline. https://htek.dev/articles/all-agent-harnesses-live-comparison

9. **Codebase audit — 13 orphaned testing modules** (see below)

10. **CONTEXT.md — Tool Catalog** — The harness exposes tools like `memory`, `skill`, `tool_search` as primitives. Quality evaluation should be a tool/skill, not a root-level module.

---

## Codebase evidence

### 13 testing-specific modules at `backend/harness/*.py` root

| Module | Lines | Symbols | Function | Data access pattern |
|---|---|---|---|---|
| `coverage_gaps.py` | 172 | 7 | Parse coverage reports, persist, find gaps | Raw SQL x3 |
| `flaky_detector.py` | 136 | 10 | Compute flaky scores, auto-quarantine, notify | Raw SQL x5 |
| `flaky_auto_quarantine.py` | ~20 | 7 | Scheduled quarantine sweeps | Raw SQL |
| `quality_score.py` | 257 | 15 | Composite quality score from 5 weighted factors | Raw SQL x10 |
| `quality_policy.py` | ~50 | 11 | Quality gate policy enforcer | Raw SQL |
| `defect_prediction.py` | 107 | 7 | Risk scores per module (failure rate + coverage) | Raw SQL x6 |
| `test_plan.py` | ~150 | 33 | Test plan generation algorithm | Raw SQL |
| `test_impact.py` | ~80 | 14 | Impact analysis for changed files | Raw SQL |
| `test_generator.py` | ~30 | 9 | Test case generation | Raw SQL |
| `visual_testing.py` | ~60 | 10 | Visual diff/snapshot testing | Raw SQL |
| `rca.py` | ~200 | 18 | Root cause analysis for failures | Raw SQL |
| `risk_scoring.py` | ~30 | 6 | Risk scoring for PRs | Raw SQL |
| `results_store.py` | ~80 | 9 | Test results persistence | Raw SQL |

**Total: ~1,400 lines, ~156 symbols, ~30+ raw SQL queries**

### Compare to harness core modules

| Module | Lines | Symbols | Integration |
|---|---|---|---|
| `orchestrator.py` | ~400 | 39 | Uses events, middleware, checkpoint, services |
| `events.py` | ~500 | 44 | Central event bus, all modules emit through it |
| `dispatcher.py` | ~200 | 18 | Uses channels, hook pipeline, services |

### The gap

All 13 testing modules share the same pattern: `async def fn(db: Any, ...) -> dict[str, Any]` with raw SQL. None of them use:
- The `events.py` event bus for emitting quality signals
- The `middleware/` pipeline for instrumentation
- The `services/` layer for business logic
- The `observability/` sub-package for OpenTelemetry spans
- Shared query utilities from `db_helpers.py`

They're **orphans** — left behind from the testing-era architecture, replicating the same data-access pattern 13 times without integration into the harness core.

### The deletion test

Delete all 13 modules. The complexity doesn't vanish — it reappears across the API routers (which call these modules) and the frontend pages (which display the results). But the pattern IS worth fixing: the complexity could be concentrated in `harness/eval/` with one shared data-access layer, one shared event emission point, and one shared error-handling pattern.
