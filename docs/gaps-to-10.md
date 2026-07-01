# Gaps to 10/10

**Goal:** Bring every dimension of TestAI to 10/10 for a single-tenant deployment.
**Method:** Identify gaps → prioritize → design → implement → verify.

---

## Dimension Scores (from test-user-assessment-report.md)

| Dimension | Current Score | Target |
|---|---|---|
| Dashboard UI | 9/10 | 10 |
| API Surface | 9/10 | 10 |
| Agent Engine | 9/10 | 10 |
| LLM Integration | 9/10 | 10 |
| Sandbox / Execution | 8/10 | 10 |
| CI/CD Integration | 7/10 | 10 |
| Security / Auth | 3/10 | 10 |
| Frontend Build | 2/10 | 10 |
| Test Coverage | 6/10 | 10 |

**Constraint:** Single-tenant only. Multi-tenant concerns are out of scope.

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

### G2: HTTP Authentication & Authorization (3/10 → 10/10)
- **Problem:** No HTTP auth middleware (`deps.py` has no auth)
- **Problem:** CORS allows `*` origins
- **Problem:** All API endpoints are open to anyone with network access
- **Constraint:** Single tenant, so no multi-tenant isolation needed. Still need auth to prevent unauthorized access.

### G3: CI/CD Integration Depth (7/10 → 10/10)
- **Problem:** Some integration endpoints are thin (Linear/Jira/Sentry are stubs)
- **Problem:** No CI/CD e2e pipeline test (G48 from gap analysis)

### G4: Sandbox / Execution (8/10 → 10/10)
- **Problem:** Docker Desktop instability on Windows (crashes, API errors)
- **Problem:** Per-subagent memory isolation deferred (G30)
- **Problem:** GPU support missing (G49)

### G5: Test Coverage (6/10 → 10/10)
- **Problem:** No orchestrator integration tests (G24)
- **Problem:** No codegraph tool tests (G36)
- **Problem:** No CI/CD e2e pipeline test (G48)

### G6: P2 Bug Fixes
- 10: Legacy HookRegistry used in plugins
- 11: `json` re-imported inside loop
- 12: Dependency graph false positives
- 13: Knowledge graph tool no cache
- 14: Curator ignores `db` argument
- 15: Curator first-run fragility
- 16: Pricing cache TTL unit hidden
- 17: `discover_plugins` swallows errors
- 18: MCPClient constructor no config
- 19: Import mismatch (documented, already resolved)
- 20: Lifespan swallows SandboxManager errors
- 21-25: P3 polish items

### G7: API Surface Polish (9/10 → 10/10)
- **Problem:** Router prefix collision (`/sessions/{id}` vs `/sessions/recordings`)
- **Problem:** Router duplication across baskets
- **Problem:** In-memory stores (TestPlans, Workflows) lost on restart

---

## Prioritization

TBD — will be determined through the interview process.

---

### G8: Runtime React Errors
- **Problem:** React error #31 on `/workflows` — a workflow step object is being used as a React element type. Root cause not yet identified
- **Fixes applied (18 files):**
  - 7 `Record<string, any>` icon maps → `Record<string, ElementType>` — `workflows/executions`, `audit`, `notifications`, `BlueprintPanel`, `AgentsPanel`, `ChannelsPanel`, `AppHeader`
  - 6 `icon: any` prop types → `icon: ElementType` — `agents/[name]`, `admin`, `cost`, `evaluate`, `quality`, `BackendProvidersSettings`
  - 1 `FolderIcon(props: any)` → `props: React.SVGProps<SVGSVGElement>` in `AdvancedPipelineConfig.tsx`
  - 1 `React.lazy` missing ErrorBoundary → wrapped in `settings/page.tsx:runner`
  - 1 `SavedFilters.tsx` — `icon: string` → `IconName` union type derived from `ICON_MAP as const`
  - 1 barrel re-export (`pipeline/index.ts:48`) — source changed to named export, import updated
  - 7 `React.lazy` wrappers — verified correct, no changes needed
  - ~10 `React.ReactNode` icon fields — verified correct pattern (pre-rendered JSX elements, rendered as `{icon}`)
- **TypeScript:** Passes with 0 errors
- **Remaining:** The specific `/workflows` error still needs runtime debugging
