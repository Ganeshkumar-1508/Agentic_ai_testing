# Candidate 16: Delete or merge the dead `environments/` — a duplicate execution backend with zero consumers

**Strength**: Strong | **Category**: dead code / parallel implementation

---

## Research sources (10)

### Agent harness execution environment patterns

1. **Hermes Agent** — Single `agent/` subpackage with one `run_agent.py` and one gateway. One execution path. No parallel backends. https://github.com/NousResearch/hermes-agent

2. **OpenCode** — Single `internal/llm` + `internal/session`. Tools and models in one module. No duplicate abstractions. https://github.com/opencode-ai/opencode

3. **OpenHands** — Single backend system. No duplicate environment abstractions. https://github.com/All-Hands-AI/OpenHands

4. **Pantheon (r3moteBee)** — Single `agent/` directory. One execution path. No parallel systems. https://github.com/r3moteBee/pantheon

5. **SWE-agent** — Single `SWEEnv` environment. One abstraction for all execution. https://github.com/SWE-agent/SWE-agent

6. **DeerFlow** — Single `backends/` system (the same upstream that this project's `backends/` was ported from). No duplicate `environments/`. https://github.com/bytedance/deer-flow

7. **AgentKit (inngest)** — Single Agent + Network model. One execution abstraction. https://github.com/inngest/agent-kit

8. **Citadel** — Single operating layer. No parallel abstractions. https://github.com/SethGammon/Citadel

9. **Codebase audit — environments/ has zero external consumers** (see below)

10. **CONTEXT.md — Workspace Container** — "Each subagent gets its own sandbox container (Docker)". The domain model defines one execution model, not two.

---

## Codebase evidence

### Two parallel execution backend systems, one unused

| System | Files | Lines | Consumers | Purpose |
|---|---|---|---|---|
| **`backends/`** | 8 files | ~1,700 | 4 modules (tools + codegraph) | Actual execution backend |
| **`environments/`** | 3 files | 177 | **0 external** | Duplicate, dead |

### The unused system

```
harness/environments/
├── __init__.py    (1 line — "Execution environment backends.")
├── base.py        (79 lines — BaseEnvironment with process management)
└── ssh.py         (98 lines — SSHEnvironment with ControlMaster persistence)
```

**Zero external consumers.** Only `environments/ssh.py` imports from `environments/base.py`. No tool, service, or phase imports from `environments/`. The entire directory is dead code.

Meanwhile `backends/` has:
- `backends/base.py` (694 lines) — the real BaseEnvironment with snapshot management, CWD tracking, command wrapping
- `backends/docker.py` (46 symbols) — Docker container orchestration
- `backends/local.py` (32 symbols) — local process execution  
- `backends/ssh.py` (27 symbols) — SSH with file sync
- `backends/factory.py` (38 symbols) — backend construction
- `backends/file_sync.py` (35 symbols) — file sync for remote backends
- `backends/credential_files.py` (19 symbols) — credential injection
- `backends/backend_configs.py` (8 symbols) — configuration

### Origin hypothesis

Both `backends/` and `environments/` appear to be ported from Hermes Agent (both docstrings say "adapted from Hermes"). They were likely ported at different times by different developers, and `environments/` was the earlier attempt. When `backends/` was later built out with Docker, factory, file sync, and credential injection, the old `environments/` was left behind.

### The deletion test

Delete `harness/environments/`. Nothing breaks. 177 lines of dead code removed. If someone later needs an SSH backend, `backends/ssh.py` already exists and is fully integrated with Docker, Local, factory, file sync, and credential injection.

### The contraction

- **Delete** `harness/environments/` entirely (3 files, 177 lines, 0 consumers)
- Or: **Merge** any salvageable patterns from `environments/base.py` into `backends/base.py` (unlikely — `backends/` is already more comprehensive)
