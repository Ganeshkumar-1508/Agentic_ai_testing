# TestAI Architecture Decision Tree — Grilling Session

**Date**: 2026-06-21
**Mode**: Relentless Q&A. Each candidate walked down its design tree, one decision at a time. Each Q locked before moving on.
**Goal**: Resolve architectural friction in TestAI's agent harness against 2026 state-of-the-art (Claude Code, OpenAI Codex CLI, Hermes, OpenClaw, OpenHands, Aider, OpenCode, Pi).
**Starting recommendation**: C04 (kg_refresh) — smallest in scope (~3 days), unblocks better subagent behavior in every other candidate, seam already half-built.

---

# Candidate C04 — `kg_refresh` tool at coordinator level

**Context**: KG is built once at orchestrator setup (`orchestrator.py:333`) and synced once at orchestrator end (`orchestrator.py:568-569`). Subagents in the middle see a **stale** view. The June 18 2026 audit flagged this as a `High` gap. The proposal: promote `KnowledgeGraphSyncer.sync` to a tool the coordinator can call mid-run.

**Files involved**:
- `backend/harness/services/knowledge_graph_syncer.py:185` (existing `sync` collaborator)
- `backend/harness/toolsets.py` (add `kg_refresh` to `coordinator` toolset)
- `backend/harness/codegraph.py:39` (`_run_in_sandbox` is the underlying primitive)
- `src/components/.../KGPanel.tsx` (new frontend component)

---

## Decision Q1 — kg_refresh trigger model

**Question**: When should the KG get refreshed during a run? Four trigger models.

**Options presented**:
- (A) Manual via tool call — LLM is the gatekeeper
- (B) Auto-hook on write tools — guaranteed fresh
- (C) Pre-query auto-refresh — lazy
- (D) Background timer — opaque

**Recommended**: (A) Manual via tool call — gives the coordinator LLM agency to decide when a refresh is worth the cost (a 10-second sync on a 50k-file repo is non-trivial). (B) is robust but burns cycles. (C) couples query semantics to refresh state. (D) is opaque.

**Locked answer**: **(A) Manual via tool call.**

**Reasoning recorded**:
- The coordinator already has 22 read-only `codegraph_*` tools in its toolset. Adding a write tool is a precedent, but it's a controlled one.
- The LLM is the right place to reason about cost vs. freshness — it's the entity that will pay the cost of the next query.
- (B) auto-hook is appealing but a chatty subagent doing 10 edits triggers 10 syncs; even with debounce, the timing is wrong (sync after the LAST edit, not after every edit).
- (C) pre-query coupling creates state in the query path — a query tool's behavior changes based on when it was last called.
- (D) background timer is opaque — the coordinator doesn't know when refresh ran.

---

## Decision Q2 — kg_refresh tool surface (v1)

**Question**: What can the coordinator pass to `kg_refresh`? The current `KnowledgeGraphSyncer.sync` is no-arg. Three options.

**Research done** (per user request):
- `codegraph sync` is incremental by default and auto-detects changes via mtime
- `codegraph init --index` is the full reindex primitive (called at setup)
- No paths/scope flag is wired in the current codegraph call
- Status dict returned: `{nodeCount, edgeCount, symbols, files, ...}` from `codegraph status -j`
- Default timeouts: `index=600s`, `sync=60s`

**Options presented**:
- (A) No args — `kg_refresh()` always runs `codegraph sync` (incremental, fast)
- (B) Optional `mode="incremental"|"full"` — default incremental, opt-in full reindex
- (C) Optional `paths=[...]` — LLM scopes to a specific path
- (D) All of the above — full surface

**Recommended**: (A) No args for v1. `codegraph sync` is already correct; the LLM doesn't need to reason about scope. Add (B) later if the LLM starts getting confused. (C) is YAGNI — if the LLM knows which path changed, it already has the file content.

**Locked answer**: **(A) No args.**

**Reasoning recorded**:
- `codegraph sync` is incremental by design — changed files are auto-detected via mtime. No paths filter is needed.
- The status dict already returns `nodeCount` and `edgeCount` — the LLM can read the counts to decide what to do next.
- (B) full reindex is recoverable by the user calling `kg_refresh()` and accepting the cost. If the LLM empirically confuses incremental with full, add the param later.
- (C) is YAGNI: if the LLM knows the path, it has the file. The KG just needs to know about it, which `codegraph sync` does automatically.

---

## Decision Q3 — kg_refresh access model

**Question**: Who can call `kg_refresh`? `kg_refresh` is a write to the KG (rerun sync, copy DB, write provenance). Today the coordinator's toolset has 22 read-only `codegraph_*` tools. Adding `kg_refresh` introduces the first coordinator-only write tool.

**Options presented**:
- (A) Coordinator only — `coordinator` toolset gains `kg_refresh`; leaf workers do NOT inherit it
- (B) Coordinator + read-only-leaf workers — read-only roles can also refresh
- (C) Any role — added to a shared 'intelligence' toolset
- (D) Configurable per-role — Role YAML gets a `kg_refresh: true|false` flag

**Recommended**: (A) Coordinator only. The reasoning: leaf workers should signal "I need fresh data" to the coordinator via a comment or a return value, not call `kg_refresh` themselves. The coordinator reasons about cost.

**Locked answer**: **(A) Coordinator-only.**

**Reasoning recorded**:
- The 6-layer tool access model in the domain glossary is explicit about leaf worker restrictions. `kg_refresh` is a write tool — it should follow the same pattern.
- (B) opens the door to N leaf workers thrashing the KG.
- (C) is the current pattern for the old `kg_*` tools, which is part of the problem we're solving (those tools are being phased out).
- (D) is over-engineered for v1. If a project legitimately needs leaf workers to refresh, they can submit a PR.

**Consequence**: The blocked-tools list at `harness/tools/delegate_task.py:312-317` (the leaf worker allowed-tools set) explicitly does NOT include `kg_refresh`. New leaves default to excluded.

---

## Decision Q4 — kg_refresh return shape

**Question**: What does `kg_refresh` return? The current `KnowledgeGraphSyncer.sync` returns a snapshot. For the LLM to decide what to do next, it needs to know what CHANGED, not just the current state.

**Options presented**:
- (A) Just the status dict — what `KnowledgeGraphSyncer.sync` already returns
- (B) Status dict + delta since last refresh — `added: N symbols, removed: M, modified: K`
- (C) Status dict + list of changed files
- (D) Status dict + diff at symbol level

**Recommended**: (B) Status + delta. The delta is the natural unit the LLM reasons about.

**Locked answer**: **(B) Status dict + delta since last refresh.**

**Reasoning recorded**:
- (A) is insufficient because the LLM can't tell a meaningful refresh from a no-op. If two consecutive refreshes return the same nodeCount, the LLM has no signal.
- (B) requires storing the previous status in `SandboxKGContext`. The delta is the natural unit the LLM reasons about: "3 symbols were added, I should re-query the affected files."
- (C) is too verbose for LLM decision-making; useful for human review but not for the LLM's next move.
- (D) is the most informative but most expensive to compute; rarely needed.

**Consequence**: `SandboxKGContext` gains a `last_status: dict | None` field initialized to `None`. After each `kg_refresh` (and the post-coordinator sync), `last_status` is updated. The delta is computed at tool-call time by comparing current status to `last_status`.

---

## Decision Q5 — kg_refresh debounce

**Question**: What stops the coordinator from calling `kg_refresh` in a tight loop?

**Options presented**:
- (A) Hard debounce — default 60s window; `force=true` escape hatch
- (B) Soft debounce — runs anyway with warning
- (C) No debounce — let the LLM thrash
- (D) Per-context debounce — debounce per (session, subagent_id)

**Recommended**: (A) Hard debounce with `force=true` escape. The escape hatch matters because some legitimate scenarios require back-to-back refreshes.

**Locked answer**: **(A) Hard debounce with `force=true` escape.**

**Reasoning recorded**:
- A chatty coordinator could call `kg_refresh` 10 times in a row. Each sync costs 5-30 seconds of sandbox time and tokens for the tool call. The delta is the same on each call (no files changed). Pure waste.
- (B) burns cycles. The LLM sees the warning but may not self-correct.
- (C) is irresponsible. The cost of thrash is real.
- (D) is over-engineered for v1 — `kg_refresh` is coordinator-only, so per-subagent debounce adds little.

**Return shape on debounce**:
```python
{
    "success": True,
    "skipped": True,
    "last_refresh_age_seconds": 23,
    "force_available": True,
    "message": "Refusing to refresh; last refresh was 23s ago. Pass force=true to override."
}
```

**Configuration**: env var `KG_REFRESH_DEBOUNCE_SECONDS` (default 60).

---

## Decision Q6 — kg_refresh observability data surface

**Question**: Where does the refresh event live? The dashboard wants to show "KG last synced 23s ago, +3 symbols, -1 function".

**Options presented**:
- (A) `stream_events` table with new `kg.refreshed` event_type
- (B) New `kg_refresh_log` table — purpose-built
- (C) Push to SSE directly without DB persistence
- (D) All of the above

**Recommended**: (A) `stream_events` for v1. The `stream_events` table is already the source of truth for everything tool-related.

**Locked answer**: **(A) `stream_events` `kg.refreshed` event.**

**Reasoning recorded**:
- The dashboard already subscribes to `stream_events` via SSE. Adding a new event_type is a 10-line change.
- (B) creates a parallel data model and a sync problem (when do they agree?). The cost of dual-writes is not worth the marginal query convenience.
- (C) loses history. Non-starter for debugging past runs.
- (D) is maximum redundancy, maximum sync headaches.

**Event payload schema**:
```json
{
    "type": "kg.refreshed",
    "timestamp": "2026-06-21T14:23:45Z",
    "session_id": "...",
    "nodeCount": 1234,
    "edgeCount": 5678,
    "delta": { "added": 3, "removed": 0, "modified": 2 },
    "duration_ms": 1240,
    "skipped": false,
    "force": false
}
```

---

## Decision Q7 — End-of-run sync after kg_refresh

**Question**: Should the existing end-of-run `KnowledgeGraphSyncer.sync` at `orchestrator.py:568-569` still run after `kg_refresh` lands?

**Options presented**:
- (A) Keep always — defense in depth
- (B) Remove — coordinator is responsible
- (C) Conditional — only if no `kg_refresh` in last 5 min
- (D) Conditional — only if last `kg_refresh` was skipped/error

**Recommended**: (A) Keep always. `codegraph sync` is incremental and idempotent; running it again at end-of-run costs ~1s.

