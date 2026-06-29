# Decision Memo: Replace Swarms with In-House Agent Harness Control Plane

**Date:** 2026-05-22  
**Decision Type:** Architecture / Reliability / Execution Governance  
**Decision Scope:** Agentic test-execution control plane (not test authoring UX)

---

## 1) Executive Decision

**Recommendation:** **Conditional Go**  
**Confidence:** **Medium**  
**Why:** Lane 1 frameworks are materially stronger than current Swarms-based baseline on deterministic orchestration primitives and run observability; however, Lane 2 evidence is incomplete under the evidence rule (official + independent) and should remain benchmark-only unless additional evidence is collected.

**Top 3 unresolved risks before full Go:**
1. **Evidence completeness risk (Lane 2):** insufficient independent evidence for deterministic replay/auditability claims.
2. **Adapter parity risk:** migration can regress behavior if adapters do not preserve today’s pipeline semantics.
3. **Operational replay risk:** current system lacks first-class replay manifest/trace export standard; must be implemented in Phase 1/2.

---

## 2) Context and Current Baseline (Repo-Aligned)

This memo evaluates replacing the Swarms orchestrator with a custom adapter-based Agent Harness control plane, prioritizing **reliability + determinism** in agentic test execution.

### 2.1 Current baseline files and observed determinism gaps

Primary baseline files:
- [`backend/app/agents/swarm_manager.py`](backend/app/agents/swarm_manager.py)
- [`src/lib/agent-orchestration-service.ts`](src/lib/agent-orchestration-service.ts)
- [`backend/app/api/v1/endpoints/agents.py`](backend/app/api/v1/endpoints/agents.py)
- [`src/lib/services/log-storage-service.ts`](src/lib/services/log-storage-service.ts)
- [`src/app/api/workflow/route.ts`](src/app/api/workflow/route.ts)
- [`src/app/api/workflow/[id]/stream/route.ts`](src/app/api/workflow/[id]/stream/route.ts)
- [`backend/harness/agent.py`](backend/harness/agent.py)
- [`backend/api/server.py`](backend/api/server.py)

Observed gaps (aligned to determinism/reliability objective):
- **Non-deterministic IDs and run identity:** runtime IDs built with time/random (e.g., `Date.now()` + `Math.random()`), which blocks reproducible run identity and deterministic replays.
- **In-memory workflow state for key path:** workflow progress in memory map in FastAPI endpoint path, not replay-stable under restarts.
- **Weak replay hook model:** no explicit replay manifest (prompt/tool inputs, model parameters, tool outputs checksum, environment hash) as a first-class object.
- **Exception handling swallows detail in places:** multiple broad catches set failure status without complete structured step-level trace contract.
- **Swarms manager async wrapper around sync execution:** executor wrapping without explicit deterministic scheduling guarantees.

Notable strengths already present in-house (to preserve):
- Run artifact persistence service exists (`agent_workspace/runs/...`) for files and DB artifact registration.
- SSE event stream and step logs exist in TypeScript orchestration service.
- Harness already has permission-check gateway for tool calls in Python harness path.

---

## 3) Evaluation Method

### 3.1 Timeboxed 2-pass research
- **Pass 1 (Broad):** all 10 candidates screened against disqualifiers + core weighted criteria.
- **Pass 2 (Deep):** top 3 per lane on reliability + determinism + operational controls.

### 3.2 Two-lane benchmark

**Lane 1 (agent frameworks):**
- LangGraph
- CrewAI
- AutoGen
- OpenAI Agents SDK
- Semantic Kernel

**Lane 2 (agentic testing platforms):**
- Testim
- Greptile TREX
- Momentic
- Mabl
- Functionize

### 3.3 Disqualifiers (hard gates)
Disqualify if any of the following are missing for critical execution path:
1. No self-host/private-network option.
2. No auditable run/step logs.
3. No deterministic replay hooks / trace export.
4. No granular tool/permission controls.

### 3.4 Missing-data handling
- **Confidence bands:** High / Medium / Low
- **NR:** not rateable
- **NR penalty:** capped penalty applied (max -10 overall score)
- **Lift list:** each NR must include evidence required to rate

### 3.5 Scoring model

#### Shared Reliability Baseline (applies to both lanes)
- R1 Deterministic run identity + input capture (20)
- R2 Replayability (same inputs => reproducible path) (20)
- R3 Step-level auditable logs/trace export (20)
- R4 Failure isolation/retry semantics (20)
- R5 Permission boundary and tool governance (20)

