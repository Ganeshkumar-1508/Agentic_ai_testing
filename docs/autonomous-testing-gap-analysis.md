# Autonomous Agentic Testing — Feature Gap Analysis

**Date:** 2026-06-09
**Method:** Codebase exploration + industry research (Qodo, Greptile, TestSprite, Anthropic, Google Cloud, Azure)

---

## Priority Key

| Icon | Meaning |
|------|---------|
| 🔴 **P0** | Blocks end-to-end flow |
| 🟡 **P1** | High value, industry-proven |
| 🟢 **P2** | Polish/scale |

---

## ✅ P0 — Critical Gaps (All Resolved)

| # | Gap | Status | Resolution |
|---|-----|--------|------------|
| 1 | PhaseRunner implementations | ✅ Superseded | Kanban-driven model replaces phases. OrchestratorEngine + kanban dispatcher handles flow. |
| 2 | Knowledge Graph Write-Back | ✅ Not needed | CodeGraph SQLite auto-sync handles all KG updates. No Postgres KG needed. |
| 3 | PR Webhook Endpoint | ✅ Done | `pr_webhook.py` with HMAC verification for GitHub, GitLab, Bitbucket. `@testai` mention support. |
| 4 | Artifact Persistence Schema | ✅ Done | `artifacts` table added to `schema.sql` in migration. |

## ✅ P1 — High Value (All Resolved)

| # | Gap | Status | Resolution |
|---|-----|--------|------------|
| 5 | Evaluator-Optimizer Loop | ✅ Done | Review agent blocks → task unblocked → fix agent retries with prior context via `kanban_show` prior_outcomes. Structured handoff via `summary` + `metadata`. |
| 6 | Incremental KG Re-Index | ✅ Done | `codegraph sync` provides incremental file-level re-indexing natively. |
| 7 | Test Impact Analysis | ✅ Done | `test_impact` tool wraps `codegraph affected --stdin --quiet`. Detects changed files via git diff, returns affected test files. Registered in dispatcher toolset. |
| 8 | Sandbox Workspace/Browser | ✅ Already implemented | `SandboxFileTree` + `SandboxTerminal` are real components with API integration. No placeholders. |
| 9 | HITL Gates | ✅ Superseded | System is fully autonomous — orchestrator auto-approves. Optional `needs_review` flag on kanban tasks. |
| 10 | Git Webhooks | ✅ Done | `pr_webhook.py` handles GitHub/GitLab/Bitbucket with HMAC verification. `_run_pr_pipeline` triggers auto-fix loop.

---

## 🟢 P2 — Backend/Core Priority (Remaining)

### 11. Multi-Repo Orchestration

**Status:** ⚠️ Partial — Backend
**Files:** `backend/harness/multi_repo_coordinator.py`, `backend/harness/cross_repo.py`
**What exists:** Coordinator module exists but not wired into `orchestrate` tool or `OrchestratorEngine`.
**Required:** When a task spans repos → coordinator clones all → analyzes cross-repo deps → delegates per-repo sub-tasks via kanban.

### 12. Sprint / Release Tracking

**Status:** ⚠️ Partial — Backend  
**Files:** `backend/api/routers/sprint_api.py`, `backend/harness/sprint_trends.py`
**What exists:** Sprint API and trends module exist but kanban doesn't integrate.
**Required:** Kanban tasks linkable to milestones. Sprint velocity tracked per-agent.

### 15. Flaky Test Automation

**Status:** ⚠️ Partial — Backend
**Files:** `backend/harness/flaky_detector.py`, `backend/harness/flaky_auto_quarantine.py`, `backend/harness/kanban/rules.py`
**What exists:** Flaky detection + auto-quarantine logic works. Kanban `flaky_heat` column exists.
**Required:** Wire kanban automation rule: flaky score > threshold → auto-create kanban task in `flaky_heat` → assign to fix agent.

### 16. Coding Standards Rules Engine

**Status:** ❌ Missing — Backend
**Files:** `backend/harness/kanban/rules.py` (existing when-then pattern)
**Required:** Rules engine that checks code against configurable standards. Reuse `kanban/rules.py` when-then pattern applied to code review findings.

## 🟢 P2 — UI/Polish Priority (Later)

### 13. Cost Allocation Dashboard
✅ Done — `GET /api/cost/per-role` endpoint + `CostBreakdownCard` widget on dashboard.

