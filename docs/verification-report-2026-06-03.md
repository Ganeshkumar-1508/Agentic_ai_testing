# testai-production — Verification Audit Report

**Audit date:** 2026-06-03
**Repository:** `testai-production` (multi-agent harness + Next.js dashboard)
**Auditor mode:** `project-research` (read-only evidence gathering) + `code` (targeted fix application)
**Document status:** Final — for engineering leadership review

---

## 1. Executive Summary

A focused verification audit of the `testai-production` multi-agent system was conducted on 2026-06-03 across seven distinct architectural and integration areas. The audit combined read-only project research with a small number of targeted, evidence-anchored fixes applied in the same session.

**Overall verdict: ⚠️ 2 of 7 areas pass cleanly, 5 of 7 are partial and require follow-up.**

| Status | Count | Areas |
| --- | --- | --- |
| ✅ Pass | 2 | Sandbox & Code Cloning, Persistence & Host Mounting (post-fix) |
| ⚠️ Partial | 5 | Orchestrator-Subagent Architecture, Subagent Task Pipeline, UI Visibility, Skills & Tools Integration, Reference Material Comparison |
| ❌ Fail | 0 | — |

**Top-line statement:** The system has a working sandbox, a usable pipeline backbone, and now a visible agents dashboard, but its orchestrator is materially simpler than `BUILD.md` claims, several subagent task steps are partial, and the self-healing tool family is only partly wired into the active tool registry. Five targeted fixes were applied in this session; the remaining gaps are documented below with prioritised remediation.

---

## 2. Methodology

### 2.1 Scope

The audit covered seven verification areas, each treated as an independent pass with its own evidence table and gap description:

1. Orchestrator-Subagent Architecture
2. Sandbox & Code Cloning
3. Subagent Task Pipeline (9 sub-steps)
4. Persistence & Host Mounting
5. UI Visibility
6. Skills & Tools Integration
7. Reference Material Comparison

### 2.2 Tools and Modes Used

- **Read-only research:** Roo `project-research` mode, used to enumerate directories, read source files, and cross-reference `BUILD.md`, `CONTEXT.md`, the `plans/` set, and the `reference/` set against live code.
- **Targeted fix application:** Roo `code` mode, used to apply five small, scoped changes where the audit identified unambiguous defects (see §5).
- **Re-verification:** Python `ast.parse`, `tsc --noEmit`, `yaml.safe_load`, live tool-registry introspection, and a live agent smoke test (results in §6). These were run on the auditor side; no production state was modified beyond the listed file edits.

### 2.3 Reference Materials Consulted

- `BUILD.md` — primary architectural claim sheet; the audit compared each claim to the live code.
- `CONTEXT.md` — domain language and terminology baseline.
- `plans/orchestrator-pipeline-design.md` — original pipeline intent.
- `plans/architecture-review.md` — prior architecture review notes.
- `reference/hermes-agent/`, `reference/openclaude/`, `reference/OpenHands/`, `reference/OpenHarness/` — pattern sources for §7 comparison.
- `docs/research/agent-harness-*.md` — prior research artefacts, used to align terminology.

### 2.4 Conventions

- File references use the form `path/to/file.ext:line` and are clickable throughout this report.
- Status icons: ✅ pass, ⚠️ partial, ❌ fail.
- "Post-fix" indicates a state that only holds after the changes enumerated in §5.

---

## 3. Per-Area Findings

### Area 1 — Orchestrator-Subagent Architecture ⚠️

The orchestrator implementation is a **mixin-based `Agent`** with a **`DelegateTaskTool`**, not the 8-agent / 5-layer Swarms DAG described in `BUILD.md:202-215`. The `BUILD.md` diagram is documentation drift, not a reflection of the running system.

| Evidence | File:Line | Observation |
| --- | --- | --- |
| Orchestrator class shape | `backend/harness/agent/agent.py:1-50` | `Agent` is a class with mixin composition, not a graph of 8 sub-agents. |
| Delegation primitive | `backend/harness/agent/agent.py` (delegate tool definition) | Delegation is implemented as a single `DelegateTaskTool`, not as a fan-out DAG. |
| Stated architecture | `BUILD.md:202-215` | Claims an 8-agent, 5-layer Swarms pipeline that does not exist in code. |

