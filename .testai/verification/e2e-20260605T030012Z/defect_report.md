# E2E validation report

Artifact dir: `.testai/verification/e2e-20260605T030012Z`
Session ID: `43597ee8-4132-4f5b-8e4c-c0a49c39d077`

## Pass/fail matrix
- preflight_health_routes_provider: **PASS**
- pipeline_start: **PASS**
- delegate_stream: **FAIL**
- sandbox_apis: **PASS**
- kanban_apis: **PASS**
- delegation_ops_apis: **PASS**
- knowledge_graph_api_fs: **PASS**
- testcase_persistence_fs: **FAIL**
- standalone_autoheal: **FAIL**
- pipeline_integrated_autoheal: **FAIL**
- cost_token_endpoints: **PASS**
- ui_route_prefix_api_wiring: **PASS**
- web_search_docs_package_evidence: **FAIL**

## Defects
### E2E-003 — Critical
- Endpoint/artifact: `GET /api/delegate/43597ee8-4132-4f5b-8e4c-c0a49c39d077/stream`
- Repro: Open SSE stream after pipeline start
- Expected: Lifecycle events stream
- Actual: No stream events captured
- Evidence: see `defect_log.json` and endpoint artifacts
- Suspected area: delegate SSE / pipeline event emission
- Retest: stream emits started/progress/completed events

### E2E-004 — High
- Endpoint/artifact: `delegate stream + agent_workspace/knowledge-graphs`
- Repro: Run pipeline and inspect stream/files
- Expected: Per-test and per-fix KG updates during run
- Actual: No direct KG update evidence in stream
- Evidence: see `defect_log.json` and endpoint artifacts
- Suspected area: pipeline KG integration
- Retest: stream shows KG updates per test/fix; filesystem graph updated during run

### E2E-005 — High
- Endpoint/artifact: `pipeline stream`
- Repro: Run pipeline with autoheal mandatory
- Expected: Pipeline-integrated autoheal evidence appears when failures occur
- Actual: No pipeline-integrated autoheal evidence in stream
- Evidence: see `defect_log.json` and endpoint artifacts
- Suspected area: pipeline autoheal integration
- Retest: pipeline invokes autoheal as part of run, not only /api/tests/heal

### E2E-006 — High
- Endpoint/artifact: `pipeline stream/artifacts`
- Repro: Run pipeline requiring web/search/docs/package evidence
- Expected: Direct usage evidence captured
- Actual: No direct web/search/docs/package installation evidence in stream
- Evidence: see `defect_log.json` and endpoint artifacts
- Suspected area: tool usage observability / orchestrator instructions
- Retest: artifacts show web/search/docs usage and package install logs

### E2E-104 — Medium
- Endpoint/artifact: `http://127.0.0.1:8001/api/testcases`
- Repro: Call testcases_list
- Expected: Endpoint returns 2xx
- Actual: Endpoint failed
- Evidence: see `defect_log.json` and endpoint artifacts
- Suspected area: testcases_list
- Retest: endpoint returns 2xx with valid JSON

