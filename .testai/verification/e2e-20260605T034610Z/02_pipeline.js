const { BASE, save, request, jsonBody } = require('./e2e_common');

(async () => {
  const pipeline = await request('pipeline_start', 'POST', `${BASE}/api/pipeline/from-requirements`, {
    requirements: 'End-to-end validation run: inspect sample banking POC like a real user, generate tests, execute them, persist testcase and knowledge graph updates per test, use web/search/docs evidence, install packages if required, and perform pipeline-integrated autoheal on failures. Do not expose secrets.',
    repo_url: 'https://github.com/Ganeshkumar-1508/bank_poc_agentic_ai',
    repo_provider: 'github',
    language: 'python',
    framework: 'auto',
    test_types: ['api', 'frontend', 'integration'],
    custom_instructions: 'Mandatory: per-test and per-fix KG updates; pipeline-integrated autoheal; direct web/search/docs usage and package installation evidence.',
    timeout_seconds: 900,
    parallelism: 1,
    retry_on_failure: true,
    max_retries: 1,
    continue_on_failure: true,
    artifact_paths: ['.testai/**', 'test-results/**', 'coverage/**'],
  }, 45000);
  save('pipeline_start.json', pipeline);
  const session = jsonBody(pipeline).session_id || null;
  let events = [];
  let streamError = '';
  if (session) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 180000);
      const response = await fetch(`${BASE}/api/delegate/${session}/stream`, { headers: { 'user-agent': 'testai-e2e-validator' }, signal: controller.signal });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (events.length < 600) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop();
        for (const line of lines) if (line.trim()) events.push({ t: new Date().toISOString(), line });
        if (/completed|failed|cancelled|done/i.test(events.slice(-80).map(e => e.line).join('\n'))) break;
      }
      clearTimeout(timer);
    } catch (error) {
      streamError = String(error && error.stack || error);
    }
  }
  save('delegate_stream.json', { session_id: session, event_count: events.length, stream_error: streamError, events });
  console.log(JSON.stringify({ pipeline: pipeline.ok ? 'started' : 'failed', session_id: session, stream_events: events.length, stream_error: streamError }, null, 2));
})().catch(error => { console.error(error); process.exit(1); });
