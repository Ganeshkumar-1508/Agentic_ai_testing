# TestAI: Complete Porting Analysis from References

**Date**: 2026-06-27
**Sources**: Hermes, DeerFlow, OpenHands, OpenClaude — all in `reference/`

## Inventory: What Already Exists in TestAI

| Feature | TestAI File | Reference Equivalent |
|---------|-------------|---------------------|
| skill_manage | `tools/skill_tools.py:350` | Hermes `tools/skill_manager_tool.py` |
| skill_evolve/info/stats | `tools/skill_evolution_tools.py` | Hermes curator |
| process_registry | `tools/process_registry.py` | Hermes `tools/process_registry.py` |
| cronjob | `tools/cronjob_tool.py` | Hermes `tools/cronjob_tools.py` |
| delegate_task | `tools/subagent.py` | Hermes `tools/delegate_tool.py` |
| HookPipeline (3-phase) | `hook/pipeline.py` | Hermes middleware chain |
| 34 providers | `providers/__init__.py` | Hermes provider profiles |
| DB-backed tracker | `services/job_checkpoint.py` | Hermes in-memory only |
| compressions lineage | `context_compressor/compressor.py` | Hermes lineage rotation |
| Postgres stores | `store/adapters/postgres.py` | DeerFlow's multi-backend pattern |
| browser_navigate/snapshot | `tools/browser.py` | Hermes browser_tool (simpler) |
| web_search/web_fetch | `tools/web_tools.py` | DeerFlow community/ (simpler) |
| per-orchestrator pipeline | `phases/pipeline.py` | DeerFlow RunManager |

## Full Porting Catalog

### Tier P0: High Value, Low Effort (1-3 days each)

| # | Feature | Source | File(s) | Effort | Impact |
|---|---------|--------|---------|--------|--------|
| 1 | **session_search tool** | Hermes | `reference/hermes-agent/tools/session_search_tool.py` (18 symbols) | 2d | Cross-session FTS5 search — agents recall past solutions |
| 2 | **web_extract tool** | Hermes | `reference/hermes-agent/tools/web_tools.py` (61 symbols) | 1d | Structured HTML extraction vs markdown-only web_fetch |
| 3 | **Clarify with multi-choice** | Hermes | `reference/hermes-agent/tools/clarify_tool.py` (9 symbols) | 1d | Better UX — agents ask structured questions |
| 4 | **Browser click/type/scroll** | Hermes | `reference/hermes-agent/tools/browser_tool.py` (153 symbols) | 3d | Full web automation — currently 2 tools only |
| 5 | **Memory per-user isolation** | DeerFlow | `reference/deer-flow/.../runtime/user_context.py` (17 symbols) | 2d | Multi-tenant safety — every user gets isolated state |

### Tier P1: Medium Value, Medium Effort (3-5 days each)

| # | Feature | Source | File(s) | Effort |
|---|---------|--------|---------|--------|
| 6 | **13 search providers** | DeerFlow | `reference/deer-flow/.../community/{tavily,jina,firecrawl,searxng,serper,brave,browserless,exa,image_search,ddg_search,infoquest,groundroute,fastcrw}/` | 3d |
| 7 | **RunEventStore (JSONL + memory)** | DeerFlow | `reference/deer-flow/.../runtime/events/store/{base,jsonl,memory,db}.py` | 3d |
| 8 | **RunManager (persistence + retry)** | DeerFlow | `reference/deer-flow/.../runtime/runs/manager.py` (46 symbols) | 3d |
| 9 | **Token breakdown by caller type** | DeerFlow | `reference/deer-flow/.../runtime/runs/store/base.py` — tracks lead/subagent/middleware tokens separately | 2d |
| 10 | **PTY terminal tool** | Hermes | `reference/hermes-agent/tools/terminal_tool.py` (105 symbols) | 4d |
| 11 | **CLI entry point** | Hermes | `reference/hermes-agent/cli.py` | 4d |

### Tier P2: Niche / Structural (5-7 days each)

| # | Feature | Source | Effort |
|---|---------|--------|--------|
| 12 | **Slack/Discord messaging adapters** | DeerFlow | `reference/deer-flow/backend/app/channels/{slack,discord}.py` | 5-7d |
| 13 | **Docker sandbox** | DeerFlow | `reference/deer-flow/.../community/aio_sandbox/` (7 files) | 5d |
| 14 | **Auth middleware + user context** | OpenHands | `reference/OpenHands/openhands/app_server/user/user_context.py` | 5d |
| 15 | **Org-level app settings** | OpenHands | `reference/OpenHands/enterprise/server/services/org_app_settings_service.py` | 3d |
| 16 | **Schema migrations (Alembic)** | DeerFlow | `reference/deer-flow/.../persistence/migrations/` | 3d |
| 17 | **3-tier system prompt** | Hermes | `reference/hermes-agent/agent/prompt_builder.py` | 4d |
| 18 | **Checkpointer with multi-backend** | DeerFlow | `reference/deer-flow/.../runtime/checkpointer/{provider,async_provider}.py` | 3d |
| 19 | **Subprocess isolation** | N/A | Spawn subagents as separate processes | 1-2w |

## Recommended Order

```
Week 1: P0 items 1-5 (session_search, web_extract, clarify, browser, user_context)
Week 2: P1 items 6-9 (search providers, event store, run manager, token tracking)
Week 3: P1 items 10-11 (terminal, CLI) + P2 items 12 (one messaging adapter)
Week 4: P2 items 14-15 (auth, org settings) + 17 (system prompt)
```

It would take roughly **one month** with focused effort to bring TestAI's harness to
full parity with the reference implementations across all dimensions.
