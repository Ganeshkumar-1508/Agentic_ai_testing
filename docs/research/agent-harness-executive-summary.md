# Executive Summary: Agent Harness Replacement Decision

**Date:** 2026-05-22  
**Decision:** **Conditional Go** (medium confidence)

---

## What was evaluated

We evaluated replacing Swarms with an in-house adapter-based Agent Harness control plane, using reliability + determinism as the top criterion.

Two-lane benchmark used:
- **Lane 1 frameworks:** LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Semantic Kernel
- **Lane 2 testing platforms:** Testim, Greptile TREX, Momentic, Mabl, Functionize

Benchmark included:
- Separate weighted scorecards per lane
- Shared reliability baseline
- Disqualifier screening
- Missing-data policy (confidence bands + NR + capped penalty)

---

## Current-state findings (repo baseline)

Baseline files reviewed:
- [`backend/app/agents/swarm_manager.py`](backend/app/agents/swarm_manager.py)
- [`src/lib/agent-orchestration-service.ts`](src/lib/agent-orchestration-service.ts)
- [`backend/app/api/v1/endpoints/agents.py`](backend/app/api/v1/endpoints/agents.py)
- [`src/lib/services/log-storage-service.ts`](src/lib/services/log-storage-service.ts)

Key determinism gaps identified:
1. Non-deterministic ID generation using timestamp/random patterns in orchestration paths.
2. In-memory workflow progress state on backend endpoint path.
3. No first-class replay manifest contract (inputs/config/tool outputs/hash lineage).
4. Partial inconsistency in structured failure trace semantics.

---

## Outcome by lane

## Lane 1 (frameworks)

Top-ranked candidates:
1. **LangGraph** (highest)
2. **OpenAI Agents SDK**
3. **Semantic Kernel**

Interpretation:
- Lane 1 provides the strongest path to deterministic control-plane construction with auditable traces and adapter flexibility.
- These options are suitable for Phase 1 adapter parity + Phase 2 shadow runs.

## Lane 2 (agentic testing vendors)

Interpretation:
- Under strict evidence rule (official + independent per scored claim), most determinism-critical claims are currently **NR** due to missing independent corroboration in this timebox.
- Lane 2 should remain optional/integrative until evidence gaps are closed.

---

## Recommendation

**Conditional Go** to in-house adapter-based Agent Harness control plane, with these conditions:
1. Start with Lane 1 adapters (LangGraph and OpenAI Agents SDK first).
2. Implement deterministic manifest + replay + trace-export standards before cutover.
3. Use shadow runs to prove reliability SLOs prior to production migration.
4. Keep Lane 2 out of primary control-plane dependency until NR evidence is lifted.

---

## Top 3 unresolved risks

1. Lane 2 evidence completeness risk (independent corroboration gaps).
2. Adapter parity risk during migration from current Swarms semantics.
3. Replay-forensics standardization risk if manifest/trace schema is delayed.

---

## Non-binding roadmap snapshot

- **Phase 0: Readiness** — define deterministic run schema and reliability SLOs.
- **Phase 1: Adapter parity** — implement framework adapters without API/log regressions.
- **Phase 2: Shadow runs** — dual execution against Swarms baseline; validate replay fidelity.
- **Phase 3: Cutover** — staged migration with rollback and operational hardening.

---

## Evidence posture

- Lane 1 scored claims: supported using official docs + independent GitHub telemetry.
- Lane 2 scored claims: heavily NR where independent corroboration was unavailable in accessible sources.
- Commercial lens applied as lightweight risk view (pricing type, cost drivers, contract friction, TCO band).

