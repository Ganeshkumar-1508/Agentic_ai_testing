# Architecture Refactor — Decision Log

**Started:** 2026-06-03
**Method:** Skill-driven pruning with per-category Q&A

---

## Q&A 1: Pruning scope

**Question:** What do we prune first?

**Answer:** Prune speculative code (dead dependencies, never-used packages).

**Decision:** Tackle clear wins first (no-impact deletions). Gray areas deferred until wireframes exist.

---

## Q&A 2: Stub routers + plans/ + healing

**Question:** Delete stub routers? Touch plans/? Delete broken healing_api?

**Answer:**
1. Plans/ folder → **DO NOT TOUCH**
2. Self-healing (healing_api) → **KEEP** — it's for Greptile greploop / testim research. Module not created yet, but intended.
3. Gray area routers (defect, sprint, triage, generate, digest, artifacts) → **Create wireframes first** using design-taste-frontend skill, save in plans/. Then re-ask.

---

## Q&A 3: Wireframe approach

**Question:** How to wireframe these 6 features?

**Answer:** Research each feature's backend module to understand what data it provides, then create one HTML wireframe per feature showing the key UI screens. Save in plans/.

---

## Q&A 4: Router wireframes created

**Created:** 6 wireframe HTML files in `plans/`:
- `defect-prediction-wireframe.html`
- `sprint-quality-trends-wireframe.html`
- `defect-triage-wireframe.html`
- `test-generation-wireframe.html`
- `daily-digest-wireframe.html`
- `artifacts-wireframe.html`

**Status:** Awaiting review. User asked to re-ask the keep/delete question after wireframes exist.

---

## Q&A 5: Stub routers — final decision

**Question (re-ask):** With wireframes in `plans/`, keep or delete the 6 stub routers?

**Answer:** **KEEP.** API surface stable; backend modules are real working code. Wireframes serve as future feature specs.

---

## Q&A 6: Dead dependencies — confirmed deletions

**Deleted (clear wins, no impact):**
- `SQLAlchemy` from `backend/requirements.txt` (never imported — all DB access is raw asyncpg)
- `bun-types` from `package.json` (project runs on Node.js, not Bun)
- `std-env` from `package.json` (not imported)
- `z-ai-web-dev-sdk` from `package.json` (not imported)
- `@radix-ui/react-icons` from `package.json` (lucide-react used instead)

**Kept (still used):**
- `cross-env` — used in package.json `"start"` script, not in source imports

---

## Q&A 7: CI Pipeline

**Problem:** Existing `.github/workflows/testai-pr.yml` sends a webhook to `localhost:8001` (broken in CI). No code quality gates run.

**Solution (researched from Hermes + OpenClaude patterns):**
- Keep existing `testai-pr.yml` as-is (product integration, not CI)
- Add new `.github/workflows/ci.yml` with:
  - **Frontend job:** checkout → setup Node → npm ci → tsc --noEmit → eslint → vitest → next build
  - **Backend job:** checkout → setup Python → pip install → import check → pytest

**Decision:** Two workflow files. New `ci.yml` runs on PR/push to main.

---

## Q&A 8: Router consolidation

**Problem:** 37 individual router modules → 34 import lines + 34 `include_router()` calls.

**Solution:** Created 4 aggregation modules:
- `agent_routes.py` — chat, pipeline, delegate, runs, events, sandbox
- `settings_routes.py` — settings, tools_management, permissions, cost, kanban
- `admin_routes.py` — admin, ops, health, logs, analytics + 14 stub routers
- `integration_routes.py` — integrations, pr_webhook, pr_manager, notify, traceability, testcases

**Result:** 34 import lines → 4. 34 registrations → 4 `for` loops. main.py: 385→322 lines.

---

## Q&A 9: Single-file query engine (merge mixins)

**Deleted (5 files):** emitters.py, interrupts.py, reflexion.py, tools.py, loop.py
**Kept:** agent.py (659 lines — merged), reflexion_memory.py, validation.py, curation.py, deps.py, protocols.py
**Updated:** `__init__.py` exports, test file (MRO test → method-existence test)

**Result:** 12 → 7 files in `harness/agent/`. Agent is now a single unified class.

---

## Q&A 10: Tool self-registration + check_fn

**Changes:**
1. Updated `registry.register()` to forward check_fn, default_level, etc.
2. Added helpers: `env_available()`, `any_env_available()`, `binary_available()`, `check_any()`
3. Added check_fn to 7 tools: browser, computer_use, image_generate, database_query, send_message, web_search, docker_executor

**Result:** Without API keys → 48 tools shown. With API keys → 51+ tools. Tools gracefully disable.

---

## Q&A 11: Startup instrumentation

**Added:** `StartupTimer` class with 16 checkpoints across the 18-step lifespan.
**Output:** Timed report at INFO level on boot showing each phase with delta.

---

## Q&A 12: Agent workspace mount into sandbox

**Fix:** Moved `agent_workspace` mount from `__init__` (eager) to `_effective_scope` (lazy).

---

## Q&A 13: Pipeline enhanced_goal KG hint fix

**Fix:** Replaced npm reference with `kg_generator` tool hint.

---

## Q&A 14: Sandbox reuse and lifecycle

**Answer:** Yes — per-repo volumes persist. Container destroy ≠ data loss.

**Backend state:**
- `DELETE /sandbox/{session_id}` — destroy endpoint exists
- `POST /sandbox/exec-containers/reap` — reaper exists
- Sandbox TTL is currently hardcoded in `docker_executor.py:reap_idle_containers`

**Pending frontend items:**
- Sandbox TTL configuration UI (Settings page)
- Manual destroy button on sandbox page
- Knowledge Graph page matching `plans/knowledge-graph-understand-anything.html` wireframe

---

*End of decision log. Update as new questions are resolved.*
