# Candidate 17: Consolidate the fragmented security/permissions model into a single enforcement seam

**Strength**: Worth exploring | **Category**: security architecture / fragmented enforcement

---

## Research sources (10)

### Agent harness security patterns

1. **Aakash Gupta — "The 6 Components That Make Harnesses Work"** — Component 2: "Filesystem access management. Harnesses define accessible directories, allowed operations, and conflict resolution." Component 6: "Lifecycle hooks." Security is ONE component, not 7 fragmented files. https://aakashgupta.medium.com/2025-was-agents-2026-is-agent-harnesses-heres-why-that-changes-everything-073e9877655e

2. **Aakash Gupta — "Three Harness Design Principles"** — Principle 2: "Progressive disclosure. Start with limited tools and permissions. Expand as tasks require. Least privilege by default." A single policy model, not fragmented enforcement. https://aakashgupta.medium.com/2025-was-agents-2026-is-agent-harnesses-heres-why-that-changes-everything-073e9877655e

3. **OpenCode** — Single `opencode.json` config with permission model. MCP tools have a unified "Permission system for controlling access." One config, one enforcement point. https://github.com/opencode-ai/opencode

4. **Anthropic — Claude Code sandboxing** — "Reducing approval friction without losing control through better sandboxing and policy design." One sandbox model, one policy system. https://www.anthropic.com/engineering/claude-code-sandboxing

5. **Citadel** — "Safety hooks: 35 Node hook scripts across 29 lifecycle events protect files, gate risky actions, and record handoffs." One hook system for all safety. https://github.com/SethGammon/Citadel

6. **a0 Agent Harness** — Single "Guardrail System" in the safety section. One system, one doc page. https://deepwiki.com/a0-community-plugins/agent_harness/10-web-ui

7. **Hermes Agent** —`builtin_hooks/` directory with one pattern for all permission hooks. Deterministic gates are one subsystem, not scattered across middleware + hooks + registry + manager. https://github.com/NousResearch/hermes-agent

8. **CONTEXT.md — Tool Access Model** — "Six-layer isolation: child tools = requested ∩ parent, always-blocked set, orchestrator exception, MCP allow-list, skills scoped, credentials injected." The domain model defines ONE model with six layers, but the implementation splits it across 7+ files.

9. **CONTEXT.md — Autonomy Model** — "Guardrails (hooks + HITL) always-on as safety net." Guardrails are ONE concept in the domain model, but the code has 7+ enforcement mechanisms.

10. **Codebase audit — security enforcement split across 7+ files** (see below)

---

## Codebase evidence

### Security/permissions enforcement is split across 7+ files

| File | What it enforces | Mechanism |
|---|---|---|
| `permissions/manager.py` (54 sym) | File access permissions | PermissionManager class |
| `permissions/file_state.py` (34 sym) | File state tracking | Change detection |
| `permissions/glob_rules.py` (19 sym) | Glob-based access rules | Pattern matching |
| `middleware/guardrails.py` (20 sym) | Pre-tool authorization | Middleware hook |
| `middleware/safety.py` (11 sym) | Safety finish reason | Provider response filter |
| `hook_registry.py` (22 sym) | Deterministic allow/block/ask gates | JSON rules + check_pre |
| `sandbox_scope.py` (16 sym) | Sandbox isolation scope | Scoping rules |
| `tools/registry.py` (tool level) | Tool default_level (allow/ask/deny) | Decorator/attribute |
| `agent/tool_dispatch.py` (role gating) | Role-based tool access | allowed_tools set |

### The coordination gap

| Scenario | Which systems fire | What they decide |
|---|---|---|
| Agent tries to `rm -rf /` | hook_registry.check_pre → guardrails → tool_dispatch role gate | 3 decisions, no ordering contract |
| Agent writes to a protected file | permissions/manager → sandbox_scope → guardrails | 3 checks, no shared state |
| Agent calls a denied tool | tool_dispatch role gate → hook_registry → guardrails | 3 checks, same answer |

Each system independently decides allow/block/ask. There's no `SecurityEnforcer` that coordinates them, no ordering guarantee, no shared policy model, no unified audit log. The CONTEXT.md defines "six-layer isolation" as a single concept, but the implementation is 7+ files with no coordinator.

### The contraction

Define a `SecurityEnforcer` that coordinates all 7 enforcement mechanisms into one seam:
- **Policy** — one `PolicyConfig` (allow/block/ask rules, globs, sandbox scope, tool defaults)
- **Enforcement** — ordered pipeline: role gate → tool level → hook_registry → guardrails → permissions → sandbox → audit
- **Audit** — unified log of all enforcement decisions

This matches Aakash Gupta's "Filesystem access management" as one component, OpenCode's single `opencode.json` permission model, and the domain model's "six-layer isolation" as one coordinated system.
