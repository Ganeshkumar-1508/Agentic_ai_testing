import json
with open('/tmp/evt2.json') as f:
    d = json.load(f)
t = {}
for e in d['events']:
    t[e['type']] = t.get(e['type'], 0) + 1
for k, c in sorted(t.items()):
    print(f'  {c:4d} x {k}')
