# TestAI — Domain Glossary

Terms used by the agent architecture layer. Implementation details do not belong here — only concepts that span multiple modules or appear in design discussions.

## Agent & Delegation

- **Agent** — a single autonomous loop: `LLM.chat` → tool-call loop → response. Owns a `session_id`, a `system_prompt`, and a list of `ChatMessage`s.

- **Subagent** — an Agent spawned by another Agent (the parent). Has an isolated conversation, restricted tools, and its own `subagent_id`. Does not share context with the parent.

- **Parent Agent** — the Agent that called `delegate_task` to spawn a subagent. May be the root agent or another subagent acting as orchestrator.

- **Hybrid Adaptive Tree** — the delegation architecture: flat (parent→worker) by default, automatically escalating to a recursive tree when task complexity or repo size requires it. Depth is dynamic, not static.

- **Adaptive Depth Trigger** — a heuristic that causes the orchestrator to escalate from flat to hierarchical. Five triggers: task breadth (>5 subtasks), context pressure (>70% window), worker failure, repo size (>100 files), tool specialization (disjoint tool sets).

- **Subagent Lifecycle** — three modes: Sync (blocking inline call), Fan-Out (parallel spawn + collect_results), Background (fire-and-steer with subagent_id). The orchestrator chooses based on task nature and adaptive depth triggers.

- **Tool Access Model** — six-layer isolation: (1) child tools = requested ∩ parent, (2) always-blocked set for leaf workers, (3) orchestrator exception retains delegate_task, (4) MCP allow-list per subagent, (5) skills scoped to subagent goal, (6) credentials injected per-task at spawn time.

- **Autonomy Model** — hybrid: Autonomous (agent discovers tools/skills/MCPs on-demand from catalog) by default, Scoped (explicit constraint per agent type/goal) for sensitive tasks, Guardrails (hooks + HITL) always-on as safety net.

- **Skill/MCP Registration** — filesystem-first, Postgres mirrors metadata for dashboard. Skills are `SKILL.md` files at `~/.testai/skills/<name>/` (global) or `<cwd>/.testai/skills/<name>/` (project). MCP servers in `<cwd>/.testai/mcp.json`. Discovery: filesystem scan at startup → lightweight name+desc index → agent loads full content on-demand via `skill` tool.

- **Role** — a declaration (YAML + Pydantic schema) that configures an Agent: system_prompt, allowed_tools, allowed_skills, model with fallback, delegation_depth, bash_constraints, output_contract. Every subagent is an instance of a Role. Roles live in `.testai/agents/` (built-in) and `.testai/agents/_custom/` (user overrides).

- **Agent Registry** — the set of all available Role definitions. The orchestrator resolves a role name to a Role spec. Resolution order: user-defined DB role (via UI) → project `_custom/` YAML → built-in YAML. First match wins, with a startup warning on override.

- **Run** — the unit of work. A single execution of the autonomous orchestrator (or, for chat interactions, a single chat invocation that produced a `pipeline_runs` row). Owns a `run_id`, a `source` (user|github|cron|slack|linear|chat-submission), a tree of subagent invocations, and a `tier` (1=autonomous, 2=supervised, 3=human-authored). Runs are durable: progress survives process restarts via `stream_events` + checkpoints. The chat surface and the job/PR/webhook surface both produce Runs — they share the same concept.

- **JobSpec** — the handoff payload from the chat Role to the orchestrator. The chat Role's `submit_job` tool produces one of these; `OrchestratorEngine.run_job_spec(spec)` consumes it. Fields: `prompt`, `repo_url`, `branch`, `tier`, `capabilities` (e.g. `write_test_files`, `open_pr`), `approval` (review_queue routing), and `context` (carrying the chat session_id and agent_id). The dispatcher no longer unpacks the spec into ad-hoc args — the spec is the unit of handoff.

- **Tier** — the graduated autonomy level for a Run. Three values, matching the model used by Mabl / Bug0 / testRigor / Greptile:
  - `1` (autonomous) — the orchestrator runs to completion and opens a PR on success.
  - `2` (supervised) — the orchestrator runs, but the coordinator agent posts the diff to a kanban task and stops before `commit_and_open_pr`. A human reviews; the CI step opens the PR.
  - `3` (human-authored) — the orchestrator does NOT run code. It creates a kanban board carrying the spec's prompt as a proposal. A human reviews and either re-submits as tier 1/2 or rejects.
  Tier is set at job creation (either by the user via `submit_job`, or by the source system: a webhook defaults to tier 1, a Slack thread might default to tier 2, etc.). It is **not** mutable mid-run.

- **Orchestrator** — the autonomous work surface. Lives at `harness/orchestrator.py` (class `OrchestratorEngine`). The class's entry points are `run_job_spec(spec)`, `run_single(...)`, `run_multi(...)`, and `run(...)`. Internally the orchestrator sets up the sandbox, clones the repo, indexes the knowledge graph, loads cross-run memory, runs explore agents, creates a kanban board, then spawns a coordinator subagent via `delegate_task`. The coordinator drives the actual work: it plans via `orchestrate`, monitors via `orchestrate_monitor`, and fans out to subagents via `delegate_task`. The orchestrator is the only thing in the system that writes code, runs bash, or opens PRs.

- **Coordinator** — a special subagent Role spawned by the orchestrator to drive one job. The coordinator is the "manager" of the job: it plans, delegates, monitors. The orchestrator delegates TO the coordinator, never to leaf agents directly. The coordinator's `allowed_tools` is `["read", "write", "intelligence", "delegate", "specialized"]` — the full heavy toolset. The chat Role's `allowed_tools` does NOT include this set; only the orchestrator-spawned coordinator gets it.

