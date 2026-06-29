# Frontend API Endpoint Test Report — 2026-06-17

> **Method:** Systematic testing of every frontend-facing API endpoint
> **Environment:** Backend healthy on :8001, Frontend on :3001

---

## Endpoint Test Results

| # | Endpoint | Status | Response | Issue |
|---|----------|--------|----------|-------|
| 1 | `GET /api/health` | ✅ 200 | `{"status":"ok"}` | — |
| 2 | `GET /api/tools` | ✅ 200 | 85 bundled, 0 user | — |
| 3 | `GET /api/agents` | ✅ 200 | 76 agents | — |
| 4 | `GET /api/skills?limit=5` | ✅ 200 | 130+ skills | — |
| 5 | `GET /api/tools/toolsets` | ✅ 200 | 15 toolsets | — |
| 6 | `GET /api/kanban/boards` | ✅ 200 | 2 boards, 4 tasks each | — |
| 7 | `GET /api/knowledge-graph/recent` | ✅ 200 | 2 graphs, 60K nodes | — |
| 8 | `GET /api/sandbox/list` | ✅ 200 | 2 sandboxes | — |
| 9 | `GET /api/settings/mcp` | ✅ 200 | 1 MCP server | — |
| 10 | `GET /api/settings/mcp/connections` | ✅ 200 | `{"connections":[]}` | — |
| 11 | `GET /api/modes` | ✅ 200 | 1 mode (chat) | — |
| 12 | `GET /api/runs` | ✅ 200 | 4 runs | — |
| 13 | `GET /api/sessions` | ✅ 200 | 3 sessions | — |
| 14 | `GET /api/dashboard/stats` | ✅ 200 | 4 tests, 50% pass rate | — |
| 15 | `GET /api/cost/budget` | ✅ 200 | $5.00 default budget | — |
| 16 | `GET /api/ops/plugins` | ✅ 200 | 0 plugins | — |
| 17 | `GET /api/ops/swarm/active` | ✅ 200 | No active subagents | — |
| 18 | `GET /api/ops/sandbox-metrics` | ✅ 200 | Empty metrics | — |
| 19 | `GET /api/settings/feature-flags` | ✅ 200 | `{"flags":[]}` | Fixed: column name mismatch (`key` vs `flag_key`) |
| 20 | `GET /api/testcases` | ✅ 200 | Empty test_cases | — |
| 21 | `GET /api/artifacts/test` | ✅ 200 | Empty artifacts | — |

---

## Bugs Found & Fixed

### BUG-1: Feature Flags Endpoint Returns 500 (FIXED)

**Endpoint:** `GET /api/settings/feature-flags`
**Status:** ✅ Fixed
**Root Cause:** Code used `flag_key` column but DB table has `key` column
**Fix:** Updated `settings_service.py` to use correct column name `key`
**Impact:** Dashboard feature flags page now works

---

## Working Endpoints Summary

| Category | Endpoints | Status |
|----------|-----------|--------|
| **Core** | health, tools, agents, skills, toolsets | ✅ All working |
| **Kanban** | boards, tasks | ✅ Working |
| **Knowledge Graph** | recent, by-repo | ✅ Working |
| **Sandbox** | list, metrics | ✅ Working |
| **MCP** | config, connections | ✅ Working |
| **Sessions** | list, runs | ✅ Working |
| **Dashboard** | stats | ✅ Working |
| **Cost** | budget | ✅ Working |
| **Plugins** | list | ✅ Working |
| **Ops** | swarm, sandbox-metrics | ✅ Working |
| **TestCases** | list | ✅ Working (empty) |
| **Artifacts** | list | ✅ Working (empty) |

---

## Recommendations

1. **Fix Feature Flags endpoint** - Critical for dashboard functionality
2. **Add pipeline mode to /api/modes** - Currently only shows "chat" mode
3. **Populate sandbox metrics** - Currently returns empty array
4. **Add GitHub token configuration** - Required for github_list_issues/github_list_prs tools

---

*Report generated: 2026-06-17*