**Locked answer**: **(A) Keep always.**

**Reasoning recorded**:
- The end-of-run sync is the **last word** on host cache state. If the coordinator didn't call `kg_refresh` in the last few minutes (e.g., a short run, or a coordinator that was about to commit and PR), the end-of-run sync catches the final state.
- (B) introduces risk: a coordinator that forgot to call `kg_refresh` at the end leaves a stale host cache for the next run.
- (C) and (D) are clever but the cost they save is sub-second on a no-op refresh.
- Defense in depth is the right tradeoff here. The end-of-run sync is **idempotent** with `kg_refresh` (both use incremental sync). Running it twice is harmless.

---

## Decision Q8 — kg_refresh UI surface

**Question**: Where does the KG refresh surface in the dashboard?

**Options presented**:
- (A) Header pill only — "KG: last synced 23s ago (+3 symbols)"
- (B) Header pill + dedicated panel — at-a-glance + history
- (C) Inline in tool call timeline — each `kg_refresh` shows as a tool call entry
- (D) Permanent sidebar widget

**Recommended**: (B) Header pill + dedicated panel. Header pill for at-a-glance freshness; panel for history and debug.

**Locked answer**: **(B) Header pill + dedicated panel.**

**Reasoning recorded**:
- The header pill pattern is already used elsewhere in the dashboard for state indicators (e.g., "memory last updated 2m ago"). Consistent.
- A dedicated panel gives the developer the debug surface they need (full history, deltas, durations).
- (A) is too thin for debugging — no history.
- (C) buries the signal in noise. The tool call timeline has hundreds of entries.
- (D) takes permanent real estate for a feature used occasionally.

**Pill copy**:
```
Default:   "KG: 23s ago · +3 symbols"
Stale:     "KG: 5m ago · stale"  (red dot)
Error:     "KG: refresh failed"   (red dot, click to expand)
Never:     "KG: not yet refreshed" (gray dot)
```

---

## Decision Q9 — KG panel hero content

**Question**: The panel opens on click. What does the user see first?

**Options presented**:
- (A) Latest refresh hero — most recent at top, large
- (B) Aggregate stats header — "23 refreshes, +45 -12 net" up top, list below
- (C) Time series sparkline — chart of nodeCount over time at top
- (D) Filter controls — date range / session filter at top

**Locked answer**: **(A + B + C + D)** — full layered debug panel: latest refresh hero, aggregate stats header, time series sparkline, filter controls.

**Reasoning recorded**:
- The user picked all four. The panel is a debug surface; richness is appropriate.
- (A) gives the most-recent at-a-glance.
- (B) gives the actionable aggregate signal ("is the KG changing meaningfully?").
- (C) gives a visual trend.
- (D) gives filtering for runs with many refreshes.

**Panel layout sketch**:
```
┌─ KG Activity ────────────────────────────────────────┐
│  23 refreshes · +45 -12 net · 1.2s avg · last 23s ago │
│                                                      │
│  [time-series sparkline of nodeCount over run]       │
│                                                      │
│  ── Latest refresh ──                                │
│  14:23:45  +3 / -0 / ~2  · 1.2s · 1234 → 1237 nodes  │
│  payload: { ... }                                    │
│                                                      │
│  ── Filter: [All ▾] [Session ▾] [Date range ▾] ──    │
│                                                      │
│  ── All refreshes ──                                 │
│  14:23:45  +3 -0 ~2  1.2s                             │
│  14:21:12  +1 -0 ~0  0.8s                             │
│  14:18:33  +5 -2 ~1  2.1s                             │
│  ...                                                 │
└──────────────────────────────────────────────────────┘
```

---

## Decision Q10 — kg_refresh failure model

**Question**: What does the LLM see when the sync fails? `kg_refresh` can fail in 4 ways: (1) `codegraph sync` returns non-zero, (2) sync times out (60s), (3) DB copy to host fails, (4) sandbox is unreachable.

**Options presented**:
- (A) Categorized error re-raise — return `{success: false, error, category, duration_ms, recoverable}`
- (B) Silent retry once with backoff, then re-raise
- (C) Silent return with warning
- (D) Return success with `stale: true` flag

**Recommended**: (A) Categorized error re-raise. The LLM needs to know if it's safe to continue using the KG or if the agent should switch to read-only mode.

**Locked answer**: **(A) Categorized error re-raise.**

**Reasoning recorded**:
- The current `KnowledgeGraphSyncer.sync` silently catches all exceptions and returns `{}`. This is the anti-pattern. The LLM has no signal.
- (B) hides useful information and adds latency on the first failure.
- (C) is the current anti-pattern. No.
- (D) is clever but the LLM doesn't know what `stale: true` means without context. Categorical errors are more actionable.

**Failure return shape**:
```python
{
    "success": False,
    "error": "codegraph sync returned exit code 1: <stderr>",
    "category": "sync_failed",  # or "timeout" | "copy_failed" | "sandbox_unreachable"
    "duration_ms": 60230,
    "recoverable": True,  # or False
    "context": {
        "sandbox_id": "...",
        "last_successful_status": { ... }  # what we had before
    }
}
```

**Recoverability matrix**:
- `sync_failed` (exit code 1): recoverable — usually means mtime glitch; retry likely succeeds
- `timeout`: recoverable — sandbox may be slow; retry later
- `copy_failed`: recoverable — host disk issue; retry
- `sandbox_unreachable`: not recoverable — escalate to user

---

## Implementation sketch (post-grill)

**New file**: `backend/harness/tools/kg_refresh_tool.py` (~150 lines)

```python
class KgRefreshTool(BaseTool):
    """Coordinator-only tool: trigger an incremental KG sync mid-run."""

    name = "kg_refresh"
    description = "Re-index the knowledge graph so subsequent codegraph_* queries see the latest state."

    def __init__(self, *, debounce_seconds: int = 60):
        self._debounce_seconds = debounce_seconds
        self._last_refresh_at: float = 0.0
        self._last_status: dict | None = None
        self._lock = asyncio.Lock()

    async def run(self, force: bool = False, **kwargs) -> ToolResult:
        # 1. Debounce check
        now = time.monotonic()
        elapsed = now - self._last_refresh_at
        if not force and elapsed < self._debounce_seconds:
            return ToolResult(success=True, output={
                "skipped": True,
                "last_refresh_age_seconds": int(elapsed),
                "force_available": True,
            })

        # 2. Run the sync
        ctx = get_kg_context()  # session_id → SandboxKGContext
        start = time.monotonic()
        try:
            fresh = await KnowledgeGraphSyncer.sync(sandbox, repo_path, ctx)
            if not fresh:
                raise KgRefreshError(category="sync_failed", message="empty status")
        except KgRefreshError:
            raise
        except Exception as exc:
            # Categorize
            category = self._categorize_failure(exc)
            raise KgRefreshError(category=category, message=str(exc),
                                 recoverable=category != "sandbox_unreachable")

        # 3. Compute delta
        delta = self._compute_delta(fresh, self._last_status)

        # 4. Update state
        async with self._lock:
            self._last_refresh_at = time.monotonic()
            self._last_status = fresh

        # 5. Emit observability event
        await emit_stream_event({
            "type": "kg.refreshed",
            "session_id": ctx.session_id,
            "nodeCount": fresh.get("nodeCount"),
            "edgeCount": fresh.get("edgeCount"),
            "delta": delta,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "skipped": False,
            "force": force,
        })

        return ToolResult(success=True, output={
            "nodeCount": fresh.get("nodeCount"),
            "edgeCount": fresh.get("edgeCount"),
            "delta": delta,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "last_refresh_at": time.time(),
        })
```

**Toolset change** (in `backend/harness/toolsets.py`):
```python
COORDINATOR_TOOLSET = (
    # ... existing 22 tools
    "kg_refresh",  # NEW: incremental sync trigger
)
```

**Leaf-worker blocked list** (in `backend/harness/tools/delegate_task.py:312`):
```python
allowed_leaf = {
    "bash", "read_file", "write_file", "edit_file", "apply_patch",
    "glob", "grep", "list_files", "web_fetch", "web_search",
    "codegraph_explore", "codegraph_search", "codegraph_node",
    "codegraph_callers", "codegraph_callees", "memory",
    "tool_search", "todo", "skills_list", "skill_view",
    # NOTE: kg_refresh is intentionally NOT in this set
}
```

**Frontend component** (in `src/components/.../KGPanel.tsx`):
- Subscribes to SSE for `kg.refreshed` events
- Computes aggregate stats client-side
- Renders hero + sparkline + filterable list

**Test plan**:
- Unit tests for debounce logic (force override, window boundary)
- Unit tests for delta computation (added, removed, modified)
- Unit tests for failure categorization
- Integration test: real codegraph sync against a small repo
- E2E test: coordinator calls `kg_refresh`, dashboard panel updates

---

## Open questions for C04 (deferred to next grilling session)

1. Should `kg_refresh` also emit an L1 promotion event for the L1Indexer? (Currently the L1Indexer extracts from tool calls, not from KG events.)
2. What happens during a multi-repo run? Each repo has its own KG; does `kg_refresh` know which repo the coordinator is currently working on?
3. Should the dashboard show KG staleness as a "warning" state when no refresh has happened in >5 minutes, even if the user hasn't requested one?
4. How does `kg_refresh` interact with the L2 memory pipeline (`l2_reflection.py`)? Does it count as an "agent work" event that the L2 curator should summarize?
5. What about C03 (push-based completion) — when the orchestrator receives a `subagent.completed` event for a leaf worker that wrote files, should it auto-trigger a `kg_refresh`?

---

# Candidate C08 — JobSpec canonicalisation

**Context**: The June 18 2026 audit found three separate frontend flows bypass the `JobSpec` handoff that the domain glossary says is canonical: Agent page → `/api/agent/run`, Pipeline → Orchestrate → `/api/delegate`, Pipeline → Quick Test → `/api/pipeline/from-requirements`. None of them construct a `JobSpec`. The chat Role's `submit_job` tool is the only place that does. Deletion test: if you delete the `JobSpec` concept, none of the three flows breaks — proving the seam is hypothetical, not real.

**JobSpec today**: `backend/harness/jobs/spec.py:108` is a dataclass with 12 fields: `spec_id`, `run_id`, `source`, `prompt`, `repo_url`, `branch`, `sha`, `tier`, `capabilities`, `approval`, `context`, `created_at`. The CONTEXT.md glossed over some of these.

