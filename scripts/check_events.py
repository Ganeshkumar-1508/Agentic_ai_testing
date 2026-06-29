import json
with open('/tmp/evt.json') as f:
    d = json.load(f)
for e in d['events']:
    if e['type'] in ('subagent.completed','orchestration.completed','orchestration.started'):
        p = e['payload']
        if e['type'] == 'subagent.completed':
            status = p.get('status')
            dur = p.get('duration_sec', 0)
            output = str(p.get('output_preview', ''))[:100]
            print(f"Subagent: status={status} dur={dur:.2f}s output={output}")
        elif 'result' in p:
            r = p['result']
            if isinstance(r, dict):
                success = r.get('success')
                out = str(r.get('output', ''))[:200]
                print(f"Orch done: success={success} output={out}")
            elif isinstance(r, str):
                print(f"Orch done: {r[:200]}")
        else:
            print(f"{e['type']}: {str(p)[:100]}")