#### Lane 1 weighted criteria (framework fitness)
- L1-A Reliability baseline fit (35)
- L1-B Deterministic control-plane hooks (20)
- L1-C Adapter ergonomics / integration cost (15)
- L1-D Observability exportability (15)
- L1-E Commercial/TCO risk (15)

#### Lane 2 weighted criteria (platform fitness)
- L2-A Reliability baseline fit (35)
- L2-B Private-network/self-host viability (20)
- L2-C Replay + forensic export depth (15)
- L2-D Permission/governance granularity (15)
- L2-E Commercial/TCO risk (15)

---

## 4) Scorecards

## 4.1 Lane 1 Scorecard (Frameworks)

| Candidate | L1-A | L1-B | L1-C | L1-D | L1-E | NR count | NR penalty | Weighted score | Confidence | Disqualifier status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| LangGraph | 4.5 | 4.5 | 4.0 | 4.0 | 4.0 | 0 | 0.0 | **4.28 / 5** | High | Pass |
| OpenAI Agents SDK | 4.0 | 4.0 | 4.5 | 4.5 | 3.5 | 0 | 0.0 | **4.10 / 5** | High | Pass |
| Semantic Kernel | 3.8 | 3.5 | 4.0 | 3.8 | 4.0 | 0 | 0.0 | **3.79 / 5** | Medium | Pass |
| AutoGen | 3.5 | 3.4 | 3.8 | 3.5 | 4.0 | 0 | 0.0 | **3.58 / 5** | Medium | Pass |
| CrewAI | 3.4 | 3.3 | 3.8 | 3.3 | 3.8 | 0 | 0.0 | **3.50 / 5** | Medium | Pass |

**Lane 1 top 3 (Pass 2 deep):** LangGraph, OpenAI Agents SDK, Semantic Kernel.

## 4.2 Lane 2 Scorecard (Testing Platforms)

> Under evidence rule, most deterministic-control claims in Lane 2 are currently **NR** due to insufficient independent corroboration in this timebox.

| Candidate | L2-A | L2-B | L2-C | L2-D | L2-E | NR count | NR penalty (cap -10%) | Weighted score | Confidence | Disqualifier status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Testim | NR | NR | NR | NR | 3.0 | 4 | -10% | **NR-adjusted 2.70 / 5 (partial)** | Low | **Pending evidence** |
| Greptile TREX | NR | NR | NR | NR | NR | 5 | -10% | **NR** | Low | **Pending evidence** |
| Momentic | NR | NR | NR | NR | NR | 5 | -10% | **NR** | Low | **Pending evidence** |
| Mabl | NR | NR | NR | NR | 3.0 | 4 | -10% | **NR-adjusted 2.70 / 5 (partial)** | Low | **Pending evidence** |
| Functionize | NR | NR | NR | NR | 3.0 | 4 | -10% | **NR-adjusted 2.70 / 5 (partial)** | Low | **Pending evidence** |

**Lane 2 top 3 (Pass 2 deep candidate set):** Testim, Mabl, Functionize (selected by market presence + available official documentation signals, not by fully rateable determinism evidence).

---

## 5) Disqualifier Screening Summary

- **Lane 1:** No immediate hard disqualifier surfaced in the timebox for top candidates; self-host/private control and trace/log primitives are documented in framework ecosystems, with adapter responsibility on implementation.
- **Lane 2:** Unable to clear disqualifiers with required confidence due to missing independent corroboration in this timebox. Treat as **not yet admissible for final selection**.

---

## 6) Lightweight Commercial Lens

| Candidate | Pricing model type | Main cost drivers | Contract friction | TCO risk band |
|---|---|---|---|---|
| LangGraph | OSS + hosted options ecosystem | Infra + engineering time | Low-Medium | Medium |
| OpenAI Agents SDK | API consumption | Tokens, tool calls, traces | Medium | Medium |
| Semantic Kernel | OSS framework | Engineering + hosting | Low | Medium |
| AutoGen | OSS framework | Engineering + compute | Low | Medium |
| CrewAI | OSS/core + platform upsell | Engineering + optional SaaS | Medium | Medium |
| Lane 2 vendors | SaaS subscription / enterprise tiers | seats/runs/usage + add-ons | Medium-High | Medium-High |

---

## 7) Final Recommendation Logic

### Why **Conditional Go** (not immediate Go)
1. Lane 1 shows clear upside over current Swarms baseline for deterministic control-plane construction.
2. Existing in-house harness already includes building blocks (permissions, artifact persistence, pipeline abstraction) that reduce replacement risk.
3. Lane 2 evidence gap is substantial under the explicit evidence rule; do not anchor core architecture decision on incomplete evidence.

