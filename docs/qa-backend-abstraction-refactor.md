# QA: Backend Abstraction Refactor

**Date:** 27 June 2026
**Status:** Approved (Option 1, hard cut, 3 backends)
**Source session:** Plan grilled 27 June 2026 via `grill-me` skill
**Handoff:** `docs/handoff-testai-general-purpose-harness.md` Section 5

---

## 1. Scope (verified against codebase, not guessed)

**Goal:** Replace the single-Docker `SandboxManager` with a `BaseEnvironment` family supporting Local, Docker, and SSH backends. Hard cut (no facade), test rewrites in the same PR, pre-prod environment.

**Verified facts (from direct Read + codegraph + grep):**

| Fact | Source |
|---|---|
| Only 1 session entry point: `POST /api/jobs` (`submit_job`) | `backend/api/routers/jobs.py:229` |
| `JobSpecRequest` (HTTP DTO) at `jobs.py:46`, has `extra="allow"` | `jobs.py:53` |
| `JobSpec` dataclass at `backend/harness/jobs/spec.py:251` | direct read |
| `JobSpec.capabilities: list[str]` (not dict) | `spec.py:261` |
| `SandboxManager` has ~13 production call-sites, 4 test files | grep + codegraph |
| `execution_targets.py` is dead code (0 callers) | codegraph |
| `LocalSubprocess`, `DockerSandbox`, `ExecutionTarget`, `ExecResult` are unused | codegraph |
| `sandbox_config` table exists (k/v, `key TEXT, value TEXT`) for size/image/network | `backend/api/routers/sandbox_config.py:30,60,75` |
| `RunnerConfigSettings.tsx` already exists, talks to `/api/settings/sandbox` | `src/components/settings/RunnerConfigSettings.tsx:32-44` |
| `backend_type`, `ssh_config`, `local_config` — don't exist anywhere | grep |
| `Settings` table shape TBD (handoff claimed, not yet located) | not yet verified |
| `JobSpecRequest.capabilities: list[str] = Field(default_factory=list)` | `jobs.py:62` |
| `JobSpec.to_dict()` serializes for storage/wire transfer | `spec.py:302` |
| `subagent.py` and `orchestrator.py` have `INSERT INTO sessions` (5 sites total) | `subagent.py:378,485`; `orchestrator.py:906`; `store/adapters/postgres.py:70` |

---

## 2. What we decided

### 2.1 Scope of backends (Q2)

- **3 backends:** Local, Docker, SSH
- **Dropped:** Modal, Daytona, Singularity
- **Include:** `_ThreadedProcessHandle` (40 lines, free insurance for future Modal/Daytona)
- **Dropped:** `_HERMES_PROVIDER_ENV_BLOCKLIST`, sudo transform, `_transform_sudo_command`, `_rewrite_compound_background`, Windows path translation, Git Bash lookup, set_activity_callback thread-local, `FileSyncManager` integration with hermes credentials

### 2.2 Architecture (Q3-Q5)

- **Port hermes' `BaseEnvironment` ABC** with cross-platform branches kept (Windows code paths preserved, not stripped)
- **Local + Docker + SSH** as separate subclasses
- **`DockerBackend` = full replacement** for `SandboxManager` (not a wrapper). 749 lines of `SandboxManager` logic extracted and adapted.
- **`FileSyncManager`** ported (needed for SSH file sync)
- **`_ThreadedProcessHandle`** ported (free insurance, ~40 lines)
- **Cross-platform from day one** (Windows branches kept in hermes port). You develop on Windows; the cost of "drop and re-add" is higher than "keep now."

### 2.3 Migration strategy (Q7)

- **Hard cut, no facade.** Delete `sandbox_manager.py` and `execution_targets.py` in the same PR as the new backends.
- **13 production call-sites** rewired to factory.
- **4 test files rewritten** (not just edited) in the same PR.

### 2.4 Schema (Q9-Q11)

