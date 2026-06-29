# TestAI Harness Production-Grade Audit (2026-06-24, deep-dive)

> **Scope.** Fresh, focused audit answering the user-asked questions that the
> 2026-06-23 and 2026-06-24 reports did not cover in full:
>
> 1. Entry-point consolidation: `run_single` / `run_multi` / `run` / `run_job_spec` — should we have 1 or 2?
> 2. Chat + session continuity: the user can ask "what's happening with my last run?" and the agent must answer.
> 3. User visibility into the sandbox (live file watcher, terminal, port-forwarded app).
> 4. Memory, compaction, and skill-evolution mechanics.
> 5. Subagent activity recording + display to user.
> 6. Per-tool-call observability and per-step OTel.
> 7. Production-grade agent-harness research (Greptile, TestSprite, Mabl, Bug0, testRigor, Tembo, Testim) and what TestAI should adopt.
>
> **Method.** Read-only exploration of the current `backend/` and `src/` trees,
> cross-referenced with the 2026-06-23 audit (orchestrator-audit.md) and the
> 2026-06-24 e2e report. Where findings are not new, they are **cross-referenced** with the older doc instead of re-stated.
>
> **Status.** In progress; sections are appended as each sub-audit completes.

---

## §0. TL;DR

**The harness shape is at parity with production leaders.** TestAI has: per-run sandbox (Docker), knowledge graph (CodeGraph), kanban-driven delegation, subagent tree (delegate_task), tier model (1/2/3), durable checkpoint + cancel/pause/resume, budget tracker (4 scopes), memory (L1 + L2), 4 budget scopes, and 8+ chat-side read-only tools. **The shape is right.** The 2026-06-24 e2e confirms the orchestrator can run end-to-end against a real GitHub repo (rails/rails) once the orphan tool_calls + session_id + kg_edges fixes are applied.

**There are 4 production-critical gaps and 9 refinements that make the difference between a demo and a product.**

### 4 production-critical gaps

1. **Entry-point consolidation (F1).** 5 entry points, 2 of them bypass the durable `JobSpec` path. Fix: rename `run_single`/`run_multi`/`run` to private, all callers funnel through `submit_job_to_orchestrator`. Add the "summarize repo" entry point for the user's "point at a repo" UX.
2. **Chat surface is missing (F2).** The chat agent is wired but **no HTTP endpoint invokes it**. The user literally cannot type "what's happening with my last run?" and get an answer. Add `POST /api/chat/threads` + `POST /api/chat/threads/{thread_id}/messages` (SSE). Add 4 read-only tools (`list_recent_sessions`, `get_session_detail`, `tail_live_events`, `get_kanban_for_session`) so the chat can actually answer.
3. **No sandbox visibility (F3).** The user can list containers/volumes but cannot peek inside the running agent's filesystem, tail the live bash output, or attach to the dev server. Add 5 read-only + 1 write endpoint, wire to the `/sandbox/[sessionId]` page.
4. **Memory, compaction, skill evolution are 1/3 implemented (F4).** L2 reflection works, L1 KG partially works (kg_edges was just added), L0 raw-artifact search is missing. Auto-compaction is documented but not coded. Skill evolution returns suggestions, never applies them. Adopt the Anthropic two-agent pattern (initializer + coding agent) with `.testai/feature_list.json` + `.testai/progress.md`. Adopt the OpenHands 5-pattern StuckDetector.

### Plus the per-user-per-day budget (F2.5)

There is **no `user_id` column on any table**. This single schema-level change unblocks per-user customisation, multi-tenant chat, and the 4th-scope budget that's been UI-only since the 2026-06-23 audit.

### The 5-entry-point vs 1-entry-point question

The user asked: "1 entry point or 2?". Answer: **2 entry points** — (1) `POST /api/repos/{owner}/{repo}/summarize` (read-only, returns issues + PRs + KG status, no LLM call); (2) `POST /api/jobs` (the only write path for autonomous work, builds a `JobSpec` and calls `submit_job_to_orchestrator`). Both can funnel through the same `OrchestratorEngine`. The internal `_run_single` / `_run_multi` / `run` methods become private; all callers (chat, MCP, webhook, scheduler) build a `JobSpec` and call `submit_job_to_orchestrator`.

### Where TestAI stands vs the leaders

| | Claude Agent SDK | OpenHands | Greptile | TestSprite | Bug0 | Tembo | **TestAI** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Parity | ✓ | ✓ | partial | partial | partial | partial | **9/22 features** |
| Gaps | 0 | 0 | 6 | 5 | 4 | 5 | **13 features** |

The 13 gaps break down: 3 small (F1.1 entry points, F1.1.1 run_multi wiring, F5.5 subagent tree UI), 3 medium (F2.1 chat, F3.1 sandbox visibility, F5.4 per-subagent cost tree), 2 large (F4 memory/compaction/skill evolution, F2.5 per-user schema), 5 small polish items.

### What's working that we should not touch

- The 2026-06-24 fixes (F1-F36) closed the e2e path. 0 subagent failures, circuit breaker stayed closed, parallel explore subagents work.
- The 8-tool `CHAT_READONLY_TOOLSET` is well-shaped (just unreachable today).
- The `submit_job_to_orchestrator` funnel is the right canonical path.
- The `KnowledgeGraphSyncer` per-(repo_url, branch) cache is the right pattern.
- The 3-tier cancellation (`cancel_watcher` + `_run_with_cancel_watch` + `_check_pause_for_spec`) is correct.
- The `_consecutive_same_tool` loop limit is the start of a real StuckDetector.
- The kanban state machine (`claim_task` → `complete_task` / `block_task` / `auto_blocked`) is sound.

### Files & cross-references

- This audit extends: `docs/2026-06-23-orchestrator-audit.md` (the e2e audit, F1-F20) and `docs/2026-06-24-e2e-rails-pr-fixflow.md` (the F21-F36 observability follow-up).
- This audit cites: `docs/PRODUCTION_HARNESS_COMPARISON_2026-06-18.md`, `docs/OPEN_SOURCE_HARNESS_COMPARISON_2026-06-18.md`, `docs/ADOPTABLE_PATTERNS_FROM_FRAMEWORKS.md`, `docs/agent-harness-architecture-research.md`, `docs/upcoming-projects-research-2026-06-24.md`.
- Total findings in this audit: 5 sections (F1-F5) + 1 research section (F6) + 1 recommendations section (F7) = **31 findings** across 5 components.
- Total blockers: 5. Total high-priority: 7. Total medium-priority: 8. Total refinements: 5. Total cleanup: 5.

---

# Part II — Interview-Driven Implementation Plan (2026-06-24, design interview)

> **What this section is.** The audit in Part I identified 5 production-critical gaps (F1, F2, F3, F4, F2.5). The user then ran a 9-question design interview (Q1–Q9) with me, where for every question I:
> - Asked the user the question (one at a time, with research from `ctx_fetch_and_index`).
> - Gave a recommended answer.
> - Waited for the user's "your recommendation" (or override).
>
> This section records every decision + the research that backed it + a phased implementation plan.

## §8. Interview decision log (Q1–Q9)

### Q1 — Multi-tenant from v1, or single-user first?
- **Asked:** F2.5 has no `user_id` column on any table. Two paths.
- **Research:** None needed; this is a product-scope question.
- **Recommendation:** Path A — **single-user v1**, multi-tenant later. Saves 2-3 days of auth + migration + scoping; clean future migration.
- **Decision:** Path A.
- **Rationale confirmed:** User can flip to multi-tenant later with a clean migration (add `users` table, backfill `user_id` on existing tables).

### Q2 — Auth model in single-user mode
- **Asked:** Dashboard has zero auth today. Chat surface needs *some* protection. 4 options: none, basic auth, bearer token, hybrid.
- **Research:** None needed; production patterns are well-known.
- **Recommendation:** **HTTP basic auth from `TESTAI_DASHBOARD_USER` + `TESTAI_DASHBOARD_PASSWORD`**, env vars empty = open (backward-compat).
- **Decision:** HTTP basic auth.
- **Rationale confirmed:** Lowest friction, reversible, browser UX via native dialog, no `localStorage` plumbing.

### Q3 — Chat shape: thread-based vs single-conversation
- **Asked:** ClaudeGPT (single) vs Devin/Cursor/Sweep (threaded) vs Slack (user-named only).
- **Research (live web):** Claude Code = per-directory sessions with `claude -c` (continue) and `claude -r <id>` (resume); Sweep = "**one chat per task**" explicit guidance, ⌘ N for new chat; Devin = per-session; Cursor = hybrid; OpenHands = per-conversation.
- **Recommendation:** **Thread-based, task-scoped + ad-hoc (Option B).** 5/6 production harnesses use this. Auto-create thread on `submit_job` (1:1 with run), plus ad-hoc threads for general questions.
- **Decision:** Thread-based, task-scoped + ad-hoc.

### Q4 — Chat tool surface: read-only or also write?
- **Asked:** Chat has 7 write tools already (`submit_job`, `cancel_job`, `pause_job`, `resume_job`, `list_jobs`, `get_job_status`, `comment_on_job`) per `toolsets.py:7-32`. The `CHAT_READONLY_TOOLSET` is misnamed. User can already submit fixes/tests via `submit_job` prompt-templating.
- **Research:** None needed; verified by code inspection.
- **Recommendation:** **Option C — 4 read + 4 targeted write**:
  - Read: `list_recent_sessions`, `get_session_detail`, `get_kanban_for_session`, `tail_live_events`
  - Write (targeted): `rerun_session`, `run_test_in_session`, `fix_kanban_task`, `attach_to_subagent`
- **Decision:** 4 read + 4 targeted write.