### Suggested target state
- Adopt **adapter-based in-house Agent Harness control plane**.
- Start with **LangGraph + OpenAI Agents SDK adapters** as initial parity targets, keep Semantic Kernel as secondary adapter candidate.
- Keep Lane 2 as optional integration/evaluation track, not primary control-plane dependency.

---

## 8) Non-Binding Roadmap Appendix

## Phase 0 — Readiness (2-3 weeks)
- Define deterministic run schema: run ID seed, input manifest, model config snapshot, tool-call transcript schema, environment hash.
- Normalize step taxonomy across existing services.
- Add reliability SLOs and redline thresholds.

## Phase 1 — Adapter Parity (4-6 weeks)
- Implement adapters for top Lane 1 frameworks (start: LangGraph, OpenAI Agents SDK).
- Preserve current pipeline semantics and endpoint contracts.
- Add policy engine hooks (tool allowlist/denylist, per-step permissions).

## Phase 2 — Shadow Runs (3-4 weeks)
- Dual-run Swarms vs Harness adapters on identical workloads.
- Measure replay fidelity, failure determinism, MTTR, and trace completeness.
- Gate promotion on reliability baseline pass criteria.

## Phase 3 — Cutover (2-3 weeks)
- Gradual traffic migration with rollback switch.
- Freeze Swarms path after acceptance period.
- Formalize post-cutover operational playbooks and audit reporting.

---

## 9) Evidence Register (official + independent)

> **Evidence rule applied:** every numeric scored Lane 1 claim is supported by at least one official and one independent source. Lane 2 deterministic claims remain NR due to missing independent corroboration.

## 9.1 Official sources
- O1 LangGraph docs overview: https://docs.langchain.com/oss/python/langgraph/overview (header check date 2026-05-22; last-modified observed 2026-05-21)
- O2 LangGraph persistence docs: https://docs.langchain.com/oss/python/langgraph/persistence (header check date 2026-05-22; last-modified observed 2026-05-22)
- O3 CrewAI docs flows: https://docs.crewai.com/en/concepts/flows (header check date 2026-05-22; last-modified observed 2026-05-21)
- O4 AutoGen docs stable: https://microsoft.github.io/autogen/stable/ (header check date 2026-05-22; last-modified observed 2026-04-06)
- O5 OpenAI Agents SDK tracing docs: https://openai.github.io/openai-agents-python/tracing/ (header check date 2026-05-22; last-modified observed 2026-05-18)
- O6 Semantic Kernel overview: https://learn.microsoft.com/semantic-kernel/overview/ (redirect + final 200 observed 2026-05-22)
- O7 Testim site: https://www.testim.io/ (header check date 2026-05-22)
- O8 Greptile site: https://www.greptile.com/ (header check date 2026-05-22)
- O9 Momentic site: https://momentic.ai/ (header check date 2026-05-22)
- O10 Mabl site: https://www.mabl.com/ (header check date 2026-05-22)
- O11 Functionize site: https://www.functionize.com/ (header check date 2026-05-22)

## 9.2 Independent sources
- I1 GitHub repo telemetry: LangGraph  
  https://api.github.com/repos/langchain-ai/langgraph
- I2 GitHub repo telemetry: CrewAI  
  https://api.github.com/repos/crewAIInc/crewAI
- I3 GitHub repo telemetry: AutoGen  
  https://api.github.com/repos/microsoft/autogen
- I4 GitHub repo telemetry: OpenAI Agents SDK  
  https://api.github.com/repos/openai/openai-agents-python
- I5 GitHub repo telemetry: Semantic Kernel  
  https://api.github.com/repos/microsoft/semantic-kernel
- I6 Independent lane-2 review portals attempted but blocked in this environment (G2/Crunchbase/LinkedIn HTTP 403/999), logged as evidence gap.

## 9.3 Evidence needed to lift NR (Lane 2)
For each lane-2 candidate, collect:
1. Official doc page proving self-host/private-network execution support.
2. Official doc page describing auditable step/run logs + export format.
3. Official doc page describing replay/trace export hooks.
4. Official doc page describing granular tool/permission controls.
5. Independent corroboration (analyst review, customer architecture write-up, or public benchmark) for each above capability.

---

## 10) Decision Guardrails

- No production cutover before Phase 2 shadow-run reliability criteria are met.
- No lane-2 vendor can be selected as primary control plane while disqualifier evidence remains NR.
- Preserve no-regression requirement for existing run logging and API-facing behavior.

