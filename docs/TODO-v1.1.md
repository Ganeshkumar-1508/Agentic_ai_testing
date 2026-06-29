# TODO — v1.1+ Candidates

Deferred from v1 per the 2026-06-25 review of "curator PR opener" + "feature list"
items. Each entry has re-introduction criteria so we know when to revisit.

## 1. Skill-evolution PRs (skill_evolution_prs)

**Status:** Schema table dropped. No code paths reference it.

**Why deferred:** No reference harness (Hermes, OpenClaude, OpenHarness) files
curator PRs. Evolved skills land in `~/.testai/skills/` and the next session
picks them up via `skill_view`. For single-user v1, the local-FS pattern is
sufficient.

**Re-introduce when ANY of:**
- We need **version history** of skill changes (audit, rollback beyond the
  `.usage.json` sidecar).
- We need **human-review-before-use** — a skill shouldn't be auto-applied
  until a human approves the diff.
- We need **cross-machine sync** — a developer wants to share evolved skills
  between two testai installs.
- The skills library grows past ~50 skills and we need a review surface beyond
  the local FS.

**Re-introduction shape:** Single `skill_evolution_prs` table
(`id`, `skill_name`, `from_version`, `to_version`, `diff`, `pr_url`, `status`,
`created_at`, `merged_at`) + a `submit_skill_pr(skill_name, diff)` tool +
an `/api/curator/pending-prs` endpoint. `run_evolution()` writes the diff +
a "pending" row, never opens the actual PR (human does).

## 2. Per-feature test tracker (Feature list with `passes`)

**Status:** No schema, no code. Concept from Anthropic's eval framework,
not grounded in any reference harness.

**Three interpretations considered (all deferred):**
- **(A) Per-feature test tracker** — `feature_name`, `passes`, `last_run_at`,
  `last_output`. Hook = test-runner that parses pytest output. Use case:
  "did the last run verify login + search?".
- **(B) Per-skill quality flag** — `passes_quality_review: bool` on each
  `skills_index` row, set by the LLM curator pass. Skills failing review
  are hidden. Replaces Hermes-style `state: active|stale|archived`.
- **(C) Smoke-test suite tracker** — `smoke_name`, `passes`, `duration_ms`,
  `last_failure_message`. Hook = wrapper running our 14 `manual_*.py` smokes.

**Re-introduce when ANY of:**
- We have ≥ 1 reviewer asking "did the last test run cover feature X?" —
  build **(A)**. Schema: `feature_evals(run_id, feature_name, passes,
  last_output, captured_at)`.
- The LLM curator starts producing false-positive skill creations that we
  need to filter — build **(B)**. Schema: `passes_quality_review BOOL` on
  `skills_index`.
- We need a CI-style "all smokes pass" gate before deploys — build **(C)**.
  Schema: `smoke_runs(smoke_name, passes, duration_ms, last_failure,
  last_run_at)`. ~30 LoC for the wrapper + 1 endpoint.

**Prefer (C) first** if/when we add it — it's the smallest, most directly
useful, and reuses the 14 existing manual smokes. **(B)** second if the
curator's quality drift becomes painful. **(A)** last, only if the test
corpus outgrows a single name-to-test mapping.

## 3. Workspace PR (job → branch → owner/repo PR)

**Status:** Not built. Was considered under "PR opener" but lives in a
different layer (orchestrator step, not curator).

**Why deferred:** This is a `commit_and_open_pr` orchestrator step, not a
curator feature. The user confirmed via the 2026-06-25 decision to drop the
PR opener scope. When the orchestrator's "open PR" path is built, it should
go in `harness/orchestrator.py` as a Tier-1 step, using a GitHub App token
and the `gh` CLI (or a direct `requests.post` to the GitHub API).

**Re-introduce when:** we have ≥ 1 user who actually wants the agent to
push branches and open PRs on a remote repo (the current orchestrator
runs to completion in a local workspace container with no push step).

## Related (not from this review, but worth tracking)

- **AST-based code index** (`harness/code_index/`) — for chat-tool exposure
  of `list_symbols`, `find_callers`, `get_definition`. Augments
  `repo_analyzer` / `summarize_repo`. v1.1+ since text-based FTS memory
  covers v1.
- **Auth (HTTP basic env-var)** — dropped for v1 (local-only deployment).
  Re-add when we move off the laptop.
- **Multi-tenant `user_id` (Path B)** — already deferred to v1.1.