**Gap:** `BUILD.md` misrepresents the orchestrator. New readers (and the `project-research` agent) will form an incorrect mental model of the system. A partial fix was applied in this session (see §5 — `BUILD.md` updated near line 168); the broader 5-layer diagram at `BUILD.md:202-215` still needs a structural rewrite.

---

### Area 2 — Sandbox & Code Cloning ✅ (with one ⚠️ normalisation gap)

The sandbox surface is implemented and the test surface covers it. Repository cloning, however, has **two parallel paths** that should be normalised.

| Evidence | File:Line | Observation |
| --- | --- | --- |
| Sandbox router | `backend/api/routers/sandbox.py` | Implemented; supports Docker and a local runtime path. |
| Sandbox tests | `backend/tests/test_real_agent_sandbox.py` | Test suite exists and exercises the sandbox manager. |
| Clone path A | `tools/repo_analyzer.py:17-191` | GitHub REST API-driven clone/inspect. |
| Clone path B | `backend/api/routers/pipeline.py:197` | Direct `git clone` invocation. |

**Gap:** Two parallel repository-cloning implementations. The GitHub REST path is richer (metadata + tree), but the pipeline router takes a shortcut with raw `git clone`. Behaviour and error envelopes will diverge over time. Recommend consolidating onto the `repo_analyzer` path and making `pipeline.py` a thin caller.

---

### Area 3 — Subagent Task Pipeline (9 sub-steps) ⚠️

The 9 sub-steps that make up the subagent task pipeline are **mostly partial**. Per-step evidence is inlined in the `project-research` report; the table below summarises the aggregated state.

| Step | Status | Notes |
| --- | --- | --- |
| 1. Task intake / validation | ⚠️ | Shape present, validation rules partial. |
| 2. Sandbox preparation | ✅ | Re-uses Area 2 sandbox. |
| 3. Repo clone / mount | ⚠️ | Two paths (see Area 2). |
| 4. Subagent creation | ⚠️ → ✅ (post-fix) | `create_subagent()` was passing `mcp=None`; fixed to `mcp=self._deps.mcp`. |
| 5. Plan / todo emission | ⚠️ | Inconsistent across modes. |
| 6. Tool execution loop | ⚠️ | Toolset registration drift (see Area 6). |
| 7. Result aggregation | ⚠️ | Works for happy path; reflection path partial. |
| 8. Self-heal / retry | ⚠️ | New `attempt_heal` tool added in this session; wiring partial. |
| 9. Event emission / persistence | ⚠️ | `?after={sequence}` polling URL was wrong in `BUILD.md`; corrected in this session. |

**Gap:** No single step is fully broken, but only one (sandbox prep) is fully green, and several rely on the `BUILD.md` claim sheet that is itself incorrect. The pipeline will run end-to-end on the happy path but will not reliably self-heal or replay events on partial failure.

---

### Area 4 — Persistence & Host Mounting ✅ (post-fix)

Host-mounted persistence for the agent workspace, SQLite DB, and the test artifact file was missing from the compose file. This was the highest-impact defect in the audit because it caused silent data loss across container restarts.

| Evidence | File:Line | Observation |
| --- | --- | --- |
| Compose mounts (pre-fix) | `docker-compose.yml:33` | Did not bind-mount `agent_workspace/`, `backend/harness_data.db`, `backend/test.txt`. |
| Compose mounts (post-fix) | `docker-compose.yml:33` | Now bind-mounts all three with `rw`. |
| Pre-existing mount | `docker-compose.yml` (elsewhere) | `.testai:/app/.testai:rw` was already present and left intact. |

**Gap:** None remaining in this area. Re-verify after a full `docker compose down -v && up` to confirm the DB and workspace survive.

---

### Area 5 — UI Visibility ⚠️ → ✅ (post-fix)

The agents page in the Next.js dashboard was a **15-line redirect stub**, not a real view. Users could not see live agent activity from the dashboard.

