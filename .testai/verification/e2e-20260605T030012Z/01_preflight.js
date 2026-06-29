const { BASE, FRONT, save, shell, request } = require('./e2e_common');

(async () => {
  save('docker_compose_ps.json', shell('docker compose ps'));
  save('docker_backend_env_redacted.json', shell('docker compose exec -T backend python -c "import os,json; keys=[\'DEFAULT_MODEL\',\'OPENAI_BASE_URL\',\'OPENAI_API_KEY\',\'OPENCODE_BASE_URL\',\'OPENCODE_MODEL\',\'OPENCODE_API_KEY\']; print(json.dumps({k:(\'<present-redacted>\' if \'KEY\' in k and os.getenv(k) else os.getenv(k,\'<missing>\')) for k in keys},indent=2))"'));
  const openapi = await request('openapi', 'GET', `${BASE}/openapi.json`, null, 30000);
  save('openapi.json', openapi);
  let routes = [];
  try { routes = Object.keys(JSON.parse(openapi.body_text).paths || {}).sort(); } catch {}
  save('route_inventory.json', { count: routes.length, routes });
  const baseline = {};
  for (const [name, url] of [
    ['backend_api_health', `${BASE}/api/health`],
    ['backend_root_health', `${BASE}/health`],
    ['frontend_home', `${FRONT}/`],
    ['frontend_api_proxy_health', `${FRONT}/api/health`],
    ['providers', `${BASE}/api/settings/providers`],
    ['modes', `${BASE}/api/modes`],
    ['cost_global', `${BASE}/api/cost/global`],
    ['cost_models', `${BASE}/api/cost/per-model`],
    ['cost_budget', `${BASE}/api/cost/budget`],
  ]) baseline[name] = await request(name, 'GET', url);
  save('baseline_endpoints.json', baseline);
  console.log(JSON.stringify({ preflight: 'done', route_count: routes.length, passed: Object.values(baseline).filter(v => v.ok).length, failed: Object.values(baseline).filter(v => !v.ok).length }, null, 2));
})().catch(error => { console.error(error); process.exit(1); });