**Three endpoint bodies** (very different shapes):
- `/api/agent/run` (`agent.py:31-37`): `AgentRunRequest(prompt, mode, session_id, repo_url, tier)` — 5 fields
- `/api/delegate` (`delegate.py:29-40`): `DelegateRequest(prompt, repo_url, branch, repos, tasks, context, toolsets, role, run_in_background, model, mcp_servers)` — 11 fields
- `/api/pipeline/from-requirements` (`pipeline.py:57-94`): `PipelineFromRequirements` — 30+ fields including test-specific config (`pre_commands`, `post_commands`, `cache_directories`, `browser`, `os`, etc.)

**Research grounding**: Tembo exposes `POST /session/create` with `{prompt, description, agent, repositories, codeRepoIds, targetBranch, branchName, queueRightAway}`. Devin exposes `POST /sessions` with `{prompt, create_as_user_id}`. Both return immediately with `id`, run async, status via polling. **TestAI's JobSpec is more sophisticated than competitor equivalents because testing is a vertical with fine-grained control needs.** The 12 fields are justified; the 30+ from-requirements extras are testing-specific and live in `context.test_config`.

**Files involved**:
- `backend/harness/jobs/spec.py:108` (JobSpec definition)
- `backend/harness/store/protocols.py:288` (JobSpecStore protocol)
- `backend/api/routers/agent.py:39` (`/api/agent/run`)
- `backend/api/routers/delegate.py:67` (`/api/delegate`)
- `backend/api/routers/pipeline.py:57` (`/api/pipeline/from-requirements`)
- `src/app/(dashboard)/agent/page.tsx`
- `src/app/(dashboard)/pipeline/page.tsx`
- `src/stores/pipeline-store.ts`

---

## Decision Q1 — JobSpec canonicalisation scope

**Question**: The three endpoints have very different bodies (5, 11, 30+ fields). Where does canonicalization happen?

**Options presented**:
- (A) All are jobs. Expand JobSpec to ~30 fields
- (B) Two shapes: JobSpec (what to do) + TestSpec (how to test)
- (C) Stuff from-requirements extras into JobSpec.context as a dict
- (D) Keep the three endpoints as wrappers. Each builds a JobSpec before calling the orchestrator. JobSpec is canonical at the orchestrator boundary, not at the API boundary.

**Recommended**: (D). The three endpoints are PRODUCT surfaces (chat, quick test, orchestrate) with different UX requirements. They SHOULD have different request shapes. Canonicalization happens at the orchestrator boundary.

**Locked answer**: **(D) Canonicalize at orchestrator boundary, not API.**

**Reasoning recorded**:
- CONTEXT.md says "JobSpec is the unit of handoff" — that's at the handoff to the orchestrator, not at the API surface.
- The three API endpoints serve different product surfaces (chat, quick test, orchestrate). Conflating their request shapes would harm UX.
- (A) bloats JobSpec to ~30 fields. Most fields are unused in the chat path.
- (B) creates a new shape. Two shapes is the opposite of canonicalization.
- (C) is lazy and loses type safety.

---

## Decision Q2 — `tier` field handling

**Question**: JobSpec requires `tier` (1/2/3). The three endpoints handle tier very differently: `/api/agent/run` has `tier: int` field, `/api/delegate` doesn't have tier (uses `role: str = "leaf"`), `/api/pipeline/from-requirements` doesn't have tier.

**Options presented**:
- (A) Make tier REQUIRED in all three — breaking change
- (B) Default tier=1 (autonomous) for endpoints that don't have it — backwards compatible
- (C) Make tier OPTIONAL with per-endpoint default (all default to 1, can be overridden)
- (D) Tier from user/org settings

**Recommended**: (C). All three get optional `tier` field with default=1. Non-breaking.

**Locked answer**: **(C) Optional with per-endpoint default (all default to 1).**

**Reasoning recorded**:
- The chat endpoint already has tier; we extend the pattern.
- The other two don't have tier today, so adding it as optional with default=1 is non-breaking.
- Tier=1 (autonomous) is the right default for all three — quick-test is end-to-end, orchestrate is already autonomous, chat with pipeline mode runs the orchestrator.
- (D) requires a settings layer that doesn't exist yet.

---

## Decision Q3 — Where do from-requirements 30+ extras live?

**Question**: `PipelineFromRequirements` has 30+ fields, only 3 of which (prompt, repo_url, branch) map directly to JobSpec. The rest are test-specific (`pre_commands`, `cache_directories`, `browser`, `os`, `runtime_version`, etc.).

**Options presented**:
- (A) Stuff them all into `JobSpec.context.test_config` as a typed sub-model
- (B) Extend JobSpec with each from-requirements field as optional (~30 fields)
- (C) Pass a separate `TestConfig` object alongside JobSpec
- (D) Rewrite from-requirements to use only JobSpec fields (breaking)