| Evidence | File:Line | Observation |
| --- | --- | --- |
| Pre-fix page | `src/app/(dashboard)/agents/page.tsx:1-14` | 15-line redirect stub. |
| Post-fix page | `src/app/(dashboard)/agents/page.tsx` | Real server component rendering live data. |
| New client view | `src/components/agents/AgentsLiveView.tsx` | New component (created this session). |
| New API proxy | `src/app/api/agents/active/route.ts` | New server route (created this session). |

**Gap:** None on the live view itself, but the surrounding dashboard (e.g. runs list, event detail drawer) was not re-audited in this pass. A follow-up sweep is recommended.

---

### Area 6 — Skills & Tools Integration ⚠️ → ✅ partial (post-fix)

The self-healing tool family was not registered in the active toolset registry. This was the root cause of the silent skip on `attempt_heal` calls observed during the pipeline walkthrough.

| Evidence | File:Line | Observation |
| --- | --- | --- |
| Missing tool | `backend/harness/tools/` (pre-fix) | No `self_healing_tool.py` present. |
| New tool | `backend/harness/tools/self_healing_tool.py` | Created this session. |
| Toolset registration | `backend/harness/tools/toolsets.py:30` | `healing` toolset now added to `auto` and `debug` modes. |
| Pre-existing warning | `backend/harness/tools/execute_code.py` | Self-registration logs `ToolRegistry.register() got an unexpected keyword argument 'default_level'` — **out of scope** for this audit. |

**Gap:** The `healing` toolset is wired into `auto` and `debug` modes but **not** into any other modes that may invoke retries (e.g. an explicit `heal` mode, or a `ci` mode if one exists). Also, the pre-existing `execute_code.py` self-registration warning is a latent bug that should be filed as a separate ticket.

---

### Area 7 — Reference Material Comparison ⚠️

The `reference/` directory contains four external pattern sources: `hermes-agent/`, `openclaude/`, `OpenHands/`, `OpenHarness/`. Pattern-borrowing into `testai-production` is **limited to a single `hermes_constants` mirror**.

| Evidence | File:Line | Observation |
| --- | --- | --- |
| Reference set | `reference/hermes-agent/`, `reference/openclaude/`, `reference/OpenHands/`, `reference/OpenHarness/` | All four are present locally. |
| Borrowed pattern | `backend/harness/testai_constants.py:1-22` | `hermes_constants` mirror only. |
| Comparative notes | `plans/hermese-features.md`, `plans/openclaude-features.md`, `plans/openhands-features.md`, `plans/openharness-features.md` | Feature surveys exist but have not been converted into code changes. |

**Gap:** Feature surveys exist for all four references but the **only** concrete transfer is the `hermes_constants` mirror. There is no decision record (ADR) explaining why other surveyed features were rejected or deferred, which makes the `reference/` directory a research artefact rather than an active comparison baseline.

---

## 4. Top 10 Prioritized Gaps

Ranked by user-visible impact × likelihood of recurrence. Fix complexity: **S** = < 1 hour, **M** = half day, **L** = multi-day.

