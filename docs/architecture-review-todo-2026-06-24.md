# Architecture Review — Implementation Todo

Date: 2026-06-24
Source: `docs/architecture-review-qa-2026-06-23.md`
Research: `docs/upcoming-projects-research-2026-06-24.md`

---

## Phase 1: Done ✓

All items from the architecture review report have been implemented:

| Item | Description | Status |
|------|-------------|--------|
| C10 | Delete legacy hooks/registry.py | ✅ |
| C4 | Extract KG types to lib/types/kg.ts | ✅ |
| C3 | Delete typed client + schema.d.ts | ✅ |
| C6 | DashboardWidgetService — 15 methods extracted | ✅ |
| C7 | Delete unused EventSourcedState | ✅ |
| C5 | Replace 7 if/elif chains with dict-based dispatch | ✅ |
| C2 | Split KanbanService + pluggable TaskReviewer ABC | ✅ |
| F5 | Wire multi-repo PR coordination into run_multi | ✅ |
| F4 | Add test-result feedback loop to codegraph | ✅ |
| C1 | Phase system — RunPhase, RunContext, KGIndexPhase | ✅ |
| F6 | RunSummaryPhase — hidden agent for post-run summary | ✅ |

---

## Phase 2: Upcoming Projects — Adoption Queue

### Priority 1 — High Impact

- [ ] **P1: Sponsio** — Replace/upgrade PermissionManager with deterministic policy enforcement (~3 sprints)
  - `harness/permissions/sponsio_adapter.py`
  - Port existing permission rules to Sponsio contracts
  - Remove old PermissionManager path

- [ ] **P2: TokenTamer** — AST-based context compression in context_compressor (~2 sprints)
  - `harness/context_compressor/ast_skeletonizer.py`
  - Tool-aware stale read compression
  - Wire into tool dispatch

- [ ] **P3: Scenario** — Simulation-based agent testing (~2 sprints)
  - Adapt TestAI's agent to Scenario AgentAdapter interface
  - Write simulation tests for coordinator, subagent delegation, tool dispatch

- [ ] **P4: Chorus** — AI-DLC workflow for KanbanService (~2 sprints)
  - Add AI-DLC stages (Idea→Proposal→Execute→Verify→Done)
  - Agent Connections-style dashboard widgets

- [ ] **P5: Mirage** — Unified VFS to replace API-specific tools (~3 sprints)
  - Integrate Mirage into sandbox workspace
  - Replace top 5 API-specific tools with Mirage filesystem paths

- [ ] **P6: Nono** — Zero-latency sandbox backend (~2 sprints)
  - Nono adapter in SandboxManager
  - Profile registry for TestAI's sandbox profiles

- [ ] **P7: Cognee** — Upgrade memory layer with knowledge graph (~2 sprints)
  - Replace memory_tool backend with Cognee
  - Migrate L1/L2 memory to knowledge graph

- [ ] **P8: oh-my-pi** — Hash-anchored edits + LSP pre-flight (~4 sprints)
  - Hash-anchored edit_file tool
  - LSP diagnostics before file writes
  - DAP integration in sandbox

- [ ] **P9: Logfire** — Pydantic observability dashboard (~1 sprint)
  - Wire OTel exporter to Logfire endpoint
  - Add Logfire dashboard widgets

### Priority 2 — Medium Impact

- [ ] **P10: abtop** — Agent process monitor widget (~1 sprint)
  - Add live agent monitor panel to observability dashboard
  - Per-session token/context/rate-limit tracking
  - Orphan port detection in sandbox reaper

- [ ] **P11: claude-tap** — Agent API traffic inspector (~1 day)
  - Use during development for debugging tool call formatting
  - Reference for implementing TestAI's own traffic inspection

- [ ] **P12: TrustGraph** — Holonic context graphs for L2 memory (~3 sprints)
  - Upgrade L2 curated memory to structured graphs with provenance
  - Replace flat key-value facts with RDF/OWL/SHACL

- [ ] **P13: BitRouter** — Cost-optimizing LLM router (~2 sprints)
  - Enhance LLMRouter with cost-based routing
  - Add budget-aware model selection

- [ ] **P14: oh-my-agent** — Domain-specialized agent roles (~2 sprints)
  - Extend Role YAML with domain expertise metadata
  - Pre-configured agent team presets

- [ ] **P15: thClaws** — OpenRouter Fusion pattern (~3 sprints)
  - Multi-model deliberation for high-stakes decisions
  - PR review and tier-2 approval via model jury

- [ ] **P16: Replayd** — Replayable agent regression tests (~1 sprint)
  - Adapter on top of existing stream_events table
  - Turn failed runs into regression tests

- [ ] **P17: Memori** — Agent-native memory infrastructure (~2 sprints)
  - Alternative memory backend evaluation vs Cognee
  - Short-term/episodic/long-term memory layers

- [ ] **P18: agentverify** — Deterministic agent testing (~1 sprint)
  - Evaluate pytest plugin for agent assertion patterns
  - Adopt if mature enough