### 14. Custom Dashboard Widgets
**Status:** ❌ UI — Defer
**Required:** User-configurable dashboard — drag widgets, select metrics, set time ranges.

### 17. IDE Plugins / CLI Tool
**Status:** ❌ UI — Defer
**Required:** CLI tool connecting to backend API for local review.

### 18. Ticketing System Integration
**Status:** ❌ Backend — Defer
**Required:** OAuth for Jira/Linear → fetch tickets as context for explore agents.

---

---

## Resolved Architecture Decisions (2026-06-09)

### 1. Orchestrator Pattern
**Decision:** Single orchestrator, two sequential phases, event-driven.
**Detail:**
- One orchestrator process per Run
- Phase 1: Analyze & Triage — pull repo, build KG, explore issues/PRs, create kanban board
- Phase 2: Execute & Verify — kanban dispatcher picks tasks, fix agents run, review, publish
- Handoff: orchestrator emits `phase.analyze.complete` → kanban board populated → dispatcher reacts

### 2. Fix Agent Loop
**Decision:** Combined self-heal + greploop, max 5 attempts with escalation.
**Detail:**
- Test fails → classify failure type:
  - Flaky (locator/timeout) → `attempt_heal` → re-run → if pass → review
  - Logic (assert/crash) → greploop: fix agent → codegraph sync → re-run → review agent
  - Permanent (invalid input, missing key) → block immediately, notify
- Max 5 fix attempts across both loops
- After 5: mark task `blocked`, send multi-channel notification

### 3. Sandbox Model
**Decision:** Daytona-style shared container with snapshots.
**Detail:**
- One sandbox (Docker container) per Run
- All subagents (Explore, Fix, Review) share the same container
- Snapshot before each fix attempt — rollback on corruption
- Named volume persists across the Run for KG data

### 4. Knowledge Graph Update
**Decision:** `codegraph sync` incremental update after each fix.
**Detail:**
- Phase 1: `codegraph init -i` (full build once)
- After each fix agent attempt (sequential): `codegraph sync` — incremental update from the single workspace
- `codegraph affected <changed_files>` to find exactly which tests to run (requires synced KG)
- Phase 2 persist: final `codegraph sync` for the review phase
- Sequential agents eliminate all KG sync complexity (no worktrees, no parallel conflicts)

### 5. Orchestrator ↔ Kanban Coordination
**Decision:** Event-driven, no polling.
**Detail:**
- Orchestrator emits typed events to `kanban_events` table
- Kanban dispatcher subscribes to events (already has SSE infrastructure)
- Kanban board is a read-only state view projected from event stream
- `orchestrate_monitor` tool remains as fallback only

### 7. Explore Agent Depth
**Decision:** Deep full semantic analysis.
**Detail:**
- Clone repo → `codegraph init -i` (full build)
- List GitHub issues + open PRs
- LLM classifies each: bug/feature/test/refactor, P0-P3 priority
- For each issue/PR: KG traces relevant code (callers, callees, impact)
- Kanban tasks include: affected files, code snippets, impact analysis summary

### 8. Fix Agent Model
**Decision:** Sequential always (no parallel fix agents).
**Detail:**
- One fix at a time per Run. No git worktrees, no merge complexity.
- Fix agent edits the single workspace directly.
- `git add -A && git commit -m "testai-baseline"` after Phase 1.
- Before each attempt: `git restore . && git clean -fd` (reset to baseline).
- After each attempt: `codegraph sync` (KG always fresh, no worktree issues).
- Rationale: LLM time is the bottleneck, not file I/O. Sequential is what TREX, Qodo, and Greptile do. Eliminates merge conflicts, worktree management, and KG sync complexity.

### 9. Configuration Model
**Decision:** 3 tiers — org-level defaults, per-run overrides, auto-learning.
**Detail:**
- Tier 2 (org defaults in DB/Portal): model per phase, max_agents, escalation rules, notification channels, HITL gates
- Tier 3 (per-run overrides): task_type, model override, max_attempts, budget cap, sandbox image
- Tier 4 (auto-learning): from approvals/rejections, fix results, user feedback (👍/👎)

### 20. LLM Provider Failover
**Decision:** Queue and retry — wait for primary, 3 retries with backoff, then fail the Run.
### 21. Agent Communication Style
**Decision:** Technical and concise. Structured data, code snippets, minimal prose.
### 22. Model Selection
**Decision:** Same model for all agent roles. Simpler configuration. User can override per-Run in Tier 3 settings.
### 27. Per-Repo Config (.testai/)