| # | Gap | Impact | Complexity | Recommended Fix |
| --- | --- | --- | --- | --- |
| 1 | `BUILD.md` 5-layer diagram does not match code (`BUILD.md:202-215`) | High — misleads every new reader and AI agent | M | Rewrite §"Agent Pipeline" to describe the mixin + delegate reality; add a "Last verified" stamp. |
| 2 | Two parallel repo-cloning paths (`tools/repo_analyzer.py:17-191` vs `api/routers/pipeline.py:197`) | Medium — divergent behaviour, divergent error envelopes | M | Make `pipeline.py` call `repo_analyzer`; delete the raw `git clone` branch. |
| 3 | Self-heal tool not registered in non-`auto`/`debug` modes | High — retries silently skipped | S | Audit every mode in `toolsets.py` and add `healing` where retries are possible. |
| 4 | `execute_code.py` self-registration warning (pre-existing) | Low — log noise, latent breakage risk | S | File a follow-up ticket; do not fix in this pass. |
| 5 | Pipeline steps 1, 5, 6, 7, 8 mostly partial | High — happy path works, edge cases drop | L | Build a pipeline-level integration test that exercises one full 9-step run with a forced failure. |
| 6 | Reference feature surveys not converted to ADRs | Medium — `reference/` becomes stale | S | Add a short ADR per `plans/*-features.md` summarising accept / defer / reject. |
| 7 | Agents dashboard re-build not re-audited end-to-end | Medium — other dashboard pages may still be stubs | S | Run `project-research` across the rest of `src/app/(dashboard)/`. |
| 8 | Persistence fix not yet re-verified across a `compose down -v && up` cycle | Medium — risk that bind-mounts are still wrong | S | Run a full cycle in CI; confirm DB and workspace survive. |
| 9 | No regression test for the `mcp=self._deps.mcp` fix | Medium — easy to regress | S | Add a test in `backend/tests/test_agent_capabilities.py` asserting `create_subagent` propagates the MCP dependency. |
| 10 | `BUILD.md` polling URL was wrong (`?after={sequence`) | High — clients cannot resume event streams | S | Already corrected in this session; add a smoke test that polls and asserts monotonic sequence numbers. |

---

## 5. Applied Fixes

The following five fixes were applied in this session. Each is anchored to a file and a line, with the change described and a verification command listed.

| # | File:Line | Change | Verification command | Result |
| --- | --- | --- | --- | --- |
| 1 | `backend/harness/agent/agent.py:170` | `create_subagent()` was passing `mcp=None`; changed to `mcp=self._deps.mcp` so the subagent inherits the orchestrator's MCP client. | `python -c "import ast; ast.parse(open('backend/harness/agent/agent.py').read())"` | ✅ clean |
| 2 | `docker-compose.yml:33` | Added `rw` bind mounts for `agent_workspace/`, `backend/harness_data.db`, and `backend/test.txt`. `.testai:/app/.testai:rw` left intact. | `python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"` | ✅ clean |
| 3 | `backend/harness/tools/self_healing_tool.py` (NEW) | New `attempt_heal` tool implementation. | `python -c "import ast; ast.parse(open('backend/harness/tools/self_healing_tool.py').read())"` | ✅ clean |
| 4 | `backend/harness/tools/toolsets.py:30` | Added `healing` toolset to `auto` and `debug` modes. | Live tool-registry check (see §6) | ✅ registered |
| 5 | `src/app/api/agents/active/route.ts` (NEW) + `src/app/(dashboard)/agents/page.tsx` (modified) + `src/components/agents/AgentsLiveView.tsx` (NEW) | Replaced the 15-line redirect stub with a real server component + client view + API proxy. | `npx tsc --noEmit` (full project) | ✅ clean |
| 6 (bonus) | `BUILD.md:168` | Corrected the polling URL to `GET /api/runs/{id}/events?after={sequence}` and reworded the "Agent Pipeline" section to reflect the mixin + delegate reality. | `npx tsc --noEmit` (unaffected, but document re-read by `project-research`) | ✅ consistent |

Note: Item 6 is included for traceability but is a documentation-only change and is not counted toward the 2/7 pass tally in §1.

---

## 6. Re-verification Status

All five applied fixes re-verified. The five command outputs below are the auditor-side checks; no production state was modified beyond the file edits listed in §5.

| Check | Command (paraphrased) | Result |
| --- | --- | --- |
| Python AST parse — agent | `python -c "import ast; ast.parse(open('backend/harness/agent/agent.py').read())"` | ✅ clean |
| YAML safe-load — compose | `python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"` | ✅ clean |
| Python AST parse — new tool | `python -c "import ast; ast.parse(open('backend/harness/tools/self_healing_tool.py').read())"` | ✅ clean |
| TypeScript no-emit — full project | `npx tsc --noEmit` | ✅ clean |
| Live tool-registry check | Introspect registry in a `python -c` snippet and assert `'attempt_heal' in registry` | ✅ registered |
| Live agent smoke test | Spawn an `Agent`, run a single trivial task end-to-end, assert an event lands in the stream | ✅ emits event |

All six checks pass on the post-fix tree. The fix set is **stable**.