- **`sessions.backend_type TEXT NOT NULL DEFAULT 'docker'`** added to `schema.sql` initial CREATE TABLE.
- **Idempotent `ALTER TABLE sessions ADD COLUMN IF NOT EXISTS backend_type TEXT NOT NULL DEFAULT 'docker'`** added to `migrations.sql` (matches existing 12-column ALTER pattern).
- **No DROP, no CASCADE, no recreation.** The 12 child FK tables (`messages`, `tasks`, `stream_events`, etc.) are untouched.
- **New table `session_backend_configs`:**
  ```sql
  CREATE TABLE IF NOT EXISTS session_backend_configs (
      session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
      config JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```

### 2.5 Why `session_backend_configs` (JSONB) over 5 flat columns (Q-final)

- Schema is fixed forever — adding a new backend doesn't migrate the table.
- Per-backend config validation lives in Pydantic models, not DDL.
- Future-proof for Modal/Daytona/etc.: `{"modal_token_id": ..., "modal_token_secret": ...}` with no migration.
- Indexable: `CREATE INDEX ... ON session_backend_configs USING GIN (config)` for queries like "all sessions on host X."
- 12-month test: 6 backends with rich config = flat columns explode. JSONB scales.
- Trade-off: ~80 lines of helper module (`backend_configs.py`) for read/write.

### 2.6 Entry points & default (Q12)

- **Single entry point:** `POST /api/jobs` (`submit_job`). All session creation (chat, cron, webhooks, A2A, workflows) funnels through here.
- **`JobSpec.backend_type: str = "docker"`** added to `backend/harness/jobs/spec.py:251`. 1 new field.
- **`JobSpecRequest.backend_type: str = "docker"`** added to `backend/api/routers/jobs.py:46`. Backward compat via `extra="allow"`.
- **Default precedence:** `JobSpec.backend_type` (if set) → `sandbox_config.default_backend_type` (k/v) → `"docker"` hardcoded fallback.
- **No env var override** (dev can use `sandbox_config` table directly).

---

## 3. Architecture decisions

### 3.1 Backend abstraction

- `backend/harness/backends/base.py` — `BaseEnvironment` ABC + `ProcessHandle` Protocol + `_ThreadedProcessHandle` + `_wait_for_process` + `_pipe_stdin` + `__del__` safety net
- `backend/harness/backends/local.py` — `LocalBackend` (subprocess, no isolation, dev-only)
- `backend/harness/backends/docker.py` — `DockerBackend` (extract from `SandboxManager`, full port)
- `backend/harness/backends/ssh.py` — `SSHBackend` (ControlMaster + FileSyncManager)
- `backend/harness/backends/file_sync.py` — `FileSyncManager` (mtime+size tracking, transactional sync)
- `backend/harness/backends/factory.py` — reads `sessions.backend_type` + `session_backend_configs.config`, returns backend instance
- `backend/harness/backends/backend_configs.py` — read/write helpers for `session_backend_configs` table

### 3.2 Schema files

- `backend/harness/memory/schema/schema.sql` — add `backend_type` to initial CREATE TABLE (line 119-131)
- `backend/harness/memory/schema/migrations.sql` — add `ALTER TABLE sessions ADD COLUMN IF NOT EXISTS backend_type` + `CREATE TABLE IF NOT EXISTS session_backend_configs`

### 3.3 Code touch list

**Production call-sites (13):**

