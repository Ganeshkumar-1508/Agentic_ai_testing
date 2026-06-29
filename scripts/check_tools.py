import json, subprocess, sys
r = subprocess.run(['curl', '-s', 'http://localhost:8000/api/sessions/b917fdbc-9ccb-4ca9-879b-ee62ca4f4042/events'], capture_output=True, text=True)
d = json.loads(r.stdout)
for e in d['events']:
    t = e['type']
    p = e['payload']
    if 'Tool' in t or 'orchestration' in t or 'subagent' in t or 'error' in str(p).lower():
        tool = p.get('tool_name', '')
        extra = p.get('status', p.get('output_preview', ''))[:80]
        print(f'  {t:35s} tool={tool or "-":30s} extra={extra}')