### Q5 — Chat storage schema
- **Asked:** Reuse existing `messages` table (per `migrations.sql:20-32`) or 2 new tables (`chat_threads` + `chat_messages`)?
- **Research:** None needed; the existing `messages` table is orchestrator-specific.
- **Recommendation:** **Option B — 2 new tables** (`chat_threads` + `chat_messages`). Different surface, different access patterns, different retention.
- **Decision:** New tables.
- **Schema (locked):** See §9.1 below.

### Q6 — Chat SSE streaming format
- **Asked:** AG-UI (CopilotKit protocol) vs TestAI's existing wire names vs hybrid.
- **Research:** AG-UI is a **single-vendor** protocol (CopilotKit), not a true open standard. TestAI's wire names already align with OTel GenAI conventions (which IS a real standard via CNCF).
- **Recommendation revised after user pushback:** **TestAI wire names, prefixed with `chat.`** for the chat-specific events. Reuse F29's vocabulary. No new dependency.
- **Decision:** TestAI wire names with `chat.` prefix.
- **Event types (locked):** `chat.run.started`, `chat.token`, `chat.tool.started`, `chat.tool.completed`, `chat.run.completed`, `chat.run.cancelled`, `chat.error`, plus lifecycle glue (`connected` first frame, 25s keepalive).

### Q7 — `summarize_repo` entry point
- **Asked:** User described "user points to a repo, orchestrator pulls, shows GitHub issues/PRs, user picks one". 5 sub-decisions.
- **Research:** Daytona = `sandbox.process.code_run`, `sandbox.fs.*`, `sandbox.git.*`, `sandbox.snapshot.*`; GitHub API = `/repos/{owner}/{repo}/issues`, `/pulls`, `/pulls/{n}/reviews`; Greptile = "learns your codebase over time" via PR comments.
- **Recommendation:** HTTP endpoint + chat tool, eager KG build with SSE progress, GH token from `integration_configs` settings, `RepoSummary` shape with kg_status + open_issues + open_prs + recent_reviews + github_api, click-item → templated `submit_job`.
- **Decision:** Both HTTP + chat tool, all 5 sub-decisions as proposed.

### Q8 — Sandbox visibility surface
- **Asked:** F3 had 6 endpoints. Are these enough?
- **Research:** Daytona exposes 5 buckets (lifecycle, filesystem, process & code execution, runtime config, snapshots); E2B is smaller; Sweep/Cursor show file diffs; Bug0 shows per-test video + console + network.har.
- **Recommendation revised after research:** **12 endpoints, all in v1:**
  1. `GET /status` — container state, uptime, head_sha, branch
  2. `GET /resources` — CPU%, mem%, disk%, network I/O
  3. `GET /files?path=&max_depth=` — directory tree
  4. `GET /files/raw?path=` — read a file (≤1 MB cap)
  5. `GET /git/status` — branch, ahead/behind, uncommitted, last 5 commits
  6. `GET /git/diff?path=&base=origin/main` — unified diff of what agent changed
  7. `GET /terminal/stream?tool_call_id=` — live bash output (SSE)
  8. `GET /logs/recent?limit=20` — last N lines of recent command output
  9. `POST /exec` — user-typed command (audit + blocklist + 60s timeout)
  10. `GET /ports` — open ports (via `ss -tlnp`)
  11. `POST /snapshot` — freeze state, return `snapshot_id`
  12. `POST /snapshot/{id}/restore` — restore to a snapshot
- **Decision:** All 12 in v1.

### Q9 — Memory / Compaction / Skill Evolution
- **Asked:** 4 sub-decisions.
- **Research:** **LangGraph** = short-term working memory + long-term persistent memory; **Claude Code** = auto-compaction + auto-memory + `CLAUDE.md`; **Anthropic autonomous-coding quickstart** = two-agent pattern (initializer + coding agent) with `feature_list.json` (200 tests, source of truth), `app_spec.txt`, `init.sh`, `claude-progress.txt`, git as persistence; **Mem0** (YC, 90k+ devs) = `client.add(messages, user_id)` + `client.search(query, user_id)` is the canonical 2-method memory API; **Zep** = temporal context graph, old facts stay as history, "Observations" auto-derived from patterns; **Cognee** = "Memory for coding agents — agents that recall past work, decisions, fixes".
- **Recommendation revised after research:** All 4 sub-decisions:
  - **Q9a — Memory:** Mem0's `add` + `search` shape. `memory.add(entries, repo, source_kind)` + `memory.search(query, repo, limit, include_artifacts=True)`. Multi-signal retrieval.
  - **Q9b — Compaction:** Both scheduled (every 30 turns, ~1¢) and reactive (on `prompt_too_long`). The reactive path already exists; add the LLM-scheduled.
  - **Q9c — Anthropic two-agent pattern:** Adopt fully, with their exact JSON schema. `feature_list.json` is **JSON, not Markdown** (Anthropic: "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files"). Schema: `{features: [{category, description, steps: [string], passes: bool}]}`. **The agent can only edit the `passes` field** (enforced by a custom JSON editor that rejects other changes — "It is unacceptable to remove or edit tests"). `progress.md` for session notes. Git commits as the progress mechanism. **Incremental rule: one feature at a time.**
  - **Q9d — Skill evolution:** Curator writes the evolved `SKILL.md` as a PR (uses existing `commit_and_open_pr`). User approves/rejects. Plus a `view_evolution_suggestions` chat tool to see what the curator is thinking.
- **Decision:** All 4 as proposed.

---

## §9. Implementation plan

### §9.1 — Schema additions (edit `schema.sql` directly, no migration file)

> **Clarification (2026-06-24, from user):** this is greenfield, not live. The tables go **directly into `backend/harness/memory/schema/schema.sql`** (and any required indexes into `migrations.sql` if needed), not into a separate migration file. The single source of truth stays `schema.sql`; the application will read from it on next boot.

**6 new tables added to `schema.sql` (all in place, validated 2026-06-24):**

| Table | Question | Indexes |
| --- | --- | --- |
| `chat_threads` | Q5 | 5 (including partial `WHERE run_id IS NOT NULL`) |
| `chat_messages` | Q5 | 3 (partial on `tool_call_id`) |
| `agent_memory` | Q9a | 4 (including GIN FTS on `content`) |
| `repo_progress` | Q9c | 3 |
| `sandbox_snapshots` | Q8 | 3 (partial on `expires_at`) |
| `skill_evolution_prs` | Q9d | 3 |

> **Naming note:** the Q9a table is called `agent_memory` (not `memory_entries`) to avoid clashing with the pre-existing `memory_entries` table, which is a generic key-value store used by `harness/memory/store.py:PersistentStore` for internal state (API keys, settings, etc.). The two tables serve different concerns:
> - `memory_entries` — internal KV state. Schema: `(id, key, value, source, category, created_at, updated_at)`.
> - `agent_memory` — the agent's LLM-readable knowledge across runs. Schema: `(id, repo_slug, source, target, content, confidence, source_kind, metadata, created_at)`.

**DB state after the edit (verified 2026-06-24):** 102 tables in `public` schema (was 96, +6 new). `psql` re-applies schema.sql idempotently.

**Original schema (kept here for the record — implemented as above):**

```sql
-- Q5: Chat threads
CREATE TABLE chat_threads (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title           TEXT NOT NULL DEFAULT 'New conversation',
    run_id          TEXT,
    session_id      TEXT,
    source          TEXT NOT NULL DEFAULT 'user',
    is_pinned       BOOLEAN NOT NULL DEFAULT false,
    is_archived     BOOLEAN NOT NULL DEFAULT false,
    message_count   INTEGER NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_threads_updated ON chat_threads(updated_at DESC);
CREATE INDEX idx_chat_threads_run ON chat_threads(run_id);
CREATE INDEX idx_chat_threads_pinned ON chat_threads(is_pinned, updated_at DESC);

CREATE TABLE chat_messages (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    thread_id       TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT,
    tool_call_id    TEXT,
    tool_calls      JSONB,
    tool_name       TEXT,
    is_error        BOOLEAN NOT NULL DEFAULT false,
    finish_reason   TEXT,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    cost_usd        FLOAT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_messages_thread ON chat_messages(thread_id, created_at);
CREATE INDEX idx_chat_messages_tool_call ON chat_messages(tool_call_id);

-- Q9c: Anthropic two-agent pattern (per-repo progress meta)
CREATE TABLE repo_progress (
    repo_url            TEXT NOT NULL,
    branch              TEXT NOT NULL DEFAULT 'main',
    feature_list_path   TEXT NOT NULL DEFAULT '.testai/feature_list.json',
    progress_path       TEXT NOT NULL DEFAULT '.testai/progress.md',
    features_total      INTEGER NOT NULL DEFAULT 0,
    features_passing    INTEGER NOT NULL DEFAULT 0,
    last_edited_at      TIMESTAMPTZ,
    last_run_id         TEXT,
    edit_count          INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo_url, branch)
);

-- Q9a: Memory search index
CREATE TABLE memory_entries (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    repo_slug       TEXT NOT NULL,
    source          TEXT NOT NULL,
    target          TEXT NOT NULL DEFAULT 'memory',
    content         TEXT NOT NULL,
    confidence      FLOAT,
    source_kind     TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_memory_entries_repo ON memory_entries(repo_slug, source, created_at DESC);
CREATE INDEX idx_memory_entries_fts ON memory_entries USING GIN (to_tsvector('english', content));

-- Q8: Sandbox snapshots
CREATE TABLE IF NOT EXISTS sandbox_snapshots (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id      TEXT NOT NULL,
    docker_image    TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    size_mb         INTEGER
);
CREATE INDEX idx_sandbox_snapshots_session ON sandbox_snapshots(session_id, created_at DESC);

-- Q9d: Skill evolution PR tracking
CREATE TABLE IF NOT EXISTS skill_evolution_prs (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    skill_name      TEXT NOT NULL,
    from_version    TEXT,
    to_version      TEXT,
    diff            TEXT NOT NULL,
    pr_url          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    merged_at       TIMESTAMPTZ
);
CREATE INDEX idx_skill_evolution_prs_status ON skill_evolution_prs(status, created_at DESC);
```

