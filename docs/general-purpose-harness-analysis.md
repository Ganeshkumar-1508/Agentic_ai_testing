# TestAI: General-Purpose Agent Harness Analysis

**Date**: 2026-06-27
**Purpose**: Determine whether TestAI's harness can serve as a general-purpose agent
harness (like Hermes, OpenCode, DeerFlow) or is limited to testing/SWE tasks.

---

## Table of Contents

1. [The Nine Components of a Harness](#1-the-nine-components-of-a-harness)
2. [Tool-For-Tool Comparison](#2-tool-for-tool-comparison)
3. [Platform & Channel Coverage](#3-platform--channel-coverage)
4. [Delegation & Subagent Architecture](#4-delegation--subagent-architecture)
5. [Skill & Extensibility Systems](#5-skill--extensibility-systems)
6. [Memory & Persistence](#6-memory--persistence)
7. [Context Management & Compression](#7-context-management--compression)
8. [System Prompt Assembly](#8-system-prompt-assembly)
9. [Provider Model](#9-provider-model)
10. [What Would It Take?](#10-what-would-it-take)
11. [Recommendation](#11-recommendation)

---

## 1. The Nine Components of a Harness

From the Arize AI analysis ("What is an Agent Harness?", Apr 2026, `arize.com/blog`),
every production harness converged on the same nine components independently.
Here's how TestAI scores against Hermes (the most feature-rich open harness).

### 1.1 Outer Iteration Loop

**Hermes** (`reference/hermes-agent/agent/conversation_loop.py`):
- `run_conversation()` — synchronous loop with tool-calling, interrupt checks, budget
  tracking, grace call, compression, checkpointing, plugin hooks
- 3 API modes: `chat_completions`, `codex_responses`, `anthropic_messages`
- Supports streaming (via `stream_callback`) and non-streaming paths
- `build_turn_context()` extracts all per-turn setup (prologue pattern)

**TestAI** (`backend/harness/agent/agent.py`):
- `run_stream()` — async generator loop for SSE, `run()` — blocking wrapper
- Single API mode (LLMRouter dispatches to providers)
- Supports streaming (SSE via `TokenGenerated`/`ReasoningGenerated` events)
- `build_turn_context()` in `harness/agent/turn_context.py`

**Gap**: None. Both have a proper iteration loop with tool-calling, streaming, and
interrupt support. Hermes has 3 API modes vs TestAI's 1, but TestAI's LLMRouter
handles provider differences internally.

### 1.2 Context Management & Compression

**Hermes** (`reference/hermes-agent/agent/context_compressor.py`):
- Lossy summarization of middle conversation turns
- Head/tail protection by token budget
- Iterative summary updates on re-compression
- **Lineage rotation**: closes SQLite row, creates child session, records
  parent-child lineage (per Arize AI analysis)
- Anti-thrashing: tracks effectiveness, skips if <10% savings

**TestAI** (`backend/harness/context_compressor/compressor.py`):
- Same algorithm: prune old tool results → protect head → protect tail by token
  budget → summarize middle turns with structured LLM prompt
- Head/tail protection, iterative summary updates, anti-thrashing
- **Lineage table**: `compressions` DB table with `session_id`, `before_tokens`,
  `after_tokens` (added June 2026, `harness/services/job_checkpoint.py`)
- Session lineage wiring: `compress()` accepts `session_id` parameter, agent.py
  passes `self.session_id` at call site

**Gap**: Minor. Hermes does full session rotation (closes SQLite row, creates child
session), which enables recursive CTE queries for lineage. TestAI logs compression
events to a `compressions` table but doesn't rotate the session. For most use
cases, the table is sufficient.

### 1.3 Skills & Tools Management

**Hermes** (`reference/hermes-agent/toolsets.py`, `reference/hermes-agent/tools/registry.py`):
- 28 named toolsets (web, terminal, file, browser, vision, image_gen, delegation,
  cronjob, memory, todo, skills, homeassistant, spotify, kanban, discord, etc.)
- 70+ tools registered in central registry
- 6 terminal backends (local, docker, ssh, modal, daytona, singularity)
- 14 browser tools (navigate, snapshot, click, type, scroll, back, press,
  get_images, vision, console, cdp, dialog)
- Service-gated tools via `check_fn` (only appear when prerequisites met)
- `_HERMES_CORE_TOOLS` (shared across all platforms) + `TOOLSETS` dict per platform

**TestAI** (`backend/harness/tools/toolsets.py`, `backend/harness/tools/registry.py`):
- 20 named toolsets (chat, read, write, intelligence, delegate, healing, kanban,
  specialized, plan, team, analysis, execution, shell, persistence, session,
  browser, orchestrator, coordinator, test-writer, bug-fixer, code-reviewer,
  security-auditor, docs-writer)
- 50+ tools in central registry
- Code intelligence tools (codegraph_explore, codegraph_search, codegraph_node,
  codegraph_callers, codegraph_callees) — **unique advantage for SWE tasks**
- Knowledge graph tools (kg_search, kg_callers, kg_callees, kg_graph_status,
  semantic_search, lsp) — **unique advantage**
- 2 browser tools (navigate, snapshot) vs Hermes' 14
- Service-gated tools via registry's `check_fn`

**Gap**: Hermes has ~20 more tools overall, especially in:
- Browser automation (14 tools vs 2)
- Terminal backends (6 backends vs 1)
- Platform-specific tools (discord, feishu, spotify, homeassistant)
- Cron scheduling

TestAI's code intelligence and knowledge graph tools are **unique strengths** that
Hermes doesn't have. These are valuable for general SWE tasks (code analysis,
dependency tracing, architectural understanding).

### 1.4 Subagent Management

**Hermes** (`reference/hermes-agent/tools/delegate_tool.py`):
- `delegate_task(goal, context, toolsets)` — single subagent
- `delegate_task(tasks=[...])` — fan-out, N parallel
- `background=True` — fire-and-forget, results via delegation queue
- Roles: `leaf` (no delegate_task), `orchestrator` (retains it)
- Max spawn depth: configurable (default 2)
- Max concurrent children: configurable (default 3)
- Circuit breaker + retry with exponential backoff
- Child timeout: configurable
- Subagents run as **asyncio tasks in-process** (same as TestAI)

**TestAI** (`backend/harness/tools/subagent.py`, `backend/harness/tools/delegate_task.py`):
- `Subagent.spawn(goal, role, toolsets)` — single subagent
- `Subagent.spawn_many(goals=[...])` — fan-out, N parallel
- `delegate_task` tool with modes: Sync, Fan-Out, Background
- Roles: `leaf` (no delegate_task), orchestration roles
- Max spawn depth: configurable (default 5)
- Max concurrent children: configurable (default 10)
- Circuit breaker + retry with env-configurable settings (`SUBAGENT_RETRY_MAX_ATTEMPTS`)
- Child timeout: configurable (default 1000s)
- Subagents run as **asyncio tasks in-process** (same as Hermes)
- **DB-backed tracker**: `_SubagentTracker` seeds completed subagents from sessions
  table on restart (`harness/services/job_checkpoint.py`)

**Gap**: Minimal. Both have the same capabilities. TestAI's DB-backed tracker
is actually more durable than Hermes' in-memory tracking. Both have the same
limitation (in-process asyncio tasks die on crash).

### 1.5 Built-in Prepackaged Skills

**Hermes** (`reference/hermes-agent/skills/`, `reference/hermes-agent/optional-skills/`):
- Bundled skills (always available): skills/ directory
- Optional skills (install via `hermes skills install`): optional-skills/ with
  categories: autonomous-ai-agents, blockchain, communication, creative, devops,
  email, health, mcp, migration, mlops, productivity, research, security,
  web-development
- `skill_manage` tool lets agents CREATE and EDIT their own skills
- Curator system: background skill lifecycle management (review, archive, backup)
- Skill usage tracking (`tools/skill_usage.py`)

**TestAI** (`<project>/.testai/skills/<name>/SKILL.md`):
- SKILL.md files at filesystem level
- `skills_list`, `skill_view` for read-only discovery
- No `skill_manage` tool — agents cannot create or edit skills
- No curator system — no automatic review/archive of agent-created skills
- No optional skill hub — all skills are user-installed or bundled

**Gap**: **Significant.** TestAI has the infrastructure (SKILL.md files exist) but
lacks the agent-facing tooling. Without `skill_manage`, agents cannot extend
themselves. Without a curator, agent-created skills grow stale. This limits
the harness's ability to grow with use.

### 1.6 Session Persistence & Recovery

**Hermes** (`reference/hermes-agent/hermes_state.py`, `reference/hermes-agent/gateway/session.py`):
- SQLite + FTS5 for full-text search across past sessions
- WAL journaling for concurrent access
- `session_search` tool for agent-driven recall across sessions
- Session lineage via compression rotation (parent-child chain)
- Resume: `hermes --resume <session_id>` restores conversation history

**TestAI** (`backend/harness/store/adapters/postgres.py`):
- PostgreSQL — stronger than SQLite for multi-user web deployment
- `PostgresSessionStore` with recursive CTE for session tree queries
- `PostgresEventStore` for streaming event log
- Checkpoints (`backend/harness/checkpoint.py`) for superstep, before-action,
  approval-gate checkpoints
- Resume: `run_resumed_job_spec()` in orchestrator for job-level resume
- No `session_search` tool — agents cannot query past sessions

**Gap**: TestAI's Postgres backend is stronger for web deployment. Missing
`session_search` tool for agent-driven cross-session recall. Hermes' FTS5
search across sessions is a useful capability for general-purpose agents.

### 1.7 System Prompt Assembly

**Hermes** (`reference/hermes-agent/agent/prompt_builder.py`):
- 3 tiers: stable (identity, tool guidance, skills), context (AGENTS.md,
  CLAUDE.md, .cursorrules), volatile (memory snapshots, user profile, timestamp)
- Prompt caching: Anthropic cache breakpoints for prefix caching
- Context files auto-discovered from cwd

**TestAI** (`backend/harness/prompt_builder.py`):
- System prompt built from mode + toolsets
- Skills index content loaded on-demand via `skill` tool
- Memory context from `store.get_recent_context()`
- No tier separation (everything in one prompt)

**Gap**: Minor. Hermes' 3-tier system with prompt caching is more sophisticated.
TestAI's single-prompt approach is simpler but less cache-friendly.

### 1.8 Lifecycle Hooks

**Hermes** (`reference/hermes-agent/gateway/hooks.py`):
- One `HookRegistry` for event hooks (agent:start, agent:step, agent:end,
  command:*, session:start, session:end)
- Plugin hooks (in-process Python callbacks) for pre/post tool, pre/post LLM
- Filesystem hooks (shell scripts) for gateway events
- No middleware chain — hooks are event-based, not phase-based

**TestAI** (`backend/harness/hook/pipeline.py`):
- Unified `HookPipeline` with 3 ordered phases (DETERMINISTIC_GATE → MIDDLEWARE → PLUGIN)
- 16 middleware classes covering sanitization, token budgets, guardrails, audits,
  loop detection, subagent limits, LLM error handling, title generation
- `HookRegistry` from `_hook_system.py` for plugin events
- Deterministic gates from `hook_registry.py` for allow/block/ask

**Gap**: None. TestAI's hook system is actually more structured than Hermes'
(ordered phases vs flat events). The C1 refactor unified 3 overlapping systems.

### 1.9 Permission & Safety Layer

**Hermes** (`reference/hermes-agent/agent/tool_guardrails.py`):
- `ToolGuardrail` with "halt" decision for repeated non-progressing attempts
- Permission modes: auto, ask, architect, debug
- `clarify` for mid-task user questions
- File operation guards (write_approval.py, path_security.py)
- Tirith security scanning

**TestAI** (`backend/harness/permissions/manager.py`):
- Permission modes: auto, ask, architect, debug
- Tool categories: read, write, analyze, delegate
- `HookRegistry` for deterministic allow/block/ask rules
- `HookPipeline` for middleware-level pre-tool authorization
- Guardrail middleware for pluggable authorization providers
- Sandbox audit middleware for bash command classification

**Gap**: None. Both have comprehensive permission systems. TestAI's middleware
approach is more extensible (plug in new authorization providers via the pipeline).

### 1.10 Summary: Nine Components

| Component | TestAI | Hermes | Verdict |
|-----------|--------|--------|---------|
| Outer iteration loop | ✅ | ✅ | Equal |
| Context management | ✅ lineage table | ✅ lineage rotation | TestAI: sufficient |
| Skills & tools | ⚠️ 20 toolsets | ✅ 28 toolsets | **Gap: -8 toolsets** |
| Subagent management | ✅ DB-backed | ✅ in-memory | TestAI: more durable |
| Prepackaged skills | ❌ no skill_manage | ✅ curator + skill_manage | **Gap: no agent self-extension** |
| Session persistence | ✅ Postgres | ✅ SQLite | TestAI: stronger for web |
| System prompt | ⚠️ single tier | ✅ 3 tiers | Minor gap |
| Lifecycle hooks | ✅ 3-phase pipeline | ✅ event hooks | TestAI: more structured |
| Permission layer | ✅ middleware-based | ✅ guardrails | Equal |

---

## 2. Tool-For-Tool Comparison

### File: `reference/hermes-agent/toolsets.py` vs `backend/harness/tools/toolsets.py`

Hermes toolsets (28 total):

| Toolset | Hermes tools | TestAI equivalent | Notes |
|---------|-------------|-------------------|-------|
| `web` | web_search, web_extract | web_search, web_fetch | web_fetch is markdown-only; no web_extract |
| `terminal` | terminal, process | bash | **Gap**: PTY-based terminal + background process mgmt |
| `file` | read_file, write_file, patch, search_files | read_file, write_file, edit_file, apply_patch, glob, grep | Equivalent. TestAI has glob/grep which are search |
| `browser` | 14 browser tools | browser_navigate, browser_snapshot | **Gap**: 14 vs 2 browser tools |
| `vision` | vision_analyze | vision_analyze | Equivalent |
| `image_gen` | image_generate | image_generate | Equivalent |
| `skills` | skills_list, skill_view, **skill_manage** | skills_list, skill_view | **Gap**: no skill_manage |
| `todo` | todo | todo | Equivalent |
| `memory` | memory | memory | Equivalent |
| `delegation` | delegate_task | delegate_task | Equivalent |
| `cronjob` | cronjob | ❌ | **Gap**: no cron scheduling |
| `kanban` | kanban_show/list/complete/block/comment/create/link/unblock | kanban_list/show/create/assign/start/complete/block/unblock/comment/heartbeat/link | Equivalent |
| `code_execution` | execute_code | execute_code | Equivalent |
| `session_search` | session_search | ❌ | **Gap**: no cross-session search |
| `clarify` | clarify | question | Equivalent |
| `computer_use` | computer_use | computer_use | Equivalent |
| `homeassistant` | 4 HA tools | ❌ | **Gap**: niche, not critical |
| `spotify` | 7 Spotify tools | ❌ | **Gap**: niche |
| `discord` | discord, discord_admin | ❌ | **Gap**: platform-specific |
| `moa` | mixture_of_agents | ❌ | Advanced reasoning |
| `tts` | text_to_speech | ❌ | Voice output |
| `video_gen` | video_generate | ❌ | Niche |
| `x_search` | x_search | ❌ | X/Twitter search |
| `transcription` | transcribe_audio | ❌ | Niche |
| `rl` | reinforcement_learning | ❌ | Research tool |

TestAI-unique toolsets:

| Toolset | TestAI tools | Hermes equivalent | Notes |
|---------|-------------|-------------------|-------|
| **`intelligence`** | codegraph_explore, codegraph_search, codegraph_node, codegraph_callers, codegraph_callees, semantic_search, lsp | ❌ | **Unique**: structural code search + LSP |
| `analysis` | repo_analyzer, tech_stack_detector, detect_languages, osv_check, coverage_analyzer | ❌ | **Unique**: repo analysis + CVE scanning |
| `healing` | attempt_heal | ❌ | Testing-specific |
| `execution` | execute_code, docker_executor, docker_image_list | execute_code only | TestAI has Docker tools |
| `shell` | powershell, notebook_edit | ❌ | Windows-specific |
| `orchestrator` | orchestrate, orchestrate_monitor + full toolset | ❌ | Job-oriented orchestration |
| `coordinator` | curated toolset for manager agent | ❌ | Unique role pattern |

### File-by-File: Key Missing Hermes Tools

| File | Tool | What it does | Gap severity |
|------|------|-------------|-------------|
| `reference/hermes-agent/tools/terminal_tool.py` | `terminal` | PTY-based interactive shell with process isolation | **High** — enables interactive stdin, background tasks, streaming output |
| `reference/hermes-agent/tools/process_registry.py` | `process` | Background process management (spawn, list, kill, wait) | **High** — run a dev server, monitor it, kill on completion |
| `reference/hermes-agent/tools/cronjob_tools.py` | `cronjob` | Schedule recurring tasks with cron expressions | **High** — daily test runs, maintenance, monitoring |
| `reference/hermes-agent/tools/skill_manager_tool.py` | `skill_manage` | Agent-driven skill creation and editing | **High** — agent self-extension |
| `reference/hermes-agent/tools/session_search_tool.py` | `session_search` | Cross-session full-text search with summarization | **Medium** — recall past solutions |
| `reference/hermes-agent/tools/browser_tool.py` | 14 browser tools | Full browser automation | **Medium** — web interaction beyond navigation |
| `reference/hermes-agent/tools/web_tools.py` | `web_extract` | Structured content extraction from HTML | **Medium** — richer than markdown-only fetch |
| `reference/hermes-agent/tools/feishu_doc_tool.py` | Feishu doc tools | Platform-specific | **Low** — niche |
| `reference/hermes-agent/tools/spotify/*.py` | Spotify tools | Music playback | **Low** — niche |

### File-by-File: TestAI's Unique Strengths

| File | Tool(s) | What it does | Why it matters |
|------|---------|-------------|----------------|
| `backend/harness/tools/codegraph_tools.py` | 5 tools | AST-level code search, dependency graph traversal | **Unique**: no other harness has structural code search at this depth |
| `backend/harness/tools/knowledge_graph_tool.py` | 4 tools | Knowledge graph query (semantic + structural) | **Unique**: cross-repo KG for architecture understanding |
| `backend/harness/tools/lsp_tools.py` (via intelligence) | `lsp` | LSP protocol client for go-to-definition, completions | **Unique**: no other harness exposes LSP to the agent |
| `backend/harness/services/artifact_store.py` | artifact_save/list/read | Per-run artifact persistence with TTL | Good for any task that generates outputs |
| `backend/harness/services/failure_classification.py` | failure analysis | Classifies errors as retryable vs defect | Useful for any error-prone workflow |

---

## 3. Platform & Channel Coverage

### File: `reference/hermes-agent/gateway/platforms/` vs TestAI

Hermes has 20+ messaging platform adapters in `reference/hermes-agent/gateway/platforms/`:
- telegram, discord, slack, whatsapp, signal, matrix, mattermost, email, sms,
  dingtalk, feishu, wecom, weixin, bluebubbles, qqbot, homeassistant, webhook,
  api_server, yuanbao

Plus:
- **ACP adapter** (`reference/hermes-agent/acp_adapter/`): VS Code, Zed, JetBrains
  integration via Agent Communication Protocol
- **TUI** (`reference/hermes-agent/ui-tui/`): Ink (React) terminal UI
- **Desktop** (`reference/hermes-agent/apps/desktop/`): Electron app
- **Cron** (`reference/hermes-agent/cron/`): Durable scheduled job execution
- **CLI** (`reference/hermes-agent/cli.py`): Interactive terminal
- **Batch runner** (`reference/hermes-agent/batch_runner.py`): Parallel batch processing

TestAI has:
- **Web dashboard** (Next.js + FastAPI): the only surface
- **REST API** (FastAPI): programmatic access
- No CLI, no TUI, no messaging adapters, no IDE integration, no cron, no desktop app

### Gap Analysis

| Entry point | Hermes | TestAI | Impact |
|-------------|--------|--------|--------|
| Interactive CLI | ✅ `cli.py` | ❌ | **Cannot run from terminal** |
| TUI | ✅ `ui-tui/` Ink React | ❌ | No rich terminal UI |
| Web dashboard | ❌ (PTY bridge only) | ✅ Next.js | TestAI's strength |
| REST API | ✅ `api_server` adapter | ✅ FastAPI | Both have this |
| Slack integration | ✅ `gateway/platforms/slack.py` | ❌ | No messaging input |
| Discord integration | ✅ `gateway/platforms/discord.py` | ❌ | No messaging input |
| IDE integration | ✅ `acp_adapter/` | ❌ | No IDE integration |
| Cron scheduling | ✅ `cron/scheduler.py` | ❌ | No periodic tasks |
| Desktop app | ✅ `apps/desktop/` (Electron) | ❌ | Web-only |
| Batch processing | ✅ `batch_runner.py` | ❌ | No offline batch mode |

---

## 4. Delegation & Subagent Architecture

### Hermes (`reference/hermes-agent/tools/delegate_tool.py`, lines 2074+)

```
delegate_task(goal, context, toolsets, background=False)
  → spawns subagent with isolated session + terminal context
  → parent waits for result (sync) or receives via delegation queue (background)
  → child returns structured summary

delegate_task(tasks=[...])  // Fan-out
  → spawns N subagents in parallel
  → concurrency capped by delegation.max_concurrent_children (default 3)

Roles:
  - leaf: cannot call delegate_task, clarify, memory, send_message, execute_code
  - orchestrator: retains delegate_task for recursive spawning
```

Key pattern: **subagent gets its own terminal session**. Each child has an isolated
shell with its own CWD, environment, and process tree. This is critical for
multi-task workflows where each task needs independent state.

### TestAI (`backend/harness/tools/subagent.py`, `backend/harness/tools/delegate_task.py`)

```
Subagent.spawn(goal, role, toolsets, timeout=1000)
  → creates child session row in sessions table
  → spawns Agent with restricted toolsets via agent_factory
  → parent waits for result (sync)

Subagent.spawn_many(goals=[...])  // Fan-out
  → spawns N subagents in parallel
  → concurrency capped by max_children (default 10)

Roles:
  - leaf: restricted tools, no delegate_task
  - orchestration roles: retain delegate_task
```

Key difference: TestAI's subagents get **filesystem worktree isolation** (separate
git worktree via `harness/services/subagent_filesystem.py`). This is better for
parallel file operations — two subagents can edit different files in the same
repo without conflicts. Hermes doesn't have worktree isolation.

**TestAI's strength**: worktree isolation per subagent via
`harness/services/subagent_filesystem.py` (lines 280-282):
```python
WRITE_TOOLS = {"write_file", "edit_file", "apply_patch", "write", ...}
READ_TOOLS = {"read_file", "list_files", "glob", ...}
```

**Hermes' strength**: per-subagent terminal isolation with separate shell
environment. Each Hermes subagent gets its own `terminal` session with
independent CWD, env vars, and process tree.

### Summary

| Feature | Hermes | TestAI | Winner |
|---------|--------|--------|--------|
| Async spawn | ✅ background=True | ✅ Background mode | Tie |
| Fan-out | ✅ tasks=[...] | ✅ spawn_many() | Tie |
| Result collection | ✅ delegation queue | ✅ collect_results() | Tie |
| Max depth | ✅ configurable (2) | ✅ configurable (5) | Tie |
| Circuit breaker | ✅ | ✅ (env-configurable) | Tie |
| Retry | ✅ exponential backoff | ✅ env-configurable | Tie |
| Child timeout | ✅ configurable | ✅ configurable (1000s) | Tie |
| Terminal isolation | ✅ per-child shell | ❌ shared sandbox | **Hermes** |
| Worktree isolation | ❌ | ✅ git worktrees | **TestAI** |
| DB-backed tracking | ❌ in-memory | ✅ sessions table | **TestAI** |

---

## 5. Skill & Extensibility Systems

### Hermes (`reference/hermes-agent/tools/skill_manager_tool.py`)

The `skill_manage` tool is the key differentiator. It lets agents:

1. **Create skills**: `skill_manage(action="create", name=..., content=...)`
   → writes SKILL.md → curator reviews → skill becomes available
2. **Edit skills**: `skill_manage(action="edit", name=..., content=...)`
3. **Delete skills**: `skill_manage(action="delete", name=...)`
4. **List skills**: `skills_list` — shows available skills with descriptions
5. **View skills**: `skill_view` — loads full SKILL.md content

The curator (`reference/hermes-agent/agent/curator.py`) manages the skill lifecycle:
- `curator run` — reviews agent-created skills, auto-archives stale ones
- `curator status` — shows skill health
- `curator archive/restore` — lifecycle management
- Skills are stored at `~/.hermes/skills/<category>/<name>/SKILL.md`

Skills are just markdown files with a standard frontmatter format:
```yaml
---
name: my-skill
description: Does X thing
version: 1.0
---
Instructions for the agent...
```

### TestAI (`backend/harness/tools/skill_tools.py`)

TestAI's skill system is read-only:
- `skills_list` — lists available skills (name + description)
- `skill_view` — loads full SKILL.md content
- No `skill_manage` — agents cannot create, edit, or delete skills
- No curator — no automatic review/archive

Skills are discovered from filesystem:
- `<cwd>/.testai/skills/<name>/SKILL.md` (project)
- `~/.testai/skills/<name>/SKILL.md` (global)

### Gap Detail

The absence of `skill_manage` means:
1. Agents can't encode learned patterns as reusable skills
2. Every run starts with the same fixed skill set
3. The harness doesn't grow with use
4. No "write a skill for this and use it next time" pattern

Adding `skill_manage` requires:
- A tool that writes SKILL.md files
- A curator-like system to review agent-created skills
- Usage tracking for auto-archiving stale skills

Reference: `reference/hermes-agent/tools/skill_manager_tool.py:55` lines.

---

## 6. Memory & Persistence

### Hermes

**Session storage** (`reference/hermes-agent/hermes_state.py`):
- SQLite with FTS5 for full-text search
- WAL journaling
- `session_search` tool for agent-driven cross-session recall
- Session lineage via compression rotation

**Memory system** (`reference/hermes-agent/agent/memory_manager.py`):
- `MemoryProvider` ABC — pluggable backends (honcho, mem0, supermemory, etc.)
- `MemoryManager` orchestrates multiple providers
- L0: raw artifacts (tool call history)
- L1: indexed facts
- L2: curated lessons (via `memory` tool)
- `memory` tool: save/recall facts across sessions

### TestAI

**Session storage** (`backend/harness/store/adapters/postgres.py`):
- PostgreSQL — stronger for multi-user web
- Recursive CTE for session tree queries
- Streaming events via `PostgresEventStore`
- Checkpoints via `CheckpointManager` (`backend/harness/checkpoint.py`)

**Memory system** (`backend/harness/memory/`):
- `PersistentStore` (`harness/memory/store.py`)
- L0: artifact store (`harness/services/artifact_store.py`)
- L1: reflection memory (`harness/agent/reflexion_memory.py`)
- L2: `memory` tool for agent-driven fact storage
- No pluggable memory provider system
- No cross-session search tool

### Gap

| Feature | Hermes | TestAI | Impact |
|---------|--------|--------|--------|
| Live session storage | SQLite + FTS5 | PostgreSQL | TestAI stronger for multi-user |
| Cross-session search | ✅ session_search tool | ❌ | Medium — agents can't learn from past runs |
| Pluggable memory providers | ✅ MemoryProvider ABC | ❌ | Medium — limited to built-in memory |
| L0/L1/L2 pipeline | ✅ | ✅ | Both have tiered memory |
| Session lineage | ✅ via compression rotation | ✅ via compressions table | Both have lineage |

---

## 7. Context Management & Compression

### Hermes (`reference/hermes-agent/agent/context_compressor.py`)

Algorithm:
1. Prune old tool results (cheap, no LLM call)
2. Protect head messages (system prompt + first exchange)
3. Protect tail messages by token budget (~20K tokens)
4. Summarize middle turns with structured LLM prompt
5. On re-compression, iteratively update the previous summary
6. **On compression**: close current SQLite row → create child session → record
   parent-child lineage → rotate session ID

Key details from Arize AI analysis:
> "Compression is also a session lifecycle event. On compression, Hermes closes the
> current SQLite session row, creates a child session seeded by the summary, rotates
> the session ID, and records parent-child lineage. If a long conversation compresses
> multiple times, you get a lineage chain instead of one repeatedly rewritten transcript."

### TestAI (`backend/harness/context_compressor/compressor.py`)

Algorithm (nearly identical):
1. Prune old tool results (`prune_old_tool_results` in pruning.py)
2. Protect head messages (`protect_head_size`)
3. Protect tail by token budget (`find_tail_cut_by_tokens`)
4. Summarize middle turns with structured LLM prompt (`generate_summary`)
5. On re-compression, iteratively update previous summary
6. **On compression**: log to `compressions` DB table with session_id, before/after
   tokens (`record_compaction`)

### Gap

The algorithms are nearly identical. The difference:
- Hermes does **session rotation** — closes the old session, creates a new child
  session, records lineage. This means the session tree has a rich parent-child chain.
- TestAI does **event logging** — writes a row to the `compressions` table with
  token counts and session_id. The session itself stays in place.

For most use cases, TestAI's approach is sufficient. The `compressions` table can
be queried to show compression history. Session rotation (which changes session IDs)
adds complexity for web UIs that reference session IDs in URLs.

---

## 8. System Prompt Assembly

### Hermes (`reference/hermes-agent/agent/prompt_builder.py`)

Three-tier system prompt assembly:
1. **Stable tier** (cached, rarely changes):
   - Identity (SOUL.md)
   - Tool guidance for enabled tools only
   - Skills index content
   - Environment hints (Tmux, container detection)
   - Platform hints

2. **Context tier** (changes with cwd):
   - AGENTS.md, CLAUDE.md, .cursorrules from current directory
   - Prompt-injection scanning before loading

3. **Volatile tier** (changes every turn):
   - Memory snapshots (L2 facts)
   - User profile material
   - External memory-provider blocks
   - Timestamp + model/provider metadata

Prompt caching: Anthropic cache breakpoints between tiers. Cache remains valid
across turns as long as stable + context tiers don't change.

### TestAI (`backend/harness/prompt_builder.py`)

Single-prompt assembly:
1. Build system prompt from mode + toolsets (`build_system_prompt`)
2. Add context from `store.get_recent_context()` if available
3. Add skill content on-demand via `skill` tool
4. Add memory via `memory` tool during conversation

No tier separation. Everything goes into one system prompt. No prompt caching
optimization.

### Gap

Hermes' 3-tier system with prompt caching is more sophisticated and cost-effective
for long-running conversations. TestAI's single-prompt approach works but doesn't
benefit from prefix caching.

For a web-based product, this matters less than for a CLI tool (web sessions tend
to be shorter). But for long-running orchestration jobs, tiered prompts would
reduce token waste.

---

## 9. Provider Model

### Hermes (`reference/hermes-agent/agent/runtime_provider.py`)

Provider resolution is a **shared runtime resolver** used by CLI, gateway, cron,
ACP, and auxiliary calls. Key features:
- 18+ supported providers (OpenRouter, Anthropic, OpenAI, Gemini, Bedrock, etc.)
- 3 API modes: `chat_completions`, `anthropic_messages`, `codex_responses`
- Transport adapters normalize wire formats
- Provider-specific quirks handled by profile extensions
- Fallback chain: primary → fallback providers on failure
- OpenRouter provider routing preferences

### TestAI (`backend/harness/providers/`)

Provider resolution via module-level registry + DB-backed runtime config:
- 34 providers (after C2 refactor: 16 config-driven + 8 complex file-based)
- LLMRouter holds runtime profiles from DB (`provider_configs` table)
- Single API mode (`LLMRouter` dispatches internally)
- Provider-specific quirks via `build_extra_body()` / `build_api_kwargs_extras()`
- Circuit breaker per provider (3 failures → open for 30s)
- Quality scoring per model (success rate - latency penalty)

### Comparison

| Feature | Hermes | TestAI |
|---------|--------|--------|
| Provider count | 18+ | 34 |
| API modes | 3 (chat, anthropic, codex) | 1 (LLMRouter dispatches) |
| Config source | config.yaml | DB (provider_configs table) |
| UI-managed | ❌ | ✅ via Settings page |
| Fallback chain | ✅ provider chain | ✅ circuit breaker |
| Quality scoring | ❌ | ✅ (provider health tracking) |
| Event rings | ❌ | ✅ (provider_events table) |

TestAI has more providers (34 vs 18+) and the UI-managed config is better for web.
Hermes has 3 distinct API modes vs TestAI's 1, but TestAI's LLMRouter handles
the differences internally.

---

## 10. What Would It Take?

### Tier 1: Quick Wins (1-3 days each, high impact)

| Change | Files to create/modify | Effort | Impact |
|--------|----------------------|--------|--------|
| **`skill_manage` tool** | `backend/harness/tools/skill_manager_tool.py` | 2-3 days | **High** — agent self-extension |
| **`session_search` tool** | `backend/harness/tools/session_search_tool.py` | 2-3 days | **High** — cross-session recall |
| **`web_extract` tool** | Enhance `web_fetch` or add new tool | 1 day | Medium — structured content |
| **Cron scheduler** | `backend/harness/scheduler/cron.py` | 3-5 days | **High** — periodic tasks |
| **Expand browser tools** | Enhance `browser_tool.py` (add click, type, scroll) | 3-5 days | Medium — richer web automation |

### Tier 2: Medium Effort (3-7 days each, structural)

| Change | Files to create/modify | Effort | Impact |
|--------|----------------------|--------|--------|
| **PTY terminal tool** | `backend/harness/tools/terminal_tool.py` + `harness/environments/pty.py` | 3-5 days | **High** — interactive shell |
| **Process management** | `backend/harness/tools/process_registry.py` | 2-3 days | **High** — bg process mgmt |
| **CLI entry point** | `backend/cli/main.py` (reuse Agent from harness) | 3-5 days | **High** — headless operation |
| **System prompt tiers** | Refactor `prompt_builder.py` for 3-tier assembly | 3-5 days | Medium — prompt caching |
| **Session lineage rotation** | Enhance `compress()` to create child sessions | 3-5 days | Medium — lineage chain |
| **3-tier system prompt** | Refactor `prompt_builder.py` | 3-5 days | Medium — prompt caching |

### Tier 3: Major Features (1-2 weeks each)

| Change | Files to create/modify | Effort | Impact |
|--------|----------------------|--------|--------|
| **Slack adapter** | `backend/harness/gateway/platforms/slack.py` | 5-7 days | **High** — messaging input |
| **Discord adapter** | `backend/harness/gateway/platforms/discord.py` | 5-7 days | **High** — messaging input |
| **Skill curator** | `backend/harness/skills/curator.py` | 5-7 days | High — skill lifecycle |
| **Plugin system** | Plugin discovery + registration for tools/memory | 5-7 days | **High** — extensibility |
| **Subprocess isolation** | Spawn subagents as subprocesses via subprocess/socket | 1-2 weeks | **High** — crash isolation |

### Total

Rough estimate: **20-35 days** to reach Hermes-level general-purpose capability,
depending on which Tier 3 features are included. The core harness is already there;
the gaps are in entry points (CLI, messaging, cron), extension (skills, plugins),
and tool completeness (terminal, browser).

---

## 11. Recommendation

### Short-term (focus on quick wins)

1. **Add `skill_manage` tool** (2-3 days) — enables agent self-extension, the
   biggest force multiplier. Agents can encode patterns as reusable skills.
   Reference: `reference/hermes-agent/tools/skill_manager_tool.py`.

2. **Add `session_search` tool** (2-3 days) — enables cross-session recall.
   Agents can search past conversations for solutions. Reference:
   `reference/hermes-agent/tools/session_search_tool.py`.

3. **Add PTY terminal tool** (3-5 days) — enables interactive shell, background
   processes, streaming output. The `bash` tool is a fire-and-forget command
   runner; a PTY terminal is an interactive session. Reference:
   `reference/hermes-agent/tools/terminal_tool.py`.

### Medium-term (structural improvements)

4. **Add cron scheduler** (3-5 days) — enables periodic tasks. Reference:
   `reference/hermes-agent/cron/scheduler.py`.

5. **Expand browser tools** (3-5 days) — add click, type, scroll, etc.
   Reference: `reference/hermes-agent/tools/browser_tool.py`.

6. **Add CLI entry point** (3-5 days) — enables headless operation, scripting.
   The harness already works; it just needs a CLI wrapper around
   `Agent.run_stream()`.

### Long-term (product direction decisions)

7. **Messaging adapters** — Slack/Discord/Telegram. Only if the product wants
   to be a multi-channel agent platform.

8. **Subprocess isolation** — Only if subagent crash isolation becomes a
   production requirement. The DB-backed tracker mitigates this for now.

9. **Plugin system** — Only if third-party extension is a goal. Hermes' plugin
   system adds significant maintenance surface.

### Final Verdict

**TestAI's harness is already 80% general-purpose.** The agent loop, middleware,
providers, tool dispatch, subagent delegation, session persistence, and
permission layer are all generic. The testing-specific tools are a thin layer on
`TOOLSETS` — they don't constrain the architecture.

The three things that make it "testing-oriented" rather than "general-purpose":
1. **Toolsets default to test-focused roles** (test-writer, bug-fixer,
   code-reviewer) rather than general-purpose ones (research, writing, data-analysis)
2. **No agent self-extension** (no `skill_manage`, no curator)
3. **No entry-point diversity** (web-only, no CLI, no messaging, no cron)

All three are solvable without touching the core harness. The harness itself is
general-purpose. The product focus is what narrows it.

---

## Sources

- Arize AI: "What is an Agent Harness?" (Apr 2026) — nine-component model
- Arize AI: "How Hermes implements an open source agent harness architecture" (Jun 2026)
- Hermes Agent reference: `reference/hermes-agent/toolsets.py`, `tools/delegate_tool.py`,
  `gateway/hooks.py`, `agent/context_compressor.py`, `tools/skill_manager_tool.py`,
  `tools/terminal_tool.py`, `cron/scheduler.py`, `hermes_state.py`
- TestAI codebase: `backend/harness/tools/toolsets.py`, `agent/agent.py`,
  `hook/pipeline.py`, `context_compressor/compressor.py`, `store/adapters/`,
  `services/job_checkpoint.py`
- DeerFlow Architecture (DeepWiki): multi-service topology, middleware pipeline
- Greptile TREX blog: agent-in-agent orchestration, shared context
