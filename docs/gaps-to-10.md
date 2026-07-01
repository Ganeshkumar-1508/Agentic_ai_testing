# Gaps to 10/10

**Goal:** Bring every dimension of TestAI to 10/10 for a single-tenant deployment.
**Method:** Identify gaps → prioritize → design → implement → verify.

---

## Dimension Scores (from test-user-assessment-report.md)

| Dimension | Previous | Current | Target |
|---|---|---|---|
| Dashboard UI | 9/10 | 9/10 | 10 |
| API Surface | 9/10 | 9/10 | 10 |
| Agent Engine | 9/10 | 9/10 | 10 |
| LLM Integration | 9/10 | 9/10 | 10 |
| Sandbox / Execution | 8/10 | 8/10 | 10 |
| CI/CD Integration | 7/10 | 7/10 | 10 |
| Security / Auth | 3/10 | 3/10 | 10 |
| Frontend Build | 2/10 | **10/10** | 10 |
| Test Coverage | 6/10 | 6/10 | 10 |

**Constraint:** Single-tenant only. Multi-tenant concerns are out of scope.

### Phase Readiness (verified against codebase 2026-07-01)

| Phase | Gaps | Fixed | Partial | Missing | Readiness | Notes |
|---|---|---|---|---|---|---|
| Phase 1 (Reliability) | 7 | 7 | 0 | 0 | **~100%** | Complete |
| Phase 2 (Isolation) | 7 | 6 | 1 | 0 | **~95%** | G34 zombie cleanup is dead code only |
| Phase 3 (Observability) | 12 | 8 | 2 | 2 | **~70%** | G24, G48 still missing; G36, G37, G39, G46 were wrongly reported missing |
| Phase 4 (Intelligence) | 10 | 7 | 3 | 0 | **~80%** | G26, G31, G40 partial; G35, G41, G45 were wrongly reported missing |
| Phase 5 (User Facing) | 6 | 4 | 2 | 0 | **~75%** | G43, G47 wrongly reported missing; G9, G44 partial |

---

## Gap Register

### G1: Frontend Build Reliability (2/10 → 10/10)
- **Problem:** `npm run build` fails on Windows — `lightningcss.win32-x64-msvc.node` missing from optionalDependencies
- **Problem:** Docker frontend build times out (2+ hours) and frequently gets ECONNRESET from npm registry
- **Constraint:** Single tenant, so we only need one reliable build path
- **Fix applied:**
  - Added missing optionalDependencies: `lightningcss-win32-x64-msvc`, `@tailwindcss/oxide-win32-x64-msvc`, `lightningcss-linux-x64-gnu`, `@tailwindcss/oxide-linux-x64-gnu`
  - Set npm fetch-timeout to 600000ms in Dockerfile.frontend
  - Added `--os=linux --cpu=x64` fallback for gnu variants in npm install
  - Will build with `--network=host` to bypass Docker DNS issues
- **Verification:** Docker build succeeded (frontend image built, Next.js compiled in 98s)
- **Remaining:** `ignoreBuildErrors` flipped to `false` — TypeScript errors in tests fixed by installing `@testing-library/dom`

### G2: HTTP Authentication & Authorization (3/10 → 10/10) — BLOCKING
- **Problem:** No HTTP auth middleware (`deps.py` has no auth)
- **Problem:** CORS allows `*` origins
- **Problem:** All API endpoints are open to anyone with network access
- **Constraint:** Single tenant, so no multi-tenant isolation needed. Still need auth to prevent unauthorized access.

### G3: Test Coverage (6/10 → 10/10) — PARTIAL
- **G24:** No orchestrator integration tests — CONFIRMED MISSING. Unit tests exist but all patch out sandboxes. No full lifecycle test.
- **G48:** CI/CD e2e pipeline test — SKELETON EXISTS. `e2e.yml` runs 3 HTTP health checks only. No real pipeline test.
- ~~G36: No codegraph tool tests~~ — VERIFIED INCORRECT. `test_codegraph_tools.py` (287 lines) tests all 4 tools.

### G4: Sandbox / Execution (8/10 → 10/10) — 95% COMPLETE
- **G34:** Zombie session cleanup — CONFIRMED. `sweep_orphan_sessions()` and `reap_orphan_containers()` exist as dead code but are never wired into startup/scheduler loops.
- Docker Desktop instability — platform-level issue, not a code gap.

