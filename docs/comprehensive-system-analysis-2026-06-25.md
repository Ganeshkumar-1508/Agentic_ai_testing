# TestAI — Comprehensive System Analysis & Architecture Report

**Date:** 2026-06-25  
**Scope:** Full-stack analysis of orchestrator, sandbox, knowledge graph, memory, subagents, tools, skills, observability  
**Method:** Codebase audit + competitive research (Greptile TREX, Tembo AI, TestSprite, Testim, Mabl, Bug0, E2B, Modal, Daytona) + production harness comparison (Anthropic Claude Code, OpenAI Codex, Devin, GitHub Copilot, Hermes, OpenCode, OpenClaw)

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Component-by-Component Analysis](#3-component-by-component-analysis)
    - 3.1 Orchestrator Engine
    - 3.2 Subagent System
    - 3.3 Sandbox & Workspace Isolation
    - 3.4 Knowledge Graph
    - 3.5 Memory System
    - 3.6 Event Bus & Observability
    - 3.7 Tool Catalog & Skills
    - 3.8 Kanban Board
    - 3.9 Artifact Storage
    - 3.10 Budget & Rate Limiting
4. [Competitive Landscape](#4-competitive-landscape)
5. [Gap Analysis](#5-gap-analysis)
6. [Subtasks & Roadmap](#6-subtasks--roadmap)
7. [Recommendations](#7-recommendations)

---

## 1. Executive Summary

TestAI is a **production-grade agent orchestrator** for autonomous testing and code fixing. It has evolved significantly since the 2026-06-18 architecture review, with major improvements in:

- **Event observability** — F21-F33 fixes added wire-name normalization, 3 observability panels, typed event emission, and live SSE feeds
- **Subagent reliability** — F12 (tool exception handling), F3 (error classifier), F4 (circuit breaker)
- **Resume capability** — C08 pause/resume with full checkpoint persistence
- **Sandbox snapshots** — `docker commit`-based snapshot/restore (C4.1, Greptile/E2B pattern)
- **Container Registry** — Protocol-based lifecycle management (C5)

**Remaining gaps** (in priority order):
1. **No worktree isolation** — subagents share the same sandbox filesystem; Claude Code, Devin, and GitHub Copilot all use per-agent worktrees
2. **No stuck-detector** — only 1/5 patterns detected vs OpenHands' StuckDetector
3. **Knowledge graph is write-only** — `kg_edges` only recently populated, no LLM extraction of triples
4. **Single-entry point confusion** — `run_single`, `run_multi`, `run_job_spec` coexist; should consolidate
5. **No OpenTelemetry export** — wire names align with OTel conventions but no exporter wired
6. **No per-tool latency metrics** — p50/p95 not tracked

---

## 2. Architecture Overview

```
User / GitHub / Slack / API
          │
          ▼
┌─────────────────────────────┐
│   OrchestratorEngine        │
│   (run_job_spec / run_single)│
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   JobSpec                   │
│   (prompt, repo, tier, cap) │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   Coordinator (subagent)    │
│   - plans via _llm_decompose│
│   - delegates via task tool │
│   - monitors via heartbeat  │
│   - updates kanban board    │
└──────────┬──────────────────┘
           │
     ┌─────┴──────┬──────────┐
     ▼            ▼          ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│Explore  │ │Worker   │ │Reviewer │
│Subagents│ │Subagents│ │Subagents│
└────┬────┘ └────┬────┘ └────┬────┘
     │           │           │
     ▼           ▼           ▼
┌─────────────────────────────────────┐
│         Docker Sandbox              │
│  (per-session volume + container)   │
│  - git clone                        │
│  - dependency install               │
│  - test execution                   │
│  - artifact generation              │
└─────────────────────────────────────┘
```

**Key insight from the Anthropic harness research** (Nov 2025): ~98.4% of a production agent is harness infrastructure — only ~1.6% is AI decision logic. Four independently-built agents (Claude Code, Codex CLI, Aider, OpenClaw) all converged on the same harness patterns, suggesting this architecture is a fundamental constraint.

---

## 3. Component-by-Component Analysis

### 3.1 Orchestrator Engine

**File:** `backend/harness/orchestrator.py`  
**Class:** `OrchestratorEngine`

| Feature | Status | Notes |
|---------|--------|-------|
| `run_job_spec` | ✅ GA | Entry point for chat→orchestrator handoff |
| `run_single` | ✅ GA | Single-repo execution |
| `run_multi` | ⚠️ EXISTING | Only 1 caller, no tests |
| `run_resumed_job_spec` | ✅ NEW (C08) | Resume from checkpoint |
| Tier 3 proposals | ✅ NEW (C03) | Human-authored proposal path |
| Cancel watcher | ✅ NEW (C08) | `run_with_cancel` for job cancellation |
| Pause/resume | ✅ NEW (C08) | `JobCheckpoint` + `apop_checkpoint` |
| Subagent tracker | ✅ NEW (C08) | Hermes/openclaude/ohmo research pattern |
| Run success detector | ✅ NEW (C00-C-5) | `RunSuccessDetector` with strategy adapters |

**Issues found:**
- `run_multi` has **no tests** and only 1 caller — dead code risk
- Goal decomposition (`_llm_decompose`) hallucinates — F6 fix not yet applied
- Container name truncated to `testai-sandbox-` with no session suffix — F7 still open

**Entry point consolidation:** Currently 3 entry points (`run_single`, `run_multi`, `run_job_spec`). The user wants a unified path: user points to repo → orchestrator pulls repo, shows issues/PRs → user selects item → orchestrator fulfills. `run_job_spec` is the closest but doesn't surface GitHub issues/PRs for user selection.

### 3.2 Subagent System

**File:** `backend/harness/tools/subagent.py`  
**Class:** `Subagent`

| Feature | Status | Notes |
|---------|--------|-------|
| `spawn()` — single subagent | ✅ GA | Blocks until done |
| `spawn_many()` — fan-out | ✅ GA | N parallel, returns list |
| `collect()` — background collect | ✅ GA | Await background results |
| `cancel()` — cancel subagent | ✅ GA | Cancels + children |
| Rate limiting (circuit breaker) | ✅ GA | 3-state: CLOSED/OPEN/HALF_OPEN |
| Budget tracker | ✅ GA | Per-run hard/soft caps |
| Depth control | ✅ GA | `max_spawn_depth` configurable |
| Heartbeat monitoring | ❌ MISSING | Hermes pattern not implemented |
| Stale detection | ⚠️ PARTIAL | Only `_consecutive_same_tool` check |
| Worktree isolation | ❌ MISSING | All subagents share same container |
| Resume capability | ⚠️ PARTIAL | Job-level resume, not subagent-level |
| 0-API-call diagnostics | ❌ MISSING | Stuck subagents are black boxes |

**Research comparison:**

| Feature | Hermes | OpenCode | OpenClaw | **TestAI** |
|---------|--------|----------|----------|------------|
| Heartbeat | ✅ | ❌ | ❌ | ❌ |
| Stale detection (5 patterns) | ⚠️ 2/5 | ❌ | ❌ | ⚠️ 1/5 |
| Timeout per subagent | ✅ | ❌ | ❌ | ⚠️ Via circuit breaker |
| 0-API-call diagnostic | ✅ | ❌ | ❌ | ❌ |
| Context modes (isolated/fork) | ❌ | ❌ | ✅ | ❌ |
| Push-based completion | ❌ | ❌ | ✅ | ❌ |
| Worktree isolation | ❌ | ❌ | ❌ | ❌ (all share) |

**The OpenHands StuckDetector** detects 5 patterns:
1. Repeating action-obs (4+) ❌
2. Repeating action-err (3+) ❌
3. Agent monologue (3+) ❌
4. Alternating ping-pong (6+) ❌
5. Context-window overflow ❌

TestAI detects only `_consecutive_same_tool` (20 identical calls). This is a significant blind spot.

### 3.3 Sandbox & Workspace Isolation

**Files:** `backend/harness/sandbox_manager.py`, `backend/harness/sandbox/registry.py`

| Feature | Status | Notes |
|---------|--------|-------|
| Docker container per session | ✅ | `testai-sandbox-{session_id[:12]}` |
| Docker volume per session | ✅ | `testai-ws-{session_id}` |
| Volume persistence (KG + deps) | ✅ | kept across runs by default |
| Container recovery after restart | ✅ | `_recover_containers()` |
| Container Registry (Protocol) | ✅ NEW (C5) | `InProcessContainerRegistry`, Protocol for future adapters |
| SandboxSnapshot | ✅ NEW (C4.1) | `docker commit`-based |
| Host workspace dir sync | ✅ | Hermes pattern `SANDBOX_WORKSPACE_DIR` |
| Per-subagent sandbox | ❌ MISSING | All subagents share one container |
| Network isolation modes | ⚠️ PARTIAL | Labels set, but no deny-all mode |
| gVisor or Firecracker | ❌ | Standard Docker, no microVM |
| GPU support | ❌ | No GPU passthrough |

**Research comparison — sandbox isolation:**

| Platform | Isolation | Cold Start | Max Session | GPU |
|----------|-----------|------------|-------------|-----|
| **TestAI** | Docker container | ~1-3s | Configurable | ❌ |
| **E2B** | Firecracker microVM | ~150ms | 24h | ❌ |
| **Modal** | gVisor | Sub-second | Configurable | ✅ A100/H100 |
| **Daytona** | OCI/Docker | 27-90ms | Unlimited | ❌ |
| **Tembo** | Dedicated Linux VM | Seconds | Session | ❌ |
| **Greptile TREX** | Disposable sandbox | ms | Per-review | ❌ |
| **TestSprite** | Cloud sandbox | Seconds | Session | ❌ |

**Critical gap:** All subagents share ONE sandbox container. Claude Code uses git worktrees per agent; Devin uses separate containers; GitHub Copilot App uses per-task sessions with worktrees. Without worktree isolation, parallel subagents editing the same file will conflict.

**Container name truncation (F7):** `testai-sandbox-` (16 chars) + session_id[:12] hits Docker's 64-char name limit with no room for a meaningful suffix.

### 3.4 Knowledge Graph

**Files:** `backend/harness/services/artifact_store.py` (L1Indexer), `backend/api/routers/knowledge_graph_api.py`

| Feature | Status | Notes |
|---------|--------|-------|
| `kg_nodes` table | ✅ | Inserted by L1Indexer |
| `kg_edges` table | ✅ EXISTS, ⚠️ PARTIAL POPULATED | F9 fix applied but not verified |
| L1Indexer.promote() | ✅ | Writes nodes + co-occurrence edges |
| LLM triple extraction (subject/predicate/object) | ❌ | Microsoft Neo4j pattern not implemented |
| KG API endpoints | ✅ | Full CRUD + visualization |
| Frontend KG visualization | ✅ | Interactive graph with Entity/Relation/SemanticSummary |
| Orama search integration | ✅ | Semantic search across KG |
| Cross-run memory (L2) | ⚠️ PARTIAL | Basic memory tool exists |

**The kg_edges gap:** The L1Indexer's docstring claimed "summary nodes + edges" but only nodes were written until the F16 fix. Even with the F16 fix, edges are only `co_occurs_in_run` — no semantic relation extraction. Microsoft's Agent Framework uses Neo4j + LLM extraction for true triple extraction.

**What production KG in agentic testing looks like:**
- **Greptile:** Semantic code graph indexing the entire repo, not just the diff
- **TestSprite:** Infers product intent from PRDs + codebase
- **TestAI:** File-level co-occurrence only — no semantic understanding

### 3.5 Memory System

**Files:** `reference/hermes-agent/tools/memory_tool.py`, `backend/harness/tools/` (memory tool)

| Feature | Status | Notes |
|---------|--------|-------|
| MEMORY.md / USER.md persistence | ✅ | File-based cross-run memory |
| Character limits | ✅ | 2200 / 1375 chars |
| Batch operations (add/replace/remove) | ✅ | Single-call consolidate |
| Threat pattern scanning | ✅ | Injection/exfiltration protection |
| System prompt snapshot | ✅ | Freezes at load time for prefix cache |
| Cross-run memory (L2 curated lessons) | ⚠️ PARTIAL | Basic, no auto-curation |
| Memory compaction agent | ⚠️ PARTIAL | OpenCode-style compaction exists |
| Per-subagent memory isolation | ❌ | Subagents share parent memory |

**The compaction gap:** OpenCode has a hidden "compaction agent" that auto-compacts long context. TestAI's `checkpoint.py` + resume endpoint implement the Anthropic "full context reset + handoff artifact" pattern, but there's no automatic compaction mid-run like OpenCode's system agent.

### 3.6 Event Bus & Observability

**Files:** `backend/harness/events.py`, `src/lib/hooks/use-activity-feed.ts`, `src/components/activity/ObservabilityPanels.tsx`

| Feature | Status | Notes |
|---------|--------|-------|
| Typed events (18 types) | ✅ | F29 fix — wire names normalized |
| SSE feeds (global + per-session) | ✅ | `GET /api/events/_global`, `/{session_id}` |
| Activity feed UI | ✅ | Ring buffer, filters, pause/resume |
| Observability panels (3 panels) | ✅ NEW (F33) | Tools health, Cost burn, Error categories |
| Per-tool success rate | ✅ | Via `_aggregations` endpoint |
| Token cost tracking | ✅ | USD-per-minute estimates |
| Error categories histogram | ✅ | `ErrorEvent.category` |
| Subagent events (spawned/completed) | ✅ | Structured typed events |
| OpenTelemetry export | ❌ | Wire names align, no exporter wired |
| Per-tool latency p50/p95 | ❌ | `duration_ms` not on ToolExecutionCompleted |
| Cancel/interrupt event type | ❌ | AG-UI pattern not implemented |
| LLM call streaming | ⚠️ PARTIAL | `TokenGenerated`, `ReasoningGenerated` emitted but frontend doesn't render live |

**The F21-F33 fixes** transformed observability from "essentially dead" to a functioning dashboard. The key fix was the `wire_name()` function in `events.py` that maps class names to dot-notation names for all 18 typed events.

### 3.7 Tool Catalog & Skills

**Files:** Backend tools in `backend/harness/tools/`, skills in `docs/agent-skills/skills/`

| Feature | Status | Notes |
|---------|--------|-------|
| 79-tool catalog | ✅ | Via `/api/tools` |
| Tool isolation per role | ✅ | `toolsets` parameter in Subagent |
| MCP server support | ✅ | MCP discovery + invocation |
| Skills system | ✅ | `docs/agent-skills/skills/` with SKILL.md |
| Code intelligence tools (codegraph) | ✅ | `codegraph_callees`, `codegraph_search`, etc. |
| ast-grep structural search | ✅ | AST pattern matching |
| Web fetch/search | ✅ | DuckDuckGo + HTTP fetch |
| Delegate task tool | ✅ | Subagent spawning |

**Skill isolation per subagent:** The tool access model specifies 6-layer isolation:
1. Child tools = requested ∩ parent
2. Always-blocked set for leaf workers
3. Orchestrator exception retains delegate_task
4. MCP allow-list per subagent
5. Skills scoped to subagent goal
6. Credentials injected per-task at spawn time

**Skills are filesystem-first** with Postgres mirroring. Discovery is via filesystem scan → lightweight name+desc index → agent loads full content on-demand.

### 3.8 Kanban Board

**Files:** `backend/api/routers/kanban.py`, backend services

| Feature | Status | Notes |
|---------|--------|-------|
| Board creation | ✅ | 7-column default: triage, backlog, ready, in_progress, review, done, flaky_heat |
| Task CRUD | ✅ | Create, update, complete, delete |
| Orphan sweep | ✅ | `sweep_orphan_in_progress` |
| Column defaults | ⚠️ | Schema default (6 cols) ≠ API default (7 cols) — F10 |

**The hallucinated goal problem (F6):** The LLM-driven `_llm_decompose` step produces task graphs that sometimes have nothing to do with the original prompt. The fix (not yet applied) is to add a goal-extraction sanity check: compare the LLM-decomposed sub-tasks against the original prompt's named entities.

### 3.9 Artifact Storage

**Files:** `backend/harness/services/artifact_store.py`

| Feature | Status | Notes |
|---------|--------|-------|
| L0 raw artifacts | ✅ | Per-type configurable TTL (tests=permanent, trajectories=30d, transcripts=7d) |
| L1 indexed facts | ✅ | `kg_nodes` + `kg_edges` (F16 fix) |
| L2 curated lessons | ⚠️ PARTIAL | Memory tool, no auto-curation |
| `agent_artifacts.expires_at` | ✅ | TTL column exists |
| Agent-created test files | ✅ | Persisted with TTL |
| Config artifacts | ✅ | Settings stored in DB |

### 3.10 Budget & Rate Limiting

**Files:** `backend/harness/budget_tracker.py`, `backend/harness/tools/circuit_breaker.py`

| Feature | Status | Notes |
|---------|--------|-------|
| `budgets` table | ✅ | Exists with scope, name, soft_usd, hard_usd, enabled, created_at, updated_at |
| Per-run budget | ✅ | Hard + soft caps |
| Per-subagent budget check | ✅ | 95% pre-check before spawn |
| Spawn rate limiter | ✅ | 10-in-30s window, 60s cooldown |
| Circuit breaker (3-state) | ⚠️ | Works but threshold too sensitive for 79-tool catalog |
| Per-role circuit breaker config | ❌ | Coordinator should probe slower |

---

## 4. Competitive Landscape

### 4.1 Greptile TREX

**Architecture (from Greptile blog, June 2026):**
- **Main agent** = orchestrator that reads diff, identifies issues
- **TREX subagents** = one per issue, spun up in parallel
- **Shared context** — subagents inherit what the main agent found (not starting from scratch)
- **Disposable sandbox** per review, started in ms, thrown away after
- **Multi-modal artifacts** — screenshots, logs, API traces, execution scripts, video
- **Model-agnostic harness** — main agent and subagents can use different providers

**Key lesson:** Greptile tried "separate agents" first (wasteful, overlapping) then "single agent" (overloaded). The winning pattern was **shared context + per-issue subagents**.

### 4.2 Tembo AI

**Architecture:**
- **Dedicated Linux VM** per session — stronger isolation than Docker containers
- **5 sandbox sizes** (Micro→Ultra: 2 vCPU/4GB → 32 vCPU/128GB)
- **Ephemeral** — destroyed when session ends
- **Nix dev shells** for custom dependencies
- **Nested virtualization** for Docker-in-Docker
- **No code persistence** after session (except snapshots)

**Key differentiator:** VM-level isolation (stronger than TestAI's Docker containers). GPU support for ML workloads.

### 4.3 TestSprite

**Architecture (MCP-native):**
- **IDE-native agent** via MCP — works in Cursor, Windsurf, Claude Code, VS Code
- **Understands intent** from PRDs and codebase, not just code
- **Cloud sandboxes** for test execution
- **Failure classification** — real bug vs test fragility vs environment
- **Auto-heal** — tightens selectors, waits, data, schema assertions
- **Structured fix guidance** via MCP back to coding agents

**Key differentiator:** Full auto-healing loop — detects → diagnoses → heals → sends fix guidance. Raised pass rates from 42% to 93% in benchmarks.

### 4.4 Production Harness Features (Composite)

| Feature | Claude Code | GitHub Copilot | Devin | **TestAI** |
|---------|-------------|---------------|-------|------------|
| Parallel subagents | ✅ | ✅ | ✅ | ✅ |
| Worktree isolation | ✅ | ✅ | ❌ | ❌ |
| Heartbeat monitoring | ⚠️ | ❌ | ❌ | ❌ |
| Stuck detection | ⚠️ | ⚠️ | ❌ | ⚠️ 1/5 |
| Resume mid-task | ✅ | ✅ | ✅ | ✅ |
| Per-subagent timeout | ✅ | ✅ | ✅ | ❌ |
| Background execution | ✅ | ✅ | ✅ | ✅ |
| Foreground/Background switch | ✅ | ✅ | ✅ | ❌ |
| Cancellation | ✅ | ✅ | ✅ | ✅ |
| Budget controls | ✅ | ✅ | ❌ | ✅ |
| OTel export | ✅ | ✅ | ❌ | ❌ |
| Per-tool latency metrics | ✅ | ❌ | ❌ | ❌ |

---

## 5. Gap Analysis

### 5.1 Critical Gaps

| # | Gap | Impact | Fix Effort | Competitor Reference |
|---|-----|--------|-----------|---------------------|
| G1 | **No worktree isolation** | Parallel subagents conflict | 3-5 days | Claude Code worktrees, GitHub Copilot per-task sessions |
| G2 | **No stuck detector** | Wasted compute, zombie agents | 2-3 days | OpenHands StuckDetector (5 patterns) |
| G3 | **Goal decomposition hallucination** | Wrong tasks created | 1 day | Add entity-sanity-check regex |
| G4 | **kg_edges only co-occurrence** | No semantic understanding | 5-7 days | Microsoft Neo4j Memory Provider pattern |
| G5 | **Subagent sandbox sharing** | No isolation between workers | 5-7 days | E2B/Modal/Daytona per-execution sandbox |

### 5.2 Important Gaps

| # | Gap | Fix Effort |
|---|-----|-----------|
| G6 | **Single entry point consolidation** (run_single/run_multi/run_job_spec → 1 or 2) | 2-3 days |
| G7 | **Per-tool latency metrics** (p50/p95) | 1-2 days |
| G8 | **OpenTelemetry export** | 3-5 days |
| G9 | **Container name truncation** (F7) | 1 day |
| G10 | **Heartbeat monitoring** (Hermes pattern) | 3-5 days |
| G11 | **0-API-call diagnostics** (stuck before first LLM call) | 2-3 days |
| G12 | **Per-role circuit breaker configuration** | 1-2 days |
| G13 | **Kanban column default inconsistency** (F10) | <1 day |
| G14 | **Pipeline-store stale component cleanup** (F27) | 2-3 days |
| G15 | **Subagent-level resume** (not just job-level) | 3-5 days |

### 5.3 Desirable Gaps

| # | Gap | Notes |
|---|-----|-------|
| G16 | **GPU support** for sandboxes | Heavy infra investment |
| G17 | **gVisor/Firecracker isolation** | Heavy infra investment |
| G18 | **AG-UI protocol compliance** (interrupt event) | Standards alignment |
| G19 | **A2A protocol compatibility** | Future multi-vendor interop |
| G20 | **Cross-repo KG stitching** | Multi-repo analysis |

---

## 6. Subtasks & Roadmap

### Phase 1: Reliability (Week 1-2)

```
□ G3  Goal decomposition sanity check (1 day)
□ G9  Container name truncation fix (1 day)
□ G13 Kanban column default fix (<1 day)
□ G10 Heartbeat monitoring (3-5 days)
□ G2  Stuck detector (2-3 days)
□ G11 0-API-call diagnostics (2-3 days)
```

### Phase 2: Isolation (Week 2-3)

```
□ G1  Worktree isolation (3-5 days)
□ G5  Per-subagent sandbox (5-7 days)
□ G12 Per-role circuit breaker (1-2 days)
□ G15 Subagent-level resume (3-5 days)
```

### Phase 3: Observability (Week 3-4)

```
□ G7  Per-tool latency metrics (1-2 days)
□ G8  OpenTelemetry export (3-5 days)
□ G14 Pipeline-store cleanup (2-3 days)
□ G18 AG-UI interrupt event (2-3 days)
```

### Phase 4: Intelligence (Week 4-6)

```
□ G4  Semantic KG (LLM triple extraction) (5-7 days)
□ G6  Entry point consolidation (2-3 days)
□ G16 GPU support (Research)
□ G19 A2A protocol (Research)
```

### Phase 5: GitHub Issues/PRs Integration (New Feature)

```
□ GH1 GitHub API integration — list issues, PRs, reviews
□ GH2 User selects item from issue/PR list
□ GH3 Orchestrator runs on selected item
□ GH4 Results posted back to GitHub as PR comment / review
□ GH5 Cross-session context — user asks "what happened to PR #123"
```

---

## 7. Recommendations

### 7.1 Immediate Actions (This Week)

1. **Fix goal decomposition hallucination (G3)** — Add entity sanity check: extract named entities from the prompt (PR number, function name, error message) and reject LLM output if no task contains any of them. This is a one-regex fix in `orchestrator.py:_llm_decompose`.

2. **Fix container name truncation (G9)** — Shorten prefix from `testai-sandbox-` to `tsb-`. This gives 61 chars for the session id instead of 48.

3. **Add heartbeat monitoring (G10)** — Implement Hermes' `_heartbeat_loop` pattern in `subagent.py`. The pattern is well-documented: periodic activity propagation, stale detection with configurable thresholds (tight for idle, higher for in-tool).

4. **Add stuck detector (G2)** — Implement OpenHands' 5-pattern StuckDetector. Each pattern is a counter in the agent loop; when any threshold is exceeded, emit `ErrorEvent(category="stuck", ...)` and terminate.

### 7.2 Architecture Decisions

5. **Consolidate to 2 entry points** — Keep `run_job_spec` (full pipeline with tier/spec) and rename `run_single` to `run_repo` (bare-metal, no spec). Remove `run_multi` or reimplement it as `run_job_spec` with `context_repos`.

6. **GitHub Issues/PRs as first-class input** — Add a new `run_github_item` that:
   - Takes a URL ({owner}/{repo}/issues/{n} or /pull/{n})
   - Fetches the issue/PR body + comments + commits
   - Creates a JobSpec with the issue context
   - Runs through normal `run_job_spec` pipeline
   - Returns results + optionally posts back to GitHub

7. **Worktree isolation strategy** — Use Docker volumes per subagent (already have volume-per-session pattern). Mount a subagent-specific subdirectory on the shared volume: `/workspace/.subagents/{sa_id}/`. The coordinator merges completed work back to `/workspace/`.

### 7.3 Production Hardening

8. **Per-tool latency tracking** — Add `duration_ms` field to `ToolExecutionCompleted` event. The `_aggregations` endpoint can then compute p50/p95 per tool.

9. **OpenTelemetry export** — Add a 5th sink to the EventBus (`events.py:EventBus`). The wire names already align with OTel GenAI semantic conventions; the exporter is a one-class addition.

10. **Semantic KG extraction** — Add an LLM call in `L1Indexer.promote()` that extracts `(subject, predicate, object)` triples from L0 artifacts. Start with a focused prompt for the first file of each run, use the result to populate `kg_edges` with typed relations.

### 7.4 User Visibility & Chat Integration

11. **Live sandbox view** — The user asked "can the user see whatever is happening in the sandbox?" Current state: `SandboxManager.list_sandboxes()` returns metadata, but there's no real-time terminal output streaming. Add WebSocket-based `docker attach` streaming to the `/sandbox/[sessionId]` page.

12. **Session-aware chat agent** — When the user asks about previous/running sessions in the chat interface, the agent needs access to:
   - `sessions` table (status, goal, model, duration)
   - `stream_events` table (per-session event log)
   - `job_specs` table (spec status, tier)
   - `kanban_tasks` table (task progress)
   - `messages` table (conversation history)
   
   Add a `session_query` tool that queries these tables with natural language filters.

13. **Subagent activity visibility** — The `SubagentPanel` in the frontend shows active/completed subagents with their status, duration, token usage, and cost. This data is available via `GET /api/sessions?parent_session_id=X`. Ensure the dashboard surfaces this prominently.

### 7.5 What Would Have Prevented These Bugs

Based on the F1-F35 findings from the 2026-06-24 e2e run:

1. **Tool exception handling** (F12) — Hard exceptions from tool dispatch leaked orphan `tool_calls`. Fix: wrap `_dispatcher.execute()` in try/except. **Root cause:** Missing `handle_tool_errors=True` pattern (LangGraph fixed this in 2024).

2. **Error classifier** (F3) — `invalid_request_error` categorized as `unknown` → no retry. **Root cause:** Incomplete error category table. Need to sync with provider docs.

3. **Event observability** (F21-F33) — Events declared but not emitted, wire names mismatched, frontend filters stale. **Root cause:** No integration test that verifies "event declared = event emitted = frontend renders it". Add a `test_event_roundtrip` that creates a mock agent, runs one tool call, and verifies all expected events appear in the SSE feed.

4. **Goal hallucination** (F6) — LLM decomposed prompt into unrelated tasks. **Root cause:** No prompt-output validation. LLM output must be validated against prompt semantics before accepting.

---

## Appendix A: Key Files Reference

| Component | Path | Lines |
|-----------|------|-------|
| OrchestratorEngine | `backend/harness/orchestrator.py` | ~1800 |
| Subagent class | `backend/harness/tools/subagent.py` | ~1240 |
| SandboxManager | `backend/harness/sandbox_manager.py` | ~800 |
| Container Registry | `backend/harness/sandbox/registry.py` | ~240 |
| Event Bus | `backend/harness/events.py` | ~350 |
| Agent loop | `backend/harness/agent/agent.py` | ~1100 |
| Memory Tool | `reference/hermes-agent/tools/memory_tool.py` | ~600 |
| Artifact Store (L1Indexer) | `backend/harness/services/artifact_store.py` | ~250 |
| Budget Tracker | `backend/harness/budget_tracker.py` | ~200 |
| Circuit Breaker | `backend/harness/tools/circuit_breaker.py` | ~300 |
| Error Classifier | `backend/harness/tools/error_classifier.py` | ~150 |
| Cancel Watcher | `backend/harness/services/cancel_watcher.py` | ~200 |
| Job Checkpoint | `backend/harness/services/job_checkpoint.py` | ~300 |
| Activity Feed hook | `src/lib/hooks/use-activity-feed.ts` | ~250 |
| Observability Panels | `src/components/activity/ObservabilityPanels.tsx` | ~300 |
| Kanban API | `backend/api/routers/kanban.py` | ~500 |

## Appendix B: Research Sources

- Greptile TREX blog: `https://www.greptile.com/blog/trex-code-execution` (2026-06-17)
- Anthropic "Effective harnesses for long-running agents": `https://anthropic.com/engineering/effective-harnesses-for-long-running-agents` (Nov 2025)
- Ranjan Kumar "Harness Engineering" series: `https://ranjankumar.in/harness-engineering-retry-fallback-circuit-breaking-llm-resilience`
- Kubernetes Agent Sandbox: `https://kubernetes.io/blog/2026/03/20/running-agents-on-kubernetes-with-agent-sandbox/`
- E2B vs Modal vs Daytona comparison: `https://agentmarketcap.ai/blog/2026/04/10/sandboxed-code-execution-ai-agents-e2b-modal-daytona`
- Northflank sandbox guide: `https://northflank.com/blog/how-to-sandbox-ai-agents`
- htek.dev "All Agent Harnesses: The Live Comparison": `https://htek.dev/articles/all-agent-harnesses-live-comparison`
- Tembo docs: `https://docs.tembo.io/features/sandbox/overview`
- TestSprite agentic testing platform: `https://www.testsprite.com/use-cases/en/agentic-testing-platform`
- Microsoft Agent Framework Neo4j Memory: `https://learn.microsoft.com/en-us/agent-framework/integrations/neo4j-memory`
- OpenHands StuckDetector: `https://docs.openhands.dev/sdk/guides/agent-stuck-detector`

---

*Report generated: 2026-06-25*  
*Status: COMPLETE*  
*Next review: 2026-07-09*
