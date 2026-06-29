# E2E validation report

Artifact dir: `.testai/verification/e2e-20260605T042328Z`
Session ID: `a3aae15c-2b66-401d-9c60-12e6266e80b1`

## Pass/fail matrix
- preflight_health_routes_provider: **PASS**
- pipeline_start: **PASS**
- delegate_stream: **PASS**
- sandbox_apis: **PASS**
- kanban_apis: **PASS**
- delegation_ops_apis: **PASS**
- knowledge_graph_api_fs: **PASS**
- testcase_persistence_fs: **PASS**
- standalone_autoheal: **PASS**
- pipeline_integrated_autoheal: **FAIL**
- cost_token_endpoints: **PASS**
- ui_route_prefix_api_wiring: **PASS**
- web_search_docs_package_evidence: **PASS**

## Defects
### E2E-005 — High
- Endpoint/artifact: `pipeline stream`
- Repro: Run pipeline with autoheal mandatory
- Expected: Pipeline-integrated autoheal evidence appears when failures occur
- Actual: No pipeline-integrated autoheal evidence in stream
- Evidence: see `defect_log.json` and endpoint artifacts
- Suspected area: pipeline autoheal integration
- Retest: pipeline invokes autoheal as part of run, not only /api/tests/heal