**Question:** Should repos have a `.testai/` config directory?

**Options:**
1. Yes — `.testai/config.toml` for repo-level overrides (env vars, model, max_attempts)
2. No — all config in dashboard only
3. Auto-detect only — no config files needed

**Decision:** Yes — `.testai/config.toml` for per-repo overrides.
**Scope:** env_vars, ignore_paths, model_override, max_attempts, notification_channels, branch_filter.
**Reasoning:** Every major platform has per-repo config: Greptile (`.greptile/rules`), Qodo (`.pr_agent.toml`), CodeRabbit (`.coderabbit.yaml`), OpenCode (`opencode.json`), Claude Code (`CLAUDE.md`). Config is version-controlled alongside code, shared by the team.

### 26. Question Tool Policy
**Decision:** Restricted — orchestrator must approve, only as last resort after all autonomous options exhausted. Follows Greptile/CodeRabbit pattern: review tools never ask.

### 25. Sandbox Cleanup
**Decision:** Both — explicit container destroy on Run completion + TTL reaper (configurable, default 1hr) for abandoned containers.

### 24. Default Branch Detection
**Decision:** Auto-detect — webhook PR → source branch, issue/manual → default branch. GitHub API for default branch detection.

### 23. Prompt Caching
**Decision:** Cache system prompts + tool definitions automatically. Anthropic/OpenAI prompt caching for ~50% cost savings on multi-turn agents.

### 19. Issue/PR Discovery
**Decision:** ENTER phase pre-fetches issues and PRs via `git_providers.py`. Passed as `repo_context` to the orchestrator. No agent API calls needed.
**Detail:**
- ENTER phase calls `GitHubProvider.list_open_prs()` + `list_open_issues()`
- Results stored in `repo_context` dict: tech_stack, prs[], issues[], files, has_tests
- `repo_context` passed to `orchestrate` tool for LLM decomposition
- Explore agent receives it as context, focuses on KG analysis
- Rate limiting, auth, pagination handled by Python code, not LLM

