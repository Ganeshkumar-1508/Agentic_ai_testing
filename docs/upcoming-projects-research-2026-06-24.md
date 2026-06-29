# Upcoming Projects — Can Benefit TestAI

Researched 2026-06-24. Projects found via GitHub topic search and web research.
Each entry includes relevance to TestAI and specific patterns to adopt.

---

## Tier 1: Directly Adoptable (High Impact)

### 1. Sponsio — Deterministic Agent Safety
**Stars:** 477 | **Repo:** SponsioLabs/Sponsio | **Language:** Python/TypeScript
**What it does:** Runtime policy enforcement for AI agents. Compiles safety rules into deterministic contracts checked in <0.01ms with zero LLM cost. 16 contract bundles (universal, shell, filesystem, capability, etc.). 95.6% misalignment prevention on benchmarks.

**Why for TestAI:** TestAI's 6-layer Tool Access Model is granular but runtime-expensive (relies on LLM checks and PermissionManager queries). Sponsio's approach — compile policies into deterministic checks that run in microseconds — is a direct improvement. Could replace or augment `harness/permissions/manager.py`.

**Specific patterns to adopt:**
- Policy compilation (rules → deterministic checks, no LLM in hot path)
- Contract bundles per agent type (universal, shell, filesystem match TestAI's toolsets)
- Runtime enforcement at the tool dispatch boundary (before tool executes, not after)
- 16 pre-built contract bundles as reference for TestAI's permission rules

**Effort to integrate:** ~3 sprints
- Sprint 1: Sponsio integration adapter in `harness/permissions/sponsio_adapter.py`
- Sprint 2: Port existing permission rules to Sponsio contracts
- Sprint 3: Remove old PermissionManager path, validate with existing tests

---

### 2. TokenTamer — Context Compression Proxy
**Stars:** 123 | **Repo:** borhen68/TokenTamer | **Language:** Python
**What it does:** Drop-in proxy between agent and LLM API that compresses code context by 50-80%. Uses AST parsing to skeletonize "background" files (preserving signatures, stripping bodies). Tool-aware compression: skeletonizes stale `tool_result` reads while keeping the latest read intact. Injects Anthropic cache breakpoints for ~73% off input tokens.

**Why for TestAI:** TestAI's `context_compressor/` does lossy summarization of conversation turns, but doesn't do AST-level code compression. TokenTamer's approach is complementary — compress code at the tool-result level before it enters the conversation, rather than compressing the conversation after the fact.

**Specific patterns to adopt:**
- AST-based file skeletonization (strip function bodies, keep signatures + imports)
- Tool-aware stale read detection (which file reads are old vs current)
- Anthropic prompt caching breakpoint injection (TestAI has `prompt_caching.py` — TokenTamer's approach is more aggressive)
- Streaming proxy architecture (no latency overhead, compression in milliseconds)

**Effort to integrate:** ~2 sprints
- Sprint 1: AST skeletonizer in `harness/context_compressor/ast_skeletonizer.py`
- Sprint 2: Wire into tool dispatch (compress tool results before storing in conversation)

---

### 3. Chorus — AI-Human Collaboration Harness
**Stars:** 1k | **Repo:** Chorus-AIDLC/Chorus | **Language:** TypeScript/Next.js
**What it does:** Agent harness for AI-Human Collaboration. AI-DLC workflow: Idea → Proposal → Document + Task DAG → Execute → Verify → Done. Fine-grained agent permissions (5 resources × 3 actions matrix). Agent Connections for live observability (streaming transcripts, instruction injection, interrupt/resume). Reversed Conversation pattern (AI proposes, humans verify).

**Why for TestAI:** Chorus' workflow model maps directly to TestAI's KanbanService and tier system. The AI-DLC workflow is a richer task lifecycle than TestAI's current kanban (which is board→task→column). Chorus' Agent Connections pattern is a richer UX on top of TestAI's SSE streaming.

**Specific patterns to adopt:**
- AI-DLC workflow stages for KanbanService (Idea→Proposal→Execute→Verify→Done)
- 5×3 permission matrix (replaces current role-based tool gating with resource+action pairs)
- Agent Connections dashboard pattern for real-time agent observability
- Reversed Conversation for tier 2 (supervised) workflow

**Effort to integrate:** ~2 sprints
- Sprint 1: Add AI-DLC workflow stages to KanbanService
- Sprint 2: Agent Connections-style dashboard widgets

---

## Tier 2: Medium-Term Opportunities

### 4. oh-my-pi — Hash-Anchored Coding Agent
**Stars:** 14.3k | **Repo:** can1357/oh-my-pi | **Language:** Rust/TypeScript
**What it does:** AI coding agent with hash-anchored edits (checksum file before writing — rejects edit if file changed), LSP wired into every write (renames update barrel files automatically), DAP integration (debugger attachment), time-traveling stream rules (abort mid-token on rule violation), subagent delegation.

**Relevant patterns for TestAI:**
- **Hash-anchored edits:** `edit_file` tool should checksum the file before applying the edit. If the file on disk doesn't match the expected hash, reject the edit. This prevents the "edited wrong file" bug that plagues all coding agents.
- **LSP pre-flight checks:** Before writing a file, run LSP diagnostics. If the edit introduces syntax errors, reject it before the LLM sees the result.
- **DAP integration:** Expose debugger ports in the sandbox. Let agents attach `lldb`/`dlv`/`debugpy` instead of sprinkling print statements.
- **Time-traveling rules:** Hook system enhancement — instead of post-hoc validation, abort the tool call mid-stream and inject a correction.

**Effort to integrate:** ~4 sprints spread across tools/editor, hooks, sandbox

---

### 5. TrustGraph — Holonic Context Graphs
**Stars:** 2.2k | **Repo:** trustgraph-ai/trustgraph | **Language:** Python
**What it does:** Structured knowledge management for agents using RDF/OWL/SHACL-based holonic context graphs. Dramatically reduces token usage by reusing context across sessions. Full provenance tracking on every fact. Versionable, composable, team-shareable context cores.

**Relevant patterns for TestAI:**
- **Holonic context model for L2 memory:** TestAI's 3-tier memory (L0 raw, L1 indexed, L2 curated) currently stores L2 as flat key-value facts. TrustGraph shows how to store them as structured, versioned graphs with provenance.
- **Context Cores:** Portable, deployable knowledge units. TestAI could adopt this for cross-run memory packaging.
- **Graph-grounded retrieval:** Instead of vector-only RAG, use graph structure to retrieve related facts with full provenance.

**Effort to integrate:** ~3 sprints for L2 memory upgrade. TrustGraph itself could be used as a dependency rather than rewritten.

---

### 6. abtop — Agent Process Monitor
**Stars:** 3.1k | **Repo:** graykode/abtop | **Language:** Rust
**What it does:** Like `htop` for AI coding agents. Monitors Claude Code, Codex CLI, OpenCode sessions in real-time. Per-session token tracking, context window %, rate limits, child processes, open ports, subagents, memory status. Terminal UI with 12 themes. Works across macOS, Linux, Windows.

**Relevant patterns for TestAI:**
- **Add to dashboard:** TestAI's observability dashboard could add an abtop-style live agent monitor panel showing per-session token usage, context window %, rate limits, and active subagents.
- **Orphan port detection:** If a subagent spawns a server and forgets to kill it, abtop detects the orphan. TestAI's sandbox reaper could adopt this.
- **Rate limit monitoring:** Real-time tracking of API rate limit usage per provider. TestAI's cost tracker could surface this.

**Effort to integrate:** ~1 sprint for dashboard widget. Could use abtop as a library dependency (it exposes a Rust crate and JSON snapshot API).

---

### 7. oh-my-agent — Portable Multi-Agent Harness
**Stars:** 1.1k | **Repo:** first-fluke/oh-my-agent | **Language:** TypeScript
**What it does:** Vendor-agnostic multi-agent harness. Specialized agents by domain: frontend, backend, architecture, QA, PM, DB, mobile, infra, debug, design. Works across Claude Code, Codex, Cursor, OpenCode, Pi, Qwen Code, and more. Skills, workflows, agent teams.

**Relevant patterns for TestAI:**
- **Domain-specialized agent roles:** TestAI's Role system defines agents by tool access; oh-my-agent defines them by domain expertise. Combining both would yield richer agent role definitions.
- **Cross-IDE portability:** oh-my-agent projects `.agents/` as a single source of truth into every IDE's native format. TestAI could adopt this pattern for its Role YAML → IDE plugin mapping.
- **Agent team presets:** Pre-configured teams (Fullstack, Frontend, DevOps, etc.) that users can adopt with one command.

**Effort to integrate:** ~2 sprints for richer Role definitions. The cross-IDE projection pattern is a longer-term investment.

---

### 8. thClaws — Native Rust Agent Harness
**Stars:** 1.1k | **Repo:** thClaws/thClaws | **Language:** Rust
**What it does:** Native Rust agent harness with four surfaces (GUI, CLI, headless, webapp) from one binary. Multi-provider, MCP, skills, plugins, agent teams, media generation. OpenRouter Fusion for multi-model deliberation. Telegram/Discord/Slack/WhatsApp gateway.

**Relevant patterns for TestAI:**
- **Multi-surface architecture:** One agent engine serving desktop GUI + CLI + headless + webapp. TestAI has webapp + CLI but the engine is tightly coupled to FastAPI. thClaws' engine-first design is cleaner.
- **OpenRouter Fusion:** Multi-model deliberation — up to 8 models answer in parallel, a judge synthesizes consensus. TestAI's coordinator could use this for high-stakes decisions (PR review, tier-2 approval).
- **Media generation pipeline:** Text→Image→Video pipeline built into the agent. TestAI could use this for test-screenshot generation or visual regression testing.

**Effort to integrate:** ~3 sprints for Fusion pattern. Full integration would be a larger project.

---

## Summary

| Project | Stars | Language | Key Pattern for TestAI | Priority | Effort |
|---------|-------|----------|----------------------|----------|--------|
| **Sponsio** | 477 | Python/TS | Deterministic policy enforcement (0.01ms, zero LLM) | **High** | 3 sprints |
| **TokenTamer** | 123 | Python | AST-based context compression (50-80% savings) | **High** | 2 sprints |
| **Chorus** | 1k | TS/Next.js | AI-DLC workflow, Agent Connections dashboard | **High** | 2 sprints |
| oh-my-pi | 14.3k | Rust/TS | Hash-anchored edits, LSP pre-flight, DAP | Medium | 4 sprints |
| TrustGraph | 2.2k | Python | Holonic context graphs for L2 memory | Medium | 3 sprints |
| abtop | 3.1k | Rust | Agent process monitor (htop for agents) | Low | 1 sprint |
| oh-my-agent | 1.1k | TS | Domain-specialized agent roles, cross-IDE SSOT | Low | 2 sprints |
| thClaws | 1.1k | Rust | Multi-surface engine, OpenRouter Fusion | Low | 3 sprints |

---

## Tier 3: Additional Categories (from deeper GitHub search)

### Agent Testing & Evaluation

### 9. Scenario — Agent Testing Framework
**Stars:** 903 | **Repo:** langwatch/scenario | **Languages:** Python/TypeScript/Go
**What it does:** Agent Testing Framework based on simulations. Tests real agent behavior by simulating users in different scenarios and edge cases. Multi-turn conversation control. Combine with any LLM eval framework. Integrate your agent by implementing one `call()` method.

**Why for TestAI:** This is a direct fit for TestAI's testing mission. Currently TestAI tests agents via `pytest` + mocks. Scenario adds simulation-based testing: run a "user simulator" agent against TestAI's agent, verify tool calls, assert conversation flow, check outcomes. This would let TestAI test its own agents the way it wants to test its customers' agents.

**Specific patterns to adopt:**
- Simulation-based agent testing (user simulator vs agent under test)
- Multi-turn conversation assertions (state.has_tool_call, state.has_message)
- Scenario script control (.user() → .agent() → assert → .succeed())
- Framework-agnostic AgentAdapter interface

**Effort to integrate:** ~2 sprints
- Sprint 1: Adapt TestAI's agent to Scenario's AgentAdapter interface
- Sprint 2: Write simulation tests for coordinator, subagent delegation, tool dispatch

---

### 10. Replayd — Replayable Agent Regression Tests
**Stars:** 17 | **Repo:** TaimoorKhan10/replayd | **Language:** Python
**What it does:** Turn failed AI agent runs into replayable regression tests. Catch regressions before they ship. Records agent trajectories and replays them deterministically.

**Why for TestAI:** TestAI's `stream_events` + checkpoint system already captures run trajectories. Replayd's pattern would let TestAI replay a failed Run as a regression test — ensuring that a fix doesn't regress on a previous failure. Natural fit with the existing event store.

**Effort to integrate:** ~1 sprint (adapter on top of existing stream_events table)

---

### 11. agentverify — Deterministic Agent Testing (pytest plugin)
**Stars:** 8 | **Repo:** simukappu/agentverify | **Language:** Python
**What it does:** pytest plugin for deterministic testing of AI agents. Assert agent actions, not vibes.

**Why for TestAI:** Could replace or augment TestAI's existing test patterns. If mature, adopt as the standard testing approach for TestAI's own agents.

---

### Agent Security & Sandboxing

### 12. Nono — Zero-Latency Agent Sandbox
**Stars:** 2.8k | **Repo:** always-further/nono | **Language:** Rust
**What it does:** Sandbox any AI agent in seconds with zero setup, zero daemon, zero container, zero VM. Enforces least-privilege sandbox (read/write to cwd only — SSH keys, cloud creds, rest of disk invisible). Supports macOS, Linux, Windows (WSL2). Composable policy system, credentials injection, L7 filtering, supply chain security, audit. Profile registry for all major agents (Claude Code, Codex, Hermes, OpenCode, OpenClaw, etc.).

**Why for TestAI:** **Directly relevant to TestAI's sandbox strategy.** Nono solves the same problem TestAI's Docker sandbox solves, but with zero latency — no container startup, no daemon. Uses kernel-native isolation (namespace + seccomp) instead of Docker. TestAI could:
- Add Nono as a lightweight sandbox backend alongside Docker (for dev/CI where Docker is too heavy)
- Use Nono's profile registry as inspiration for TestAI's sandbox profiles
- Adopt Nono's composable policy system for TestAI's permission model

**Key difference from TestAI's Docker sandbox:** Nono is lighter but less isolated (process-level vs container-level). Docker is better for CI/production; Nono is better for dev iteration speed.

**Effort to integrate:** ~2 sprints for Nono adapter in SandboxManager

---

### 13. Mirage — Unified Virtual Filesystem for Agents
**Stars:** 3.2k | **Repo:** strukto-ai/mirage | **Language:** Python/TypeScript
**What it does:** Unified Virtual File System for AI Agents. Mounts services (S3, GDrive, Slack, Gmail, Redis, GitHub, Linear, Notion, Postgres, etc.) side-by-side as one filesystem. Any LLM that knows `bash` can read, grep, and pipe across every backend with zero new vocabulary. 50+ built-in backends. Portable workspaces that can be cloned, snapshotted, and versioned.

**Why for TestAI:** This is a **game-changer for TestAI's tool system.** Instead of writing N separate API tools for Slack, GitHub, Jira, etc., TestAI could mount them all as filesystem paths. Agents would use `grep /slack/channels/general/` instead of `slack_search`. The same `bash` tool would work everywhere. This massively simplifies TestAI's tool catalog — potentially eliminating 10-15 API-specific tools in favor of one universal filesystem.

**Specific patterns to adopt:**
- Mount external services as filesystem paths (Slack channels → `/slack/`, GitHub issues → `/github/`)
- Replace API-specific tools with filesystem operations (no new tool needed)
- Portable workspaces for agent session state
- Extensible command system (register custom commands per resource + filetype)

**Effort to integrate:** ~3 sprints
- Sprint 1: Integrate Mirage into sandbox workspace
- Sprint 2: Replace top 5 API-specific tools with Mirage filesystem paths
- Sprint 3: Extend tool_dispatch to prefer Mirage paths over API calls

---

### Agent Observability

### 14. Logfire — AI Observability (by Pydantic)
**Stars:** 4.3k | **Repo:** pydantic/logfire | **Language:** Python
**What it does:** AI observability platform for production LLM and agent systems. Built by the Pydantic team. Traces, metrics, logging for LLM calls, tool executions, agent steps. OpenTelemetry-based.

**Why for TestAI:** TestAI already has OpenTelemetry support (F04). Logfire is a purpose-built dashboard on top of OTel that's specifically designed for agent traces. Could replace or augment TestAI's custom observability dashboard with a Pydantic-maintained solution. Direct integration path since TestAI already uses Pydantic.

**Effort to integrate:** ~1 sprint (wire OTel exporter to Logfire endpoint)

---

### 15. Claude-TAP — Agent API Traffic Inspector
**Stars:** 2k | **Repo:** liaohch3/claude-tap | **Language:** Python
**What it does:** Intercept and inspect Coding Agent API traffic from Claude Code, Codex CLI, Gemini CLI, Cursor CLI, OpenCode, Kimi, Pi, and Hermes in a local trace viewer. MITM proxy for agent ↔ LLM traffic.

**Why for TestAI:** Could be used as a debugging tool during TestAI's own development. Inspect exactly what the LLM sends and receives. Useful for debugging tool call formatting, prompt construction, and response parsing. Also useful as a reference for implementing TestAI's own traffic inspection.

**Effort to integrate:** ~1 day (run alongside TestAI during development)

---

### Agent Memory

### 16. Cognee — Open-Source AI Memory Platform
**Stars:** 20.1k | **Repo:** topoteretes/cognee | **Language:** Python
**What it does:** Open-source AI memory platform for agents. Persistent long-term memory across sessions with a self-hosted knowledge graph engine. GraphRAG, vector search, cognitive architecture.

**Why for TestAI:** Directly relevant to TestAI's L1/L2 memory tiers. Currently TestAI stores memory as flat key-value facts via `memory_tool.py`. Cognee provides a full memory platform with knowledge graphs, vector search, and cross-session persistence — could replace or augment the memory layer.

**Effort to integrate:** ~2 sprints (replace memory_tool backend with Cognee)

---

### 17. Memori — Agent-Native Memory Infrastructure
**Stars:** 15.4k | **Repo:** MemoriLabs/Memori | **Language:** Python
**What it does:** Agent-native memory infrastructure. LLM-agnostic layer that turns agent execution and conversation into structured, persistent state. MCP-compatible. Long-term, short-term, episodic memory.

**Why for TestAI:** Similar to Cognee but more focused on conversation/execution memory rather than knowledge graphs. TestAI's L0 raw artifacts + L1 indexed facts pattern aligns with Memori's approach.

---

### Agent LLM Gateway & Routing

### 18. BitRouter — Agentic LLM Gateway
**Stars:** 185 | **Repo:** bitrouter/bitrouter | **Language:** Rust
**What it does:** Open-source agentic LLM gateway & router. Cost-optimizes agentic workflows. Works with any harness, any model. MCP, ACP support. Litellm-compatible.

**Why for TestAI:** TestAI's `LLMRouter` already handles multi-provider routing. BitRouter adds cost optimization — automatically routes to the cheapest model that can handle a given request. Could be used as a fallback/enhancement for TestAI's provider resolution.

---

## Updated Summary

| Priority | Project | Stars | Key Pattern for TestAI | Effort |
|----------|---------|-------|----------------------|--------|
| **1** | Sponsio | 477 | Deterministic policy enforcement (0.01ms, zero LLM) | 3 sprints |
| **2** | TokenTamer | 123 | AST-based context compression (50-80% savings) | 2 sprints |
| **3** | Scenario | 903 | Simulation-based agent testing (agents test agents) | 2 sprints |
| **4** | Chorus | 1k | AI-DLC workflow, Agent Connections dashboard | 2 sprints |
| **5** | Mirage | 3.2k | Unified VFS — replace 10-15 API tools with filesystem ops | 3 sprints |
| **6** | Nono | 2.8k | Zero-latency sandbox (alternate to Docker) | 2 sprints |
| **7** | Cognee | 20.1k | Memory platform with knowledge graph (replace memory_tool) | 2 sprints |
| **8** | oh-my-pi | 14.3k | Hash-anchored edits, LSP pre-flight, DAP | 4 sprints |
| **9** | Logfire | 4.3k | Agent observability dashboard (Pydantic/OTel) | 1 sprint |
| 10 | TrustGraph | 2.2k | Holonic context graphs for L2 memory | 3 sprints |
| 11 | abtop | 3.1k | Agent process monitor dashboard widget | 1 sprint |
| 12 | claude-tap | 2k | Agent API traffic inspector | 1 day |
| 13 | Replayd | 17 | Replayable agent regression tests | 1 sprint |
| 14 | BitRouter | 185 | Cost-optimizing LLM router | 2 sprints |
| 15 | oh-my-agent | 1.1k | Domain-specialized agent roles | 2 sprints |
| 16 | thClaws | 1.1k | Multi-surface engine, OpenRouter Fusion | 3 sprints |
| 17 | agentverify | 8 | Pytest plugin for deterministic agent testing | 1 sprint |
| 18 | Memori | 15.4k | Agent-native memory infrastructure | 2 sprints |