### G5: Observability Gaps — 70% COMPLETE
- **G32:** Per-tool cost tracking — CONFIRMED. `ToolCostTracker` in-memory only (`tool_dispatch.py:74`), `token_usage` table lacks `tool_name` column.
- **G38:** Dead component cleanup — CONFIRMED PARTIAL. Stale DB references to deleted tools, no automated detection.
- ~~G36: No codegraph tool tests~~ — VERIFIED INCORRECT. `test_codegraph_tools.py` exists (287 lines).
- ~~G37: Live terminal streaming missing~~ — VERIFIED INCORRECT. `pty_bridge.py` + WebSocket `/sandbox/{session_id}/pty` exists.
- ~~G39: Provider health display missing~~ — VERIFIED INCORRECT. `ProviderHealthSection` exists in `models/page.tsx:148`.
- ~~G46: Tool health dashboard missing~~ — VERIFIED INCORRECT. `ToolsHealthPanel` in `ObservabilityPanels.tsx:138`.

### G6: Intelligence Gaps — 80% COMPLETE
- **G26:** Context modes (isolated/fork) — CONFIRMED PARTIAL. Only auto-compression exists, no isolated/fork modes.
- **G31:** Memory tool text-only — CONFIRMED PARTIAL. Text-first entries in flat markdown files, no structured schema.
- **G40:** Cross-session learning — CONFIRMED PARTIAL. ReflexionMemory + MemoryTool exist but limited to error-pattern reflections.
- ~~G35: Context compression missing~~ — VERIFIED INCORRECT. Full implementation: `compressor.py` (650 lines), `pruning.py` (549), `summary.py` (612).
- ~~G41: Skill versioning partial~~ — VERIFIED INCORRECT. `VersionTracker` with history, agent tools, admin API endpoint.
- ~~G45: Flaky test root cause partial~~ — VERIFIED INCORRECT. Full `rca.py` (304 lines) with classification and severity.

### G7: User-Facing Gaps — 75% COMPLETE
- **G9:** PR auto-merge — CONFIRMED. Referenced in docs/prompts but no implementation.
- **G42:** Cross-session chat context — CONFIRMED MISSING. Memory persists but conversation context does not.
- **G44:** Artifact lifecycle UI — CONFIRMED PARTIAL. Backend TTL system exists, no UI config.
- ~~G43: Sandbox config UI partial~~ — VERIFIED INCORRECT. Full UI in `RunnerConfigSettings.tsx` (333 lines) + backend API.
- ~~G47: Multi-repo orchestration partial~~ — VERIFIED INCORRECT. Full implementation: `cross_repo.py`, `multi_repo_coordinator.py`, API routes, orchestrator integration.

### G8: P2 Bug Fixes — DONE
- Legacy HookRegistry, json re-import, dependency graph, KG cache, curator bugs, pricing cache, plugin errors, MCPClient config — all fixed or documented.

---

## Prioritization

| Priority | Gap | Phase | Effort | Impact |
|---|---|---|---|---|
| **P0** | G2: HTTP Auth | Security | 2-3d | Unblocks production deployment |
| **P1** | G34: Zombie cleanup wiring | Isolation | 1d | Prevents resource leaks |
| **P1** | G24: Orchestrator integration tests | Test Coverage | 3-5d | Validates full agent lifecycle |
| **P2** | G48: CI/CD e2e test | Test Coverage | 2-3d | Catches regressions |
| **P2** | G32: Per-tool cost tracking | Observability | 2d | Cost visibility per tool |
| **P3** | G26: Context modes | Intelligence | 3-5d | Advanced subagent context |
| **P3** | G40: Cross-session learning | Intelligence | 3-5d | Smarter agents over time |
| **P3** | G9: PR auto-merge | User Facing | 1-2d | Reduces manual work |
| **P3** | G44: Artifact lifecycle UI | User Facing | 1d | Data retention management |
| **Low** | G31: Memory structured entries | Intelligence | 2-3d | Richer memory format |
| **Low** | G38: Dead component cleanup | Observability | 1d | Codebase hygiene |

---

### G8: Runtime React Errors — **FIXED**
- **Root cause:** `WorkflowDefinition.to_dict()` returned `steps` as a full array of step objects, not a count. The frontend rendered `{wf.steps || 0}` which tried to render objects as React children. React 19 throws error #31.
- **Fix (3 files):**
  - `backend/harness/workflows/models.py` — Added `steps_count` to `to_dict()` return
  - `src/app/(dashboard)/workflows/page.tsx` — Uses `steps_count` instead of `steps`
  - `src/components/cron/BlueprintPanel.tsx` — Uses `steps_count` instead of `steps`
- **Additional type safety fixes (20+ files):**
  - 7 `Record<string, any>` icon maps → `Record<string, ElementType>`
  - 6 `icon: any` prop types → `icon: React.ElementType`
  - 1 `FolderIcon(props: any)` → `React.SVGProps<SVGSVGElement>`
  - 1 `React.lazy` missing ErrorBoundary → wrapped in settings page
  - 1 `SavedFilters` → `IconName` union type
  - 1 barrel re-export → named export
  - 11 dead `const API = ...` variables removed
  - 11 redundant `as any` casts removed from dashboard/history pages
- **TypeScript:** 0 errors. Tests: 90/90 pass.