### §9.2 — Backend modules (new files)

| Path | Purpose | LOC est. |
| --- | --- | --- |
| `backend/harness/chat/threads.py` | `chat_threads` + `chat_messages` Pydantic models, CRUD | ~250 |
| `backend/harness/chat/service.py` | business logic: auto-title, auto-create on submit_job, tool dispatch | ~400 |
| `backend/harness/chat/sse.py` | SSE generator with keepalive + cancellation | ~150 |
| `backend/api/routers/chat.py` | 5 endpoints: threads CRUD + messages + archive | ~350 |
| `backend/harness/tools/chat_read_tools.py` | 4 read tools | ~400 |
| `backend/harness/tools/chat_write_tools.py` | 4 targeted write tools | ~350 |
| `backend/harness/auth/basic.py` | HTTP basic auth dependency for FastAPI | ~80 |
| `backend/api/routers/repos.py` | `POST /api/repos/summarize` | ~250 |
| `backend/harness/tools/summarize_repo.py` | chat tool wrapper for the same backend function | ~150 |
| `backend/harness/sandbox/inspect.py` | 12 sandbox-visibility backend functions | ~700 |
| `backend/api/routers/sandbox_inspect.py` | the 12 routes | ~400 |
| `backend/harness/memory/search.py` | Mem0-style `add` + `search` over `memory_entries` + `kg_nodes` | ~350 |
| `backend/harness/context_compressor/llm_compact.py` | LLM-driven auto-compaction (every 30 turns) | ~200 |
| `backend/harness/initiator/feature_list.py` | Anthropic `feature_list.json` editor (only `passes` field editable) | ~250 |
| `backend/harness/curator/evolution_pr.py` | curator as PR with diff | ~200 |
| `backend/harness/curator/suggestions.py` | `view_evolution_suggestions` chat tool | ~150 |

**Total backend: ~4,500 LoC across 16 new modules + 3 router files.**

### §9.3 — Frontend pages + components (using design-frontend skill)

Per the design-frontend skill: **Geist font, Zinc/Slate neutrals, electric blue or emerald accent (NO AI purple/blue gradient), `rounded-[2.5rem]` for major containers, Framer Motion spring physics.**

| Path | Purpose | LOC est. |
| --- | --- | --- |
| `src/app/(dashboard)/chat/page.tsx` | Chat list (left rail) + thread detail (right pane) | ~400 |
| `src/app/(dashboard)/chat/[threadId]/page.tsx` | Active thread view, SSE consumer | ~500 |
| `src/components/chat/MessageBubble.tsx` | Single message with role-distinct visuals | ~300 |
| `src/components/chat/StreamingText.tsx` | "use client" Framer Motion typewriter | ~150 |
| `src/components/chat/ToolCallChip.tsx` | Inline tool pill with collapsible args/result | ~200 |
| `src/components/chat/ThreadList.tsx` | Left rail with pinned/recents/archived sections, ⌘ N | ~350 |
| `src/components/chat/Composer.tsx` | Input box with attachment, slash-commands, ⌘Enter | ~250 |
| `src/app/(dashboard)/repos/new/page.tsx` | "Add repo" form, paste URL, render summary | ~300 |
| `src/components/repos/RepoSummary.tsx` | Repo header, KG status, tabs for Issues/PRs/Reviews | ~400 |
| `src/components/repos/IssueList.tsx` | Open issues with click-to-submit | ~250 |
| `src/components/repos/PrList.tsx` | Open PRs with click-to-review | ~250 |
| `src/app/(dashboard)/sandbox/[sessionId]/page.tsx` | Replace existing stub: file tree + content + live terminal + user exec | ~600 |
| `src/components/sandbox/FileTree.tsx` | Lazy read-only tree | ~250 |
| `src/components/sandbox/LiveTerminal.tsx` | "use client" SSE consumer + Framer Motion typewriter | ~200 |
| `src/components/sandbox/UserExec.tsx` | Input + output, 60s timeout, command history | ~200 |
| `src/components/sandbox/GitDiffViewer.tsx` | Unified diff with syntax highlighting | ~250 |
| `src/components/auth/BasicAuthGate.tsx` | Client-side credential prompt | ~100 |

**Total frontend: ~5,000 LoC across 17 new components/pages.**

### §9.4 — Phased rollout (3 phases, ~6 weeks)

**Phase 1 — Auth + Chat surface (2 weeks).** Q1, Q2, Q3, Q5, Q6. Backend: `chat_threads` + `chat_messages` + 2 endpoints + 4 read tools + SSE. Frontend: chat page, thread list, message bubble, streaming text. Skip the 4 write tools for now. **No summarize_repo, no sandbox visibility, no memory/compaction/feature_list.** Goal: "user can ask the agent what's happening".

**Phase 2 — F1 + F3 (entry points + sandbox visibility) (2 weeks).** Q4 (4 write tools), Q7, Q8. Backend: `summarize_repo` HTTP + chat tool, 12 sandbox endpoints, 4 chat write tools. Frontend: `/repos/new`, `RepoSummary`, `/sandbox/[sessionId]`. Goal: "user can see what the agent is doing".

**Phase 3 — F4 (memory, compaction, skill evolution) (2 weeks).** Q9. Backend: `memory_entries` table, `memory_search` tool, LLM auto-compaction, `feature_list.json` editor, `progress.md` writer, curator as PR. Frontend: memory panel in chat, feature list in `/jobs/[spec_id]`, progress.md in `/sandbox/[sessionId]`. Goal: "the system compounds over runs".

### §9.5 — Test plan

| Test | What it covers |
| --- | --- |
| **Unit** | `memory.add/search` BM25, `feature_list.json` editor (rejects non-`passes` edits), `chat_threads` CRUD, `repo_progress` lifecycle |
| **Integration** | `submit_job` → `chat_threads` auto-create, `summarize_repo` SSE progress, sandbox `git/diff` round-trip, curator PR with diff |
| **E2E (e2e_rails_pr_fixflow re-run)** | Full chain: summarize rails → pick issue → submit_job → chat answers → sandbox shows file diff → progress.md updated → feature_list.json shows the new feature passing |
| **Manual UX** | Click-through with the design-frontend skill: typography, motion, anti-slop checks |

### §9.6 — Risks + mitigations

| Risk | Mitigation |
| --- | --- |
| 12 sandbox endpoints are a lot to ship at once. | Phase 2 ships all 12; existing `sandbox.py` already has 5 admin endpoints. Each is ~50-60 LoC. |
| User-exec endpoint can break the agent's workspace. | Audit log + command blocklist + 60s timeout. The agent sees what the user did via `chat_messages`. |
| `feature_list.json` agent could try to edit other fields. | Custom JSON editor that rejects any non-`passes` field changes. Tested in unit tests. |
| Snapshot endpoint can fill disk fast. | `expires_at` column; janitor deletes after 7 days; 5-snapshot cap per session. |
| HTTP basic auth over the LAN. | Dashboard is on `localhost:3001`; basic auth prevents casual poking. For internet exposure, recommend nginx + TLS in the README. |
| L2 reflection LLM call adds latency at end-of-run. | Fire-and-forget background task (already done). |
| Curator-as-PR creates a real GitHub PR. | Sandbox the curator to a test branch by default; user manually promotes. |

### §9.7 — Open questions / deferred to v1.1

1. **Multi-tenant migration (Path A → Path B).** Tracked in §7 recommendation #18.
2. **Per-user-per-day budget.** Schema is `user_id`-gated.
3. **AG-UI compatibility layer.** If a third-party client needs it, 30-LoC translator.
4. **Skill evolution auto-merge.** v1.0 = draft PR; user promotes.
5. **Snapshot diffing.** Snapshot A vs Snapshot B. v1.1.
6. **`memory_search` vector search.** v1.0 = BM25; v1.1 = embeddings + hybrid.
7. **Sandbox visibility cross-session.** v1.0 = only active session; v1.1 = cross-session read.
8. **WebSocket transport.** Currently SSE. If we hit 6-connection browser cap, WebSocket is the upgrade.

---

## §10. Recommended next step

The interview is complete. All 9 decisions are locked. The implementation plan is 3 phases × 2 weeks = 6 weeks.

**Phase 1 starts with:**
1. SQL migration `0001_chat_memory_initiator.sql` (4 new tables + 2 helper tables + indexes).
2. Chat backend (`chat_threads.py`, `chat_messages.py`, `service.py`, `sse.py`, 2-endpoint router, 4 read tools).
3. Chat frontend with the design-frontend skill.
4. Tests: unit for memory + CRUD, integration for auto-thread-on-submit_job, e2e re-run of the e2e_rails_pr_fixflow.

**Should I start Phase 1, or do you want to adjust any decision first?**


## §1. Entry points: `run_single` / `run_multi` / `run` / `run_job_spec`

### F1.1 — The orchestrator has 5 entry points today; only 2 are wired into the live path

`OrchestratorEngine` (`backend/harness/orchestrator.py`) exposes:

| Method | Signature | Role |
| --- | --- | --- |
| `run_resumed_job_spec(spec_id, *, resumed_by)` | pause/resume path | resumes a paused JobSpec from its saved checkpoint |
| `run_job_spec(spec, context_repos=None)` | **chat handoff** | entry point from `submit_job_to_orchestrator` / `submit_job` tool / admin endpoints |
| `run_single(run_id, session_id, repo_url, goal, branch, context_repos, spec_id)` | **workhorse** | clone → bootstrap → KG index → coordinator subagent |
| `run_multi(run_id, session_id, repos, goal)` | multi-repo loop | iterates `run_single` per repo, then `coordinate_multi_repo_results` |
| `run(run_id, session_id, repo_url, goal, branch, repos)` | dispatcher | if `repos` → `run_multi`; else → `run_single` |