- **Observability** — two tiers: (1) Web dashboard with real-time delegation tree via SSE/WebSocket, session history, token cost breakdown, root cause diagnosis, flaky test detection, coverage gap analysis, approval queue, activity heatmap; (2) optional OpenTelemetry export for existing enterprise observability infra.

- **Workspace Container** — per-run persistent Docker container. Repo cloned at `/workspace`, dependencies pre-installed. Each subagent gets its own sandbox container (Docker); sibling sandboxes share a named volume for artifact exchange but not execution environments. Per-subagent sandbox failure does not affect parallel siblings (orchestrator respawns with last checkpoint, max 2 retries). Single image: `nikolaik/python-nodejs` (Python 3.x + Node.js 22.x). Agents install additional runtimes (Go, Rust, Java) via bash as needed.

- **Artifact Storage** — test files, reports, and agent outputs persisted to Postgres with per-type configurable TTL. Defaults: committed test files = permanent, trajectories = 30d, LLM transcripts = 7d. Configured in Settings → Data Retention.

- **Cost Budgets** — four scopes (per-subagent, per-phase, per-run, per-user-per-day), each with soft (warn) and hard (throttle) caps. Four-step auto-throttle ladder: switch HITL mode → demote parallel to sequential → switch to cheaper model → pause. All defaults overridable per-run and per-org in Settings → Budgets.

- **PR Merge Strategy** — three modes configurable per-run via UI: (1) fully autonomous (agent pushes and merges), (2) PR + notify (agent opens PR with summary, human reviews), (3) PR + auto-merge on CI pass. Prod-code changes always require human review by default.

- **Database** — PostgreSQL as the single data store. Tables: `sessions` (tree-structured via `parent_session_id`), `messages` (JSONB content), `tasks` (status + priority + JSONB payload), `artifacts` (per-session file metadata), `token_usage` (cost tracking). Tree queries via recursive CTEs.

- **Agent Communication** — internal agents communicate through the shared backend (Postgres + direct function calls), not via A2A wire protocol. A2A patterns (task/send, task/stream, task/cancel) guide the API design so an A2A adapter can be added later without rewriting.

- **User Intervention** — five layers: Hooks (deterministic Pre/Post tool, SessionStart), Steer (inject mid-turn), HITL (approve/review/clarify/edit checkpoints), Control (interrupt/pause/cancel/fork), Reliability (checkpoint/resume).

## Tool Catalog

The complete set of primitive tools available to agents. No tool has baked-in knowledge of any test framework, language runtime, or build tool. Every tool is a generic capability the agent composes into workflows.

**FILESYSTEM — always available to all roles:**

- **bash** — execute arbitrary shell commands in the sandbox. The agent's universal execution primitive: runs tests, installs packages, starts servers, lints code, generates coverage. The agent reads stdout/stderr and interprets results itself.
- **read** — read file contents by path.
- **write** — create or overwrite a file.
- **edit** — surgical find-and-replace in an existing file. Accepts `old_string` and `new_string`.
- **apply_patch** — apply a multi-file diff in a single call. GPT-series models use this instead of `edit`+`write`.
- **glob** — find files by glob pattern (`**/*.test.ts`, `src/**/*.py`).
- **grep** — search file contents by regex or literal string.
- **list** — list directory contents.

**CODE INTELLIGENCE — read-only, gated per role:**

- **ast_grep** — structural code search by AST pattern. Finds code by syntax, not text. Example: "find all async functions missing try-catch" or "find all React components without data-testid". Powered by ast-grep (Rust, tree-sitter).
- **code_search** — semantic search across the entire codebase. Finds symbols, types, and references by name or fuzzy match.
- **dependency_graph** — BFS-based dependency analysis. Answers: "what calls this function?", "what depends on this module?", "what is the import chain?".
- **lsp** — Language Server Protocol client. Real-time hover info, go-to-definition, completions, find-references.

**KNOWLEDGE — all roles:**

- **web_fetch** — fetch URL content, convert to markdown.
- **web_search** — search the web via DuckDuckGo or configurable backend.
- **memory** — read and write cross-run facts. Three tiers: L0 raw artifacts, L1 indexed facts, L2 curated lessons.
- **skill** — discover and load reusable instructions from the skill registry.
- **tool_search** — discover available tools by capability at runtime. Lets the agent ask "what tools can write files?" or "what tools can search the web?".

**ORCHESTRATION — orchestrator and delegation-capable roles only:**

- **task** — spawn a subagent. Three modes: Sync (blocking), Fan-Out (parallel), Background (fire-and-steer). The orchestrator's primary delegation primitive.
- **send_message** — push structured results to external channels (Slack, Jira, Linear, email, webhook).
- **question** — pause and ask the user for clarification or approval. Returns the user's response.
- **todo** — track task progress across multiple LLM turns. Create, update, complete, and list tasks.

**SPECIALIZED — gated by Role YAML, opt-in:**

- **computer_use** — browser automation: screenshot, click, scroll, type, navigate. For end-to-end testing agents. Requires a vision-capable model.
- **vision_analyze** — analyze an image or screenshot sent by another tool. For non-vision models to understand visual output.
- **diagram** — generate Mermaid diagrams (flowcharts, sequence diagrams, ERDs, architecture diagrams). For reviewer and documentation agents.
- **database_query** — run read-only SQL queries against a configured database. For backend-testing agents.
- **image_generate** — generate images from a text prompt. For documentation and reporting agents.