| File | Line | What changes |
|---|---|---|
| `backend/harness/agent/agent.py` | 342 | `sandbox_manager` → `backend_factory` |
| `backend/harness/orchestrator.py` | 79 | same |
| `backend/harness/orchestrator.py` | 906 | `INSERT INTO sessions` adds `backend_type` |
| `backend/harness/phases/sandbox_prepare.py` | 44 | `sandbox_manager.get_or_create` → `factory.get_backend` |
| `backend/harness/services/job_control.py` | 405 | same |
| `backend/api/routers/admin.py` | 627 | same |
| `backend/api/routers/delegate.py` | 383 | same |
| `backend/harness/agent/tool_dispatch.py` | 157 | pass `backend_factory` instead of `sandbox_manager` |
| `backend/harness/tools/delegate_task.py` | 203, 592, 1218 | same |
| `backend/harness/tools/file_tools.py` | 21, 382, 417, 426, 436, 449, 460, 473, 483, 491, 516, 541 | tool runs use `backend.run()` |
| `backend/harness/tools/execute_code.py` | 35, 141 | same |
| `backend/harness/tools/docker_tool.py` | 12, 61, 286 | same |
| `backend/harness/tools/subagent.py` | 378, 485 | `INSERT INTO sessions` adds `backend_type` |
| `backend/harness/store/adapters/postgres.py` | 70 | same |
| `backend/api/main.py` | 461 | wire `BackendFactory` at startup |
| `backend/api/routers/sandbox.py` | 24 | new endpoints for backend CRUD |
| `backend/api/routers/sandbox_config.py` | 28 | extend `SandboxConfigUpdate` with `default_backend_type` |

**Test files (4):**

| File | Lines | What changes |
|---|---|---|
| `backend/tests/test_sandbox_manager.py` | 472 | full rewrite to test `DockerBackend` directly |
| `backend/tests/test_sandbox_snapshot.py` | 365 | rewrite to test `DockerBackend.snapshot()` / `restore()` |
| `backend/tests/test_sandbox_scope.py` | 296 | rewrite to test new scope model on `DockerBackend` |
| `backend/tests/test_sandbox_git_runner.py` | 213 | rewrite to test git ops via `DockerBackend` |

**UI files (1):**

| File | Lines | What changes |
|---|---|---|
| `src/components/settings/RunnerConfigSettings.tsx` | 159 | extend with `default_backend_type` selector + per-backend config form |

**Deleted:**

| File | Lines | Reason |
|---|---|---|
| `backend/harness/sandbox_manager.py` | 749 | replaced by `DockerBackend` |
| `backend/harness/tools/execution_targets.py` | 115 | dead code (0 callers) |

**Net change:** ~2,000 net lines (3 backends + factory + schema + UI + test rewrites), ~860 deleted.

---

## 4. What we explicitly rejected (for the record)

| Option | Reason rejected |
|---|---|
| Option B in handoff (BackendProvider wrapper, leave SandboxManager) | SandboxManager is 749 lines, would still be the only "real" implementation. Two code paths in prod. |
| Facade pattern (keep SandboxManager as shim) | "Don't want to become complex later" — facade adds a layer with no future purpose. |
| `execution_targets.py` is "existing primitive" | Verified dead code. 0 callers in `backend/`. |
| Per-agent or per-execution backend storage (not per-session) | Doesn't match user mental model: "I want this job on my laptop, that one in Docker." Per-session wins. |
| Env var `BACKEND_TYPE_DEFAULT` for default precedence | `sandbox_config` table already exists for k/v settings. Reuse. |
| 6 backends (Modal, Daytona, Singularity too) | Scope creep. YAGNI. Can add later with the established pattern. |
| 1 backend (just Local) | Doesn't satisfy "competitive parity with Hermes." |
| Drop + recreate `sessions` table | 12 child FK tables would need surgery. Not worth it in pre-prod + no schema migration needed. |
| 5 flat columns on `sessions` for backend config | Doesn't scale: 6 backends = 25+ mostly-NULL columns. JSONB scales. |
| `extra="allow"` in `JobSpecRequest` as the only mechanism | Means backend_type wouldn't be in Pydantic schema, breaks OpenAPI. Add it as a proper field. |
| Per-test migration (rewrite incrementally) | Hard cut decided: "we don't want this to become complex later." |
| "Linux-only prod" (drop Windows branches in hermes port) | You develop on Windows. Cost of "drop and re-add" > cost of "keep now." |

---

## 5. Open questions (none — all resolved)

Every question in the grilling session was resolved. See `docs/handoff-testai-general-purpose-harness.md` Section 5 for the original 2-option framing (Option A vs Option B); this QA document supersedes it.

---

## 6. Implementation order (suggested)