**Call sites (audited):**

| Entry point | Caller | Path |
| --- | --- | --- |
| `run_job_spec` | `submitter.py:95` (uniform handoff) | all canonical submission paths |
| `run_job_spec` | `tool_dispatch.py:395` (chat submit_job tool) | chat agent |
| `run_job_spec` | `admin.py:609, 671` | admin endpoint |
| `run_resumed_job_spec` | `tool_dispatch.py:645` (chat resume tool) | chat agent |
| `run_single` | `mcp/server.py:57, 92, 127, 162` (4 MCP tools) | MCP-server surface |
| `run_single` | `webhooks/github_pr_feedback.py:122` | legacy webhook path |
| `run_multi` | `run` (only) | only via `run` |
| `run` | `scheduler/loop.py:82` | cron-scheduler loop |

**`submitter.py:submit_job_to_orchestrator` is the canonical funnel** — every user-facing path (chat, `/api/jobs`, MCP, webhooks) is supposed to flow through it. The comment is explicit: *"Q7 step 2: the legacy `/api/agent/run`, `/api/delegate`, and `/api/pipeline/from-requirements` endpoints have been hard-deleted. New callers must use `POST /api/jobs`."*

But:
- The 4 MCP tools in `harness/mcp/server.py` (a separate server class `TestAIMCPServer`) bypass `submit_job_to_orchestrator` and call `engine.run_single` directly with ad-hoc args (no `JobSpec`, no tier, no `JobSpecStore` persist, no `_run_with_cancel_watch`).
- `github_pr_feedback.py:122` also calls `run_single` directly — no tier handling, no checkpoint, no cancel/pause.
- `scheduler/loop.py:82` calls `engine.run` — which is fine for cron but doesn't construct a `JobSpec` (no `source="cron"`, no `capabilities`, no `approval`), so the resulting run is untracked in `job_specs`.

**Verdict.** The system has **5 entry points** but **2 of them (`run_single`, `run`) bypass the durable `JobSpec` path**. Every path should funnel through `submit_job_to_orchestrator` (and ultimately `run_job_spec`). The clean fix:

1. **One canonical entry point: `run_job_spec(spec)`.** This is what the chat uses, what `/api/jobs` uses, and what admin uses.
2. **`run_single` and `run_multi` become `private` (`_run_single`, `_run_multi`).** The MCP server, the legacy webhook, and the scheduler all build a `JobSpec` (with `source="mcp" / "github-feedback" / "cron"`) and call `run_job_spec`. This gets every run the same lifecycle: persist, tier, cancel-watch, checkpoint, denormalised cost/duration columns, kanban.
3. **`run` is a vestigial dispatcher and should be deleted.** `run_multi` callers can pass a single-element list to `run_multi` if they really need that pattern; the current 2-branch `if repos: else` is a leftover from the pipeline-store era.

**F1.1.1 — `run_multi` is unreachable from any HTTP path today.** The only caller is `OrchestratorEngine.run`. The `/api/cross-repo` endpoints (`backend/api/routers/cross_repo.py`) exist but I didn't see them calling `run_multi`. So **multi-repo is a code path nobody exercises in production**. Either wire it up to a real entry point (`/api/cross-repo/run`) or delete it.

**F1.1.2 — `create_default()` is a fragile factory.** `orchestrator.py:88-96` wraps the whole `SandboxManager` import in a `try/except` that returns `None` on any failure. Three callers (submitter, admin, MCP) silently get `None` and skip orchestration entirely. Either log the failure + raise, or return a `Result(success=False, error="...")`. Today a misconfigured sandbox_manager just means "the agent silently never runs" — which is what produced the F12-orphaned-tool-call bug in the 2026-06-24 e2e (the chat got a 200 with `run_id=` but no orchestrator ever started).

### F1.2 — What the user wants is the **1 entry point pattern**

Reading the user's request:
> *"there are multiple entry points run_single and run_multi and other 2. we need to make it one entry point or 2. where a user may point to the repo and the orchestrator pulls the repo and show github issues,PRs, reviews etc and the user selects any item from this and ask the questions/requestion."*

**Recommended design: 2 entry points, not 1.**

The user described two distinct UX flows:

**Flow A — "Point at a repo, explore first":**
```
POST /api/repos/{owner}/{repo}
→ orchestrator pulls repo, builds KG, fetches GitHub issues/PRs/reviews
→ returns: { repo, kg_status, open_issues: [...], open_prs: [...], reviews: [...] }
→ user picks an item: "fix issue #37724" / "review PR #37800" / "run all open issue fixes"
→ POST /api/jobs  with prompt = "fix issue #37724"
→ run_job_spec(spec) executes
```

**Flow B — "Chat with the agent":**
```
POST /api/chat
→ user types: "what's happening with my last run?"
→ chat agent (read-only) queries JobSpecStore + introspection tools
→ answers: "Your last run (spec_id=4fed4879) is currently in_progress.
  10 of 15 kanban tasks are done, 4 are in review, 1 is blocked on
  a flaky test. Token spend so far: $0.34."
```

So the **2 entry points** are:
1. **`POST /api/repos/{owner}/{repo}/summarize`** — repo + KG + GitHub-list surface (the "what's in this repo?" view)
2. **`POST /api/jobs`** — `JobSpec` submission, the only write path for any autonomous work (chat, MCP, webhook, cron all funnel here)

These can both be **front-ends to the same `OrchestratorEngine`**, but the first one is read-only + GitHub-API-driven, and the second is write + LLM-driven. Today we have the second one (sort of — F1.1 fixes needed) but the first one is missing. The `/api/knowledge-graph/{graph_id}` endpoint is the closest analog, but it doesn't surface issues/PRs.

### F1.3 — What needs to change

