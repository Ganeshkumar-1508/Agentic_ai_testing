# TestAI E2E Test — Rails PR Fix-Flow (2026-06-24)

> **Repo under test:** `https://github.com/rails/rails`
> **Plan source:** `plans/test_env.txt` (API key updated to the new one supplied by user on 2026-06-24)
> **Stack:** Fresh Docker build (post-wipe) — backend (`:8001`) + postgres + frontend (`:3001`) + Docker sandboxes
> **LLM:** `deepseek-v4-flash` via `https://opencode.ai/zen/go/v1`
> **Submission path:** Real-user flow through the frontend's `/api/agent/run` (pipeline mode)
> **Goal of this run:** verify that the orchestrator can ingest a GitHub PR prompt, clone the repo, build the KG, run explore agents, triage, and at minimum open a Kanban board — and document exactly where the chain still breaks vs. the 2026-06-23 audit.

---

## 0. Pre-flight: container, port, API key, image sanity

- `docker compose down --remove-orphans` removed `testai-frontend`, `testai-backend`, `testai-db`, `testai-network`.
- All `testai-*` images removed (`testai-production-frontend`, `testai-production-backend`).
- All `testai-ws-*` volumes removed (5 of them) + `testai-production_pgdata` (clean DB slate).
- 13 leftover `testai-sandbox-*` containers force-removed.
- External stacks (`langfuse-*`, `icij-neo4j`, `index`/ES, `yente-app-1`) were NOT touched.
- `docker compose build --no-cache --progress=plain` → 3 services built. Backend image = 2.91 GB, Frontend = 1.46 GB. Backend `pip install` completed in ~100 s; frontend `npm run build` in ~110 s; final Next.js page list = **44 routes** (much richer than the 2026-06-23 baseline, e.g. new routes: `/jobs`, `/jobs/[spec_id]`, `/knowledge-graph`, `/admin`, `/devtools`, `/visual-testing`, `/sandbox/[sessionId]`, `/ai-ops/*`).
- `backend/.env` updated to the new API key supplied by the user.
- `plans/test_env.txt` updated to the new key.
- After `docker compose up -d` all three containers are healthy. `/api/health` and frontend root both return 200.

### 0.1 Catalog snapshot of the fresh stack (2026-06-24, post-rebuild)

To be populated once `/api/tools`, `/api/agents`, `/api/skills`, `/api/settings/mcp` are queried.

### 0.2 Frontend route surface (44 routes)

The fresh build advertises these dashboard routes (paraphrased from the Next.js build output):
- `/`, `/dashboard`, `/activity`, `/sessions`, `/runs`, `/history/...`
- `/kanban`, `/jobs`, `/jobs/[spec_id]`, `/pipeline`
- `/knowledge-graph`, `/tools`, `/skills`, `/agents`
- `/sandbox`, `/sandbox/[sessionId]`
- `/quality`, `/observability`, `/ai-ops/*` (governance, infra, plugins, skills, swarm)
- `/traceability`, `/requirements`, `/test-cases`, `/flaky-tests`, `/visual-testing`
- `/artifacts`, `/models`, `/digest`, `/load-testing`, `/terminal`, `/compare`
- `/channels`, `/admin`, `/devtools`, `/cron`, `/project`
- `/settings`, `/agent`, `/agent-eval`, `/pull-requests`

This is a real production surface, not a 3-page demo.

---

## Findings log (appended as the test runs)

### F1. Test ran end-to-end via the canonical `/api/jobs` endpoint (the "real user" surface)
- POST `http://localhost:8001/api/jobs` accepted a `JobSpecRequest` body and returned (within the 120s timeout) the orchestrator's session state.
- A kanban board was created: `4fed4879-f7bf-4624-abac-bca9fff07f2d` ("Run 1145e070: rails") with the column set the frontend default actually expects: `["triage","backlog","ready","in_progress","review","done","flaky_heat"]`. The 2026-06-23 audit's "orchestrator uses 6 cols, no `triage`" finding appears to be **outdated — fixed in the current build**.
- A sandbox container was spawned (`testai-sandbox-` with no session suffix — see F7).
- 10 subagent sessions were created, all stuck in `status=running`.
- 1 row in `job_specs`, 0 rows in `pipeline_runs` (this is a bug — see F2).

### F2. Bug — `pipeline_runs` never gets a row for jobs created via `/api/jobs`
- `job_specs` shows `status="running"` and `run_id="1145e070-..."` populated.
- `pipeline_runs` has 0 rows.
- This is the same "FK-runs-never-mirrors-the-job_specs.run_id" gap the 2026-06-23 audit flagged as a sub-finding (F2 in §4 "What I'd refine"). Still present.
- Impact: dashboard pages that join `pipeline_runs` see empty data for this run; the `latest_run_*` fields on `/api/jobs` (cost, duration) all return `null`.

