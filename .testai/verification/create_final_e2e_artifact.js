const fs = require('fs');
const path = require('path');

const src = path.join('.testai', 'verification', 'e2e-20260605T034610Z');
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
const name = `e2e-${stamp}`;
const dst = path.join('.testai', 'verification', name);

fs.cpSync(src, dst, { recursive: true, force: true });

function rewrite(file) {
  const p = path.join(dst, file);
  let text = fs.readFileSync(p, 'utf8');
  text = text
    .replace(/e2e-20260605T030012Z/g, name)
    .replace(/e2e-20260605T034610Z/g, name)
    .replace(/docker compose exec -T/g, 'docker compose exec');
  fs.writeFileSync(p, text, 'utf8');
}

for (const file of ['e2e_common.js', '01_preflight.js', '02_pipeline.js', '03_endpoints_and_report.js']) {
  rewrite(file);
}

const strictScript = [
  "const { save, load } = require('./e2e_common');",
  "function has(text, token){ return text.includes(token.toLowerCase()); }",
  "(async()=>{",
  "  const stream=load('delegate_stream.json',{events:[],session_id:null});",
  "  const checks=load('post_checks.json',{});",
  "  const summary=load('summary.json',{});",
  "  const events=(stream.events||[]).map(e=>String(e.line||e)).join('\\n').toLowerCase();",
  "  const exact={ pipeline_autoheal_started: has(events,'pipeline.autoheal.started'), pipeline_autoheal_completed: has(events,'pipeline.autoheal.completed'), pipeline_kg_fix_updated: has(events,'pipeline.kg_fix_updated') };",
  "  const endpointStrict={ post_api_tests_heal: !!(checks.tests_heal_standalone&&checks.tests_heal_standalone.ok), get_api_healing_stats: !!(checks.healing_stats&&checks.healing_stats.ok), get_api_ops_swarm_delegate_events: !!(checks.ops_delegate_events&&checks.ops_delegate_events.ok), post_api_testcases: !!(checks.testcase_create&&checks.testcase_create.ok) };",
  "  const core=(summary.pass_fail_matrix)||{};",
  "  const requiredCore=['pipeline_start','delegate_stream','sandbox_apis','kanban_apis','delegation_ops_apis','knowledge_graph_api_fs','testcase_persistence_fs','standalone_autoheal','pipeline_integrated_autoheal','cost_token_endpoints','ui_route_prefix_api_wiring','web_search_docs_package_evidence'];",
  "  const coreStrict=Object.fromEntries(requiredCore.map(k=>[k,core[k]==='PASS']));",
  "  const allPass=[...Object.values(exact),...Object.values(endpointStrict),...Object.values(coreStrict)].every(Boolean);",
  "  const result={artifact_dir: summary.artifact_dir, session_id: stream.session_id||summary.session_id||null, exact_stream_events: exact, endpoint_strict: endpointStrict, core_strict: coreStrict, final_verdict: allPass?'PASS':'FAIL', remaining_defects: allPass?[]:[...(summary.defect_ids||[]), ...Object.entries(exact).filter(([,v])=>!v).map(([k])=>k), ...Object.entries(endpointStrict).filter(([,v])=>!v).map(([k])=>k), ...Object.entries(coreStrict).filter(([,v])=>!v).map(([k])=>k)]};",
  "  save('strict_final_verification.json', result);",
  "  let md='# Final strict E2E verification\\n\\n';",
  "  md+='Artifact dir: '+result.artifact_dir+'\\n';",
  "  md+='Session ID: '+result.session_id+'\\n';",
  "  md+='Final verdict: **'+result.final_verdict+'**\\n\\n';",
  "  for (const [section,obj] of [['Exact stream events',exact],['Mandatory endpoints',endpointStrict],['Core evidence',coreStrict]]) { md+='## '+section+'\\n'; for (const [k,v] of Object.entries(obj)) md+='- '+k+': **'+(v?'PASS':'FAIL')+'**\\n'; md+='\\n'; }",
  "  md+='## Remaining defects\\n'+(result.remaining_defects.length?result.remaining_defects.map(x=>'- '+x).join('\\n'):'None')+'\\n';",
  "  save('FINAL_VERIFICATION.md', md);",
  "  console.log(JSON.stringify(result,null,2));",
  "})().catch(e=>{console.error(e);process.exit(1);});",
  ""
].join('\n');
fs.writeFileSync(path.join(dst, '04_strict_final_verification.js'), strictScript, 'utf8');

console.log(dst.replace(/\\/g, '/'));
