import json, subprocess
r = subprocess.run(['curl', '-s', 'http://localhost:8000/api/sessions/b917fdbc-9ccb-4ca9-879b-ee62ca4f4042/events'], capture_output=True, text=True)
d = json.loads(r.stdout)
for e in d['events']:
    if 'orchestration' in e['type'] or 'subagent' in e['type']:
        print(json.dumps(e, indent=2))
        print('---')