1. **Schema first** (lowest risk, can be done alone):
   - Edit `schema.sql` to add `backend_type` to `sessions` initial CREATE
   - Edit `migrations.sql` to add `ADD COLUMN IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS session_backend_configs`
   - Verify: `psql -d testai -f schema.sql` then `psql -d testai -f migrations.sql` is idempotent

2. **`JobSpec` + `JobSpecRequest` field** (low risk):
   - Add `backend_type: str = "docker"` to `backend/harness/jobs/spec.py:251`
   - Add `backend_type: str = "docker"` to `backend/api/routers/jobs.py:46`
   - Add `backend_type` to 5 INSERT sites in `sessions`
   - Add `backend_type` propagation to `JobSpec.to_dict()` and `JobSpecRequest` → `JobSpec` conversion

3. **Backend abstraction** (the big PR):
   - Port `BaseEnvironment` + 3 backends + `FileSyncManager` from hermes
   - Write `factory.py` + `backend_configs.py`
   - Hard cut: delete `sandbox_manager.py` + `execution_targets.py`
   - Rewrite 13 production call-sites
   - Rewrite 4 test files
   - Run full test suite, integration tests, smoke tests

4. **UI** (separate commit, can land after backend):
   - Extend `RunnerConfigSettings.tsx` with backend-type selector
   - Add `/api/settings/sandbox` GET/POST fields for `default_backend_type`
   - Add backend-specific config forms (SSH: host/user/port/key_path; Local: confirmation; Docker: existing image/network/scope)

5. **Settings → default precedence wiring** (small):
   - In `submit_job` handler: if `JobSpec.backend_type` is missing, read `sandbox_config.default_backend_type`, fall back to `"docker"`
   - Add the k/v row initialization to `sandbox_config.py` (default if missing)

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hermes port misses edge case on Windows | medium | medium | Cross-platform branches kept; add Windows integration test |
| Factory lookup is slow under load | low | medium | Cache backend instances per session_id (LRU); factory is a thin shim |
| Test rewrites miss a behavior the old tests caught | medium | high | Run old + new tests in parallel for 1 PR; compare coverage reports |
| `INSERT INTO sessions` for `backend_type` breaks an unverified path | low | high | codegraph already found 5 sites; grep for any other `INSERT INTO sessions` patterns before merge |
| Child FK tables (`messages`, `tasks`, `stream_events`) need new column for backend trace | low | low | Defer — query through `sessions` join for now |
| SSH key file path handling differs between Linux/Windows | medium | medium | Port hermes' `~`-expansion + path translation verbatim |

---

## 8. Definition of done

- [ ] `schema.sql` + `migrations.sql` changes applied to dev DB, no errors, idempotent on second run
- [ ] `JobSpec.backend_type` + `JobSpecRequest.backend_type` fields added
- [ ] 5 `INSERT INTO sessions` sites updated to write `backend_type`
- [ ] `BaseEnvironment` + 3 backends + `FileSyncManager` + `_ThreadedProcessHandle` ported from hermes (with MIT attribution in `THIRD_PARTY_LICENSES`)
- [ ] `BackendFactory` reads `sessions.backend_type` + `session_backend_configs.config`
- [ ] 13 production call-sites rewired to factory (verified by `grep -r "sandbox_manager" backend/harness backend/api` returning 0 hits except in comments)
- [ ] 4 test files rewritten and passing
- [ ] `sandbox_manager.py` and `execution_targets.py` deleted
- [ ] `RunnerConfigSettings.tsx` extended with `default_backend_type` selector
- [ ] `/api/settings/sandbox` GET/POST returns/accepts `default_backend_type`
- [ ] End-to-end test: submit a job via `submit_job` with `backend_type: "local"`, verify session row has `backend_type = "local"`, verify factory returns `LocalBackend`
- [ ] End-to-end test: submit a job with `backend_type: "ssh"` + `session_backend_configs.config = {ssh_host, ssh_user, ...}`, verify SSH session connects
- [ ] Default fallback test: submit a job with no `backend_type`, verify it uses `sandbox_config.default_backend_type`, then falls back to `"docker"`
- [ ] All existing tests still pass (no regression)
