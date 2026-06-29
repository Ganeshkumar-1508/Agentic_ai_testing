# Architecture Review — Grilling Q&A

Record of decisions made during the grilling loop. Date: 2026-06-23.

## Candidate #1: Collapse orchestrator `run_single` into composable phases

**Recommendation strength:** Strong

### Q1: Single atomic refactor or incremental Phase extraction?

**Decision:** Incremental, one Phase at a time. Start with KGIndexPhase.
**Reference:** OpenHands' 4-package split — each phase of the agent lifecycle is a separate module.

### Q2: Phase interface shape

**Decision:** Frozen immutable `RunContext` returned from each Phase.

```python
class RunPhase(Protocol):
    phase_name: str
    async def execute(self, ctx: RunContext) -> RunContext: ...
```

- `execute()` returns a new `RunContext` (immutable chaining via `dataclasses.replace`), not mutation in place
- `phase_name` is an instance attribute set via `__init__`, not a class attribute
- `RunContext` is a frozen dataclass carrying runtime data + service references
- **Reference:** Hermes Agent session lineage (compression creates new session row, doesn't mutate old one); OpenHands immutable Event pattern

### Q3: Wrapping strategy — thin wrappers or rewrite?

**Decision:** Thin Phase wrappers via Protocol (Hermes ABC pattern), not rewrites.

```python
class KGIndexPhase:
    async def execute(self, ctx: RunContext) -> RunContext:
        kg_ctx = SandboxKGContext.build(...)
        kg = await KnowledgeGraphSyncer.index(ctx.sandbox, "/workspace/repo", kg_ctx)
        return dataclasses.replace(ctx, kg_ctx=kg_ctx)
```

- **Reference:** Hermes `ContextEngine` ABC wrapping `ContextCompressor`; OpenCode service interfaces as thin wrappers around existing logic

### Q4: Pause checkpoint ownership

**Decision:** Orchestrator owns checkpoints between Phases. Individual Phases opt-in for mid-execution checkpoints (e.g., CoordinatorSpawn which runs for minutes).

```python
for phase in self._phases:
    ctx = await phase.execute(ctx)
    paused = await self.pause_checkpoint(phase=phase.phase_name)
    if paused:
        return paused
```

- **Reference:** OpenHands `conversation.pause()` / `conversation.run()` at conversation level (external control); Hermes GitHub issue #42723 requesting exactly this pattern

### Q5: Error handling and retry strategy

**Decision:** Two modes — `FATAL` (default) and `can_skip=True` (opt-in). Retries live inside Phases, not in the orchestrator.

```python
class KGIndexPhase:
    can_skip = True
    _max_retries = 2

    async def execute(self, ctx: RunContext) -> RunContext:
        # retry loop lives here, matching OpenHands' RetryMixin pattern
```

- **Reference:** OpenHands `RetryMixin` with exponential backoff at LLM call level; OpenCode Effect.ts `retry()` at service level

### Q6: Testing strategy

**Decision:** Mock sandbox, test the real Phase implementation.

```python
class FakeSandbox:
    async def run(self, command, timeout=30):
        return RunResult(stdout="inited", returncode=0)

async def test_kg_index_phase_sets_kg_ctx():
    phase = KGIndexPhase()
    ctx = RunContext(..., sandbox=FakeSandbox())
    result = await phase.execute(ctx)
    assert result.kg_ctx is not None
```

- **Reference:** OpenHands `FakeLLM`, `FakeWorkspace` in test suite

### Q7: Migration path

**Decision:** Alongside build — create Phase files, wire into `run_single` alongside inline code, remove inline after production validation.

- **Reference:** OpenCode wires new service interfaces alongside old code, deletes old code after validation

## Candidate #2: Decompose KanbanService god-class

**Recommendation strength:** Strong

### Q1: Split boundary — by entity or by lifecycle?

**Decision:** Two modules, not four. Split by lifecycle: `KanbanService` (CRUD + claims + events) and pluggable `TaskReviewer` (background LLM review). CRUD and claim lifecycle share the same DB connection, transaction patterns, and error modes.

- **Reference:** Hermes Agent keeps all kanban tools in one module (`kanban_tools.py`, 47KB); split happens at the tool/CLI boundary, not within the feature

### Q2: KanbanReviewAgent interface

**Decision:** Follow OpenHands' `SecurityAnalyzer` ABC pattern — pluggable strategy, not a standalone agent class.

```python
class TaskReviewer(ABC):
    """Pluggable review strategy — OpenHands SecurityAnalyzer pattern."""
    async def review(self, task: Task, context: ReviewContext) -> ReviewResult: ...

class LLMTaskReviewer(TaskReviewer):
    """LLM-powered review — the current behavior, extracted."""

class NoOpTaskReviewer(TaskReviewer):
    """Auto-approve — for trusted scenarios or non-PR workflows."""

class KanbanService:
    def __init__(self, db: Database, reviewer: TaskReviewer | None = None):
        self._reviewer = reviewer or NoOpTaskReviewer()
```

- **Reference:** OpenHands `SecurityAnalyzer` ABC with `LLMSecurityAnalyzer`, `NoOpSecurityAnalyzer` implementations; Hermes `kanban_complete` tool embeds review in completion flow

## Candidate #3: Unify dual API client

**Recommendation strength:** ~~Strong~~ → **Skipped**

Re-evaluated. The untyped `api` client works fine across 54 files with zero production bugs. The typed `client` is used in only 2 files. 1,763 lines of unused `schema.d.ts`. Cost to fix (54-file migration) outweighs benefit.

**Decision:** Skip. Delete the unused typed `client` export + `schema.d.ts`. Keep the untyped `api`. ~1 hour of work, removes 1,763 lines of dead code.
- **Reference:** Claude Code, Codex CLI, Hermes Agent don't use typed frontend API clients. Tool schemas are generated from Python type hints at registration time.

## Candidate #4: Extract KG types from `app/` to `lib/types/`

**Recommendation strength:** Strong

**Decision:** Do it. ~30 minute fix. Move `KGNode`, `KGEdge`, `KGCommunity` and helpers from `app/(dashboard)/knowledge-graph/_components/types.ts` to `lib/types/kg.ts`. Update 3 import paths.
- Fixes the only circular dependency risk in the frontend (utility layer depending on page layer)
- Enables testing `lib/search` and `lib/communities` without loading page components

## Candidate #5: Deepen the tool registry with permission-aware dispatch

**Recommendation strength:** ~~Worth exploring~~

**Decision:** Skip the big refactor — permissions are already well-separated in `PermissionManager`. The real friction is 7 special-cased tools in `ToolDispatcher` (submit_job, cancel_job, pause_job, etc.) that have dedicated handlers instead of being regular `BaseTool` subclasses.

**Simpler fix:** Eliminate the 7 special cases. Give each a `ToolHandler` Protocol so all 50+ tools go through the same dispatch path. ~200 lines of change.
- **Reference:** Cline registers all tools identically (MCP = built-in = same interface). OpenCode does the same — no special-casing.

## Candidate #6: Extract dashboard widgets SQL into DashboardWidgetService

**Recommendation strength:** Worth exploring

**Decision:** Do it. 800 lines, 15 endpoints with inline SQL. Extract into `DashboardWidgetService` — one method per widget, independently testable. Partially unblocked by Candidate #1's Phase pattern (dashboard widgets become read-only Phases). ~1 sprint.

## Candidate #7: Consolidate three event systems

**Recommendation strength:** Worth exploring

**Decision:** Do it. Three systems (EventBus, EventSourcedState, stream_events) doing overlapping work. Absorb `EventSourcedState`'s time-travel into `EventBus`. Delete `state/event_sourced.py`. Keep `stream_events` as SSE fallback. ~2 sprints.
- **Reference:** OpenHands has a single EventStream. LangGraph has checkpoints instead of events. Both prove one system is enough.

## Candidate #8: Extract fat route handlers into services

**Recommendation strength:** Worth exploring

**Decision:** Defer. Candidate #1 (Phase decomposition) will naturally pull business logic out of route handlers. Once Phases exist, the fat routes (settings.py 588L, admin.py 603L, sandbox.py 633L, runs.py 648L) become thin delegates. Revisit after Candidate #1 is complete.

## Candidate #9: Deepen SSE/reconnection primitives

**Recommendation strength:** Speculative

**Decision:** Defer. The `createReconnectingEventSource` factory pattern works. Duplication across 3 hooks (use-event-source, use-activity-feed, use-session-events) is real but not causing bugs. Revisit when a 4th consumer appears or when the SSE protocol changes.
- **Reference:** OpenCode uses a single `createReconnectingEventSource` with one consumer. OpenHands uses WebSocket with one EventStream. Both simpler than TestAI's 4-consumer pattern — worth adopting when refactoring the frontend event layer.

## Candidate #10: Remove deprecated hooks/registry.py

**Recommendation strength:** Speculative

**Decision:** Do it. 49 lines, already deprecated by docstring. Delete the file, audit imports, confirm nothing references it. ~1 hour of work.

## Feature: Expose ToolRegistry as MCP Server

**Recommendation strength:** ~~Worth exploring~~ → **Skipped**

Re-evaluated. None of the major harnesses (Hermes, Cline, OpenCode) expose their own tools as MCP servers. They all consume MCP externally. Security (bypasses permission gating), context (no session state), and ecosystem direction (MCP-as-consumer) all argue against it.

**Decision:** Skip. Keep TestAI as an MCP consumer. Improve MCP server discovery and tool registration instead.

## Feature: A2A (Agent-to-Agent) Protocol adoption

**Recommendation strength:** Worth exploring

**Decision:** Monitor, don't build yet. A2A v1.0 was released 2026 under Linux Foundation with Google/AWS/Microsoft backing, but no major coding harness has adopted it yet. TestAI's `delegate_task` already serves the same purpose internally. When A2A gains harness adoption (check back in 6 months), add an A2A adapter layer. ~2 sprints when the time comes.
- **Reference:** BeeAI/IBM Agent Stack is A2A-native but isn't a coding harness — it's infrastructure. No OpenCode, Claude Code, or Hermes adoption yet.

## Feature: Pluggable sandbox abstraction (SandboxExecutor protocol)

**Recommendation strength:** Worth exploring

**Decision:** Defer. TestAI's Docker sandbox works. Daytona (90ms create), E2B (pause/resume), and Modal (readiness probes) are valuable but no harness has adopted a pluggable backend yet — Hermes started but only recently added Modal to their terminal backends. Revisit when a second sandbox provider is demanded. ~3 sprints.
- **Reference:** OpenHands has 3 workspace modes (Local, Docker, Remote) — the only harness with true pluggable backends. Hermes just added Modal support to their terminal backends.

## Feature: Test-result-driven feedback loop (Greptile TREX pattern)

**Recommendation strength:** Worth exploring

**Decision:** Do it incrementally. TestAI already has codegraph + sandbox + test execution. They're just not wired together into a learning loop. Add a `TestResultFeedack` Phase that: (1) runs tests via sandbox, (2) captures diffs in test output, (3) stores results in codegraph metadata, (4) feeds back into coordinator's context. This is a natural Phase for Candidate #1's Phase system. ~2 sprints.
- **Reference:** Greptile TREX: sandboxed test execution → capture results → feed back into review loop. TestAI has all the pieces, just not connected.

## Feature: Multi-repo PR coordination (Tembo pattern)

**Recommendation strength:** Worth exploring

**Decision:** Already partially done (C08 cross_repo.py, run_multi). Complete the integration: wire `cross_repo.py` into the full Run flow so a single Run opens coordinated PRs across repos with cross-references. ~2 sprints.
- **Reference:** Tembo's core differentiator is multi-repo PR coordination. TestAI has the primitives but not the polished flow.

## Feature: Hidden system agents (OpenClaude pattern)

**Recommendation strength:** Speculative

**Decision:** Defer. OpenClaude runs hidden agents for compaction, title, summary. TestAI already has compaction but not as a named agent. The value is marginal until Candidate #1 (Phase system) is complete — at which point hidden agents are just Phases without UI visibility. ~1 sprint after Phase system is live.

## Feature: Custom mode definitions (Kilo Code pattern)

**Recommendation strength:** Speculative

**Decision:** Already done. TestAI's Role YAML system and Agent Registry are richer than Kilo Code's JSON mode configs. Kilo Code's innovation is JSON serialization being user-friendly. Add JSON export/import to Role definitions as a quality-of-life improvement. ~1 sprint.

---

## Implementation Log (2026-06-24)

All items from this review have been implemented in a single session:

| Item | Status | Detail |
|------|--------|--------|
| C10 | ✅ | Deleted `hooks/registry.py` (49 lines), redirected imports to `_hook_system` |
| C4 | ✅ | Created `lib/types/kg.ts`, fixed circular `lib/` → `app/` dependency |
| C3 | ✅ | Deleted typed `client` + `schema.d.ts` (1,763 lines), uninstalled `openapi-fetch` |
| C6 | ✅ | Extracted `DashboardWidgetService` (15 methods), router 895→85 lines |
| C7 | ✅ | Deleted `EventSourcedState` (250 lines, zero consumers), removed `state/` dir |
| C5 | ✅ | Replaced 7 if/elif chains with dict-based dispatch in `tool_dispatch.py` |
| C2 | ✅ | Extracted `TaskReviewer ABC` from `KanbanService`, `LLMReviewer` + `NoOpReviewer` |
| F5 | ✅ | Wired `coordinate_multi_repo_results()` into `run_multi` with `Depends-On` |
| F4 | ✅ | Added `store_test_results_in_codegraph()` + `get_test_failures_for_run()` |
| C1 | ✅ | Created `RunPhase` Protocol, `RunContext`, `KGIndexPhase`, wired alongside |
| F6 | ✅ | Created `RunSummaryPhase` — hidden agent for post-run summary + memory + session naming |
| F7 | ➖ | Skipped — low value |
| F3 | ➖ | Deferred — revisit when second sandbox provider demanded |
| F2 | ➖ | Deferred — revisit when A2A gains harness adoption |
| F1 | ➖ | Skipped — keep TestAI as MCP consumer |

---

## Upcoming Projects Research (2026-06-24)

18 projects found via GitHub topic search that could benefit TestAI.
Full details in `docs/upcoming-projects-research-2026-06-24.md`.

### Adoption Roadmap

| Priority | Project | Stars | Key Pattern | Effort |
|----------|---------|-------|-------------|--------|
| **P1** | Sponsio | 477 | Deterministic policy enforcement (0.01ms, zero LLM cost) | 3 sprints |
| **P2** | TokenTamer | 123 | AST-based context compression (50-80% savings) | 2 sprints |
| **P3** | Scenario | 903 | Simulation-based agent testing (agents test agents) | 2 sprints |
| **P4** | Chorus | 1k | AI-DLC workflow, Agent Connections dashboard | 2 sprints |
| **P5** | Mirage | 3.2k | Unified VFS — replace 10-15 API tools with filesystem ops | 3 sprints |
| **P6** | Nono | 2.8k | Zero-latency sandbox (lightweight alternative to Docker) | 2 sprints |
| **P7** | Cognee | 20.1k | Memory platform with knowledge graph | 2 sprints |
| **P8** | oh-my-pi | 14.3k | Hash-anchored edits, LSP pre-flight, DAP integration | 4 sprints |
| **P9** | Logfire | 4.3k | Pydantic-built agent observability (OTel-native) | 1 sprint |
| P10 | abtop | 3.1k | Agent process monitor (htop for agents) | 1 sprint |
| P11 | claude-tap | 2k | Agent API traffic inspector | 1 day |
| P12 | TrustGraph | 2.2k | Holonic context graphs for L2 memory | 3 sprints |
| P13 | BitRouter | 185 | Cost-optimizing LLM router | 2 sprints |
| P14 | oh-my-agent | 1.1k | Domain-specialized agent roles | 2 sprints |
| P15 | thClaws | 1.1k | OpenRouter Fusion (multi-model deliberation) | 3 sprints |
| P16 | Replayd | 17 | Replayable agent regression tests | 1 sprint |
| P17 | Memori | 15.4k | Agent-native memory infrastructure | 2 sprints |
| P18 | agentverify | 8 | Pytest plugin for deterministic agent testing | 1 sprint |