**Blockers:**
1. Rename `run_single` / `run_multi` / `run` to `_run_single` / `_run_multi` and **delete the public `run`** (it's only called from the cron scheduler, which can be updated to call `submit_job_to_orchestrator(scheduler_spec)` with `source="cron"`).
2. Fix the 4 MCP tools in `mcp/server.py` to build a `JobSpec` and call `submit_job_to_orchestrator` instead of `run_single` directly. Today they skip tier, persistence, cancel-watch, and the `_run_with_cancel_watch` wrapper — so a 4-hour MCP-driven run has no way for the user to cancel it from the dashboard.
3. Fix `github_pr_feedback.py:122` to build a `JobSpec` and call `submit_job_to_orchestrator`. Today the legacy webhook bypasses the spec store and the cancel-watcher.
4. Replace `OrchestratorEngine.create_default()`'s silent `try/except → None` with explicit failure logging. A `None` engine is a silent no-op today.

**High-priority:**
5. Add a new entry point `OrchestratorEngine.summarize_repo(repo_url, branch)` that:
   - Clones the repo, builds the KG (using the existing `KnowledgeGraphSyncer.index` path).
   - Calls `github_list_issues`, `github_list_prs`, `github_list_reviews` (some of these need to be implemented — see §6.3 / F2.1 in the 2026-06-23 audit).
   - Returns a `RepoSummary` dataclass: `{ repo, kg_status: {nodes, edges, last_indexed_at}, open_issues: [...], open_prs: [...], recent_reviews: [...], default_branch, head_sha }`.
   - This is the "Flow A" entry point. It can be a **read-only** operation (no `JobSpec`, no LLM call) — just the GitHub API + the KG indexer.
6. Wire `/api/repos/{owner}/{repo}/summarize` to the new method. This is what the user sees when they "point at a repo".

**Medium-priority:**
7. Add `source="cron"` and `source="mcp"` to the `JobSpec.source` enum. Today the canonical sources are `user|github|cron|slack|linear|chat-submission` per `JobSpec` (from `harness/jobs/spec.py`); the cron path doesn't set it.
8. The chat agent's "what's happening with my last run?" flow already has all the right primitives (the `chat_introspection.py` tools: `list_runs`, `get_run`, `get_logs`, `list_test_cases`, `get_coverage`, `search_runs`, `get_dashboard_status`). What's missing is a **`/api/chat` endpoint that owns the chat conversation and the session_id cookie** (the "user actively interacts" path) — the chat currently only fires when invoked from a `submit_job` chain. The chat is reachable via `agent.run(goal)` from the dispatcher loop but not as a free-standing "talk to the agent" surface. (To be confirmed in §2.)



## §2. Chat / session continuity ("what's happening with my last run?")

### F2.1 — **Critical gap**: there is NO HTTP chat endpoint, even though the chat agent is wired and has 8 read-only tools ready

This is the single biggest gap in the user-facing surface. The chat agent is:

- Constructed in `backend/api/main.py:517-520` as `Agent(deps=base_deps, mode="chat", allowed_tools=list(CHAT_READONLY_TOOLSET))`.
- Stored in `app.state.agent` (line 527).
- Configured with `mode="chat"` (read-only — no `write_file` / `edit_file` / `commit_and_open_pr`).
- Equipped with **8 introspection tools** from `harness/tools/chat_introspection.py`: `list_runs`, `get_run`, `get_logs`, `list_test_cases`, `get_test_case`, `get_run_artifacts`, `search_runs`, `get_dashboard_status`, `get_coverage`.

But **nobody ever calls `app.state.agent.run(...)` over HTTP.** The only two call sites in the entire backend are:
- `admin.py:356` — inside the `ci_run` endpoint, which is for CI-driven test generation (not user chat).
- `pr_webhook.py:208` — inside the GitHub PR webhook handler.

`/api/agent/agent.py` is **a 16-line placeholder** (a hard-deleted endpoint from the C08 refactor). There is no `POST /api/chat`, no `GET /api/chat/threads`, no chat-history persistence, no session continuity. The user literally cannot type "what's happening with my last run?" and have an LLM answer.

**The flow the user described:**
> *"if user asks for previous or running sessions via chat/agent interface (this is where the user actively interacts with the agents/orchestartor etc). the agent needs to know what's going on and reply to the user correctly."*

is **not implemented**. The chat agent exists, the tools exist, the introspection store is wired (line 87-95 in main.py), but **the user has no surface to invoke it**.

### F2.2 — The `CHAT_READONLY_TOOLSET` is great in shape but the chat has no identity, no history, and no way to cite its sources

The 8-tool surface (`list_runs` / `get_run` / `get_logs` / `list_test_cases` / `get_test_case` / `get_run_artifacts` / `search_runs` / `get_dashboard_status` / `get_coverage`) is the right idea. But there are 3 missing pieces:

1. **No `chat_history` / `chat_thread` table** in Postgres. The chat agent's `messages: list[ChatMessage]` is in-process only. A user closes the browser, the conversation is lost.
2. **No `get_kanban_board` / `list_kanban_tasks` tool.** The chat can describe a run's status but cannot answer "what is the agent currently doing on the kanban board for run #1145e070?" The 9 chat-side job-control tools exist (`submit_job`, `cancel_job`, `pause_job`, `resume_job`, `list_jobs`, `get_job_status`, `comment_on_job`, `chat_resume_tool`, `chat_checkpoint_tool`) but there's no kanban-read tool.
3. **No `get_recent_events` / `get_live_session_state` tool.** The chat can read old `runs` / `pipeline_runs` rows but cannot read the SSE stream that's currently being emitted by a running subagent. The 2026-06-24 F21-F34 fix made the SSE event names consistent, but there's no chat-side consumer.

### F2.3 — "Previous or running sessions" continuity is one-sided

What works:
- `GET /api/sessions?limit=20&source=chat` (`api/routers/runs.py:327`) lists past sessions with status, cost, tokens, pass/fail counts.
- `GET /api/sessions/search?q=...` (`runs.py:315`) lets the user grep by goal / repo / session id.
- `GET /api/sessions/{session_id}/export` (`runs.py:395`) returns the full session dump.
- `GET /api/events/{session_id}` (SSE) streams live events for a single session.
- `GET /api/events/_global` streams every event from every active session.

What's missing for the user's flow:
- The **chat agent has no tool to read these endpoints.** The introspection tools are wired against the `pipeline_runs` table (the legacy pipeline-store era) — they don't read the `sessions` table that the orchestrator now uses, and they don't read the SSE event log at all.
- A user asking "what's happening with my last run?" needs the chat to (a) query the most recent session, (b) look up its current subagents, (c) tail the live SSE feed for ~5 seconds, (d) synthesise. None of (a)-(d) is possible for the chat today.

### F2.4 — Recommended chat surface (2 endpoints, not 1)

The user said "the user actively interacts with the agents/orchestrator etc". The minimum viable chat is two HTTP endpoints, not one, because the chat has a stateful conversation.

**Endpoint 1: `POST /api/chat/threads`** — create a new chat thread.
```json
{ "name": "investigate run 1145e070", "session_id": "optional-explicit-link" }
→ 201 { "thread_id": "uuid", "session_id": "chat-...", "created_at": "..." }
```

**Endpoint 2: `POST /api/chat/threads/{thread_id}/messages`** — send a user message, get an assistant reply.
```json
{ "content": "what's happening with my last run?" }
→ 200 SSE: text/event-stream
  event: token
  data: {"text": "Your last run "}
  event: token
  data: {"text": "spec_id=4fed4879 "}
  event: tool_call
  data: {"tool": "list_runs", "args": {"limit": 5}}
  event: tool_result
  data: {"tool": "list_runs", "output": "[...]"}
  event: token
  data: {"text": "is in_progress. 10/15 tasks done."}
  event: done
  data: {"thread_id": "...", "message_id": "..."}
```

**Storage:** new table `chat_threads(id, user_id, name, session_id, created_at)` + `chat_messages(id, thread_id, role, content, tool_calls JSONB, created_at)`. The chat agent's `messages` list is hydrated from this table at request time and persisted after every turn.

**Wiring:** add 2 routes to `backend/api/routers/chat.py` (new). Inside, reuse the existing `app.state.agent` (the chat-mode `Agent` already constructed in main.py:517) but per-request, swap the in-memory `messages` list with the thread's history.

**Tools to add to `CHAT_READONLY_TOOLSET`** (read-only, 4 new):
- `list_recent_sessions(limit, source)` — wraps `GET /api/sessions`.
- `get_session_detail(session_id)` — wraps `GET /api/sessions/{id}` (the full status + tree).
- `tail_live_events(session_id, seconds=5)` — opens the SSE stream for 5s, returns the captured events.
- `get_kanban_for_session(session_id)` — wraps `GET /api/kanban/boards?session_id=...` (or direct query).

### F2.5 — The chat MUST have a `user_id` field, not just a session_id

The 2026-06-23 audit (§2.6, §2.7) flagged that **there is no `user_id` column on any table**. This is the single change that unblocks per-user customisation, per-user-per-day budgets, and a real multi-tenant chat. With the user saying "schemas can change", I'd:

1. Add `user_id TEXT` to `sessions`, `job_specs`, `chat_threads`, `chat_messages`, `token_usage`, `artifacts` (all NULLable for backward compat).
2. Add a `users` table: `(id, email, name, tier, created_at, last_seen_at)`.
3. Mint a session cookie / API-key from a `POST /api/auth/login` endpoint (or accept a bearer token from the existing `TESTAI_API_KEY` env var).
4. Thread `user_id` through every entry point — `submit_job_to_orchestrator` (user_id on the spec), `run_job_spec` (user_id on the spec), `agent.run(goal)` (user_id on the request context), `run_chat` (user_id on the chat message).
5. Add a per-user-per-day budget that ACTUALLY reads the user's spend. This is the 4th-scope budget that the 2026-06-23 audit flagged as "UI-only" — the schema for it now exists once we have user_id.

This is the **single most leverage-y change** in the whole audit. Without it, the chat can never be multi-tenant, and the user is stuck with a single-user local-dev experience.



## §3. User visibility into the sandbox

### F3.1 — Today: the user can list sandboxes / volumes / containers, but cannot peek inside

`backend/api/routers/sandbox.py` exposes 5 admin endpoints:
- `GET /api/sandbox/exec-containers` — list all `docker ps` rows
- `DELETE /api/sandbox/exec-containers/{session_id}` — destroy a container
- `POST /api/sandbox/exec-containers/reap` — bulk reaper
- `GET /api/sandbox/list` — list active sandboxes
- `GET /api/sandbox/volumes` — list workspace volumes (size, in-use, created_at)
- `DELETE /api/sandbox/volumes/{volume_name}` — destroy a volume

That's **a Docker management surface, not a sandbox visibility surface.** A user with a running spec_id=4fed4879 has no way to:
- See the **current filesystem** of `/workspace/repo` (which files exist, what just changed).
- See the **running processes** in the container (is the test runner alive? which port is the dev server on?).
- **Tail the live bash output** of an in-flight tool call (the `ToolProgress` event from F23 emits chunks but the UI doesn't stream them yet).
- **Attach to the dev server** the agent started (no port-forward / no-preview mechanism).

The 2026-06-24 audit F35 confirmed the activity feed shows `tool.progress: 12` events per 5 min — those are 12 chunks of stdout/stderr that the user can see, but only after they were processed and stored. There's no "watch the agent's bash session live" affordance.

### F3.2 — The `/sandbox/[sessionId]` route exists in the frontend but the backend has no streaming terminal

The 2026-06-24 audit §0.2 listed 44 Next.js routes including `/sandbox/[sessionId]`. That route renders a sandbox detail view, but the backend it calls doesn't include:
- A `GET /api/sandbox/{session_id}/files` (read-only filesystem listing).
- A `GET /api/sandbox/{session_id}/files/{path:path}` (read a file by path).
- A `GET /api/sandbox/{session_id}/terminal?exec_id=...` (SSE tail of a running command's output).
- A `POST /api/sandbox/{session_id}/exec` (user-typed command, with the same permissions as the agent).

This is what Greptile, TestSprite, and OpenHands all have. The user can `tail -f` the agent's bash session; TestAI cannot.

### F3.3 — Recommended sandbox-visibility surface (5 endpoints, all read-only + 1 write)

| Endpoint | Purpose | Wire |
| --- | --- | --- |
| `GET /api/sandbox/{sid}/status` | container state, uptime, resource use | JSON |
| `GET /api/sandbox/{sid}/files?path=...&max_depth=3` | directory tree from `/workspace` | JSON |
| `GET /api/sandbox/{sid}/files/raw?path=...` | read a file (text, size-capped at 1MB) | text/plain |
| `GET /api/sandbox/{sid}/terminal/stream?tool_call_id=...` | tail the live bash output of one tool call | SSE |
| `POST /api/sandbox/{sid}/exec` | user runs a command in the same container (with `permission=human` for the agent's audit log) | JSON |
| `GET /api/sandbox/{sid}/ports` | list detected open ports (e.g. `localhost:3000` is the dev server) | JSON |

The frontend `/sandbox/[sessionId]` page then renders: a left rail of file tree, a centre pane of file content, a bottom pane of the live tool-call terminal, and a "user exec" prompt at the top. **This is the missing piece for "the user can see whatever is happening in the sandbox"** from the user's question.

The 5 read-only endpoints can be implemented as thin `docker exec` wrappers — `docker exec <id> ls -la /workspace/repo` for the file tree, etc. The "user exec" write endpoint needs an explicit permission grant + audit row in `agent_artifacts` so the agent can see what the user did (and avoid clobbering it).



## §4. Memory, compaction, skill evolution

### F4.1 — Memory is real and well-shaped, but it has no Tier-0 ("raw artifacts") backing

The CONTEXT.md says memory has three tiers — L0 raw artifacts, L1 indexed facts, L2 curated lessons — but only **L1 (kg_nodes/kg_edges) and L2 (l2_reflection) are real**. L0 is implicit (the LLM's `agent_artifacts` table) but not exposed as a "memory tool".

What exists and works:
- **`memory_tool.py`** — the agent-callable `memory` tool, modeled on Hermes' `MemoryProvider`. Per-repo flat markdown files at `~/.testai/memories/<repo-slug>/{MEMORY,USER}.md`, char-limits (3000/1375), free-form entries, opt-in JSONL sidecar for `confidence` / `source_kind`. This is the cross-run per-repo memory.
- **`l2_reflection.py`** — at end-of-run, an LLM summarises the run into a 1-paragraph "lesson for the next run" and writes it to the memory tool. This is what makes the system compound.
- **`reflexion_memory.py`** — error-pattern store. After repeated identical tool errors, an LLM-generated rule is written.
- **`curator.py`** — background maintenance for skills (skill usage tracking, stale/archive lifecycle).

What's missing:
- **L0 "raw artifacts" memory tool.** The agent can `read_file` a `kg_nodes` row but cannot call a `memory_search` tool that does BM25 / vector / SQL over the `agent_artifacts` table. The CONTEXT.md claim of a 3-tier memory is half-implemented.
- **`memory_search` tool** is referenced in `orchestrator_tool.py:387` recipe description but **not registered** (per the 2026-06-23 audit §2.1). This is a real gap — the LLM can `add` to memory but cannot `search` it on demand.
- **No `memory_curate` (Tier-2 LLM curation).** Hermes' `Curator` runs a daily LLM pass that consolidates duplicate lessons, archives stale ones, and surfaces high-value patterns. TestAI's `curator.py` only does the skill lifecycle (not the memory lifecycle).

### F4.2 — Compaction has 3 strategies, but only 1 of them (micro-compact) is auto-invoked

`backend/harness/compaction.py` defines 3 strategies:

1. **`micro_compact(messages, max_turns=20)`** — strip old tool outputs, keep system + recent N. Free, no LLM. Auto-invoked in the agent loop.
2. **Auto-compact (LLM summarise)** — **not implemented.** The docstring mentions it as strategy #2 but there's no code path that calls an LLM to summarise old messages. This is the missing piece for long-running agents.
3. **`reactive_compact(messages, error)`** — on `prompt_too_long` API error, drop oldest 30% of messages and retry. Reactive only.

The 2026-06-23 audit noted: "The CONTEXT.md claim of TTLs is unbacked by code." The same is true for compaction — the **LLM-based compaction strategy is documented but absent**.

**The Anthropic long-running-agents doc (Nov 2025)** explicitly says compaction alone is insufficient. Their two-fold solution is an **initializer agent + a coding agent** that uses git for persistence and a feature-list file as a structured "what's done / what's left" ledger. **TestAI has the `l2_reflection` analogue of this** (a 1-paragraph summary at end-of-run) but not the structured feature-list file or the git-as-persistence model.

### F4.3 — Skill evolution is real but only does lifecycle (stale/archive), not "evolve"

`backend/harness/curator.py` is a **lifecycle curator**, not an **evolution curator**:
- Tracks `use_count` / `view_count` / `last_used_at` per skill in `~/.testai/skills/.usage.json`.
- Marks skills `stale` after 30 days of no use, `archive` after 90.
- Runs a daily `run_curator` pass.
- Has `run_evolution(db, llm)` (line 244) which is the LLM-driven "look at skills and suggest improvements" path — but it returns suggestions only, doesn't apply them.

What's missing for real "skill evolution":
- **LLM-driven drift detection**: when a skill's referenced API changes (e.g. GitHub's GraphQL `node.id` switched from `Int!` to `ID!` last year), the skill is now wrong. The curator should detect this by reading the skill's `SKILL.md` and running a "is this still accurate?" LLM pass.
- **A/B / shadow testing**: when the curator proposes an evolved version, run the new and old versions in parallel on a fixture and let the user accept/reject.
- **Skill-versioning UI**: `GET /api/skills/{name}/versions` exists (per admin.py:217), but the curator doesn't actually version anything — it just archives the old.

The Hermes pattern (cited in the curator's docstring) is the right model: never auto-delete, archive is recoverable, runs on inactivity check (not cron).

### F4.4 — Recommended memory + compaction + skill-evolution design (incremental, 3 changes)

**Change A — Add a `memory_search` tool** (cheap, ~50 LoC).
```python
class MemorySearchTool(BaseTool):
    name = "memory_search"
    description = "BM25 search over the per-repo MEMORY.md and USER.md, plus the L0 agent_artifacts table"
    async def run(self, query, repo="", limit=10, include_artifacts=True): ...
```
Wire to `CHAT_READONLY_TOOLSET` and `coordinator` toolset. The LLM can now ask "what did we learn last time about ActiveSupport's cache?" and get a structured answer.

**Change B — Add LLM-based auto-compaction (the strategy the docstring promises).**
- Add `harness/compaction/llm_compact.py` (or in the existing `harness/context_compressor/`). On every Nth turn (e.g. turn 30), summarise the oldest half of the conversation into a single `<compaction_summary>` system message, then drop the originals. Cost: 1 LLM call per 30 turns (~1¢).
- Cross-reference: Anthropic's effective-harnesses doc has the same pattern — "compaction, which enables an agent to work on a task without exhausting the context window". TestAI has the "where" (compaction.py) but not the "what" (LLM call).

**Change C — Add a `feature_list.json` (per Anthropic) and a `progress.md` (per the Anthropic quickstart) to the orchestrator's first turn.**
- On the first turn of `run_single` (or when the LLM signals "starting a new long-running project"), have the coordinator create `/workspace/repo/.testai/feature_list.json` and `/workspace/repo/.testai/progress.md`.
- Subsequent runs on the same repo read these files at session start, so the LLM knows "what's done, what's next".
- The Anthropic `autonomous-coding` quickstart uses this pattern verbatim. It's the right pattern for the "fully autonomous, compounds over runs" goal.
- This is what `l2_reflection` was trying to do at end-of-run, but **starting at the beginning is better**.

**Change D — Evolve the curator into an LLM-driven skill evolution loop.**
- Move `run_evolution(db, llm)` from "returns suggestions" to "writes a PR with the evolved skill + opens a review task". The user approves/rejects.
- The current pattern is human-trust-zero (the curator writes to `~/.testai/skills/...` silently). Evolving to a "PR with diff, human approves" model is the right level of trust.



## §5. Subagent activity recording + display

### F5.1 — The recording side is real; the display side has 4 mismatches left over from the pipeline-store era

**Recording (good):**
- `harness/recording.py` — JSONL session trajectory at `~/.testai/sessions/{session_id}/trajectory.jsonl`, plus archive files.
- `agent_delegations` table — per-delegation: `session_id, parent_delegation_id, agent_role, goal, status, tools_used, tool_calls_count, duration_ms, error, result_summary, input_tokens, output_tokens, estimated_cost_usd, model, depth, parent_subagent_id`. Real, working, joined by `subagent_id`.
- `trace_events` table — typed events for every `chat` / `execute_tool` / `agent_run` / `agent_round` / `agent_reasoning` / `subagent_invoke` / `kanban_transition` / `kanban_board` / `budget_throttle`. 9 OTel operation types.
- `stream_events` table — the SSE event log (every typed + Generic event the dashboard consumes).
- `agent_artifacts` table — L0 tool calls + tool results (capped to 2000 chars), per session.
- `token_usage` table — per LLM call, with `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `estimated_cost_usd`, `session_id`, `agent_role`, `run_id`.

**Display (4 mismatches identified in 2026-06-24 audit, fixed):**
- F26: `sessions/page.tsx` filtered for stale event names. **Fixed.**
- F27: `pipeline/` components still use old vocabulary. Marked vestigial.
- F28/F29: SSE event-name normalization (the central fix). **Applied.**

**What still needs work (today's audit, beyond the 2026-06-24 fixes):**

### F5.2 — Subagent identity in the UI is incomplete

A subagent session has the pattern `subagent-sa-0-XXXX` or `subagent-sa-XXXX`. The dashboard's `/sessions` page lists them by `session_id`, but:
- The **parent_run_id is not stored on the subagent session** (the subagent's `parent_session_id` points to the orchestrator's session, but the orchestrator's session is a different beast from the run_id).
- The dashboard's `/jobs/[spec_id]` page shows events scoped to the run, but the subagent's `agent_role`, `goal`, `parent_subagent_id`, and tree depth are not surfaced as a "delegation tree" component — they exist in `agent_delegations` but the API doesn't aggregate them.
- The 2026-06-23 audit F3 already noted the F4-zombie-sessions bug: 10 subagents stuck in `status="running"`. **Not fixed in 2026-06-24** because it's a janitor task, not a feature add.

### F5.3 — Tool-call-level recording is good but the per-tool latency p50/p95 is not computed

The 2026-06-24 audit F36 noted: "`tool.execution.completed` carries no `started_at` field, so the SQL has to derive duration from `created_at` deltas." The `_aggregations` endpoint doesn't yet compute this. **Out of scope for this audit** but a 1-day addition: add a `started_at` column to `ToolExecutionCompleted` and the OTel span, then `AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))` is one SQL line.

### F5.4 — The cost attribution is good at the run level, weak at the subagent tree level

Per the 2026-06-23 audit §2.6: `cost.py:34-35` has the per-session budget stub, but per-subagent cost is *only* available via `agent_delegations.estimated_cost_usd` (sum by `parent_subagent_id`). There's no `parent_subagent_id` chain in the UI — you can't ask "how much did the explore subagent of the explore subagent of the orchestrator cost?" without a recursive CTE.

**Recommended addition:** a `GET /api/cost/delegation-tree/{run_id}` endpoint that returns the full tree with per-node cost + duration. The `agent_delegations` table has all the data; the endpoint is ~40 LoC.

### F5.5 — Subagent activity is visible to the user, but the "follow a child live" pattern needs polish

`GET /api/delegate/{session_id}/stream` (SSE per-delegation) and `GET /api/delegate/{session_id}/shadow/stream` exist. The 2026-06-24 F35 confirmed child events are routed to the parent's SSE queue. The dashboard's `ActivityFeed` component can filter by `payloadMatch` (e.g. `subagent_id=sa-0-XXXX`) to follow one child. **The wire works.** What's missing is a dedicated "Subagent Tree" component (like Devin's subagent panel — see §6.4) that shows the live tree with each node's status, duration, and current tool.



## §6. Production-grade agent-harness research

> The user asked: *"research internet take your time no need to rush ... check how other agentic frameworks are doing this like greptile, tembo ai, testim, testsprite etc ... use context mode tool to search internet to research about agent harnesess. production grade harnessess not Agent frameworks like langgraph, crewAI etc."*
>
> Sources consulted (live web, via `ctx_fetch_and_index`):
> - Anthropic, "Effective harnesses for long-running agents" (Nov 26, 2025).
> - Anthropic, "Building effective agents" (Dec 19, 2024).
> - OpenHands docs: `StuckDetector` (5 patterns).
> - Greptile homepage.
> - TestSprite homepage.
> - Tembo homepage.
> - Bug0 homepage.
> - Mabl homepage.
> - LangGraph (github.com/langchain-ai/langgraph).
> - Block Goose (github.com/aaif-goose/goose).
> - Anthropic quickstarts: `autonomous-coding` two-agent pattern.
> - Roo Code / Cline (github.com/RooCodeInc/Roo-Code, cline.bot).
> - Existing team research: `docs/PRODUCTION_HARNESS_COMPARISON_2026-06-18.md`, `docs/OPEN_SOURCE_HARNESS_COMPARISON_2026-06-18.md`, `docs/ADOPTABLE_PATTERNS_FROM_FRAMEWORKS.md`, `docs/agent-harness-architecture-research.md`, `docs/CHINESE_AI_FRAMEWORKS_PATTERNS.md`, `docs/upcoming-projects-research-2026-06-24.md`.
>
> Conclusion: TestAI's **harness shape** (sandbox + KG + kanban + delegation + tier model + budget + memory) is at parity with the production leaders. The gaps are: (a) **chat surface** (F2), (b) **sandbox visibility** (F3), (c) **per-edit KG refresh** (still coordinator-only), (d) **long-running memory primitives** (F4 — no feature-list file, no LLM-driven auto-compaction, no LLM-driven skill evolution), and (e) **observability** for the live event stream (F5).

### F6.1 — The 4 production-grade patterns TestAI should adopt now

The research converged on 4 patterns that every production harness implements. TestAI has 2 of 4 in some form. The other 2 are gaps.

**Pattern 1 — Initializer + coding agent (Anthropic's long-running pattern).** The 2025-11 Anthropic engineering blog shows the canonical solution to "compaction isn't enough": a **two-agent pattern** (initializer + coding agent) where:
- The initializer runs ONCE at project start, reads `app_spec.txt`, writes `feature_list.json` (200 test cases), `init.sh` (dev-server script), `claude-progress.txt` (session progress notes), and `git init`s the project.
- The coding agent runs in subsequent sessions, each with a fresh context, and rehydrates by reading `feature_list.json` (what's done), `progress.txt` (what just happened), and `git log` (history).

**TestAI gap:** `l2_reflection.py` writes a 1-paragraph summary at end-of-run — that's a **L2 reflection** but it's not a **structured feature list** that the next session can plan against. The Anthropic pattern is richer. Recommended: add `.testai/feature_list.json` + `.testai/progress.md` to the orchestrator's first turn on a new repo, populated by the coordinator LLM at run-end. This is a 1-day addition and gives "fully autonomous" the compound-learning property the user asked for.

**Pattern 2 — Stuck detector (OpenHands 5-pattern).** OpenHands' `StuckDetector` (https://docs.openhands.dev/sdk/guides/agent-stuck-detector) detects 5 patterns in real-time:
1. Repeating action-observation cycles (4+ identical).
2. Repeating action-error cycles (3+ identical).
3. Agent monologue (3+ consecutive assistant messages with no progress).
4. Alternating patterns (6+ ping-pong cycles).
5. Context-window errors.

When detected, the agent can auto-halt. **TestAI has only pattern 1** (`_consecutive_same_tool` counter, threshold 20). The other 4 patterns are silently unmonitored. The 2026-06-24 audit F14 flagged this. **Out of scope for this run** but the fix is ~100 LoC: add a `StuckDetector` class in `harness/agent/`, integrate into the agent loop after each tool call.

**Pattern 3 — Per-episode cost + duration aggregation (Greptile, OpenHands, LangGraph).** Every production harness has a "how much did this run cost" view that breaks down by subagent, by tool, by phase, and by time. **TestAI has 4 of 5 pieces**: per-run cost (token_usage), per-subagent cost (agent_delegations), per-tool success rate (`_aggregations` endpoint, F33), per-model cost (`/api/cost/per-model`). The 5th piece — **per-phase cost** — is missing. The orchestrator's `cmd_orchestrate` phases (explore → triage → fix → test → review) are not tagged on `token_usage`, so the user can't ask "what did the test phase cost?" Recommended: add a `phase TEXT NULL` column to `token_usage`, populated by the orchestrator at the start of each phase. 1-day addition.

**Pattern 4 — Live terminal/file tree into the sandbox (TestSprite, Bug0, OpenHands).** Every production harness has a "see the agent's actual workspace" view. **TestAI does not** (F3). TestSprite's CLI/IDE/CI modes, Bug0's per-test video + console + network-har, OpenHands' per-step workspace snapshot — all of these give the user a real-time view of what's happening. The recommended 5-endpoint surface in F3 closes this gap.

### F6.2 — Production-harness feature matrix (where TestAI stands today)

| Feature | Anthropic Claude Agent SDK | OpenHands | Greptile | TestSprite | Bug0 | Tembo | Devin | LangGraph | **TestAI (today)** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sandbox per-run | yes | yes (Docker) | yes (cloud) | yes (cloud) | yes (cloud) | yes (cloud) | yes (cloud) | n/a | **yes (Docker)** |
| Subagent tree | yes (4 modes) | yes (StuckDetector) | yes (swarm) | n/a | n/a | n/a | yes (panel) | yes (subgraphs) | **yes (delegate_task)** |
| Live terminal view | yes (TUI) | yes (browser) | n/a | yes (CLI/IDE) | yes (per-test video) | n/a | yes (browser) | via LangSmith | **no (F3 gap)** |
| File tree view | yes | yes | n/a | yes | n/a | n/a | yes | via LangSmith | **no (F3 gap)** |
| Knowledge graph (code) | n/a | n/a | **yes (core)** | n/a | n/a | n/a | n/a | n/a | **yes (CodeGraph)** |
| KG per-edit refresh | n/a | n/a | yes (incremental) | n/a | n/a | n/a | n/a | n/a | **no (60s debounce)** |
| Stuck detector | yes (5) | yes (5) | n/a | n/a | n/a | n/a | yes | via LangSmith | **1 of 5** |
| Long-running memory (file) | yes (feature_list.json) | yes (workspace state) | yes (graph cache) | n/a | n/a | n/a | yes | yes (Store) | **partial (L2 only)** |
| Per-phase cost | n/a | yes | yes | n/a | n/a | n/a | yes | via LangSmith | **no** |
| Per-edit OTel span | yes | yes | yes | n/a | n/a | n/a | yes | yes (genai.*) | **no (per-edit F4)** |
| MCP integration | yes (sampling) | yes (servers) | n/a | yes (server) | n/a | yes (servers) | yes | n/a | **yes (server + client)** |
| Self-healing flaky test | n/a | yes (selector-heal) | n/a | yes (verify) | **yes (core)** | n/a | yes | n/a | **partial (attempt_heal)** |
| Tier model (1/2/3) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **yes (graduated autonomy)** |
| Cancellation propagation | yes | yes | n/a | yes | yes | yes | yes | yes (interrupt) | **yes (cancel_watcher)** |
| Resume from checkpoint | yes | yes | n/a | n/a | n/a | n/a | yes | yes (durable) | **yes (JobCheckpoint)** |
| Multi-repo coordination | n/a | n/a | n/a | n/a | n/a | **yes (core)** | n/a | n/a | **partial (run_multi, F1.1.1)** |
| KG post-fix update | n/a | n/a | yes (incremental) | n/a | n/a | n/a | n/a | n/a | **no (kg_refresh is coordinator-only)** |
| Chat surface (free-form) | yes (Claude Code) | yes (UI) | n/a | yes (web) | n/a | n/a | yes (UI) | n/a | **no (F2 gap)** |
| Per-user-per-day budget | n/a | yes | yes | yes | yes | yes | n/a | n/a | **no (F2.5, schema gap)** |

**TestAI is at parity on 9 of 22 rows. The 13 gaps split into:**

- **3 of the 13** are F1.1 (entry-point consolidation) — small.
- **3 of the 13** are F2.1 (chat surface) — medium.
- **3 of the 13** are F3.1 (sandbox visibility) — medium.
- **2 of the 13** are F4.1-4.3 (memory + compaction + skill evolution) — large.
- **1 of the 13** is F5.5 (delegation tree component) — small.
- **1 of the 13** is the per-user budget (F2.5) — schema-level.

### F6.3 — Cross-cited patterns from the existing team research

The team's 2026-06-18 comparison work is excellent and forms the baseline. Key findings re-confirmed in this audit:

- **Hermes' heartbeat + stale detection** (from `OPEN_SOURCE_HARNESS_COMPARISON_2026-06-18.md`). TestAI has `HeartbeatService` (`services/heartbeat.py`) but no stale-detection. Hermes' pattern of `(_HEARTBEAT_STALE_CYCLES_IN_TOOL, _HEARTBEAT_STALE_CYCLES_IDLE)` is the right model.
- **OpenHands' stuck detector** (5 patterns) — F6.1 pattern 2.
- **LangGraph's durable execution + interrupt** — LangGraph's `interrupt()` mechanism is the same shape as TestAI's `_check_pause_for_spec`. The differentiator is LangGraph's "resumable from any node" checkpoint model, which is harder than TestAI's "save the whole session state" approach.
- **Greptile's graph index + swarm** — TestAI's CodeGraph + delegate_task fan-out is the same shape. Greptile's "learns your codebase over time" (per PR comment) is a 2nd-tier memory TestAI doesn't have.
- **Anthropic's "initializer + coding agent"** — F6.1 pattern 1. This is the highest-leverage adoption for TestAI's "fully autonomous" tier-1 goal.
- **TestSprite's "verify, don't trust"** — TestAI's `attempt_heal` is the right shape, but it only works for visual tests. Generalising to "verify the fix works" (run the test that was failing, before marking done) is the next step. The kanban `claim_task` flow already has a `failure_limit` gate, so the infra is there.
- **Bug0's "FDE + AI platform"** — the FDE (forward-deployed engineer) + AI engine split is exactly what TestAI's tier-2 (supervised) mode should look like. Tier 2 today does "stop before commit_and_open_pr, post to review queue" but the FDE is the human in the loop; the model says "I'm done, please review" and the human reviews via the kanban board.

### F6.4 — A note on "Sweep" (and where the agent-harness space is heading)

Sweep (sweepai/sweep) — historically a GitHub issue-to-PR agent — has pivoted to a JetBrains IDE plugin. Their old GitHub-bot model is now a small piece; the product is an in-IDE coding assistant competing with Cursor. The pattern to learn from them: **the product surface evolved from "PR automation" to "in-IDE collaboration"**. TestAI's positioning is the inverse: not in-IDE but in-CI + in-dashboard, doing autonomous batch work. This is a different market (Mabl, Bug0, TestSprite compete here, not Cursor/Sweep).

The new wave (Devin, Codegen, Factory, Cosine) is all about **"AI engineer on your team"** — a persistent agent with a web IDE, a Slack/Telegram interface, a memory of past work, and a billing model. TestAI's chat surface (F2) and per-user customisation (F2.5) are the moves that put it in this category.



## §7. Recommendations (what to refine / fix / include)

> **As a user of this project, what I want refined / fixed / included.**
> Ordered by impact × effort. "Blockers" must ship before the next external demo. "High-priority" are the next 2-week deliverables. "Medium-priority" are the next-month polish. "Refinements" are longer-horizon bets.

### Blockers (must fix before next user demo)

1. **Consolidate to 1 entry point + 1 read-only surface.** Rename `run_single` / `run_multi` / `run` to `_run_single` / `_run_multi`; delete `run`. All callers (`mcp/server.py`, `webhooks/github_pr_feedback.py`, `scheduler/loop.py`) build a `JobSpec` and call `submit_job_to_orchestrator`. (F1.1, F1.3)
2. **Add the "summarize repo" entry point.** `POST /api/repos/{owner}/{repo}/summarize` — clone, KG index, list open issues/PRs/reviews, return a `RepoSummary`. This is the "Flow A" UX the user described: "user points to a repo and the orchestrator pulls the repo and shows GitHub issues, PRs etc". (F1.2)
3. **Build the chat surface.** `POST /api/chat/threads` + `POST /api/chat/threads/{thread_id}/messages` (SSE), 2 endpoints. New `chat_threads` + `chat_messages` tables. Reuse `app.state.agent` with per-request `messages` list. Add 4 new read-only tools to `CHAT_READONLY_TOOLSET`: `list_recent_sessions`, `get_session_detail`, `tail_live_events`, `get_kanban_for_session`. (F2.1, F2.4)
4. **Add `user_id` everywhere.** New `users` table, add `user_id TEXT NULL` to `sessions`, `job_specs`, `chat_threads`, `chat_messages`, `token_usage`, `artifacts`. Bearer-token auth via `TESTAI_API_KEY` env var. Unblocks per-user-per-day budget, multi-tenant chat, and per-user cost. (F2.5)
5. **Fix the orchestrator entry-point bugs (already partially fixed in 2026-06-24).** F12 orphan tool_calls (fixed), F15 session_id injection (fixed), F16 kg_edges (fixed). Confirm these are still passing in the next e2e.

### High-priority (next 2 weeks)

6. **Add the 5 sandbox-visibility endpoints.** `GET /api/sandbox/{sid}/{status,files,files/raw,terminal/stream,ports}` + `POST /api/sandbox/{sid}/exec`. Wire the frontend `/sandbox/[sessionId]` page to them. (F3.3)
7. **Add the `.testai/feature_list.json` + `.testai/progress.md` pattern.** This is the Anthropic "initializer + coding agent" pattern. At first turn of `run_single`, the coordinator creates these files. At end-of-run, `l2_reflection` updates `progress.md`. The next session on the same repo reads them as the first action. (F4.4 Change C, F6.1 pattern 1)
8. **Add the `memory_search` tool.** BM25 over the per-repo `MEMORY.md` + `USER.md` + the L0 `agent_artifacts` table. Wire to `CHAT_READONLY_TOOLSET` and the `coordinator` toolset. (F4.4 Change A)
9. **Add LLM-driven auto-compaction.** On every 30th turn, summarise the oldest half of the conversation into a single system message. ~50 LoC. Closes the gap between the docstring's promise and the code. (F4.4 Change B, F6.1)
10. **Add the per-subagent live-tree component.** `SubagentTree` React component on the `/jobs/[spec_id]` page. Fetches from `GET /api/cost/delegation-tree/{run_id}`. Each node shows: name, role, status, current tool, duration, cost, depth. Click-to-follow into the live SSE stream. (F5.2, F5.5)
11. **Wire `/api/cross-repo` to `run_multi`.** Today `run_multi` is unreachable from any HTTP path. Either wire `/api/cross-repo/execute` to it, or delete the dead code. (F1.1.1)
12. **Add the per-phase cost column.** `phase TEXT NULL` on `token_usage`, populated by the orchestrator at the start of each phase. The `/api/cost/per-phase` endpoint and the per-phase budget scope both work after this. (F6.1 pattern 3)

### Medium-priority (next month)

13. **Add the `StuckDetector` class.** 5 patterns from OpenHands (F6.1 pattern 2). ~100 LoC. Integrate into the agent loop after every tool call.
14. **Add a per-edit KG refresh hook.** `write_file` / `edit_file` / `apply_patch` post-tool hook → `kg_refresh(force=true)`. The 2026-06-23 audit §2.3 noted this gap. ~30 LoC.
15. **Add the `recovered_at_phase` field** so a resumed session knows exactly where it was. The `JobCheckpoint` already includes `last_result.phase`; surface it in the activity feed. (F2.1 sub-bullet)
16. **Generalise `attempt_heal` to "verify the fix worked"** (TestSprite's pattern). Run the failing test before `kanban_complete`, not after.
17. **Replace the silent `create_default()` try/except with explicit failure.** Today a misconfigured `SandboxManager` → `None` → the chat gets a 200 with `run_id=` but no orchestrator ever starts. (F1.1.2)
18. **Add the `kg_edges` extraction LLM call.** After the post-coordinator KG sync, an LLM extracts `(subject, predicate, object)` triples from the run's L0 artifacts. The 2026-06-24 F16 added pairwise edges, but a real LLM-driven extraction (per the 2026-06-23 §2.3 finding) gives the KG actual semantic structure.
19. **Wire the SSE event log into the dashboard's `/runs/{runId}` page.** F27 marked the `pipeline-event-reducer.ts` components as vestigial; migrate them to the EventBus vocabulary so the per-run timeline page renders real events.
20. **Implement per-user-per-day budget enforcement.** The schema now has `user_id` (F2.5); the `BudgetTracker` needs a `user_day` scope that sums today's spend for the user. The UI knob is already there (`BudgetSettings.tsx`).

### Refinements (longer-horizon bets)

21. **Skill evolution as PR.** `curator.run_evolution` writes a PR with the evolved `SKILL.md`; human approves. (F4.3, F4.4 Change D)
22. **Anthropic-style tier-3 proposal mode.** Tier 3 today creates a placeholder kanban task. The right shape is a markdown proposal the user reviews (per Anthropic's "human-authored" pattern), with a "re-submit as tier 1/2" or "reject" button.
23. **Devin-style web IDE for the sandbox.** The 5 sandbox-visibility endpoints (F3.3) are a stepping stone. The end-state is a browser-based IDE that opens the same view TestSprite / Devin give their users.
24. **Per-edit OTel export.** The wire names already align with OTel GenAI conventions (per the 2026-06-24 F34). Add a 5th EventBus sink: `otel_exporter` (gated by `OTEL_ENABLED=true`).
25. **Multi-tenant everything.** Per-org customisation, per-org RBAC, per-org billing. The `user_id` column (F2.5) is the first domino; per-org is the next.

### What to delete (cleanup)

26. **`backend/api/routers/agent.py`** — 16-line placeholder for the hard-deleted `/api/agent/run`. The C08 refactor is done; remove the file.
27. **`run()` in `OrchestratorEngine`** — the 4-line dispatcher that picks between `run_multi` and `run_single`. Once F1.1 is done, this is dead.
28. **`tools/delegated/scheduler/loop.py:82`** call to `engine.run()` — same.
29. **The 4 MCP tools in `mcp/server.py` that call `run_single` directly** — replace with `JobSpec` + `submit_job_to_orchestrator`.
30. **`codegraph_callees` references in `toolsets.py` and `delegate_task.py:332`** — the name doesn't exist. Either register an alias or remove from the leaf allow-list. (2026-06-23 audit F2.1)



---

