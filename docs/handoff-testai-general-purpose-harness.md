# Handoff: TestAI General-Purpose Agent Harness

**Date:** 27 June 2026
**Context:** Full codebase cross-reference (codegraph, 11,991 files indexed) + implementation session
**Source report:** `docs/architecture-review-general-purpose-2026-06-27.html` (updated with verification pass)

---

## 1. Verification Results

All 26 features from the original Implementation Summary (F1-F26) were cross-referenced against the current codebase using codegraph. Every feature is confirmed present and wired. See the report's Implementation Summary section for exact file paths.

**6 items originally reported as missing were found under different filenames:**

| Report Name | Actual File | Size |
|---|---|---|
| `DataPrivacySettings.tsx` | `data/privacy/DataPrivacySettings.tsx` | 4.7KB |
| `EscalationPolicySettings.tsx` | `policy/EscalationPolicySettings.tsx` | 7.4KB |
| `ModelRoutingSettings.tsx` | `routing/ModelRoutingSettings.tsx` | 6.8KB |
| `PluginManagerSettings.tsx` | `plugins/PluginManagerSettings.tsx` | 4KB |
| `StatusFooter.tsx` | `status/StatusFooter.tsx` | 5KB |
| `health_service.py` | `services/HealthService.py` | 12KB |

All 6 are imported in `src/app/(dashboard)/settings/page.tsx` as lazy loaded panels.

---

## 2. Features Built This Session (27 June 2026)

| Feature | Files | Notes |
|---|---|---|
| **DelegationTreeView rewrite** | `src/components/agents/DelegationTreeView.tsx` | SVG connector lines, spring physics, cost per node, expandable tool call list via `/api/delegate/{sessionId}/tool-calls` |
| **AgentThinkingPanel** | `src/components/agents/AgentThinkingPanel.tsx` | Live agent thinking view using shadow stream SSE |
| **WorkflowCanvas (n8n-style)** | `src/app/(dashboard)/workflows/canvas/` | @xyflow/react visual canvas, Agent/Human/Router node types |
| **WorkflowExecutor** | `backend/harness/workflow/executor.py` | DAG topological sort dispatches to `delegate_task`/`question`. Supports retry, error workflow, execution persistence |
| **BlueprintPanel integration** | `src/components/cron/BlueprintPanel.tsx` | Scheduled/Workflows tabs, lists both cron blueprints + multi-step workflows |
| **Execution History** | `src/app/(dashboard)/workflows/executions/page.tsx` | Step-level timeline, retry button, per-workflow filter via `?workflow=` |
| **Agent Evaluation Dashboard** | `src/app/(dashboard)/evaluate/page.tsx` | Arize-style four pillars: Outcome, Cost, Safety, Behavior |
| **Notification Center** | `backend/api/routers/notifications.py` | In-app bell with badge, history page, mark-read API, CSV/JSON export |
| **Agent Versioning** | `src/app/(dashboard)/agents/[name]/page.tsx` | Version snapshots on save, diff between versions, restore |
| **Audit Trail** | `backend/api/routers/audit.py` | Paginated, filterable by event type/date/agent/status, CSV/JSON export |
| **OpenTelemetry Settings** | `src/components/settings/OTelSettings.tsx` | Connection status, endpoint config, enable toggle, quick-start reference |
| **Agent Detail page** | `src/app/(dashboard)/agents/[name]/page.tsx` | Config + Versions tabs, inline editing |

---

## 3. Architectural Decisions

1. **WorkflowStep model** is shared between form view (BlueprintPanel) and visual canvas (ReactFlow). Serialization is bidirectional: `WorkflowDefinition.steps ↔ nodes[] + edges[]`.
2. **WorkflowExecutor** uses topological sort for DAG execution. It dispatches to existing primitives (`delegate_task`, `question`, `OrchestratorEngine`).
3. **Audit Trail** stamps every call with `actor: "agent"` by default. Human actions (approval, steer) set `payload["actor"] = "human"` explicitly.
4. **OpenTelemetry** integration with full GenAI semantic conventions, OTLP exporter (gRPC + HTTP), 18 span types, provider mapping.
5. **`@xyflow/react v12.11.0`** is in `package.json` — visual workflow builder without new npm deps.

---

## 4. Database Schema Changes

All new tables added to `backend/harness/memory/schema/migrations.sql`:

| Table | Purpose |
|---|---|
| `agent_versions` | Version snapshots of agent configs |
| `workflow_executions` | Execution records with step-level detail |
| `settings` | Key/value store for escalation, routing, privacy |

Existing tables leveraged (not created): `stream_events` (audit trail), `sessions` (agent versioning), `token_usage` (evaluation metrics), `notifications` (notification history), `notification_preferences` (notification config).

---

## 5. Local Backend — Detailed Analysis

The **Local Backend** feature would allow TestAI to run agents directly on the host machine (via `subprocess`) instead of inside a Docker container.

**Files in `reference/hermes-agent/tools/environments/`:**

| File | LoC | Description |
|---|---|---|
| `base.py` | 895 | `BaseEnvironment` ABC (cross-platform) |
| `local.py` | 832 | Local backend (subprocess) |
| `docker.py` | 150 | Docker backend (container) |
| `ssh.py` | 200 | SSH backend (remote) |
| `modal.py` | 100 | Modal cloud backend |
| `daytona.py` | 283 | Daytona backend |
| `singularity.py` | 120 | Singularity backend |
| `managed_modal.py` | 100 | Managed Modal (unified) |
| `__init__.py` | 10 | Module init |

Total: ~2,560 lines.

**Hermes Reference Pattern:**
- `BaseEnvironment` provides ALL shared logic: `execute()`, `_wait_for_process()`, `_wrap_command()`, `init_session()`, CWD tracking, stdin handling, activity callbacks — 700+ shared lines
- Each backend only implements `_run_bash()` (spawn the process) and `cleanup()` (release resources) — 50-150 lines each

**Two Approaches Considered:**

1. **Option A: Full Adoption (Hermes-style)** — Replace the entire `SandboxManager` with a `BaseEnvironment`-style ABC. Every backend implements `_run_bash()` and `cleanup()`.
2. **Option B: BackendProvider Wrapper (Recommended for now)** — Create a thin `BackendProvider` ABC. `SandboxManager` stays completely untouched. Old code continues using `SandboxManager` directly. New code uses `BackendProvider`.

**Decision: Option B (BackendProvider wrapper).** 
- Preserves existing battle-tested code
- Adding new backends (SSH, Modal, etc.) is trivial
- Allows gradual migration
- 0 existing references touched

---

## 6. Next Steps

1. Decide on Option A vs Option B
2. Create the `BackendProvider` ABC and implementations
3. Add a backend selector to the sandbox/agent creation UI
4. Store `session.backend` in the sessions table (column already exists but not populated)

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 327 references touched | 2-3 weeks | High regression risk | Cross-platform branches kept; add Windows integration test |
| Factory lookup is slow under load | low | medium | Cache backend instances per session_id (LRU); factory is a thin shim |
| Test rewrites miss a behavior the old tests caught | medium | high | Run old + new tests in parallel for 1 PR; compare coverage reports |
| SSH key file path handling differs between Linux/Windows | medium | medium | Port hermes' `~`-expansion + path translation verbatim |
| Child FK tables (`messages`, `tasks`, `stream_events`) need new column for backend trace | low | low | Defer — query through `sessions` join for now |

---

## 8. Definition of done

- [ ] `schema.sql` + `migrations.sql` changes applied to dev DB, no errors, idempotent on second run
- [ ] `JobSpec.backend_type` + `JobSpecRequest.backend_type` fields added
- [ ] 5 INSERT sites updated to write `backend_type`
- [ ] `BackendFactory` reads `sessions.backend_type` + `session_backend_configs.config`
- [ ] 13 production call-sites rewired to factory
- [ ] 4 test files rewritten and passing
- [ ] `sandbox_manager.py` and `execution_targets.py` deleted
- [ ] `RunnerConfigSettings.tsx` extended with `default_backend_type` selector
- [ ] `/api/settings/sandbox` GET/POST returns/accepts `default_backend_type`
- [ ] End-to-end test: submit a job via `submit_job` with `backend_type: "local"`, verify session row has `backend_type = "local"`, verify factory returns `LocalBackend`
- [ ] End-to-end test: submit a job with `backend_type: "ssh" + config`, verify SSH session connects
- [ ] Default fallback test: missing `backend_type -> sandbox_config.default_backend_type`, then falls back to `"docker"`
- [ ] All existing tests still pass (no regression)