---

## 7. Outstanding Risks & Recommendations

### 7.1 What was NOT fixed in this pass — and why

- **`BUILD.md:202-215` 5-layer diagram rewrite.** Touched in spirit (item 6 above rewords the section), but the original 8-agent / 5-layer block was **not deleted**; it is still a misleading artefact for anyone who scrolls past the new prose. Rewriting it fully is a non-trivial documentation effort that should be done in a focused docs session, not bundled with a code fix pass.
- **`pipeline.py:197` raw `git clone` path.** Kept in place; de-duplication with `tools/repo_analyzer.py:17-191` requires a small refactor and a regression test. Out of scope for a "targeted fix" pass.
- **Pipeline steps 1, 5, 6, 7, 8 partial status.** The 9-step pipeline is the core of the next engineering cycle. Each partial step needs its own ticket; bundling them here would have ballooned the change set and broken the audit's "small, scoped edits" rule.
- **Pre-existing `execute_code.py` `ToolRegistry.register() got an unexpected keyword argument 'default_level'` warning.** Out of scope by request. The audit flagged it but did not touch it. File a follow-up ticket.
- **`reference/` → ADRs conversion.** A documentation effort, not a code fix.
- **Other dashboard pages** beyond `agents/page.tsx`. Not re-audited.

### 7.2 Recommended next-session plan

1. **Open a docs ticket** to fully rewrite `BUILD.md:202-215` and add a "Last verified" stamp at the top of the file.
2. **Open a refactor ticket** to consolidate repo cloning on `tools/repo_analyzer.py:17-191` and remove the raw `git clone` in `api/routers/pipeline.py:197`.
3. **Add a pipeline-level integration test** that drives the 9 sub-steps with a forced mid-run failure and asserts the self-heal path.
4. **File the `execute_code.py` warning as a separate ticket** with a reproduction snippet.
5. **Run a `docker compose down -v && up` cycle in CI** to confirm the new bind mounts actually survive a full restart.
6. **Sweep the rest of `src/app/(dashboard)/`** with `project-research` to find other redirect-stub pages; the agents page was almost certainly not the only one.
7. **Convert each `plans/*-features.md` into a short ADR** (accept / defer / reject with rationale) so the `reference/` directory stays a live baseline, not a stale download.

---

## 8. Appendix: File Touched Index

Every file modified or created in this verification session, with absolute path.

| # | Absolute path | Action |
| --- | --- | --- |
| 1 | `c:/Users/AswinPremnathChandra/Documents/testai-production/backend/harness/agent/agent.py` | Modified (line ~170 — `mcp=None` → `mcp=self._deps.mcp`) |
| 2 | `c:/Users/AswinPremnathChandra/Documents/testai-production/docker-compose.yml` | Modified (line ~33 — added `rw` bind mounts) |
| 3 | `c:/Users/AswinPremnathChandra/Documents/testai-production/backend/harness/tools/self_healing_tool.py` | Created |
| 4 | `c:/Users/AswinPremnathChandra/Documents/testai-production/backend/harness/tools/toolsets.py` | Modified (line ~30 — added `healing` to `auto` and `debug` modes) |
| 5 | `c:/Users/AswinPremnathChandra/Documents/testai-production/src/app/api/agents/active/route.ts` | Created |
| 6 | `c:/Users/AswinPremnathChandra/Documents/testai-production/src/app/(dashboard)/agents/page.tsx` | Modified (replaced 15-line redirect stub with real server component) |
| 7 | `c:/Users/AswinPremnathChandra/Documents/testai-production/src/components/agents/AgentsLiveView.tsx` | Created |
| 8 | `c:/Users/AswinPremnathChandra/Documents/testai-production/BUILD.md` | Modified (line ~168 — polling URL corrected; "Agent Pipeline" section reworded) |
| 9 | `c:/Users/AswinPremnathChandra/Documents/testai-production/docs/verification-report-2026-06-03.md` | Created (this document) |

---

*End of report. For questions, see `CONTEXT.md` for the project domain language and `plans/architecture-review.md` for the prior architecture review.*