### 18. Review → Work Feedback Loop
**Decision:** Review rejection sends task back to `ready` with review findings in context. Increments attempt counter. Max 5 total.
**Detail:**
- Review agent rejects → task moves to `ready` (not `blocked`)
- Review agent's findings (changed_files, issues, score) saved on `task_runs` row
- `build_worker_context()` surfaces prior attempt results to the next fix agent
- Fix agent retries with full context of why the review rejected
- Increments `consecutive_failures` counter; at 5 → auto-block
- Only blocks early for security critical or breaking change findings (judge's Phase 2 vote)

### 17. Review Judge Strategy
**Decision:** Combined Qodo-style aggregation + Hermes-style voting.
**Detail:**
- Phase 1 (Qodo): dedup findings, filter noise (<0.5 confidence), resolve conflicts between agents
- Phase 2 (Hermes): voting rules — security critical → fail, avg score >3.5 → pass, <2.5 → fail, 2.5-3.5 → pass with warnings
- Output: verdict, score (0-5), findings list, summary

### 16. Live Run Dashboard
**Decision:** Full live dashboard — phase progress, agent thought stream, tool call timeline, live test results, live kanban, cost meter.
**Detail:**
- Panels (streaming in real-time via SSE):
  - Phase progress bar (ENTER → ANALYZE → SETUP → WORK → REVIEW → PUBLISH → PERSIST)
  - Agent thought stream (💭 reasoning steps, 🔧 tool calls with results)
  - Tool call timeline (timestamps, tool name, duration, success/fail)
  - Live test results (pass/fail/skip counts, coverage %)
  - Live kanban board (tasks updating as they move)
  - Cost meter (token spend per phase, running total)
- References: pipeline-page-wireframe.html (existing panels) + runs-wireframe.html (run history)

### 15. Kanban Patterns (from Hermes Agent)
**Decision:** Adopt 5 Hermes kanban patterns — run-level handoff, comment threads, circuit breaker, DAG decomposition, hallucination gate.
**Detail:**
1. **Run-level handoff**: Each fix attempt creates a `task_runs` row with `summary` + `metadata` (changed_files, tests_run, findings, error). Next attempt reads prior failures. `build_worker_context()` surfaces all prior runs to the next worker.
2. **Comment threads**: `kanban_comment` tool for durable inter-agent communication. Survives crashes, retries, and handoffs. Workers read full thread on spawn. Replaces fragile in-context handoffs.
3. **Circuit breaker**: `consecutive_failures` counter on each task. Cleared only on successful completion. At limit (default: 2 failures for spawn, 5 for fix attempts): task auto-blocks. Already partially in dispatcher (`failure_limit` in config).
4. **DAG-based decomposition**: LLM outputs `parents: [0, 2]` — zero-based indices into its own task list. DB validates the DAG with topological sort (cycle detection). Cleaner than string-based `depends_on: ["title"]`.
5. **Hallucination gate**: `kanban_complete` verifies child task IDs actually exist before allowing completion. Prevents phantom task references from hallucinated LLM output.

### 14. Infrastructure Failure Handling
**Decision:** Queue and retry — 5min intervals for up to 1 hour, then fail.
**Detail:**
- Sandbox creation failure → retry queue (same Run, same params)
- Background retry worker checks every 5 minutes
- Max retry window: 1 hour (12 attempts)
- After 1 hour: mark Run as failed, notify user via configured channel
- Covers: Docker daemon restart, disk space recovery, network blips
- Does NOT cover: permanent failures (invalid config, missing image) — those fail fast

### 13. Test Secrets & Env Vars
**Decision:** Pre-configured per-repo env vars via Settings → Env Vars panel. Sandbox injects them at runtime.
**Detail:**
- Settings → Env Vars already supports per-repo key-value storage
- Sandbox `SandboxScope.env` already injects env vars into containers
- Agent reads env vars from environment at runtime (no special tool needed)
- `credential_scanner.py` prevents secrets from being logged or committed
- Falls back to agent asking user via `question` tool if env var affects test execution

### 12. Phase Timeouts
**Decision:** Very large timeouts — 3.5hrs max per Run.
**Detail:**
| Phase | Timeout | Rationale |
|-------|---------|-----------|
| ENTER | 15 min | Clone large repos, auth, creds |
| ANALYZE | 45 min | codegraph init on 10k+ file repos |
| SETUP | 30 min | npm ci on large monorepos, pip install |
| WORK | 90 min | 5 fix attempts × 10-15min each + heal loops |
| REVIEW | 20 min | Multi-agent review: security, architecture, style, judge |
| PUBLISH | 10 min | git commit, push, PR comment |
| PERSIST | 10 min | codegraph sync, artifact save, metrics log |

### 11. Permission Model
**Decision:** OpenCode-style 3-level (allow/ask/deny) with per-role overrides. Orchestrator auto-approves `ask` for non-risky operations.
**Detail:**
- Three levels: `allow` (run freely), `ask` (orchestrator auto-approves), `deny` (blocked)
- Mode-based tool assignment already defines per-role defaults (`toolsets.py`)
- Orchestrator evaluates tool requests:
  - In allowlist → auto-approve
  - In ask list → orchestrator checks if operation is safe (e.g., `git push` to non-main = safe, `rm -rf` = blocked)
  - Truly risky operations (merge to main, delete data) → escalate to human
  - In deny list → block
- Doom loop detection: same tool called 3x with same input → pause
- Matches opencode permissions model. No complex policy engine needed.

### 10. Dependency & Test Setup
**Decision:** Agent-driven via bash. No hardcoded lookup tables, no runner configs.
**Detail:**
- `CONFIG_HINTS` removed from `tech_stack.py` — not needed, language detection uses enry/scc.
- `runner_configs` DB table and all related code removed — no per-language install/run commands.
- Agent explores repo via bash → detects package manager → installs deps.
- Agent figures out test framework via bash → runs tests.
- If runtime missing (e.g., no Node.js in Python image): `apt-get install nodejs` or `curl ... | bash`.
- Max 2 retries on install failure → skip phase if still failing.
- Matches TREX "no setup required" model and how Tembo delegates entirely to agents.

### 6. Failure Escalation
**Decision:** 5-attempt ladder with classification + multi-channel notification.
**Detail:**
- Attempt 1-2: silent retry with exponential backoff (1s → 2s → 4s)
- Attempt 3: notify orchestrator, task gets "attention" badge
- Attempt 4: Slack/Teams notification + dashboard toast (sonner)
- Attempt 5: mark `blocked`, full failure trail (Slack/Email + dashboard)
- Failure types: transient (retry), flaky (heal), logic (greploop), permanent (block)

## Implementation Order — Final State

```
Phase 1 — Make it work (P0)          ✅ DONE
Phase 2 — Make it autonomous (P1)    ✅ DONE
Phase 3 — Make it observable (P1)    ✅ DONE
Phase 4a — Backend/Core (P2)         ✅ DONE
Phase 4b — UI/Polish (P2)            ❌ NOT IMPLEMENTED (see below)
```

## ❌ Not Implemented — Phase 4b (Deferred)

These features were designed during the 49-question grilling session but not implemented. They don't block the core autonomous flow.

| # | Feature | Reason Deferred |
|---|---------|-----------------|
| 14 | **Custom Dashboard Widgets** — user-configurable drag-and-drop dashboard | UI polish, no backend changes needed |
| 16 | **Coding Standards Rules Engine** — policy-as-code for code review findings | Complex, requires AST integration with kanban rules |
| 17 | **IDE/CLI Tool** — CLI client connecting to backend API for local review | New package, CI/CD, documentation effort |
| 18 | **Ticketing Integration** — OAuth for Jira/Linear to fetch tickets as context | Requires external service OAuth flows |

## Implementation Log

### 2026-06-10 — Phase 4b: Deferred Items Completed

**Auto-resume (kanban-level, Hermes-style):**
- `OrchestratorEngine.resume_abandoned(db)` runs on startup, finds sessions `WHERE status='running' AND heartbeat_at > 5min stale`
- For each: finds kanban board by session ID → re-enters `_wait_for_board` monitoring loop
- Heartbeat updated every 60s during orchestration to prevent false reclaims
- Sessions with no board → marked `failed (abandoned-no-board)`

**L2 Curator evolution loop (SkillClaw-inspired):**
- Background loop (every hour) extends existing `curator.py`
- **Scrape**: queries completed kanban tasks with structured metadata
- **Summarize**: LLM extracts reusable pattern → name, description, category, instructions
- **Aggregate**: checks `skills_index` for duplicates before creating
- **Publish**: writes `SKILL.md` to `.testai/skills/<name>/` + indexes in `skills_index` table
- Reuses existing infra: `recording.py` (session data), `memory_entries` (storage), `curator.py` (directory management)
- Wired into `api/main.py` background loop alongside existing curator

**Cron → Orchestrator wiring:**
- `repo_url` + `branch` columns added to `cron_jobs` table
- `POST /api/admin/cron-jobs` accepts `repo_url` for repo-driven scheduled runs
- `Scheduler._execute_job()` routes to `OrchestratorEngine` when `repo_url` is set

### 2026-06-10 — Phase 4a: P2 Backend/Core Items

**Multi-repo orchestration (P2.11):**
- `OrchestratorEngine.run_multi()` processes repos sequentially — clone → KG → kanban board per repo
- `POST /api/delegate` accepts `repos: [{url, branch, token, depends_on}]` array
- Each repo gets its own kanban board, results aggregated

**Sprint/release tracking (P2.12):**
- `sprint` column added to `kanban_tasks` via migration
- `GET /api/kanban/boards/{id}/tasks?sprint=...` filter
- `GET /api/kanban/boards/{id}/sprints` — distinct sprint values
- Sprint dropdown filter on frontend kanban page

**Clean-up:**
- `rerun_flaky_test` tool removed — unnecessary complexity. `flaky_detector.py` + `flaky_auto_quarantine.py` remain for detection/quarantine.
- `attempt_heal` kept for locator self-healing.

## Architectural Decisions (continued)

### 27. Per-Repo Config (.testai/)
**Question:** Should repos have a `.testai/` config directory?
**Options:** (1) `.testai/config.toml` for repo overrides, (2) dashboard only, (3) auto-detect only
**Decision:** Yes — `.testai/config.toml` (env_vars, ignore_paths, model_override, max_attempts, notification_channels, branch_filter)
**Reasoning:** Every major platform has per-repo config: Greptile (`.greptile/rules`), Qodo (`.pr_agent.toml`), CodeRabbit (`.coderabbit.yaml`). Version-controlled, team-shared.

### 28. No-Package-Manager Repos
**Question:** How does SETUP handle repos with no package manager?
**Options:** (1) Skip SETUP, (2) Agent checks and installs via bash, (3) Universal base image
**Decision:** Agent checks and installs needed tools via bash.
**Reasoning:** Matches decision #10 (agent-driven setup). Agent runs `which python`, installs what's missing.

### 29. Question Tool Policy
**Question:** When should agents ask the user for help?
**Options:** (1) Never, (2) Pre-defined escalation points, (3) Freely
**Decision:** Restricted — orchestrator approves, only as last resort. Greptile/CodeRabbit never ask.
**Reasoning:** Maximum autonomy. Agent exhausts all options before requesting to ask the user.

### 30. Agent Communication Style
**Question:** Technical/concise or conversational/detailed?
**Options:** (1) Technical+concise, (2) Conversational, (3) Configurable
**Decision:** Technical and concise. Code snippets, file paths, minimal prose.
**Reasoning:** Matches senior engineer code review. Less token usage. More actionable.

### 31. Model Selection
**Question:** Different models per agent role?
**Options:** (1) Tiered, (2) Same model for all, (3) Configurable
**Decision:** Same model for all agent roles. Simpler. User can override per-Run.

### 32. Prompt Caching
**Question:** Cache LLM prompts for repeated patterns?
**Options:** (1) Cache system prompts, (2) No caching, (3) Cache KG queries only
**Decision:** Cache system prompts + tool definitions. ~50% cost savings on multi-turn agents.

### 33. LLM Provider Failover
**Question:** Primary model rate-limited or down?
**Options:** (1) Auto-failover, (2) Queue+retry, (3) Fallback cheaper model
**Decision:** Queue and retry primary — 3 retries (30s/60s/120s backoff).
**Reasoning:** Predictable cost. Covers transient outages.

### 34. Default Branch Detection
**Question:** Which branch to use?
**Options:** (1) Default branch, (2) User specifies, (3) Auto-detect
**Decision:** Auto-detect. Webhook PR → source branch. Issue/manual → default branch.

### 35. Sandbox Cleanup
**Question:** Cleanup after failed/abandoned runs?
**Options:** (1) Destroy on completion, (2) TTL reaper only, (3) Both
**Decision:** Both. Explicit destroy on completion + TTL reaper (1hr idle default).

### 36. Webhook Security
**Question:** Verify webhooks are from GitHub?
**Options:** (1) GitHub secret token (HMAC-SHA256), (2) GitHub App JWT, (3) None
**Decision:** GitHub secret token — standard HMAC-SHA256 verification.

### 37. No-Test Repos
**Question:** Handle repos with no existing tests?
**Options:** (1) Skip test step, (2) Generate baseline tests (TREX-style), (3) Prompt user
**Decision:** Generate baseline tests first. ANALYZE detects no tests → TREX-style generation before fix loop.

### 38. Issue/PR Filtering
**Question:** Which issues/PRs should the system process?
**Options:** (1) Open unassigned only, (2) Open including assigned (re-assign if stale), (3) Everything
**Decision:** Open unassigned issues + open PRs only. Skip closed, merged, and assigned. Clean scope, less noise.

### 39. Cross-Run Memory
**Question:** What does the system remember between runs?
**Options:** (1) L1 facts only (KG + run history), (2) L1 + L2 lessons (full learning), (3) Nothing
**Decision:** L1 + L2 — full learning across runs.
**Detail:** L1: KG (`codegraph.db`), run history, `repo_profile` (tech stack, test framework, build commands). L2: curator generates lessons from completed runs ('this test pattern works for this framework'). Reusable across repos in same org.

### 40. Self-Written Skills
**Question:** Should agents create reusable skills from their work?
**Options:** (1) Auto-generate from successful fixes, (2) Curator writes skills from run review, (3) Manually written only
**Decision:** Curator writes skills from completed runs. Background curator reviews fix patterns and creates skills. Agents focus on fixing, not skill-writing.

### 41. Checkpoint & Auto-Resume
**Question:** How does the system resume a crashed Run?
**Options:** (1) Manual restart from checkpoint, (2) Auto-resume with heartbeat detection, (3) Re-run idempotent phases
**Decision:** Auto-resume. Background watcher detects abandoned runs (no heartbeat for 5min) → auto-respawns orchestrator from last checkpoint. User sees "Run auto-resumed" in the UI.

### 42. Error Classification
**Question:** How should errors be classified during the heal loop?
**Options:** (1) Static pattern matching (current), (2) Dynamic LLM-based, (3) No classification — agent figures it out
**Decision:** Dynamic only. Remove static `classify_failure()`. Agent reads raw error output and decides next action via LLM. Matches OpenHands/Greptile pattern. `attempt_heal` kept for locator self-healing.

### 43. Data Retention
**Question:** How long should Run artifacts and logs be retained?
**Options:** (1) Fixed 30d for everything, (2) Tiered (permanent/per-type/7d), (3) User-managed via UI
**Decision:** User-managed via Settings → Data Retention. Settings page already has retention TTL per type (committed tests: permanent, trajectories: 30d, LLM transcripts: 7d). User configures per-org.

### 49. Pipeline Architecture
**Question:** Fixed phases or simpler stages?
**Research:** Greptile TREX = 3 steps (write → run → diagnose). Tembo = delegates entirely to agent. Industry trend is away from formal phases.
**Decision:** 3 stages replacing the 7-phase model:
- **Stage 1: SETUP** — clone repo, build KG, pre-fetch issues/PRs, create kanban board
- **Stage 2: EXECUTE** — kanban dispatcher picks tasks, fix agents run, self-heal + greploop
- **Stage 3: FINALIZE** — review, publish, persist artifacts + lessons

### 48. Event Schema
**Question:** What event types should the orchestrator emit?
**Options:** (1) Phase events only, (2) Phase + agent + kanban, (3) Every tool call
**Decision:** Every tool call. Full observability and replay capability. Existing `PipelineEvent` union type already supports `tool_call` and `tool_result` variants. Powered by existing `stream_events` table.

### 47. Results Delivery & Notifications
**Question:** How does the user get notified when a Run completes?
**Options:** (1) Dashboard only, (2) Dashboard + PR comment, (3) Multi-channel
**Decision:** Multi-channel — dashboard + PR comment + Slack/email. Configured per-repo via Settings → Notification Preferences. Slack/Teams/Telegram/Email adapters already implemented.

### 46. Disaster Recovery
**Question:** How does the system recover from database loss?
**Options:** (1) Standard Postgres backups, (2) Replay from event stream, (3) No recovery — ephemeral
**Decision:** Standard Postgres backups (pg_dump). stream_events table included in backups. Standard DBA practice.

### 45. Cron/Scheduled Runs
**Question:** Should the system support recurring scheduled Runs?
**Options:** (1) Yes — cron syntax in Settings → Cron page, (2) No — manual + webhook only, (3) V2 feature
**Decision:** Yes — cron syntax. Cron page already exists in frontend. Scheduler loop (loop.py) handles execution. Run source column already supports "cron" as a source type.

### 44. Multi-Tenant Isolation
**Question:** How does the system isolate concurrent Runs on different repos?
**Options:** (1) Separate containers + volumes per Run (current), (2) + TTL cleanup, (3) Full Docker compose per Run
**Decision:** Separate Docker containers + named volumes + per-session subnets. Already implemented in SandboxManager and SandboxScope. Max 5 concurrent Runs (from decision #concurrency).

---

## Implementation Log

### 2026-06-10 — Phase 3: Notifications + Frontend Polish

**Notification integration:**
- `OrchestratorEngine._send_notification()` sends Slack/email via DeliveryRouter on completion or failure
- Reads `notification_prefs` table for enabled channels matching `run:completed`/`run:failed` events
- Message includes repo URL, session ID, status summary, and dashboard link

**Frontend polish:**
- **Progress pill** on parent tasks — shows `childrenDone/childrenTotal` with progress bar
- **EventHistory** component in side drawer — last 8 events per task (created, promoted, completed, blocked, decomposed)
- **Parent/child task info** — side drawer shows parent ID and child progress
- **Result summary** — side drawer shows `resultSummary` when available

### 2026-06-10 — Phase 2: Dispatcher Enhancements + Kanban DnD

**Dispatcher auto-decompose (Hermes Auto mode):**
- Dispatcher scans for `triage` tasks every tick, runs `_llm_decompose` on up to 3 per tick
- Original task becomes parent of all children, moves to `backlog`
- Children created with proper DAG dependencies via `kanban_dependencies`
- Config knobs: `auto_decompose` (default true), `decompose_per_tick` (default 3) in board config

**Dispatcher toolset override:**
- Dispatcher reads `toolset_override` from kanban_tasks (set by decomposer's `tools` field)
- Falls back to `_WORKER_BASE_TOOLS` if not set
- `kanban_show`, `kanban_complete`, `kanban_block`, `kanban_heartbeat`, `kanban_comment` always included
- Dynamic system prompt per task showing available tools and agent role

**Kanban Drag-and-Drop:**
- `@dnd-kit/core` + `@dnd-kit/sortable` wired into swimlane view
- `SortableTaskCard` wraps existing `TaskCard` with useSortable
- `onDragEnd` detects target column and calls move mutation
- PointerSensor with 5px activation distance

**Backend API:**
- `POST /api/kanban/tasks/{id}/unblock` — retry blocked tasks
- `sessions` table migration: `repo_url` column added

### 2026-06-10 — OrchestratorEngine + Frontend Dashboard

**Architecture shift:** Removed fixed 3-stage pipeline. Pure kanban-driven model — orchestrator creates sandbox, runs `orchestrate` tool (LLM decomposes goal into DAG tasks), then polls for completion. Kanban dispatcher handles all execution.

**Backend — Hermes-style Kanban Decomposer:**
- `_llm_decompose` prompt uses zero-based `parents` indices (DAG refs, not string titles)
- DAG validation via topological sort (cycle detection, falls back to sequential)
- Swarm topology: parallel workers → verifier (gated on all) → synthesizer (gated on verifier)
- Kanban Swarm pattern (P1 Fan-out + P2 Pipeline): N fix agents in parallel, test verifier after all finish, publisher after tests pass

**Backend — OrchestratorEngine (`stages/__init__.py`):**
- `OrchestratorEngine.run(run_id, session_id, repo_url, goal)` → clone repo → build KG → `orchestrate` tool → poll `orchestrate_monitor` → return results
- Wired into `POST /api/delegate` with `repo_url` + `branch` fields
- Sessions table got `repo_url` column (migration) and API returns it

**Backend — Kanban enhancements:**
- `POST /api/kanban/tasks/{id}/unblock` endpoint for retrying blocked tasks
- `kanban_complete` now accepts `summary` + `metadata` structured handoff (Hermes run-level handoff)

**Frontend — Pipeline Page (`/pipeline`):**
- Pipeline mode toggle: "Quick Test" (existing) vs "Orchestrate" (repo-driven)
- Repo URL input with `https://github.com/owner/repo` format support
- `StageProgress` component — 3 stages (Setup → Execute → Finalize) with spring animations
- `ToolCallTimeline` — live tool call feed with timestamps and durations

**Frontend — Dashboard (`/dashboard`):**
- `ActiveOrchestrationsCard` — last 5 repo sessions with reconnect, auto-refresh 15s
- `BlockedTasksCard` — blocked kanban tasks with failure count + Retry button, auto-refresh 30s

**Frontend — Kanban Page (`/kanban`):**
- Tasks and stats auto-refresh every 10s via `refetchInterval`

### 2026-06-09 — Surgical clean-up before building OrchestratorEngine

| # | What | Why | Status |
|---|------|-----|--------|
| 1 | `tools/kg_generator.py` | Deprecated — CodeGraph replaces it | ✅ Deleted |
| 2 | `tech_stack.py` CONFIG_HINTS | Agent-driven setup, no hardcoded hints needed | ✅ Removed |
| 3 | `pr_auto_fix.py` classify_failure() | Static pattern matching replaced by dynamic LLM classification | ✅ Removed |
| 4 | `pr_manager.py` classify_failure import | Updated to remove reference | ✅ Fixed |
| 5 | `database.py` seed/get_runner_configs | Runner configs removed — agent handles setup via bash | ✅ Removed |
| 6 | `admin.py` runner_configs reference | Language/framework detection simplified to agent-driven | ✅ Fixed |
| 7 | `settings.py` runner CRUD endpoints | No longer needed | ✅ Removed |
| 8 | `test_executor.py` | Agent uses bash directly, no executor tool needed | ✅ Removed |
| 9 | `schema.sql` — added `artifacts` table | Missing table — PostgresArtifactStore depended on it | ✅ Added |
| 10 | `store/adapters/postgres.py` — reverted PostgresKnowledgeGraphStore | Unnecessary — CodeGraph SQLite handles all KG needs | ✅ Reverted |
| 11 | `schema.sql` — removed kg_nodes/kg_edges tables | Reverted with PostgresKnowledgeGraphStore | ✅ Removed |
| 12 | `store/registry.py` — reverted KG store wiring | CodeGraph SQLite is the KG source of truth | ✅ Reverted |
| 13 | `pr_webhook.py` — added HMAC for GitHub + GitLab | GitHub webhook secretly verified (official Python example matches) | ✅ Done |
| 14 | `pr_webhook.py` — Bitbucket HMAC reverted | Bitbucket Cloud doesn't use HMAC — no signature header | ✅ Fixed |
| 15 | `RunnerConfigManager.tsx` + `RunnersPanel.tsx` | Frontend panels for removed runner configs | ✅ Deprecated |

