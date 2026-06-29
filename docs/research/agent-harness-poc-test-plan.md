# Agent Harness Replacement PoC Test Plan

**Date:** 2026-05-22  
**Objective:** Validate whether an adapter-based in-house Agent Harness control plane can replace Swarms with higher reliability and determinism for agentic test execution.

---

## 1) Scope and Success Criteria

### 1.1 In scope
- Compare two candidate lanes under one shared reliability baseline:
  - **Lane 1 frameworks:** LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Semantic Kernel
  - **Lane 2 testing platforms:** Testim, Greptile TREX, Momentic, Mabl, Functionize
- Benchmark against current repo baseline implementations:
  - [`backend/app/agents/swarm_manager.py`](backend/app/agents/swarm_manager.py)
  - [`src/lib/agent-orchestration-service.ts`](src/lib/agent-orchestration-service.ts)
  - [`backend/app/api/v1/endpoints/agents.py`](backend/app/api/v1/endpoints/agents.py)
  - [`src/lib/services/log-storage-service.ts`](src/lib/services/log-storage-service.ts)

### 1.2 Out of scope
- UI redesign
- Non-agentic test authoring ergonomics
- Organization-wide procurement finalization

### 1.3 PoC success gates
PoC is successful only if all are true:
1. Candidate clears all disqualifiers.
2. Candidate meets reliability SLO thresholds (Section 7).
3. Candidate produces reproducible replay evidence for seeded test workloads.
4. Evidence rule satisfied for scored claims (official + independent).

---

## 2) Disqualifiers (Hard Gates)

Any candidate is disqualified if critical execution path lacks:
1. Self-host or private-network option.
2. Auditable run/step logs.
3. Deterministic replay hooks and/or trace export.
4. Granular tool/permission controls.

---

## 3) Two-Pass Timebox Method

## Pass 1 — Broad screen (all 10 candidates)
- Duration: 3-5 business days
- Activities:
  - Collect official + independent evidence for each criterion.
  - Run disqualifier screening.
  - Produce first-pass weighted scores.
- Output:
  - Top 3 per lane for deep pass.
  - NR inventory and evidence-lift backlog.

## Pass 2 — Deep evaluation (top 3 per lane)
- Duration: 5-8 business days
- Activities:
  - Hands-on adapter or integration spike.
  - Deterministic replay stress scenarios.
  - Failure-injection + recovery tests.
  - Trace-forensics and audit export validation.
- Output:
  - Final per-lane recommendation and confidence.

---

## 4) Shared Reliability Baseline (Both Lanes)

Each item scored 0-5 with evidence links:
1. **R1 Deterministic run identity + full input capture**
2. **R2 Replayability fidelity under fixed seeds/config**
3. **R3 Auditable step logs + trace exportability**
4. **R4 Failure isolation/retry determinism**
5. **R5 Tool permission granularity/governance**

Weights for baseline roll-up: 20 each (total 100).

---

## 5) Weighted Scorecards

## 5.1 Lane 1 scorecard
- L1-A Reliability baseline fit (35)
- L1-B Deterministic control-plane hooks (20)
- L1-C Adapter ergonomics / integration cost (15)
- L1-D Observability exportability (15)
- L1-E Commercial/TCO risk (15)

## 5.2 Lane 2 scorecard
- L2-A Reliability baseline fit (35)
- L2-B Private-network/self-host viability (20)
- L2-C Replay + forensic export depth (15)
- L2-D Permission/governance granularity (15)
- L2-E Commercial/TCO risk (15)

---

## 6) Missing-Data Policy (Mandatory)

- Confidence bands: **High / Medium / Low**
- Missing score value: **NR**
- NR penalty: capped penalty, max **-10%** to weighted total
- For every NR, record:
  1. Missing claim
  2. Why missing
  3. Official source needed
  4. Independent source needed
  5. Owner + due date to lift NR

---

## 7) Quantitative Reliability SLOs for PoC Acceptance

Candidate must meet all thresholds in Pass 2 shadow tests:
- **Replay fidelity:** >= 95% identical step graph for deterministic scenarios
- **Step log completeness:** >= 99% steps with timestamp, input hash, output hash, status
- **Transient failure recovery determinism:** >= 90% deterministic retry outcome
- **Run artifact integrity:** 100% manifest + trace + logs persisted for accepted runs
- **Permission policy enforcement:** 100% blocked forbidden tool calls with explicit audit events

---

## 8) Workload Design

### 8.1 Workload classes
1. **Happy-path deterministic pipeline** (small, medium, large requirement sets)
2. **Tool-heavy pipeline** (MCP/tool invocation density high)
3. **Failure-injection pipeline** (network timeout, model timeout, tool exception)
4. **Recovery pipeline** (resume/retry from checkpoint)

### 8.2 Seeds and config control
- Fixed model parameters (temperature, top_p, max_tokens)
- Fixed prompt templates and tool config
- Fixed dependency/runtime image where possible
- Run manifest with version hashes

---

## 9) Instrumentation and Evidence Capture

For every PoC run, capture:
1. Run manifest JSON
2. Step-level event log
3. Tool call transcript (request/response + permission decision)
4. Trace export (native format + normalized format)
5. Result summary with failure taxonomy

Persist artifacts in run storage structure aligned with existing service design:
- `input/`
- `research/`
- `agents/`
- `test-execution/`
- `trace/`

---

## 10) Current Baseline Risks to Validate During PoC

PoC must explicitly verify closure of baseline gaps identified in current repo:
- Non-deterministic IDs generated from wall-clock/random patterns in orchestration path.
- In-memory workflow state in backend endpoint path.
- Missing first-class replay manifest and trace normalization contract.
- Partial structured error semantics in some catch/failure paths.

---

## 11) Lightweight Commercial Lens (Required in final report)

For each candidate, record:
1. Pricing model type (usage / seat / enterprise tier / hybrid)
2. Dominant cost drivers (tokens, run volume, seats, storage, premium support)
3. Contract friction (low/medium/high)
4. TCO risk band (low/medium/high)

---

## 12) Deliverables

At PoC close, produce:
1. Updated decision memo with final Go / Conditional Go / No-Go
2. Final scorecards (both lanes) with confidence and NR resolution status
3. Evidence appendix (all official + independent links with date context)
4. Top 3 unresolved risks with mitigation owner/date

---

## 13) Evidence Register Seed (from this research cycle)

Official sources:
- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.crewai.com/en/concepts/flows
- https://microsoft.github.io/autogen/stable/
- https://openai.github.io/openai-agents-python/tracing/
- https://learn.microsoft.com/semantic-kernel/overview/
- https://www.testim.io/
- https://www.greptile.com/
- https://momentic.ai/
- https://www.mabl.com/
- https://www.functionize.com/

Independent sources:
- https://api.github.com/repos/langchain-ai/langgraph
- https://api.github.com/repos/crewAIInc/crewAI
- https://api.github.com/repos/microsoft/autogen
- https://api.github.com/repos/openai/openai-agents-python
- https://api.github.com/repos/microsoft/semantic-kernel

Known evidence gaps to resolve:
- Independent corroboration for lane-2 deterministic replay/auditability/private-network claims.