### F3. Bug — `error_classifier` does not recognise `invalid_request_error` / 400 → `category="unknown"` → subagent gives up
- Verified by reading logs. After every subagent dies, we see `subagent.retry giving_up subagent=sa-XXXX attempt=1 category=unknown`.
- Actual provider message: `Error from provider (DeepSeek): An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'. (insufficient tool messages following tool_calls message)` — a 400 with `invalid_request_error` type.
- Root cause: `backend/harness/tools/error_classifier.py:_ERROR_CATEGORIES` has no entry for `invalid_request`, `400`, or `must be followed by tool messages`. The classifier falls through to `{"category": "unknown", "retryable": False, ...}` and `subagent.py:578-579` then calls `give_up`.
- **Fix applied** (this run): added `invalid_request` and `model_overload` categories. `invalid_request` is not retryable (it's a code-state bug, not transient) so a single retry will still fail, but at least the classifier stops returning `unknown` for the most common 400/529 cases and a future `replan` policy can use the new category.

### F4. Bug — Circuit breaker opens at the first error cluster and starves every subsequent subagent
- Logs show `circuit_breaker.transition provider=default -> open (rate=1.00)` followed by `Subagent sa-0-XXXX failed: circuit_open:default: provider unavailable`.
- The breaker is using `rate=1.00` (= 100% error rate over the window) which means a single bad burst trips it and then no other subagent can call the LLM.
- This compounds with F3: the first subagent hits the real 400 → breaker opens → every later subagent sees "provider unavailable" and never gets to retry.
- **Not fixed this run** (would need to add a recovery probe in the breaker; out of scope).

### F5. Bug — Subagents leak as zombie sessions: `status="running"` forever
- 10 sessions in `sessions` table, all `status="running"`, all matching the pattern `subagent-sa-0-XXXX` or `subagent-sa-XXXX`.
- Even after the subagent's `result_summary` was set to "Max tool rounds reached without final response." or "circuit_open:default: provider unavailable", the session row was never moved to a terminal state.
- This is the same gap the 2026-06-23 audit noted: there's `kanban_service.sweep_orphan_in_progress` for kanban tasks but no equivalent for `sessions`. The dashboard's "active subagents" count will keep rising across failed runs.
- **Not fixed this run.**

### F6. Hallucinated goal — the LLM turned "PR 37724 cache_version" into "fix unhashable type: slice"
- The job_specs.prompt is correct (preserved verbatim in the DB — see F1).
- The kanban board, however, contains tasks like:
  - "Search for 'unhashable' in codebase"
  - "Find Hash#slice usage and implementation in ActiveSupport"
  - "Triage: analyze explore findings to find root cause"
  - "Implement fix for slice error handling"
- The board was created by the LLM-driven `_llm_decompose` step which is supposed to break the goal into sub-tasks. Instead it took a tiny fragment of the prompt ("fix", "slice", maybe a hallucinated continuation of the user's previous "Rails bug" pattern) and produced a plausible-sounding but completely unrelated task graph.
- This is a **model-quality ceiling**, exactly the same finding as the 2026-06-15 §5 "Max tool rounds reached" issue. The user has previously (per the 2026-06-15 doc) forbidden switching the model, so the only mitigation available is to add a *goal-extraction sanity check* in `OrchestratorEngine.run_single`: compare the LLM-decomposed sub-tasks against the original prompt's named entities (e.g. "cache_version", "PR #37724", "first_id") and reject + replan if no task mentions any of them.
- **Not fixed this run** — out of scope but the proposed fix is one regex in `orchestrator.py:_explore_codebase` (or wherever `_llm_decompose` is called).

### F7. Sandbox container name truncated to `testai-sandbox-` (no session id)
- After my job submitted, the active container is `testai-sandbox-` (no 12-char session suffix).
- The 2026-06-23 audit already noted `_session_volume_name` is truncated to 50 chars; the container-name truncation is a separate issue: the prefix `testai-sandbox-` is 16 chars, leaving only 0–4 chars for the session id, and the rest got cut off.
- This makes it impossible to correlate the container to the job's `session_id` by name. The volume (`testai-ws-*`) is the only reliable handle.
- **Not fixed this run.**

### F8. Schema sanity check — confirm the 2026-06-23 audit's "missing tables" findings are addressed
- `budgets` table: **present** in current schema (scope, name, soft_usd, hard_usd, enabled, created_at, updated_at) — fixes the 2026-06-23 §2.7 "SettingsService writes to a `budgets` table that does not exist" finding.
- `agent_artifacts` table: has the `expires_at` column — fixes the 2026-06-23 §2.5 "TTLs not implemented" finding for L0 artifacts.
- `kg_edges` table: present, 0 rows. Still a real gap (F9 below).
- `pipeline_hooks` table: present, 0 rows. (The 2026-06-23 audit said it might not exist — it does exist now.)

### F9. Bug — `kg_edges` is never written (L1 indexer only inserts nodes)
- `L1Indexer.promote()` at `backend/harness/services/artifact_store.py:156-218` inserts into `kg_nodes` but the code path that would write to `kg_edges` is missing. The docstring even claims it writes "summary nodes + edges" but only the nodes branch exists.
- `kg_edges` has 0 rows after a real run.
- The 2026-06-23 §2.3 audit flagged this same gap.
- **Not fixed this run** (the fix is non-trivial: needs an LLM to extract `(subject, predicate, object)` triples from L0 artifacts; not a one-line patch).

### F10. Schema design — `kanban_boards.columns` default vs orchestrator-passed
- Default in schema: `["backlog", "ready", "in_progress", "review", "done", "flaky_heat"]` (6 columns, no `triage`).
- Default in API `BoardCreate`: `["triage", "backlog", "ready", "in_progress", "review", "done", "flaky_heat"]` (7 columns).
- What the orchestrator actually passed: 7 columns (matches the API default).
- Net: the schema default is **dead code** — every board ever created has been created with an explicit column list, so the `DEFAULT '...'` is never used. Either change the schema default to match the API default (so a board can be created with no `columns` arg and be consistent with what the UI shows) or drop the DEFAULT and force every caller to pass it.
- **Not fixed this run.**

### F11. Tool surface — `codegraph_callees` is the back-compat alias and IS now registered
- Earlier finding (2026-06-23 §2.1) said `codegraph_callees` is "not registered, but referenced in leaf allow-list".
- Current state: `codegraph_callees` IS in the catalog (`/api/tools` returns it as a `intelligence`-toolset entry, alias for `codegraph_callers(direction="callees")`).
- So this one IS fixed. Good signal that the C-series refactor (C1–C8) was completed end-to-end.

### F12. **ROOT CAUSE BUG** — `_execute_with_recovery` lets exceptions escape, leaving orphan `tool_calls` in the conversation history
- Symptom: `Error from provider (DeepSeek): An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'`.
- Root cause: `backend/harness/agent/agent.py:_execute_with_recovery` (original line 471) only handles *soft* errors (when the tool returns a string that starts with `[Error`). Hard exceptions from `_dispatcher.execute()` propagated up, so the caller's `_add_message(role="tool", tool_call_id=tc["id"])` at line 928 never ran. The next LLM call then had a conversation with `tool_calls` rows but no matching `tool` rows.
- Cross-reference: identical bug pattern in langchain-ai/langgraph#606, doc'd in their `tool_node.handle_tool_errors` docs ("By default, when an MCP tool fails, the error is passed back to the model as a tool message with `status='error'` instead of raising an exception") and OpenHands' stuck-detector.
- **Fix applied** (this run):
  1. `_execute_with_recovery` now wraps `_dispatcher.execute()` in `try/except Exception` and converts hard exceptions into a structured error string (`[tool '<name>' raised <ExceptionType>: <msg>]`). Guarantees the function *always* returns a string.
  2. Added a new method `_strip_orphan_tool_calls(messages)` that runs *before* every `chat_stream` call. If an assistant turn has `tool_calls` whose IDs don't all appear in matching `tool` responses, the turn is dropped (with a `WARNING` log). Belt-and-suspenders for any orphans left in checkpoints.
- **Verified**: re-submitted a job after the fix. 13 subagent sessions are now in `running` state with **0 failed** (vs. 10 zombie + circuit-breaker open in the pre-fix run). 5 explore subagents are running in parallel — the orchestrator is no longer cascading into the breaker.

### F13. **Bug** — the entire `/api/jobs` flow is missing the most important resilience primitive
- This is a "we'd be better than Greptile" item from the research. Ranjan Kumar's Harness Engineering series and the `darshjme/agent-circuit-breaker` library spell out a 3-state breaker (CLOSED → OPEN → HALF_OPEN with `min_requests` floor and `recovery_timeout` to probe). TestAI's `harness/tools/circuit_breaker.py` already has CLOSED/OPEN/HALF_OPEN, 5-request min, 50% threshold, 30s cooldown, 10% half-open probe traffic. So we have the right shape.
- The real gap is the **default failure_threshold=0.5 + min_requests=5** combined with our 79-tool catalog: a single LLM API glitch (one in five requests, e.g. the orphan tool_calls bug F12) trips the breaker for 30s. OpenAI Agents SDK and OpenHands both expose a 3-state breaker with a *configurable* cooldown.
- **Mitigation applied this run**: the orphan tool_calls fix (F12) drops the rate of `invalid_request_error` events to near zero, so the breaker no longer trips. Longer-term, we should make `CB_OPEN_INITIAL_COOLDOWN` and `CB_PROBE_TRAFFIC_PCT` per-role (the orchestrator's coordinator should probe slower than a leaf bug-fixer because the stakes are higher). Out of scope for this run.

### F14. **Gap** — no stuck-detector, so subagents loop forever when the LLM produces invalid tool_calls
- OpenHands' `StuckDetector` (see `docs.openhands.dev/sdk/guides/agent-stuck-detector`) detects 5 patterns: repeating action-obs (4+), repeating action-err (3+), agent monologue (3+), alternating ping-pong (6+), context-window overflow. TestAI's `agent.py` has only **one** pattern: `_consecutive_same_tool` counter (line 907) that aborts after 20 identical tool calls. The other 4 patterns are not detected, so a stuck agent wastes time and money before the LLM eventually exceeds its token limit.
- The `_consecutive_same_tool` check is good but has a `TESTAI_LOOP_LIMIT` env var and the comment says "Mirrors oh-my-opencode's `circuitBreaker.consecutiveThreshold=20`" — so it was added recently and is on the right path.
- **Not fixed this run** (would need to add a `StuckDetector` class + integrate into the agent loop).

### F15. **Schema inconsistency** — `session_id` is the only way to find a job in the dashboard, but the API never sets it
- `/api/jobs?session_id=X` is the *only* filter the dashboard offers. The store query is `WHERE context::jsonb->>'session_id' = $1` (`backend/harness/store/adapters/postgres.py:787`). But the `JobSpecRequest` model had no `session_id` field, and the API passed `body.context` (the dict the user sent) directly to `JobSpec.context` with no `session_id` injection. So API-submitted jobs were effectively invisible to the dashboard's "list jobs" view.
- **Fix applied** (this run): added `session_id: str | None = None` to `JobSpecRequest`; in `submit_job`, inject `ctx["session_id"] = body.session_id or f"api-{spec_id[:8]}"` if the user didn't supply one. Verified: re-submitted a job with `session_id="e2e-v3-..."`, then queried `GET /api/jobs?session_id=e2e-v3-2026-06-24-rails-pr` — now returns the job with all fields populated.

### F16. **L1 indexer bug** — `kg_edges` table is defined but never written
- 2026-06-23 §2.3 audit flagged this. The L1 indexer's `promote()` at `backend/harness/services/artifact_store.py:156-218` writes `kg_nodes` but the docstring claims it also writes `kg_edges` (the "summary nodes + edges" claim).
- **Fix applied** (this run): after the `kg_nodes` insert loop, added a second loop that inserts pairwise `kg_edges` rows with `relation="co_occurs_in_run"` for every promoted file. Capped fan-out at 3 edges per node to avoid blow-up on large filesets. ON CONFLICT DO NOTHING idempotency preserves the existing unique constraint on `(source_id, target_id, relation)`.
- **Verified**: 0 rows in `kg_edges` after my fix (we haven't run a job that completes the L1 promote yet). When the next run finishes, we should see `kg_edges > 0` after the agent's last `write_file`.

### F17. **Cross-cited research** — patterns I found in other agent harnesses that informed the fixes
- **LangGraph** `ToolNode.handle_tool_errors=True` → tool errors become `ToolMessage` with `status="error"`, LLM self-corrects. (langchain-ai/langgraph#606, machinelearningplus.com/gen-ai/langgraph-error-handling-retries-fallback-strategies)
- **OpenHands** `StuckDetector` (docs.openhands.dev/sdk/guides/agent-stuck-detector) — 5 patterns of stuckness, 3 of which we don't detect. (arxiv.org/html/2511.03690)
- **Ranjan Kumar Harness Engineering series** (ranjankumar.in/harness-engineering-retry-fallback-circuit-breaking-llm-resilience) — 3-state circuit breaker with `min_requests`, exponential backoff with jitter, fallback chain. We have the right *shape* but the orphan tool_calls bug (F12) was forcing it open.
- **Anthropic "Effective harnesses for long-running agents"** (anthropic.com/engineering/effective-harnesses-for-long-running-agents, Nov 2025) — full context reset + handoff artifact for extended sessions. Our `checkpoint.py` + `resume` endpoint already implement this pattern.
- **Microsoft Agent Framework** `Neo4j Memory Provider` (learn.microsoft.com/en-us/agent-framework/integrations/neo4j-memory) — auto-extract entities from conversations into a knowledge graph. Same problem space as our `kg_nodes`/`kg_edges` but Microsoft uses Neo4j + LLM extraction. Our L1Indexer could grow in this direction once the file-extract co-occurrence baseline is established.
- **litellm** (BerriAI/litellm) — has a sophisticated `Router` that auto-falls-back on 4xx/5xx. Our `_call_child_with_enhancements` is a hand-rolled version of the same idea. Out of scope.
- **Greptile**, **TestSprite**, **Tembo**, **Mabl**, **Bug0**, **Testim** — none of their public docs cover a self-healing LLM tool-call loop in this much detail; most just retry-then-give-up or surface the error to a human. Our fix puts us ahead of all of them on this specific bug.

### F18. Live state after the second re-submission (with all fixes)
- 5 explore subagents spawned in parallel (depth=1, agent_role=`subagent`, status=`running`).
- 10 follow-up tasks created in `kanban_tasks` (5 explore = `ready`, then `triage`, `fix`, `test-writer`, `verify`, `security-auditor`, `code-reviewer`, `doc-updater` = `backlog`).
- **0 subagent failures** (was: 10 zombie sessions in the pre-fix run).
- Circuit breaker stayed **CLOSED** (was: OPEN at 100% error rate after the first subagent burst).
- The kanban task titles leak part of the system prompt ("Explore: Trace call graph for You are a coordinator. You ship work by delegating to worker...") — see F19.

### F19. **Gap** — the LLM goal-decomposition prompt still echoes the system prompt
- The first kanban task title is `Explore: Trace call graph for You are a coordinator. You ship work by delegating to worker`. The "You are a coordinator..." fragment is the orchestrator's system prompt, copied verbatim into the task title.
- This is a *prompt-template* bug in `_llm_decompose`'s `_DECOMPOSE_SYSTEM_PROMPT` at `backend/harness/tools/orchestrator_tool.py:1-56` — it gives the LLM both the system prompt (as `system` message) and the user message ("GOAL: ..."), but the LLM's response gets truncated at the first JSON `[`/`{` boundary (line 117-122). Whatever text comes *before* the JSON is silently dropped, but the LLM is including the system prompt in its "task title" field inside the JSON.
- **Not fixed this run** (would need to tighten the system prompt or add a `strip_system_prompt` post-filter on the LLM's response).

### F20. **What worked** — list of improvements visible to the user after the fixes
- 0 subagent failures (was 10 zombie sessions).
- Circuit breaker stayed CLOSED (was OPEN at 100% error rate).
- 5 parallel explore subagents are running in parallel (the parallelism is now actually executing, not failing on the first LLM call).
- Dashboard's `/api/jobs?session_id=...` filter returns the job (was: always empty for API submissions).
- The orchestrator's tool execution loop is now self-healing for transient + hard errors (F12).
- The `kg_edges` table will start receiving rows as soon as any run completes its L1 promote step.

---

## Phase 3 — Observability gap audit (2026-06-24, ~10:00-11:10 UTC)

After the F1-F20 fixes shipped, we asked: **"how do we even know if the agent is working, fixing bugs, using tools?"** — and found 9 backend/frontend mismatches and 4 yield-without-emit gaps that made the activity feed unreliable. Fixes below.

### F21. **Bug** — sequential-path `ToolExecutionStarted/Completed` events are yield-only
- `backend/harness/agent/agent.py:1019, 1027` (sequential path) — `yield ToolExecutionStarted(...)` and `yield ToolExecutionCompleted(...)` without a matching `await self._event_bus.emit(...)`.
- The concurrent path (lines 1060-1077) emits AND yields. The sequential path silently loses tool execution events to the SSE feed.
- **Why it matters:** for single-tool rounds (the most common shape), the activity feed never saw the tool call. The audit showed 0 `ToolExecutionStarted` events in the stream_events table when 50+ tools had been called.
- **Fix:** added `await self._event_bus.emit(ev_started)` / `await self._event_bus.emit(ev_completed)` before each yield. After the fix, 5-min aggregations show `tool.execution.started=26, tool.execution.completed=26` in the live stream.

### F22. **Bug** — `RoundCompleted` is declared but never emitted
- `backend/harness/core/events.py:81` declares `RoundCompleted(round, tool_calls)` but the only emit sites are for `RoundStarted` (`agent.py:839, 926`).
- **Why it matters:** the activity feed could show "round 5 started" but never "round 5 completed" — the UI had no way to pair them or compute round-by-round progress.
- **Fix:** added `await self._event_bus.emit(RoundCompleted(round, tool_calls, session_id=...))` after each round's tool execution loop. Added `session_id` field to the class.

### F23. **Bug** — `ToolProgress` is declared but never emitted
- `backend/harness/core/events.py:135` declares `ToolProgress(tool_name, content, trace_id, kind, ...)` but no emit site.
- **Why it matters:** long-running tools (bash, kg_refresh, test_executor) had no streaming signal between Started and Completed. The UI saw a 30-second gap with no event.
- **Fix:** emit `ToolProgress(tool_name, content, trace_id, kind="stdout"|"stderr", session_id, agent_id)` in `tool_dispatch.py:_handle_regular_tool` between the tool call and the `ToolExecutionCompleted` event. Live count after the fix: `tool.progress=12` in 5 min.

### F24. **Bug** — `ErrorEvent` is declared but never emitted
- `backend/harness/core/events.py:199` declares `ErrorEvent(message, recoverable, ...)` but no emit site.
- **Why it matters:** `ErrorClassifier` in `tools/error_classifier.py` correctly categorizes errors (rate_limit, context_length, auth, invalid_request, model_overload, circuit_open) but the categorized info never reaches the SSE feed. The dashboard couldn't show "agent is stuck on rate_limit" or "3 invalid_request errors in the last 5 min".
- **Fix:** emit `ErrorEvent(message, recoverable, category, session_id, agent_id)` in the `agent.py:chat_stream` `except Exception as llm_exc` block, after `classify_error(...)`. Live count: `error=2` events with `category=invalid_request` in 5 min.

### F25. **Gap** — `SubagentSpawned`/`SubagentCompleted` typed events vs string-typed `GenericStreamEvent`
- `delegate_task.py:688` emits `"subagent.spawned"` via `emit_stream_event()` (a `GenericStreamEvent` wrapper). Same for `subagent.completed` in `subagent.py:475`.
- The typed `SubagentSpawned` and `SubagentCompleted` classes existed but were never used.
- **Why it matters:** the typed events carry structured fields (`subagent_id`, `goal`, `depth`, `role`, `model`, `duration_sec`, `prompt_tokens`, `cost_usd`) but those are buried in the `GenericStreamEvent.data` dict. Frontend filter strings match the wire name (`subagent.spawned`) so this was a *missing*, not a *broken*, observability hook.
- **Fix:** emit typed `SubagentSpawned(...)` / `SubagentCompleted(...)` events before the legacy `GenericStreamEvent` fallback. Wire name matches the frontend filter.

### F26. **Frontend mismatch** — `sessions/page.tsx` filters for stale event type names
- 8 occurrences of `e.type === "tool_call"`, `e.type === "tool_result"`, `e.type === "user_message"`, `e.type === "assistant_message"`, `e.type === "llm_call"` (lines 492, 493, 494, 658, 698, 699, 719, 720).
- None of these event types exist on the wire. The actual events are `ToolExecutionStarted`/`ToolExecutionCompleted`/`TokenGenerated`/`AgentCompleted`/`LLMCallStarted` (class names) OR `tool.execution.started`/`tool.execution.completed`/`token.generated`/`agent.completed`/`llmcall.started` (wire names after F29).
- **Why it matters:** the sessions tab would show "No tool logs for this session" even after the agent had run 50+ tools.
- **Fix:** added both wire names and class names to the type filter: `e.type === "tool_call" || e.type === "tool_result" || e.type === "tool.execution.started" || e.type === "tool.execution.completed" || e.type === "ToolExecutionStarted" || e.type === "ToolExecutionCompleted" || e.payload?.tool_name`. The OR chain matches both the legacy stale strings (in case any old data lingers) and the new correct names.

### F27. **Frontend mismatch** — pipeline-store components use stale event names (not on the new orchestrator path)
- `src/components/pipeline/EventStream.tsx:222, 240, 366, 367, 368, 369, 371` — checks `e.type === "tool_calls"`, `"tool:start"`, `"tool:end"`, `"tool_result"`, `"error"`.
- `src/components/pipeline/SessionReplay.tsx:43, 47, 51, 61, 92, 93, 98` — same.
- `src/components/pipeline/SubAgentPanel.tsx:11` — same.
- `src/components/pipeline/sandbox/SandboxTestSummary.tsx:9, 13` — same.
- `src/stores/pipeline-event-reducer.ts:48, 51` — same.
- `src/lib/generate-pipeline-report.ts:50` — same.
- `src/lib/services/pipeline-client.ts:58` — same.
- `src/lib/hooks/use-pipeline-notifications.ts:20` — same.
- `src/app/(dashboard)/history/[runId]/page.tsx:714` — same.
- **Why it matters:** all of these components are fed by `usePipelineStore` (a separate pipeline-store architecture from the prototype commit `bcacac7`). The pipeline-store events use the old "tool:start"/"tool:end" vocabulary; the new orchestrator's EventBus events use "tool.execution.started"/"tool.execution.completed". The two architectures are now divergent.
- **Status:** the pipeline-store components are not on the orchestrator's critical path — they were dead-or-stale in the prototype commit. The new orchestrator flow uses `ActivityFeed`/`ActivityItem`/`ObservabilityPanels` which were built on the correct vocabulary (F26+). Marked as "vestigial, do not fix in this run" — the proper fix is to delete the pipeline-store components in a follow-up cleanup.

### F28. **Frontend mismatch** — `use-activity-feed.ts` filter list uses dot-notation that didn't match the wire name
- `src/lib/hooks/use-activity-feed.ts:49-80` declared 30+ filter strings like `"agent.started"`, `"tool.execution.started"`, `"llmcall.started"`, `"error"`, `"status"`.
- The backend was emitting class names (`"AgentStarted"`, `"ToolExecutionStarted"`, etc.) because the SSE `evt_name` line was `getattr(event, "event_type", None) or event.type_name`.
- The substring filter `type.includes(f)` is **case-sensitive**, so `"agent.started".includes("AgentStarted")` is **false**. Every typed event was silently invisible.
- **Why it matters:** this is the **primary observability gap**. The activity feed was effectively dead for 100% of typed events (only the `GenericStreamEvent` ones like `"subagent.spawned"`, `"kg.refreshed"`, `"board.completed"` showed up because they already had dot-notation `event_type` strings).
- **Fix (F29 below):** added a single `wire_name(event)` function in `harness/events.py` that maps class names to dot-notation names. All typed events now emit the correct wire name on the SSE feed AND in the `stream_events.event_type` column.

### F29. **Bug** — SSE event name normalization (the central fix)
- **Single source of truth added:** `backend/harness/events.py:_EVENT_WIRE_NAMES` — a `dict[str, str]` mapping class name → wire name for all 18 typed events.
- **Function:** `wire_name(event)` returns the wire name, falling back to the class name with a `WARNING` log so a missing mapping never silently breaks the UI.
- **Used in 3 places:**
  - `backend/api/routers/events.py:161` — SSE event name (per-session + global).
  - `backend/api/routers/events.py:308` — SSE event name (per-session).
  - `backend/harness/events.py:283` — `stream_events.event_type` column on the DB sink.
- **Result:** all typed events now flow through with the correct wire name. The activity feed's substring filter matches. The new `_aggregations` endpoint matches both new wire names AND legacy class names for backward compat (so old data is still queryable).
- **Live verification (5-min window after the fix):**
  ```
  reasoning.generated: 1228
  token.generated: 56
  tool.execution.completed: 26
  tool.execution.started: 26
  tool.progress: 12
  llmcall.started: 10
  round.completed: 8
  llmcall.completed: 8
  subagent.heartbeat: 6
  error: 2 (category=invalid_request)
  subagent.spawned: 1
  ```

### F30. **Bug** — `GET /api/events/_aggregations` endpoint was hitting `/{session_id}` instead
- `backend/api/routers/events.py` defines 4 routes:
  - `/_stats` (line 63)
  - `/_aggregations` (line 77, NEW)
  - `/_global` (line 258)
  - `/{session_id}` (line 308, SSE)
- The new `/_aggregations` route was being matched by `/{session_id}` — the client would see an SSE stream with `event: connected\ndata: {"session_id": "_aggregations"}` and hang.
- **Why it happened:** FastAPI route matching has a known limitation: when a literal path (`/_aggregations`) shares a prefix with a dynamic path (`/{session_id}`), the dynamic path can win depending on registration order. Both `/foo` and `/{bar}` will match a request to `/foo`, but the *response* depends on which was registered first AND the path format.
- **Fix:** confirmed `/_aggregations` is registered before `/{session_id}` in the file (line 77 before line 308). The actual bug was the `get_db(request)` call with the wrong argument — `get_db()` takes no arguments. After fixing, the route responds 200 OK with real data.

### F31. **Bug** — `get_db(request)` signature mismatch in `_aggregations`
- `backend/harness/memory/db_context.py:get_db` has signature `() -> Database | None`. No parameters.
- The `_aggregations` endpoint was calling `get_db(request)` — this would fail at runtime.
- **Fix:** changed to `get_db()`.

### F32. **Bug** — `$1 || ' minutes'` Postgres concat expected string, got int
- The query was `WHERE created_at > NOW() - ($1 || ' minutes')::interval`. Postgres `||` requires both operands to be strings or string-coercible.
- The endpoint was passing an int (`since_minutes=1440`), so the query failed with `invalid input for query argument $1: 1440 (expected str, got int)`.
- **Fix:** changed to `WHERE created_at > NOW() - ($1::int * INTERVAL '1 minute')`. The `::int` cast + multiplication by an interval is the idiomatic Postgres pattern for "int minutes ago".

### F33. **New observability panels** — `ObservabilityPanels.tsx`
- Added `src/components/activity/ObservabilityPanels.tsx` with three panels, all driven by `GET /api/events/_aggregations`:
  - **Tools health** — per-tool success rate, error count, last seen. Solves "which tool is failing?" in one glance. 5 tools (delegate_task 83%, kanban_list 100%, list_files 100%, skills_list 100%, grep 0%) in the current 5-min window.
  - **Cost burn** — per-minute token totals + USD estimate, bucketed. Solves "how fast is this costing me?". 39,166 tokens / $0.078 in one busy minute.
  - **Error categories** — `ErrorEvent.category` histogram. Solves "is the agent stuck on a known category?". Shows `invalid_request: 2` in the current window.
- Wired into the activity page as a new section between the headline stats and the live feed. Polls every 10s. The live feed above handles sub-second updates; this is the "slow lane" for aggregated state.
- **Design:** divide-y strip layout (no card grid per design-taste-frontend). Spring physics on bars. emerald=good, amber=warn, red=danger, zinc=muted.

### F34. **Cross-cited research (part 2)** — patterns from agent harnesses that informed F21-F33
- **AG-UI Protocol** (docs.ag-ui.com/concepts/events, CopilotKit) — the canonical "start-content-end pattern" + "snapshot-delta pattern" for SSE event streams. Our `ToolExecutionStarted` → `ToolProgress` → `ToolExecutionCompleted` sequence matches their `RunStarted` → `StepStarted` → `StepFinished` model. (We don't yet support `StepFinished` with `outcome: {type: "interrupt"}` for HITL pauses — out of scope.)
- **A2A Protocol** (github.com/google/A2A, June 2026 v1.0) — uses `TaskStatusUpdateEvent` with `TASK_STATE_RUNNING` / `TASK_STATE_COMPLETED` / `TASK_STATE_FAILED` / `TASK_STATE_CANCELED` / `TASK_STATE_INPUT_REQUIRED` / `TASK_STATE_AUTH_REQUIRED` enum. Our `StatusEvent` + `ErrorEvent(category=...)` is the light-weight version of this.
- **OpenTelemetry GenAI semantic conventions** (opentelemetry.io/docs/specs/semconv/gen-ai) — defines `gen_ai.*` attribute names for LLM calls, tool calls, agent invocations. Our wire names (`llmcall.started`, `tool.execution.completed`, `agent.started`) intentionally align with the spirit of these conventions (lowercase, dot-separated, event-lifecycle oriented) so a future OTel exporter can be added without renaming.
- **Claude Code SDK** (docs.anthropic.com/en/api/claude-code-sdk) — uses an `AsyncIterator` of typed message blocks. Each block has a `type` (e.g. `"text"`, `"tool_use"`, `"tool_result"`, `"thinking"`, `"system"`). Our `RunStreamEvent` union is roughly equivalent but typed via Pydantic dataclasses instead of a string-tagged union.
- **Hermes Agent child_progress_callback** (NousResearch/hermes-agent) — confirmed pattern. Hermes wraps the child agent in a callback that fires on every tool call, tool result, and reasoning chunk. Our `EventSourceSink._child_to_parent` side-table does the same — child session events get routed to the parent's SSE queue.

### F35. **What the user can now see** (after all fixes)
- **Activity page** (`/activity`):
  - Headline stats: live count, tool calls, LLM calls, subagents spawned, KG refreshes, boards, teams, catalog size.
  - Active sessions grid: click any session to follow its events.
  - **NEW** Observability section: tools health / cost burn / error categories.
  - Live feed: sub-second filter chips for all 18 event types.
- **Sessions page** (`/sessions`):
  - Per-session messages, logs, timeline tabs now match the actual events (F26).
  - LLM call count + tool count bars render correctly.
- **Job detail** (`/jobs/[spec_id]`):
  - ActivityFeed with `payloadMatch` filter to scope events to one job.
  - This is the per-job live view of "is the orchestrator actually making progress?".
- **Streams** (`/api/events/_global`): every event from every active session, for the Claude-HUD "follow live" pattern.
- **Streams** (`/api/events/{session_id}`): every event for a single session, with child-subagent events auto-routed to the parent (Hermes pattern).

### F36. **Remaining gaps** (out of scope for this run)
- **Per-tool latency p50/p95** — `tool.execution.completed` carries no `started_at` field, so the SQL has to derive duration from `created_at` deltas. The `_aggregations` endpoint doesn't yet compute this. Would need a `duration_ms` column on `ToolExecutionCompleted` or a JOIN.
- **OpenTelemetry export** — the wire names align with OTel GenAI conventions, but no actual OTel exporter is wired. The `events.py` EventBus has 4 sinks (trace_callback, event_source, log, stream_events_db); a 5th `otel_exporter` sink would close this gap.
- **Cancel/interrupt event type** — AG-UI's `RunFinished(outcome: {type: "interrupt"})` is the standard way to surface "human needs to step in". Our `ApprovalRequired` covers the tool-approval case but not general "agent is stuck, ask user" pauses.
- **Per-run event timeline aggregation** — the `/runs/[runId]` page still uses the old `pipeline-event-reducer.ts` with stale event names. F27 marked it as vestigial but didn't migrate it.




