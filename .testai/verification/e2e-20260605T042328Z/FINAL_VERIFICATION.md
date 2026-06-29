# Final strict E2E verification

Artifact dir: .testai/verification/e2e-20260605T042328Z
Session ID: a3aae15c-2b66-401d-9c60-12e6266e80b1
Final verdict: **FAIL**

## Exact stream events
- pipeline_autoheal_started: **FAIL**
- pipeline_autoheal_completed: **FAIL**
- pipeline_kg_fix_updated: **FAIL**

## Mandatory endpoints
- post_api_tests_heal: **PASS**
- get_api_healing_stats: **PASS**
- get_api_ops_swarm_delegate_events: **PASS**
- post_api_testcases: **PASS**

## Core evidence
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

## Remaining defects
- E2E-005
- pipeline_autoheal_started
- pipeline_autoheal_completed
- pipeline_kg_fix_updated
- pipeline_integrated_autoheal