**Recommended**: (A). JobSpec.context gains a typed sub-model. The orchestrator ignores `test_config` (it's for the test runner downstream).

**Locked answer**: **(A) Typed sub-model in JobSpec.context.**

**Reasoning recorded**:
- The 30+ fields ARE test-specific and don't belong at the orchestrator level.
- (B) conflates job config with test config; bloats JobSpec.
- (C) creates a new shape.
- (D) loses the test config.
- The orchestrator only sees `JobSpec`; `context.test_config` is opaque to it. The test runner downstream unpacks it.

---

## Decision Q4 — JobContext shape

**Question**: Currently `JobSpec.context: dict[str, Any]`. We need to type it. The current known uses: `session_id` (chat), `agent_id` (chat), `test_config` (from-requirements).

**Options presented**:
- (A) Pydantic with `extra='allow'` — strict for known, permissive for unknown
- (B) Strict Pydantic, no extras — any new key requires migration
- (C) Keep `dict[str, Any]` with documented keys
- (D) Typed model + metadata dict sibling

**Recommended**: (A) Pydantic with `extra='allow'`. The 4 well-known fields are typed; unknown fields allowed.

**Locked answer**: **(A) Pydantic with `extra='allow'`.**

**Reasoning recorded**:
- Strict (B) breaks the chat's existing context dict usage.
- (C) loses type safety on fields that matter.
- (D) is two-layer for the same purpose.
- (A) is forward-compatible: new fields can be added without schema migration.

**JobContext fields** (locked):
```python
class JobContext(BaseModel):
    model_config = ConfigDict(extra='allow')
    session_id: str | None = None
    agent_id: str | None = None
    test_config: TestConfig | None = None
    request_metadata: dict[str, Any] | None = None
```

---

## Decision Q5 — Chat vs API submission paths

**Question**: Today: chat.submit_job persists to `job_specs` table; orchestrator polls. The three API endpoints call `OrchestratorEngine.run_job_spec(spec)` directly. Two different paths.

**Research grounding**: Tembo and Devin both return session_id immediately, run async, status via polling. **The chat's DB+poll pattern IS the industry-standard async submission.** The three API endpoints just skip durability.

**Options presented**:
- (A) All four durable — every submission persists to `job_specs`, orchestrator polls uniformly
- (B) Chat durable, API direct (current duality)
- (C) All four direct (no DB) — uniform but loses durability
- (D) All four durable via queue (Tembo's `queueRightAway` pattern)

**Recommended**: (A). The cost of a DB write is ~5ms; the benefit of durability is huge.

**Locked answer**: **(A) All four durable, uniform path.**

**Reasoning recorded**:
- If the orchestrator crashes mid-run, an API request can be re-fetched by run_id from the `job_specs` table.
- A2A adapter benefits from durable records.
- Tembo's `queueRightAway: false` pattern is interesting but our orchestrator already has direct invocation.
- (B) is the current pattern but the duality is friction, not value.
- (C) loses durability.
- (D) is over-engineered for v1.

---

## Decision Q6 — New `/api/jobs` endpoint for external integrations

**Question**: C08 enables A2A. The A2A adapter needs to POST a JobSpec to TestAI. None of the three legacy endpoints accept a JobSpec directly.

**Options presented**:
- (A) New `POST /api/jobs` accepts a JobSpec directly
- (B) Modify `/api/delegate` to accept an optional JobSpec (dual mode)
- (C) No new endpoint — A2A adapter builds a JobSpec and calls `/api/delegate`
- (D) New endpoint AND deprecate the three legacy endpoints

**Locked answer**: **(A) New `POST /api/jobs`** with constraint: **no legacy**.

**User constraint**: "we don't want any legacy. remove them or rewrite them."

---

## Decision Q7 — Migration: remove or rewrite legacy endpoints?

**Question**: With (A) + "no legacy", the three endpoints must be removed. Pure breaking change.

**Options presented**:
- (A) Remove all three; rewrite frontend to call `POST /api/jobs`
- (B) Two-phase: phase 1 rewrite, phase 2 remove
- (C) Remove + rewrite in same sprint
- (D) Remove only `/api/delegate`

**Locked answer**: **(C) Remove + rewrite in same sprint (~2-3 weeks combined work).**

**Reasoning recorded**:
- The user wants no legacy. Two-phase would leave legacy in place.
- Single sprint, full cutover. Frontend gets a `toJobSpec()` helper per page.
- (A) and (C) are similar; (C) is the explicit framing.

---

## Decision Q8 — Chat LLM tool surface (round 1)

**Question**: The chat is the user's main surface. The LLM needs to UNDERSTAND job state (read) AND submit new jobs (write).

**Options presented**:
- (A) 4 tools: submit_job, list_jobs, get_job, cancel_job
- (B) 6 tools: above + pause_job, resume_job
- (C) 8 tools: above + add_comment, get_job_output
- (D) 4 base + plugin/config growth

**Locked answer**: **(C) 8 tools, full surface.**

**Reasoning recorded**:
- The LLM needs full context: status, output, comments.
- 8 tools is more vocabulary but each tool has a clear purpose.
- (A) is too thin; the LLM would need to ask "what's the output?" repeatedly.
- (D) adds a config dimension that complicates the chat.

**Final 8 tools** (locked):
```python
chat_tools = [
    submit_job,    # write: create a new JobSpec
    list_jobs,     # read: list jobs (with latest run info)
    get_job,       # read: get one job with full detail
    cancel_job,    # control: cancel a running job
    pause_job,     # control: pause a running job
    resume_job,    # control: resume a paused job
    add_comment,   # write: annotate a job (HITL hooks)
    get_job_output # read: get the full output of a completed job
]
```

---

## Decision Q9 — JobSpecStore extension for 8 LLM tools

**Question**: JobSpecStore protocol currently has `save` + `get_by_id`. The 8 LLM tools need `list_by_session`, `get_status`, `cancel`, `add_comment`, `get_output`.

**Options presented**:
- (A) Extend `JobSpecStore` with the new methods
- (B) New `JobLifecycle` service wraps `JobSpecStore`
- (C) Separate `JobCommentStore` for comments
- (D) Methods on the new `submit_job_to_orchestrator` shared function

**Locked answer**: **(A) Extend `JobSpecStore`.**

**Reasoning recorded**:
- One store owns the lifecycle. The 8-tool surface is one cohesive surface.
- (B) adds an abstraction that doesn't earn its keep yet.
- (C) over-fragments.
- (D) couples the submitter to read methods.

**Final JobSpecStore methods** (locked):
```python
class JobSpecStore(Protocol):
    async def save(self, spec: JobSpec) -> None
    async def get_by_id(self, spec_id: str) -> JobSpec | None
    async def list_by_session(self, session_id: str, *, limit: int = 20) -> list[JobSummary]
    async def get_status(self, spec_id: str) -> JobStatus
    async def cancel(self, spec_id: str) -> bool
    async def pause(self, spec_id: str) -> bool
    async def resume(self, spec_id: str) -> bool
    async def add_comment(self, spec_id: str, comment: JobComment) -> None
    async def get_output(self, spec_id: str) -> JobOutput
```

---

## Decision Q10 — `list_jobs` return shape

**Question**: `list_jobs` is for the LLM to show "your recent jobs" or "what's running."

**Options presented**:
- (A) Spec summaries only — 6 fields, too thin
- (B) Full JobSpec objects — too verbose
- (C) Spec summaries + latest run info — 10 fields, actionable
- (D) Spec summaries + all run IDs — requires N follow-up calls

**Locked answer**: **(C) Spec summaries + latest run info.**

**Reasoning recorded**:
- The LLM cares about job state, not full spec details.
- The latest run gives the actionable signal ("what's the status?") without follow-up get_job calls.
- Saves tokens vs. (B).
- (A) is too thin; (D) requires N follow-up calls.

**`JobSummary` shape** (locked):
```python
class JobSummary(BaseModel):
    spec_id: str
    prompt: str  # truncated to 200 chars
    repo_url: str
    tier: int
    status: str  # pending | running | completed | failed | blocked
    created_at: datetime
    latest_run_id: str | None
    latest_run_status: str | None
    latest_run_started_at: datetime | None
    latest_run_cost_usd: float | None
    latest_run_duration_s: float | None
```

---

## Implementation sketch (post-grill)

### Backend

**New file**: `backend/harness/jobs/submitter.py` (~100 lines)
```python
async def submit_job_to_orchestrator(spec: JobSpec) -> str:
    """Single entry point for all submission paths. Persists to job_specs
    and dispatches to orchestrator. Returns run_id."""
    await _job_spec_store().save(to_record(spec))
    return await OrchestratorEngine(...).run_job_spec(spec)
```

**Modified file**: `backend/harness/jobs/spec.py`
- Replace `context: dict[str, Any]` with `context: JobContext`
- Add `JobContext` Pydantic model with `extra='allow'`
- Add `TestConfig` Pydantic model with the 30+ from-requirements fields

**Modified file**: `backend/harness/store/protocols.py`
- Extend `JobSpecStore` with 7 new methods
- Add `JobSummary`, `JobStatus`, `JobComment`, `JobOutput` models

**New file**: `backend/api/routers/jobs.py` (~150 lines)
- `POST /api/jobs` — accepts JobSpec, returns run_id
- `GET /api/jobs/{spec_id}` — returns JobSpec detail
- `GET /api/jobs?session_id=X` — list jobs for a session
- `POST /api/jobs/{spec_id}/cancel`
- `POST /api/jobs/{spec_id}/pause`
- `POST /api/jobs/{spec_id}/resume`
- `POST /api/jobs/{spec_id}/comments`
- `GET /api/jobs/{spec_id}/output`

**Modified file**: `backend/api/routers/agent.py`
- `AgentRunRequest` adds optional `tier` (default 1)
- Endpoint becomes a thin wrapper: builds JobSpec, calls `/api/jobs` internally (or calls the submitter)
- Eventually deleted in the C08 migration

**Modified file**: `backend/api/routers/delegate.py`
- Add optional `tier` (default 1)
- Add optional `capabilities` (default = DEFAULT_CAPABILITIES)
- Endpoint becomes a thin wrapper; eventually deleted

**Modified file**: `backend/api/routers/pipeline.py`
- `PipelineFromRequirements` keeps its 30+ fields but adds optional `tier` and `capabilities`
- Endpoint builds JobSpec with `context.test_config = <30+ fields>`; eventually deleted

**Modified file**: `backend/harness/jobs/chat_submit.py` (or wherever chat's submit_job lives)
- `submit_job` becomes a thin wrapper around `submit_job_to_orchestrator`

### Frontend

**New helper**: `src/lib/api/jobSpec.ts`
```ts
export function toJobSpecFromAgentPage(state): JobSpec
export function toJobSpecFromPipelineOrchestrate(state): JobSpec
export function toJobSpecFromPipelineQuickTest(state): JobSpec
```

**Modified file**: `src/app/(dashboard)/agent/page.tsx`
- Replace `POST /api/agent/run` with `POST /api/jobs` + `toJobSpecFromAgentPage(state)`

**Modified file**: `src/app/(dashboard)/pipeline/page.tsx`
- Replace `POST /api/delegate` and `POST /api/pipeline/from-requirements` with `POST /api/jobs`

**Modified file**: `src/stores/pipeline-store.ts`
- Update to call `/api/jobs` instead of legacy endpoints

### Migration checklist

- [ ] Add `JobContext`, `TestConfig` Pydantic models
- [ ] Extend `JobSpecStore` with new methods
- [ ] Implement `submit_job_to_orchestrator` shared function
- [ ] Add `POST /api/jobs` endpoint
- [ ] Add `GET /api/jobs/{spec_id}`, list, cancel, pause, resume, comments, output
- [ ] Update chat's `submit_job` to use shared submitter
- [ ] Update `/api/agent/run` to call shared submitter
- [ ] Update `/api/delegate` to call shared submitter
- [ ] Update `/api/pipeline/from-requirements` to call shared submitter
- [ ] Add `toJobSpec` helpers in `src/lib/api/jobSpec.ts`
- [ ] Update `src/app/(dashboard)/agent/page.tsx` to call `/api/jobs`
- [ ] Update `src/app/(dashboard)/pipeline/page.tsx` to call `/api/jobs`
- [ ] Update `src/stores/pipeline-store.ts` to call `/api/jobs`
- [ ] Delete legacy endpoints (`/api/agent/run`, `/api/delegate`, `/api/pipeline/from-requirements`)
- [ ] Update tests
- [ ] Update API docs

**Estimated effort**: 2-3 weeks for combined backend + frontend.

---

## Open questions for C08 (deferred to next grilling session)

1. JobSpecStore: how does `pause` interact with already-running subagents? Pause the orchestrator loop? Just mark the spec?
2. `add_comment`: what's the schema? Free-form text? Structured (kind, message, author)? For HITL?
3. `get_job_output`: how big can the output be? Truncation policy? Streaming?
4. Pagination on `list_jobs`: cursor-based? offset? LLM doesn't paginate well — what's the cap?
5. JobSpecRecord column additions: do we need a `status` column or derive it from the run? Currently the table has `status='pending'` hardcoded.
6. The chat's tool `add_comment` may need a separate `JobComment` model with author, timestamp, kind.
7. The chat's `list_jobs` filtering: by status? by date range? by repo? The LLM might want to ask "show me all failed jobs from this week."
8. The `get_output` for in-progress jobs: partial output? Or 404 until complete?
9. How does C02 (Agent Teams) interact with the 8-tool surface? Does the team lead also have these tools?
10. Does `cancel_job` propagate to running subagents, or just the orchestrator?

# Candidate C01 — Worktree isolation

**Context**: Two parallel subagents in TestAI today clobber each other's files because they share the same `/workspace/repo`. The kanban board serializes through WIP limits, but this is a pass-through cost. The June 18 2026 audit flagged this as a `High` gap. Claude Code, OpenHarness, and ECC2 all solve this with git worktrees.

**Research grounding**:
- **Claude Code** (`code.claude.com/docs/en/worktrees`): per-session worktree (desktop app auto) + per-subagent worktree (`isolation: worktree` in subagent frontmatter). Location `.claude/worktrees/<name>/`. Branch `worktree-<name>`. `git worktree lock` while running. Auto-remove on completion (no changes); prompt if changes. `/batch` skill: "5 to 30 worktree-isolated subagents that **each open a pull request**" — PR-based merge.
- **OpenHarness** (`reference/OpenHarness/src/openharness/swarm/worktree.py`): per-slug worktree at `~/.openharness/worktrees/`. `_sync_worktree_to_base` → `_git_commit_all` → `_git_push_branch` → `_upsert_pull_request` (often draft) → `_merge_pull_request` if auto-merge eligible. Symlinks for `node_modules`, `.venv`, `__pycache__`, `.tox` to avoid duplication.
- **ECC2** (`docs/ECC/ecc2/src/worktree/mod.rs`): `create_for_session`, `create_draft_pr`, `merge_into_base`, `rebase_onto_base`, `merge_readiness`, `branch_conflict_preview`. Rust port of the worktree pattern.

**Production pattern (2026)**: PR-based, not fast-forward. Each worktree-isolated work unit pushes its branch and opens a draft PR. Tier-1 auto-merges; tier-2/3 awaits human review.

**Files involved**:
- `backend/harness/sandbox_manager.py:588-597` (the smoking gun — `create_worker_env` is a no-op that returns the shared container)
- `backend/harness/orchestrator.py` (where worktrees will be created)
- `backend/harness/tools/delegate_task.py:275-348` (the tool that triggers worktree creation)
- `reference/OpenHarness/src/openharness/swarm/worktree.py:135` (port source)

---

## Decision Q1 — Isolation unit (re-grilled with research)

**Question**: What is the unit of isolation? Claude Code does BOTH per-session + per-subagent.

**Options presented**:
- (A) Per-subagent only — one worktree per delegate_task
- (B) Per-session only — one worktree per orchestrator Run
- (C) Hybrid (Claude Code pattern) — per-session at top level + per-subagent for nested
- (D) Per-kanban-task only

**Recommended**: (C) hybrid. The orchestrator itself can clobber the user's working tree.

**Locked answer**: **(C) Hybrid (Claude Code pattern, Recommended).**

**Reasoning recorded**:
- Claude Code's pattern is the production reference.
- (A) is incomplete — the orchestrator itself can clobber the user's working tree.
- (B) is what Claude Code's desktop app does for top-level sessions but doesn't address subagent parallelism.
- (D) doesn't match the industry pattern.

---

## Decision Q2 — Worktree physical location

**Question**: Where do worktrees physically live? The orchestrator's main `/workspace/repo` is a Docker volume.

**Options presented**:
- (A) In the container's volume at `/workspace/repo/.testai-worktrees/<name>/`
- (B) On the host at `~/.testai/worktrees/<name>/`
- (C) As separate Docker volumes
- (D) Per-session in container, per-subagent on host

**Recommended**: (A). Matches Claude Code's pattern (worktrees in same repo).

**Locked answer**: **(A) In the container's volume.**

**Reasoning recorded**:
- Matches Claude Code's pattern.
- The volume's 7-day TTL is plenty for a Run.
- (B) is over-engineered; per-subagent worktrees shouldn't outlive the Run.
- (C) adds a Docker volume per worktree — scaling problem.
- (D) is split-brain.

---

## Decision Q3 — Branch naming scheme

**Question**: Each worktree has a branch. The naming scheme affects cleanup, audit, and grep-ability.

**Options presented**:
- (A) `testai/session-<id>` for per-session, `testai/sa-<id>` for per-subagent
- (B) Plain `<id>` no prefix
- (C) `wt/<id>` short prefix
- (D) Hash-based `wt/<8-char-hash>`

**Locked answer**: **(A) `testai/session-<id>` + `testai/sa-<id>`.**

**Reasoning recorded**:
- `testai/` prefix prevents collision with user branches.
- `session-` and `sa-` are greppable.
- (B) collides with user branches.
- (D) loses semantic info.

---

## Decision Q4 — Merge strategy (re-grilled with research)

**Question**: When a per-subagent worktree completes, how does its work get integrated?

**Research**: Claude Code's `/batch` pattern opens one PR per worktree-isolated subagent. OpenHarness: worktree → push → open draft PR → auto-merge if eligible. The 2026 pattern is **PR-based, not fast-forward**.

**Options presented**:
- (A) Per-subagent draft PR — each subagent's branch opens a draft PR
- (B) Per-subagent PR + per-session branch (double bookkeeping)
- (C) Per-team aggregation only (loses individual reviewability)
- (D) Fast-forward + PR at end-of-run (discards the 2026 pattern)

**Locked answer**: **(A) Per-subagent draft PR.**

**Reasoning recorded**:
- Matches the 2026 production pattern (Claude Code `/batch`, OpenHarness draft PR).
- Tier-1 auto-merges; tier-2/3 awaits human review.
- Each subagent's work is independently reviewable.
- (B) is double bookkeeping.
- (C) loses individual reviewability.
- (D) discards the 2026 pattern.

---

## Decision Q5 — Per-session worktree's role

**Question**: With per-subagent draft PRs as the merge strategy, what does the per-session worktree do?

**Options presented**:
- (A) Orchestrator's scratch space — reads + meta-tools; subagent PRs are independent
- (B) Orchestrator's local working tree — writes meta-artifacts there
- (C) No per-session worktree — orchestrator reads/writes from main /workspace/repo
- (D) Per-session = integration branch — orchestrator cherry-picks subagent PRs into it

**Locked answer**: **(A) Orchestrator's scratch space.**

**Reasoning recorded**:
- Matches Claude Code's pattern: top-level session has its own worktree for orchestration; subagents have their own for actual work.
- (C) loses user-tree protection.
- (D) undoes the per-subagent PR decision.
- (B) conflates orchestration with writing.

---

## Decision Q6 — Worktree cleanup

**Question**: When a per-subagent worktree completes, what happens to it?

**Options presented**:
- (A) Always keep
- (B) Auto-remove after PR is opened
- (C) Auto-remove after PR is merged
- (D) Configurable per-run

**Locked answer**: **(B) Auto-remove after PR is opened.**

**Reasoning recorded**:
- The branch is on origin (the PR is its evidence).
- The worktree's only job was to host the commits and let the subagent work.
- (A) is wasteful — worktree disk space accumulates.
- (C) is too long — 7-day `reap_stale` handles the longer case.
- (D) adds a config knob for a non-issue.

---

## Implementation sketch (post-grill)

**New file**: `backend/harness/services/worktree_manager.py` (~200 lines, port from `reference/OpenHarness/src/openharness/swarm/worktree.py`)

```python
class WorktreeManager:
    """Manage git worktrees for isolated subagent execution.

    Per-session worktree at /workspace/repo/.testai-worktrees/session-<id>/
    Per-subagent worktree at /workspace/repo/.testai-worktrees/sa-<id>/
    """

    def __init__(self, sandbox, repo_path: str):
        self._sandbox = sandbox
        self._repo_path = repo_path
        self._base_dir = f"{repo_path}/.testai-worktrees"

    async def create_worktree(self, name: str, *, slug: str) -> WorktreeInfo:
        # git worktree add -B testai/<name> <path> HEAD
        ...

    async def remove_worktree(self, name: str) -> bool:
        # git worktree remove --force <path>
        ...

    async def list_worktrees(self) -> list[WorktreeInfo]:
        # git worktree list --porcelain
        ...

    async def cleanup_stale(self, active_slugs: set[str]) -> list[str]:
        ...
```

**Modified file**: `backend/harness/tools/delegate_task.py`
- The tool creates a worktree for each subagent before spawning
- After subagent completes, the worktree's branch is pushed and a draft PR is opened
- The worktree is removed after the PR is opened

**New helper**: `harness/services/draft_pr.py`
- Opens a draft PR on origin with the subagent's branch
- Tier-1: `ready_for_review: true` (auto-merge eligible)
- Tier-2/3: `draft: true` (awaits human review)

**Modified file**: `backend/harness/sandbox_manager.py:588`
- `create_worker_env` becomes the per-session worktree orchestrator
- The session gets its own worktree before any subagent spawns

---

## Open questions for C01 (deferred)

1. The per-session worktree is created at orchestrator bootstrap. What if the user has uncommitted local changes? Skip with a warning? Snapshot via stash? Fail loudly?
2. PR base branch: always `main`? Or the branch the user is currently on? Or the branch the orchestrator cloned from?
3. Subagent commits in the worktree: are they auto-pushed, or does the lead push them after review?
4. `.worktreeinclude` (Claude Code's pattern for copying gitignored env files): do we need this for TestAI?
5. Symlink duplication (OpenHarness pattern for `node_modules`/`.venv`): do we need this?
6. Concurrent worktree lock — Claude Code uses `git worktree lock`. We should too. When?
7. Integration with the existing `SandboxManager._recover_containers` on backend restart: how do we know which worktrees belong to which session?

---

# Candidate C02 — Agent Teams

**Context**: Claude Code v2.1.x (May 2026) added **Agent Teams** — multiple coordinated sessions with a shared task list + inter-agent messaging, managed by a lead. TestAI's current pattern: kanban is passive observability, no shared team state between subagents. C02 brings this to TestAI on top of the new C01 design (per-subagent worktrees, per-subagent PRs).

**C01 context (locked)**: Per-session worktree is the orchestrator's scratch space. Each `delegate_task` call gets a per-subagent worktree and opens its own draft PR. Teams are a coordination layer over this.

**Research grounding**:
- **Claude Code** agent teams: lead + teammates; shared task list; inter-agent messaging; experimental.
- **OpenHarness** `reference/OpenHarness/src/openharness/swarm/team_lifecycle.py`: `TeamLifecycleManager` with `create_team`, `get_team`, `list_teams`, `add_member`, `remove_member`. **Filesystem JSON files** (each team is one file at `_team_file_path:289`).

**Files involved**:
- New: `backend/harness/services/team_service.py`
- New: `backend/harness/tools/team_create_tool.py`, `team_message_tool.py`, `team_dissolve_tool.py`, etc.
- New: Postgres `teams` table (with foreign tables for `team_members`, `team_messages`)
- Modified: `backend/harness/tools/delegate_task.py` (add `team_id` param)

---

## Decision Q1 — Team scope (re-grilled)

**Question**: With per-subagent PRs as the merge strategy, what does a team DO?

**Options presented**:
- (A) Pure coordination — lead has tools to message members and view shared task list. No team-aggregation.
- (B) Coordination + aggregation — lead can aggregate member work into a team-level PR.
- (C) Explicit workflow steps — coordinator creates a team, lead runs a fixed workflow.

**Locked answer**: **(A) Pure coordination.**

**Reasoning recorded**:
- Per-subagent PRs are the integration surface (per C01).
- The lead's job is to read member reports, message, and decide — not to aggregate work.
- (B) re-introduces team-aggregation, which the user rejected in C01.
- (C) is rigid.

---

## Decision Q2 — Team creation model

**Question**: When does a team EXIST?

**Options presented**:
- (A) Dynamic — coordinator calls `create_team` at runtime
- (B) Static in `.testai/teams/*.yaml`
- (C) Implicit on fan-out
- (D) Two-level dynamic + static

**Locked answer**: **(A) Dynamic.**

**Reasoning recorded**:
- The coordinator's LLM has the context to know when a team is needed.
- (B) is too rigid.
- (C) collapses the team concept into fan-out.
- (D) adds a config dimension.

**`create_team` tool** (locked):
```python
async def create_team(
    name: str,                          # human-readable name
    lead_role: str,                     # the lead's Role name
    member_roles: list[str],            # list of member Role names
    goal: str,                          # the team's objective
) -> str:                               # returns team_id
```

---

## Decision Q3 — Lead's team_* toolset

**Question**: What `team_*` tools does the lead get?

**Options presented**:
- (A) Full surface: team_create_team, team_list_tasks, team_message, team_message_broadcast, team_status, team_dissolve, team_member_progress
- (B) Minimal: team_message, team_message_broadcast, team_list_tasks, team_status (no dissolve)
- (C) Just messaging: team_message, team_message_broadcast
- (D) Configurable per team

**Locked answer**: **(A) Full surface.**

**Reasoning recorded**:
- The lead's job is to coordinate; it needs to message members, see the task list, see progress, dissolve the team.
- (B) leaves out dissolution — without it, the team lingers.
- (C) is too thin.
- (D) adds a config dimension for v1.

---

## Decision Q4 — Member's team_* toolset

**Question**: What `team_*` tools do members get?

**Options presented**:
- (A) Read + reply: team_list_tasks, team_get_messages, team_message. No broadcast, no create/dissolve.
- (B) Read-only: team_list_tasks, team_get_messages.
- (C) Same as lead.
- (D) No team tools — use kanban_comment.

**Locked answer**: **(A) Read + reply.**

**Reasoning recorded**:
- Members need to read the team's state (so they don't duplicate work) and reply to messages (so they can ask for clarification).
- They don't need broadcast (lead's job) or team management (lead's job).
- (B) is too thin — members can't ask questions.
- (C) is too much.
- (D) uses the wrong tool.

---

## Decision Q5 — Team lifecycle

**Question**: When does a team stop existing?

**Options presented**:
- (A) Lead explicitly calls team_dissolve
- (B) Auto-dissolve when all members report done
- (C) Auto-dissolve after a timeout
- (D) Hybrid: explicit OR auto when all members done

**Locked answer**: **(D) Hybrid.**

**Reasoning recorded**:
- The lead can choose to dissolve explicitly (when it knows the team is done).
- The system also auto-dissolves when all members are done (in case the lead forgets).
- The team is never stuck.
- (A) leaves orphan teams if the lead forgets.
- (B) prevents explicit early termination.
- (C) is timer-based, less precise.

---

## Decision Q6 — Team state storage (re-asked with research)

**Question**: Where does team state live?

**Research**: OpenHarness uses filesystem JSON files. TestAI uses Postgres for jobs. Server vs CLI distinction.

**Options presented**:
- (A) Postgres `teams` table — matches TestAI's existing patterns
- (B) Filesystem JSON files — matches OpenHarness
- (C) Hybrid: Postgres + filesystem
- (D) In the kanban

**Locked answer**: **(A) Postgres `teams` table.**

**Reasoning recorded**:
- TestAI is a server with concurrent requests; cross-process visibility matters.
- The OpenHarness filesystem model is for a single-process CLI; doesn't fit TestAI.
- (B) breaks the existing pattern.
- (C) is over-engineered.
- (D) conflates team state with task tracking.

**Postgres schema sketch** (locked):
```sql
CREATE TABLE teams (
    team_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lead_subagent_id TEXT REFERENCES sessions(id),
    goal TEXT,
    status TEXT NOT NULL,  -- 'active' | 'dissolved'
    created_at TIMESTAMP NOT NULL,
    dissolved_at TIMESTAMP
);

CREATE TABLE team_members (
    team_id TEXT REFERENCES teams(team_id),
    subagent_id TEXT REFERENCES sessions(id),
    role TEXT NOT NULL,  -- 'lead' | 'member'
    joined_at TIMESTAMP NOT NULL,
    PRIMARY KEY (team_id, subagent_id)
);

CREATE TABLE team_messages (
    id SERIAL PRIMARY KEY,
    team_id TEXT REFERENCES teams(team_id),
    from_subagent_id TEXT,
    to_subagent_id TEXT,  -- NULL = broadcast
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

---

## Implementation sketch (post-grill)

**New file**: `backend/harness/services/team_service.py` (~200 lines)
- `TeamService.create_team(name, lead_role, member_roles, goal) -> str`
- `TeamService.add_member(team_id, subagent_id, role)`
- `TeamService.remove_member(team_id, subagent_id)`
- `TeamService.send_message(team_id, from_subagent_id, to_subagent_id, content)`
- `TeamService.list_tasks(team_id) -> list[TaskSummary]`
- `TeamService.list_messages(team_id, subagent_id) -> list[Message]`
- `TeamService.dissolve(team_id)`
- `TeamService.cleanup_completed()` — auto-dissolve teams where all members are done

**New file**: `backend/harness/tools/team_tools.py` (~300 lines)
- `TeamCreateTool` — coordinator-facing
- `TeamMessageTool` — lead + member-facing
- `TeamMessageBroadcastTool` — lead-only
- `TeamListTasksTool` — lead + member-facing
- `TeamGetMessagesTool` — lead + member-facing
- `TeamMemberProgressTool` — lead-only
- `TeamStatusTool` — lead + member-facing
- `TeamDissolveTool` — lead-only

**Modified file**: `backend/harness/tools/delegate_task.py`
- Add `team_id: str | None = None` parameter
- When `team_id` is set, the new subagent is added to the team
- The new subagent's toolset includes the appropriate `team_*` tools based on whether it's a lead or member

**Modified file**: `backend/harness/toolsets.py`
- Add a `team_lead` toolset (full team_* surface + standard coordinator tools)
- Add a `team_member` toolset (read+reply only + standard leaf tools)

---

## Open questions for C02 (deferred)

1. The lead's `team_create_team` — can the lead spawn nested teams? For v1, this is disallowed (single-level teams only).
2. Message ordering — FIFO? Priority queue? Per-thread? For v1, FIFO.
3. Message persistence — when a team is dissolved, are messages kept (audit) or deleted? Recommendation: keep (audit trail).
4. Team size limits — is there a max number of members? Recommendation: configurable, default 8.
5. Cross-team communication — can a member of team A message a member of team B? For v1, no (single-team only).
6. Lead succession — if the lead's process dies, does the team get a new lead? For v1, no (team is dissolved if lead dies).
7. Team cost budgets — does the team have a shared budget, or per-member budgets? Per C07's auto-throttle, per-member makes sense.

---

# Candidate C03 — Push-based completion with idempotency

**Context**: `OrchestratorEngine._wait_for_board` polls every 15s for up to 90 minutes. Every event the parent needs travels through this 15-second needle-eye. The 2026 production pattern is push-based: OpenClaw uses an internal event with idempotency keys; Hermes uses heartbeat threads. TestAI's existing EventBus at `backend/harness/events.py:165-202` already provides the infrastructure — the orchestrator just doesn't use it.

**Research grounding**:
- **OpenClaw** (May 2026): "Sub-agent completion arrives as internal event"; OpenClaw attempts to wake/steer the requester; falls back to requester-agent handoff with exponential backoff; "idempotency: completion handoff uses stable idempotency key" for exactly-once.
- **Hermes**: heartbeat thread polls child activity every 5s; stale detection based on (iter, current_tool) progress.
- **TestAI's existing EventBus** (`backend/harness/events.py:165-202`): `subscribe(session_id) -> asyncio.Queue[StreamEvent]`, `emit(event)` enqueues to all subscribers. Already feeds SSE for the dashboard. Just needs the orchestrator to subscribe to its own session.

**Files involved**:
- `backend/harness/orchestrator.py:676-710` (`_wait_for_board` — the poll loop)
- `backend/harness/events.py:165-202` (existing EventBus — re-use)
- `backend/harness/stream_events` table (idempotency tracking)

---

## Decision Q1 — Subscribed events

**Question**: What events does the orchestrator subscribe to?

**Options presented**:
- (A) Just board status changes
- (B) Board status + subagent events
- (C) All events on the EventBus
- (D) Specific event types

**Locked answer**: **(B) Board status + subagent events.**

**Reasoning recorded**:
- Board status replaces the 15s poll; subagent events update the run timeline in real-time.
- (A) is too thin — the dashboard needs to show subagent progress.
- (C) is too much — the orchestrator doesn't care about every tool call.
- (D) is over-engineered for v1.

---

## Decision Q2 — Subscription mechanism (re-asked with research)

**Question**: What mechanism does the orchestrator use to subscribe?

**Research**: TestAI's existing EventBus uses `asyncio.Queue[StreamEvent]` per session_id. OpenClaw uses internal events. Hermes uses heartbeat threads.

**Options presented**:
- (A) `asyncio.Event` via existing EventBus — re-uses existing infra
- (B) Postgres LISTEN/NOTIFY — cross-process
- (C) Redis pub/sub — adds Redis dep
- (D) SSE consumer — couples control flow to transport

**Locked answer**: **(A) `asyncio.Event` via existing EventBus.**

**Reasoning recorded**:
- Re-uses existing infra. The orchestrator subscribes to its own session's `asyncio.Queue`.
- The wait becomes `queue.get()` with 60s timeout fallback.
- (B) is cross-process but adds asyncpg loop.
- (C) adds Redis dep.
- (D) couples control flow to transport.

---

## Decision Q3 — Idempotency key

**Question**: How does the orchestrator detect duplicate events?

**Options presented**:
- (A) Idempotency key = hash(subagent_id, result_hash) — OpenClaw's pattern
- (B) Idempotency key = subagent_id alone — coarser
- (C) Idempotency key = UUID per emission — no dedup
- (D) No idempotency

**Locked answer**: **(A) hash(subagent_id, result_hash).**

**Reasoning recorded**:
- result_hash is SHA of result content; same content = duplicate.
- (B) is too coarse — a subagent that legitimately runs twice (after a fix attempt) would have its second result dropped.
- (C) is no-op.
- (D) is brittle.

---

## Decision Q4 — Fallback timeout

**Question**: If the queue doesn't deliver for 60s, what happens?

**Options presented**:
- (A) Fall back to the 15s poll after 60s — defense in depth
- (B) Treat as wedged — fail the run
- (C) Wait longer (5 minutes)
- (D) Configurable per-run

**Locked answer**: **(A) Fall back to 15s poll after 60s.**

**Reasoning recorded**:
- The 60s threshold is well above expected event latency.
- The 15s poll ensures the orchestrator doesn't get stuck.
- (B) is too aggressive.
- (C) means longer recovery time.
- (D) adds a config knob.

---

## Implementation sketch (post-grill)

**Modified file**: `backend/harness/orchestrator.py:676-710`
```python
async def _wait_for_board(self, board_id, session_id, repo_url):
    event_bus = get_event_bus()
    queue = event_bus.subscribe(session_id)
    try:
        last_poll_at = time.time()
        while True:
            # Try to get an event with 60s timeout
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60.0)
                last_poll_at = time.time()  # reset poll timer

                # Idempotency check
                if event.type == "subagent.completed":
                    if self._is_duplicate(event):
                        continue
                    self._record_emit(event)

                # Process the event
                if event.type == "board.completed":
                    return {...}
                if event.type == "subagent.completed":
                    self._update_timeline(event)
            except asyncio.TimeoutError:
                pass

            # Fallback poll every 15s (defense in depth)
            if time.time() - last_poll_at >= 15:
                status = await cmd_orchestrate_monitor(board_id, max_wait_seconds=30)
                # ... existing logic
    finally:
        event_bus.unsubscribe(session_id, queue)
```

**New file**: `backend/harness/services/idempotency.py` (~50 lines)
```python
class IdempotencyTracker:
    """Track idempotency keys for sub-agent completion events.

    Idempotency key = hash(subagent_id, result_hash).
    Same key = duplicate; drop.
    """
    def __init__(self, max_size: int = 1000):
        self._seen: dict[str, str] = {}  # idempotency_key -> subagent_id

    def is_duplicate(self, subagent_id: str, result_hash: str) -> bool:
        key = f"{subagent_id}:{result_hash}"
        return key in self._seen

    def record(self, subagent_id: str, result_hash: str) -> None:
        key = f"{subagent_id}:{result_hash}"
        self._seen[key] = subagent_id
```

---

## Open questions for C03 (deferred)

1. Cross-instance delivery: if the orchestrator's process crashes and a new one picks up, the queue is lost. Should the idempotency tracker be persistent (Postgres)?
2. The fallback poll uses `cmd_orchestrate_monitor` which already polls. If the fallback runs, the orchestrator is double-checking. Acceptable cost?
3. The `event_bus.subscribe` returns a queue. Should the orchestrator drain the queue continuously or only on demand?
4. Backpressure: if the orchestrator is slow, the queue fills up (maxsize=1000). The `EventBus._enqueue` drops on overflow. What's the right overflow behavior?

---

# Candidate C06 — Subagent heartbeat + stale detection (Hermes pattern)

**Context**: `delegate_task` blocks the parent on a subagent. If the subagent hangs on a long-running tool (apt-get, web_fetch, network wait), the parent's gateway inactivity timeout can fire — killing a healthy subagent. Hermes' reference implementation in `reference/hermes-agent/tools/delegate_tool.py:1318-1684` uses a heartbeat thread.

**Files involved**:
- `backend/harness/tools/delegate_task.py` (where the heartbeat lives)
- `backend/harness/stream_events` table (progress signal source)
- `backend/harness/agent/` (the Agent class being heartbeat-monitored)

---

## Decision Q1 — Heartbeat location

**Question**: Where does the heartbeat live?

**Options presented**:
- (A) Inside `delegate_task.run()` — the tool itself runs the heartbeat
- (B) At the orchestrator — the orchestrator runs a heartbeat task in parallel
- (C) At a separate daemon — a watcher process

**Locked answer**: **(A) Inside `delegate_task.run()`.**

**Reasoning recorded**:
- The heartbeat is part of the `delegate_task` contract; the orchestrator doesn't need to know about it.
- (B) couples the orchestrator to heartbeat details.
- (C) is over-engineered.

---

## Decision Q2 — Heartbeat parameters

**Question**: Interval and stale thresholds?

**Options presented**:
- (A) Hermes defaults: 5s interval, idle threshold low, in-tool threshold high
- (B) Configurable per-tool
- (C) Configurable per-run via env var
- (D) Aggressive

**Locked answer**: **(A) Hermes defaults.**

**Reasoning recorded**:
- 5s interval is reasonable; configurability can come later.
- (B) adds per-tool complexity.
- (C) adds a config knob.
- (D) wastes cycles.

---

## Decision Q3 — Stale detection behavior

**Question**: When staleness is detected, what happens?

**Options presented**:
- (A) Raise a "subagent_stuck" error
- (B) Auto-cancel the subagent
- (C) Send a "are you stuck?" prompt
- (D) Just log; let the gateway timeout fire

**Locked answer**: **(A) Raise "subagent_stuck" error.**

**Reasoning recorded**:
- The heartbeat is for observability, not termination.
- The parent has context to decide.
- (B) is premature — a subagent in a long `apt-get` is fine.
- (C) is fragile — the subagent might be unresponsive.
- (D) defeats the purpose.

---

## Decision Q4 — Progress signal

**Question**: What counts as "progress"?

**Research**: Hermes uses `get_activity_summary()`. TestAI's Agent class doesn't have this.

**Options presented**:
- (A) Copy Hermes' `get_activity_summary()` on TestAI's Agent class
- (B) Just count tool calls
- (C) Use the existing `stream_events` — count events in the last N seconds
- (D) Use the worktree's mtime

**Locked answer**: **(C) `stream_events` count.**

**Reasoning recorded**:
- TestAI already has `stream_events`; counting them in the last N seconds is the natural progress signal.
- (A) is faithful to Hermes but duplicates work.
- (B) is too coarse.
- (D) misses "I'm thinking" activity.

---

## Implementation sketch (post-grill)

**Modified file**: `backend/harness/tools/delegate_task.py`
```python
class DelegateTaskTool(BaseTool):
    _HEARTBEAT_INTERVAL = 5.0
    _HEARTBEAT_STALE_CYCLES_IDLE = 6      # 30s of no progress when idle
    _HEARTBEAT_STALE_CYCLES_IN_TOOL = 60  # 5min of no progress when in-tool

    async def _heartbeat_loop(self, child, parent_agent, stop_event, session_id):
        last_iter = 0
        last_tool = None
        stale_count = 0

        while not stop_event.is_set():
            await asyncio.sleep(self._HEARTBEAT_INTERVAL)
            try:
                summary = child.get_activity_summary()
                current_tool = summary.get("current_tool")
                current_iter = summary.get("api_call_count", 0)

                iter_advanced = current_iter > last_iter
                tool_changed = current_tool != last_tool
                if iter_advanced or tool_changed:
                    last_iter = current_iter
                    last_tool = current_tool
                    stale_count = 0
                else:
                    stale_count += 1

                # Different thresholds for idle vs in-tool
                stale_limit = (
                    self._HEARTBEAT_STALE_CYCLES_IN_TOOL
                    if current_tool
                    else self._HEARTBEAT_STALE_CYCLES_IDLE
                )
                if stale_count >= stale_limit:
                    raise SubagentStuckError(
                        subagent_id=child._subagent_id,
                        current_tool=current_tool,
                        current_iter=current_iter,
                        last_progress_iter=last_iter,
                    )

                # Touch parent's activity timestamp
                if parent_agent and hasattr(parent_agent, "_touch_activity"):
                    parent_agent._touch_activity(
                        f"delegate_task: subagent {current_tool or 'idle'} ({current_iter})"
                    )
            except SubagentStuckError:
                raise
            except Exception as exc:
                logger.debug("heartbeat error: %s", exc)
```

**New helper**: `harness/services/activity_signal.py`
```python
def recent_event_count(session_id: str, window_seconds: float = 5.0) -> int:
    """Count stream_events for the session in the last N seconds."""
    return db.fetchval(
        "SELECT COUNT(*) FROM stream_events WHERE session_id = $1 AND created_at > NOW() - $2 * INTERVAL '1 second'",
        session_id, window_seconds,
    )
```

---

## Open questions for C06 (deferred)

1. The heartbeat runs in a thread or as an asyncio task? Hermes uses `threading.Thread` because the child runs in a thread. TestAI's subagent runs in the same asyncio loop — could be an asyncio task. But the parent's `_touch_activity` is sync.
2. The "raise" path: does the heartbeat's exception propagate to the parent's await? Need to test.
3. The stale_limit thresholds: are Hermes' defaults (6 idle / 60 in-tool) appropriate for TestAI's tool mix?
4. The heartbeat should also fire a `subagent.heartbeat` event on the EventBus for dashboard observability.

---

# Candidate C05 — A2A wire protocol (DEFERRED)

**Context**: A2A (Agent-to-Agent) is Google's JSON-RPC protocol for inter-agent communication. Methods: `task/send`, `task/stream`, `task/cancel`, `task/get`. The domain glossary says internal agents communicate via Postgres + direct function calls, with A2A patterns "guiding the API design so an A2A adapter can be added later". C08 added `POST /api/jobs` accepting JobSpec — the canonical seam.

**Honest assessment**: A2A is YAGNI for v1. TestAI's current external integrations are webhooks, cron, Slack, Linear — all can use C08's `/api/jobs` directly. A2A's value is for *external agents* driving TestAI; TestAI doesn't have concrete external-agent customers yet.

---

## Decision Q1 — Is A2A needed now?

**Options presented**:
- (A) Defer A2A — not needed for v1; build when an external agent integration is concrete
- (B) Build the thin shim now — ~200 lines, future-proofs the 2026 trend
- (C) Build a minimal shim (just `task/send` and `task/get`) — prove the concept
- (D) Defer and document — capture the design as ADR

**Locked answer**: **(A) Defer A2A.**

**Reasoning recorded**:
- The shim is small enough to add in a week when needed.
- Spending a week on YAGNI now means a week not spent on a real customer feature.
- The C08 endpoints are the seam; A2A wraps them when needed.
- (B) and (C) preempt a need that hasn't materialized.
- (D) is the right documentation step alongside (A).

---

## What to capture in the ADR

When the time comes to build A2A, the design has been pre-decided:

**Adapter scope**: thin shim. A2A's `task/send` → `POST /api/jobs`; `task/get` → `GET /api/jobs/{id}`; `task/cancel` → `POST /api/jobs/{id}/cancel`; `task/stream` → SSE.

**A2A's wire format**:
- Method: `POST /a2a/v1/task/send` with JSON-RPC body `{jsonrpc: "2.0", id, method: "task/send", params: {id, message: {parts: [...]}}}`
- Response: `{jsonrpc: "2.0", id, result: {id, status, artifacts: [...]}}`
- Stream: `POST /a2a/v1/task/stream` returns SSE with `task.statusUpdate` events

**A2A → TestAI mapping**:
- A2A's `parts[]` (text, file, data) → TestAI's `JobSpec.prompt` (concatenate text parts; ignore file/data for v1)
- A2A's `task.id` → TestAI's `JobSpec.spec_id`
- A2A's `task.status` (working, completed, failed, canceled) → TestAI's `JobSpec.status` + Run state
- A2A's `artifacts[]` → TestAI's `Run.evidence_summary` (per C04's evidence bundler)

**Authentication**: OAuth 2.0 with bearer token. Re-use TestAI's `integration_configs` token store.

**Implementation footprint**: ~200 lines in `backend/a2a/server.py`. Reuses C08's submitter.

---

## Open questions for C05 (deferred until first external-agent customer)

1. Should A2A's `parts[]` support `file` (binary upload)? TestAI's `JobSpec.prompt` is text-only.
2. Should A2A's `artifacts[]` include the full PR URL, the test run report, or both?
3. Does A2A's `push_notification` (webhook-style) work alongside the C08 SSE stream, or replace it?
4. Does the A2A adapter need its own auth (different from TestAI's dashboard auth)?

---

# Candidate C07 — Budget auto-throttle (DEFERRED)

**Context**: The domain glossary defines a 4-step budget auto-throttle ladder: (1) Switch to HITL mode (require approval), (2) Demote parallel to sequential, (3) Switch to cheaper model, (4) Pause. The current `BudgetTracker` collects snapshots but the ladder is not invoked.

**Honest assessment**: TestAI currently uses a single model for everything. The "switch to cheaper model" step assumes multi-model support, which isn't there. The other 3 steps (HITL, sequential, pause) are simpler but the multi-model assumption makes the full ladder YAGNI.

**User direction**: "we'll use a single model as of now for everything". C07 is deferred until multi-model support is added.

---

## Decision Q1 — Throttle logic location

**Options presented**:
- (A) Inside `BudgetTracker.observe()`
- (B) At the orchestrator
- (C) At the LLM router
- (D) As a separate `ThrottlePolicy` strategy

**Locked answer**: **DEFERRED**. Single-model for now.

**Reasoning recorded**:
- The "switch to cheaper model" step is the most important step in the ladder (the others are fallbacks).
- With single-model, the ladder reduces to: HITL → sequential → pause. That's 3 steps, but the model-swap step is the differentiator.
- When multi-model is added, re-grill the throttle ladder.

---

## What to capture when re-grilling

**Trigger**: when TestAI adds multi-model support (e.g., 200K Opus for complex tasks, 8B Haiku for simple ones).

**Decisions to re-grill**:
1. Throttle logic location (re-confirm the 4 options)
2. Soft/hard cap thresholds per scope (per-subagent, per-phase, per-run, per-user-per-day)
3. Which model is the "cheaper" alternative? Tier 1 = best, tier 4 = cheapest? Configurable per-org?
4. Does HITL mean (a) require human approval for every tool call, (b) require approval for destructive actions only, (c) just show a warning? — the domain glossary says "approve/review/clarify/edit checkpoints" but doesn't specify which
5. Sequential demotion: which `delegate_task(tasks=[...])` calls get demoted? Only new ones, or also in-flight ones?
6. Pause: does the run resume on the next budget cycle, or stay paused?

---

*Decision tree complete. 7 candidates captured: 5 designed, 2 deferred (C05 A2A, C07 Budget). C09 Event-sourced state is the only original candidate not addressed. See "Final Summary" below.*

---

# Final Summary

**Date**: 2026-06-21
**Mode**: Relentless Q&A grilling. 7 of 9 candidates from the architecture review walked through their design tree.
**Outcome**: 5 fully designed (40+ locked decisions), 2 deferred with documented triggers.

## Designed candidates (5)

| Candidate | Decisions | Effort | Files |
|-----------|-----------|--------|-------|
| **C04 kg_refresh** | 12 | 3 days | New `tools/kg_refresh_tool.py` + UI panel |
| **C08 JobSpec canonicalisation** | 10 | 2-3 weeks | New `POST /api/jobs` + 3 endpoint removals + frontend rewrite |
| **C01 Worktree isolation** | 6 | 1 week | New `services/worktree_manager.py` + draft PR helper |
| **C02 Agent Teams** | 6 | 1 week | New `services/team_service.py` + 7 lead/member tools |
| **C03 Push-based completion** | 4 | 3 days | Modify `_wait_for_board` to subscribe + idempotency tracker |
| **C06 Heartbeat** | 4 | 2 days | Add heartbeat loop inside `delegate_task.run()` |
| **C05 A2A wire protocol** (deferred) | 1 | ~1 week when needed | New `a2a/server.py` (thin shim over C08 endpoints) |
| **C07 Budget auto-throttle** (deferred) | 1 | ~3 days when needed | New `BudgetTracker.observe()` + 4-step ladder |

## Dependency graph (locked)

```
C08 (JobSpec canonicalisation)
  ├── enables C05 (A2A adapter — uses POST /api/jobs)
  ├── enables C02 (chat 8-tool surface — uses submit_job_to_orchestrator)
  └── replaces 3 legacy endpoints

C01 (Worktree isolation)
  ├── enables C02 (Agent Teams — coordination over per-subagent worktrees)
  └── provides per-subagent PRs (replaces team-aggregation strategy)

C04 (kg_refresh)
  └── standalone — improves subagent tool accuracy

C03 (Push-based completion)
  └── standalone — replaces 15s poll in _wait_for_board

C06 (Heartbeat)
  └── standalone — wraps delegate_task with Hermes-style stale detection

C07 (Budget auto-throttle)
  └── blocked on multi-model support
```

## Recommended sprint order

```
Sprint 1-2 (Foundation):
  ├── C04 kg_refresh (3 days)
  ├── C03 push-based completion (3 days)
  └── C06 heartbeat (2 days)

Sprint 3-5 (Multi-agent + canonical):
  ├── C08 JobSpec canonicalisation (2-3 weeks)
  │   ├── /api/jobs endpoint
  │   ├── 3 endpoint removals + frontend rewrite
  │   └── chat 8-tool surface
  ├── C01 worktree isolation (1 week)
  │   └── per-session + per-subagent
  └── C02 agent teams (1 week)
      └── depends on C01

Sprint 6-8 (Future-proof):
  ├── C05 A2A (deferred — 1 week when needed)
  └── C07 Budget (deferred — 3 days when needed)
```

Total locked-in work: ~7-9 weeks of focused engineering.

## Open questions across all candidates

1. C04: kg_refresh L1 promotion events, multi-repo behavior
2. C08: chat `add_comment` schema, `get_output` for in-progress jobs, pagination cap
3. C01: uncommitted local changes handling, PR base branch selection, `.worktreeinclude` analog
4. C02: nested teams (disallowed v1), message ordering, lead succession
5. C03: cross-instance delivery, persistent idempotency
6. C06: thread vs asyncio task for heartbeat, exception propagation
7. C05: parts file support, artifacts scope, push notification interaction
8. C07: model tiers, soft/hard cap thresholds, HITL granularity, sequential demotion scope, pause/resume

## What was NOT grilled

- **C09 Event-sourced state** — see below
- **F01-F06 Future-proof features** (MCP 2026-07-28, 1M context, OpenAI proxy, OTEL spans, plugin marketplace, dynamic workflows) — separately trackable as platform roadmap

# Candidate C09 — Event-sourced state (DEFERRED, KEEP AS-IS)

**Context**: OpenHands treats events as immutable and rebuilds state by replaying them. TestAI's `stream_events` table logs events but the agent state (the LLM message list) is reconstructed at debug time by re-running.

**Honest assessment**: The current state works. Replay is rare. The migration risk is high — the LLM message list is wired through the LLM client at every call site.

**User direction**: "keep this as is". C09 is deferred indefinitely.

**What would change if revisited**: the LLM message list becomes a projection of `stream_events` rather than a separate store. Replay is free. The risk: every Agent call site needs to be touched.

---

# Implementation status — what we discussed and can implement

The 6 designed candidates (C04, C08, C01, C02, C03, C06) are all implementable today. The 3 deferred candidates (C05, C07, C09) wait for triggers.

## Implementation status (in recommended order)

| Candidate | Decisions | Existing foundation | Effort | Blocker |
|-----------|-----------|---------------------|--------|---------|
| **C04 kg_refresh** | 12 | `KnowledgeGraphSyncer.sync` at `harness/services/knowledge_graph_syncer.py:185`; `stream_events` table | 3 days | none |
| **C03 push-based completion** | 4 | EventBus with `asyncio.Queue` at `harness/events.py:165-202` | 3 days | none |
| **C06 heartbeat** | 4 | `delegate_task.py`; stream_events | 2 days | none |
| **C01 worktree isolation** | 6 | `reference/OpenHarness/src/openharness/swarm/worktree.py:135` (port source); SandboxManager at `harness/sandbox_manager.py:588-597` | 1 week | none |
| **C02 agent teams** | 6 | `delegate_task.py`; `JobSpec` exists | 1 week | C01 (worktrees) |
| **C08 jobSpec canonicalisation** | 10 | `JobSpec` at `harness/jobs/spec.py:108`; 3 legacy endpoints (`agent.py:39`, `delegate.py:67`, `pipeline.py:57`); chat `submit_job` at `harness/jobs/spec.py` | 2-3 weeks | frontend rewrite |

## Sprint plan (concrete)

### Sprint 1-2 (Foundation) — ~3 weeks
- **C04 kg_refresh**: new `harness/tools/kg_refresh_tool.py` (~150 lines), toolset registration, frontend panel.
- **C03 push-based completion**: modify `orchestrator.py:_wait_for_board` to subscribe to EventBus, new `services/idempotency.py` (~50 lines).
- **C06 heartbeat**: add heartbeat loop inside `delegate_task.run()`, new `services/activity_signal.py` (~30 lines).

### Sprint 3-5 (Multi-agent + canonical) — ~5-7 weeks
- **C01 worktree isolation**: new `services/worktree_manager.py` (~200 lines, port from OpenHarness), modify `delegate_task.py` to create worktrees, new `services/draft_pr.py` (~50 lines).
- **C02 agent teams**: new `services/team_service.py` (~200 lines), new `tools/team_tools.py` (~300 lines), modify `delegate_task.py` to support `team_id` param, modify `toolsets.py` for `team_lead` and `team_member` toolsets.
- **C08 jobSpec canonicalisation**: add `JobContext` Pydantic model with `extra='allow'`, extend `JobSpecStore` with 7 new methods, implement `submit_job_to_orchestrator` shared function, new `api/routers/jobs.py` (~150 lines), update 3 legacy endpoints to call shared submitter (then delete), add 8 chat tools, rewrite 3 frontend pages.

### Sprint 6-8 (Future-proof) — when needed
- **C05 A2A**: ~1 week. Trigger: first external-agent customer.
- **C07 Budget**: ~3 days. Trigger: multi-model support.
- **C09 Event-sourced**: TBD. Trigger: replay becomes a hot path.

**Total locked-in work**: ~7-9 weeks of focused engineering.

## Glossary terms added during grilling

None — all decisions stayed within the existing domain glossary.

## Method note

Each question was grounded in either codebase research (codegraph) or internet research (DDG). The user made strong, decisive choices throughout, often picking the "no legacy" / "remove + rewrite" option. The grilling produced a coherent architectural story: C08 makes A2A possible, C01 unlocks C02, C03 and C06 are reliability polish, C04 is a small high-leverage tool.
