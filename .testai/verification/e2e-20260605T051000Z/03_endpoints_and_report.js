const { BASE, save, load, request, newest } = require('./e2e_common');

function ok(all, name) { return Boolean(all[name] && all[name].ok); }

(async () => {
  const pipeline = load('pipeline_start.json');
  const stream = load('delegate_stream.json', { session_id: null, events: [] });
  const session = stream.session_id || null;
  const checks = {};
  async function add(name, path, method = 'GET', body = null, timeout = 30000) {
    checks[name] = await request(name, method, `${BASE}${path}`, body, timeout);
  }
  for (const [name, path] of [
    ['sandbox_list', '/api/sandbox/list'], ['sandbox_metrics', '/api/sandbox/metrics'], ['sandbox_exec_containers', '/api/sandbox/exec-containers'],
    ['kanban_list_boards', '/api/kanban/boards'], ['ops_tools', '/api/ops/tools'], ['ops_active_subagents', '/api/ops/swarm/active'],
    ['ops_delegate_events', '/api/ops/swarm/delegate-events'], ['ops_summary', '/api/ops/swarm/summary'], ['ops_plugins', '/api/ops/plugins'],
    ['ops_hooks', '/api/ops/plugins/hooks'], ['ops_skill_usage', '/api/ops/skills/usage'], ['tools_management', '/api/tools'],
    ['agents', '/api/agents'], ['skills', '/api/skills'], ['kg_recent', '/api/knowledge-graph/recent'], ['testcases_list', '/api/testcases'],
    ['healing_stats', '/api/healing/stats'], ['testing_healing_logs', '/api/testing/healing/logs'],
  ]) await add(name, path);
  if (session) for (const [name, path] of [
    ['delegate_tree', `/api/delegate/${session}`], ['cost_session', `/api/cost/session/${session}`], ['artifacts_session', `/api/artifacts/${session}`],
    ['sandbox_resources', `/api/sandbox/${session}/resources`], ['sandbox_ports', `/api/sandbox/${session}/ports`], ['sandbox_dependencies', `/api/sandbox/${session}/dependencies`],
    ['sandbox_artifacts', `/api/sandbox/${session}/artifacts`], ['sandbox_events', `/api/sandbox/${session}/events`], ['sandbox_workspace', `/api/sandbox/workspace/${session}`],
  ]) await add(name, path);
  checks.kanban_create_board = await request('kanban_create_board', 'POST', `${BASE}/api/kanban/boards`, { name: 'E2E validation board', description: 'API validation artifact board' });
  checks.testcase_create = await request('testcase_create', 'POST', `${BASE}/api/testcases`, { name: 'E2E API-created smoke testcase', description: 'created by validation harness', steps: ['open app', 'call health endpoint'], expected_result: 'health OK', tags: ['e2e-validation'], priority: 'medium', type: 'api' });
  checks.tests_heal_standalone = await request('tests_heal_standalone', 'POST', `${BASE}/api/tests/heal`, { test_name: 'E2E synthetic failing locator', error: 'Element not found: #login-button', test_code: "await page.click('#login-button')", dom_snapshot: "<button data-testid='login-button'>Login</button>", framework: 'playwright' }, 60000);
  save('post_checks.json', checks);

  const filesystem = { 'agent_workspace/results': newest('agent_workspace/results'), 'agent_workspace/knowledge-graphs': newest('agent_workspace/knowledge-graphs'), '.testai': newest('.testai') };
  save('filesystem_evidence.json', filesystem);
  const baseline = load('baseline_endpoints.json');
  const openapi = load('openapi.json');
  const all = { ...baseline, ...checks, openapi, pipeline_start: pipeline };
  const events = stream.events || [];
  const streamText = events.map(e => e.line || e).join('\n').toLowerCase();
  const defects = [];
  const defect = (id, severity, endpoint, repro, expected, actual, evidence, area, retest) => defects.push({ id, severity, endpoint_or_artifact: endpoint, repro, expected, actual, evidence, suspected_area: area, retest_checklist: retest });
  if (!ok(all, 'frontend_api_proxy_health')) defect('E2E-001', 'High', 'http://127.0.0.1:3001/api/health', 'GET frontend proxy health', 'Frontend /api/* proxies to backend', 'Proxy health failed', baseline.frontend_api_proxy_health, 'Next.js API rewrites / route prefix wiring', ['GET /api/health through frontend returns 200']);
  if (!session) defect('E2E-002', 'Critical', 'POST /api/pipeline/from-requirements', 'Start pipeline with sample GitHub repo', 'Returns session_id and stream endpoint', 'No session_id returned', pipeline, 'pipeline API/session creation', ['POST returns session_id']);
  if (session && events.length === 0) defect('E2E-003', 'Critical', `GET /api/delegate/${session}/stream`, 'Open SSE stream after pipeline start', 'Lifecycle events stream', 'No stream events captured', { stream_error: stream.stream_error }, 'delegate SSE / pipeline event emission', ['stream emits started/progress/completed events']);
  if (session && !/knowledge|graph|kg/.test(streamText)) defect('E2E-004', 'High', 'delegate stream + agent_workspace/knowledge-graphs', 'Run pipeline and inspect stream/files', 'Per-test and per-fix KG updates during run', 'No direct KG update evidence in stream', { stream_event_count: events.length }, 'pipeline KG integration', ['stream shows KG updates per test/fix', 'filesystem graph updated during run']);
  if (session && !/heal|autoheal|self-heal|self_heal/.test(streamText)) defect('E2E-005', 'High', 'pipeline stream', 'Run pipeline with autoheal mandatory', 'Pipeline-integrated autoheal evidence appears when failures occur', 'No pipeline-integrated autoheal evidence in stream', { standalone_heal_status: checks.tests_heal_standalone && checks.tests_heal_standalone.status }, 'pipeline autoheal integration', ['pipeline invokes autoheal as part of run, not only /api/tests/heal']);
  if (session && !/web_search|search|docs|documentation|install|pip install|npm install|package/.test(streamText)) defect('E2E-006', 'High', 'pipeline stream/artifacts', 'Run pipeline requiring web/search/docs/package evidence', 'Direct usage evidence captured', 'No direct web/search/docs/package installation evidence in stream', { stream_event_count: events.length }, 'tool usage observability / orchestrator instructions', ['artifacts show web/search/docs usage and package install logs']);
  for (const name of ['sandbox_list', 'sandbox_metrics', 'sandbox_exec_containers', 'kanban_list_boards', 'ops_tools', 'ops_plugins', 'kg_recent', 'testcases_list', 'cost_global', 'cost_models']) if (!ok(all, name)) defect(`E2E-${100 + defects.length}`, 'Medium', (all[name] && all[name].url) || name, `Call ${name}`, 'Endpoint returns 2xx', 'Endpoint failed', all[name], name, ['endpoint returns 2xx with valid JSON']);
  const matrix = {
    preflight_health_routes_provider: ok(all, 'backend_api_health') && openapi.ok && ok(all, 'providers') ? 'PASS' : 'FAIL',
    pipeline_start: session ? 'PASS' : 'FAIL',
    delegate_stream: events.length ? 'PASS' : 'FAIL',
    sandbox_apis: ['sandbox_list', 'sandbox_metrics', 'sandbox_exec_containers'].every(name => ok(all, name)) ? 'PASS' : 'FAIL',
    kanban_apis: ok(all, 'kanban_list_boards') && ok(all, 'kanban_create_board') ? 'PASS' : 'FAIL',
    delegation_ops_apis: ok(all, 'ops_tools') && ok(all, 'ops_plugins') && (!session || ok(all, 'delegate_tree')) ? 'PASS' : 'FAIL',
    knowledge_graph_api_fs: ok(all, 'kg_recent') && filesystem['agent_workspace/knowledge-graphs'].length > 0 ? 'PASS' : 'FAIL',
    testcase_persistence_fs: ok(all, 'testcase_create') && ok(all, 'testcases_list') ? 'PASS' : 'FAIL',
    standalone_autoheal: ok(all, 'tests_heal_standalone') ? 'PASS' : 'FAIL',
    pipeline_integrated_autoheal: session && /heal|autoheal|self-heal|self_heal/.test(streamText) ? 'PASS' : 'FAIL',
    cost_token_endpoints: ok(all, 'cost_global') && (!session || ok(all, 'cost_session')) ? 'PASS' : 'FAIL',
    ui_route_prefix_api_wiring: ok(all, 'frontend_home') && ok(all, 'frontend_api_proxy_health') ? 'PASS' : 'FAIL',
    web_search_docs_package_evidence: session && /web_search|search|docs|documentation|install|pip install|npm install|package/.test(streamText) ? 'PASS' : 'FAIL',
  };
  const summary = { artifact_dir: '.testai/verification/e2e-20260605T051000Z', session_id: session, pass_fail_matrix: matrix, endpoint_pass_count: Object.values(all).filter(v => v && v.ok).length, endpoint_fail_count: Object.values(all).filter(v => v && !v.ok).length, defect_count: defects.length, defect_ids: defects.map(d => d.id), possible_defect_sources: ['provider env not loaded into backend container', 'route prefix mismatch between frontend and backend', 'pipeline orchestrator starts but does not emit SSE lifecycle events', 'pipeline lacks integrated KG/testcase/autoheal steps', 'sandbox Docker APIs fail under mounted docker.sock', 'required web/search/docs/package tools are unavailable or unused', 'persistence writes DB only but not filesystem artifacts'], most_likely_sources: ['pipeline lacks integrated mandatory evidence steps', 'route/API wiring or endpoint implementation gaps'] };
  save('defect_log.json', defects);
  save('summary.json', summary);
  let md = `# E2E validation report\n\nArtifact dir: \`${summary.artifact_dir}\`\nSession ID: \`${session}\`\n\n## Pass/fail matrix\n`;
  for (const [key, value] of Object.entries(matrix)) md += `- ${key}: **${value}**\n`;
  md += '\n## Defects\n';
  for (const item of defects) md += `### ${item.id} — ${item.severity}\n- Endpoint/artifact: \`${item.endpoint_or_artifact}\`\n- Repro: ${item.repro}\n- Expected: ${item.expected}\n- Actual: ${item.actual}\n- Evidence: see \`defect_log.json\` and endpoint artifacts\n- Suspected area: ${item.suspected_area}\n- Retest: ${item.retest_checklist.join('; ')}\n\n`;
  save('defect_report.md', md);
  console.log(JSON.stringify(summary, null, 2));
})().catch(error => { console.error(error); process.exit(1); });
