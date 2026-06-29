import json
with open('/tmp/evt3.json') as f:
    d = json.load(f)
for e in d['events']:
    t = e['type']
    p = e['payload']
    if 'Tool' in t or 'orchestration' in t or 'subagent' in t or 'error' in str(p).lower():
        tool = p.get('tool_name', '')
        extra = p.get('status', p.get('output_preview', ''))[:80]
        print(f'  {t:35s} tool={tool or "-":30s} extra={extra}')
