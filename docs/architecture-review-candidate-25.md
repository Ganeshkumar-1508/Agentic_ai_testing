# Candidate 25: Add persistent project memory / campaigns (missing from Citadel + Anthropic comparison)

**Strength**: New feature | **Category**: missing capability / persistent state

---

## Research sources (10)

### Agent harness campaign/persistent memory patterns

1. **Citadel — Campaigns** — "Campaigns persist, resume, and hand off across sessions." Tasks survive context resets. State lives in repo-local `.planning/` files. Three phases: scope → execute → review. https://github.com/SethGammon/Citadel

2. **Anthropic — Effective Harnesses for Long-Running Agents** — Initializer + coding agent pattern with progress files. "External artifacts become the agent's memory." Progress files (`claude-progress.txt`), feature lists, session startup protocol. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

3. **Anthropic — Two-agent pattern** — Initializer creates infrastructure + progress files. Coding agent reads progress, implements one feature at a time, commits, leaves artifacts for next session. Session startup protocol: run pwd → read progress → review feature list → run tests → implement. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

4. **paddo.dev — "external artifacts become the agent's memory"** — "Progress tracking becomes real-time run feeds. Feature lists become spec imports and task breakdowns. Session protocols become agent orchestration." https://paddo.dev/blog/agent-harnesses-from-diy-to-product/

5. **Hermes Agent** — Session persistence via SQLite (`state.db`). Sessions survive restarts. `/resume` command continues previous sessions. ACP sessions persist across editor reconnects. https://github.com/NousResearch/hermes-agent

6. **OpenCode** — `autoCompact` creates new sessions with summaries. Conversation history preserved. Continue with `-c` flag. https://github.com/opencode-ai/opencode

7. **CONTEXT.md — Run** — Runs are durable via checkpoints. But there's no "campaign" concept — a multi-session task that survives individual runs.

8. **CONTEXT.md — Artifact Storage** — "Test files, reports, and agent outputs persisted to Postgres with per-type configurable TTL." Artifacts are stored but not organized into campaigns.

9. **Codebase audit — sessions persist but campaign/project memory does not** (see below)

10. **CONTEXT.md — User Intervention — Reliability** — "Checkpoint/resume" exists for individual runs. No cross-session campaign coordination.

---

## Codebase evidence

### What exists vs what's missing

| Capability | Current project | Citadel / Anthropic |
|---|---|---|
| Session persistence | ✅ Checkpoint/resume per run | ✅ Same |
| Cross-session continuation | ❌ No "/continue campaign" concept | ✅ Campaigns survive context resets |
| Progress files | ❌ No `claude-progress.txt` equivalent | ✅ Feature lists + progress files |
| Session startup protocol | ❌ No ritualized startup | ✅ "pwd → read progress → review features → run tests → implement" |
| Task-to-campaign mapping | ❌ Tasks are ephemeral per session | ✅ Tasks belong to campaigns |
| Planning directory | ❌ No `.planning/` directory | ✅ Repo-local `.planning/` files |
| Handoff artifacts | ❌ No structured session handoff | ✅ Artifacts left for next session |

### Current code that partially overlaps

| File | Purpose | Gap |
|---|---|---|
| `checkpoint.py` | Per-run crash recovery | No cross-session campaign concept |
| `phases/` | Orchestration phases | Per-run, not multi-session |
| `jobs/spec.py` | `JobSpec` — single job definition | No campaign that spawns multiple jobs |
| `services/job_checkpoint.py` | Job-level checkpoints | No campaign-level state |
| `services/board_waiter.py` | Kanban board waiter | Board lives inside a single run |

### The contraction

Introduce a `Campaign` model following Citadel + Anthropic patterns:

```
agent_workspace/.planning/
├── campaign.json              # Active campaign state (goal, phases, progress)
├── feature_list.json          # Structured features (from Anthropic pattern)
├── progress.md                # Human-readable progress log
└── session_handoff.md         # Artifact for next session
```

Define a `Campaign` dataclass:
```python
@dataclass
class Campaign:
    id: str
    goal: str
    phases: list[Phase]
    feature_list: list[Feature]
    progress_log: list[ProgressEntry]
    artifacts: list[ArtifactRef]
    created_at: datetime
    resumed_from: str | None  # Previous session_id
```

Add a session startup protocol tool that the agent calls at the beginning of each session:
1. `pwd` — confirm location
2. `read .planning/progress.md` — review progress
3. `read .planning/feature_list.json` — review feature list
4. `bash run_tests` — run existing tests
5. Begin implementation

This turns the agent from a stateless per-session worker into a stateful campaign participant that maintains progress across context resets.
