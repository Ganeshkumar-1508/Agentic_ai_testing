import httpx, json

# Check what the frontend dashboard API returns
r = httpx.get('http://localhost:8000/api/sessions', timeout=10)
sessions = r.json().get('sessions', [])
print('=== Frontend: /api/sessions ===')
for s in sessions[:5]:
    sid = s.get('id','')[:16]
    status = s.get('status','')
    goal = (s.get('goal','') or '')[:50]
    print(f'  {sid}... | {status} | {goal}')

# Check the specific session
sid = 'be2c9684-a68'
r2 = httpx.get(f'http://localhost:8000/api/sessions/{sid}', timeout=10)
s = r2.json()
print(f'\n=== Session {sid} ===')
print(f'  status: {s.get("status")}')
print(f'  goal: {s.get("goal","")[:80]}')
print(f'  repo_url: {s.get("repo_url")}')

# Check dashboard stats
r3 = httpx.get('http://localhost:8000/api/dashboard/stats', timeout=10)
print(f'\n=== Dashboard Stats ===')
print(f'  response: {r3.status_code}')
if r3.status_code == 200:
    d = r3.json()
    print(f'  keys: {list(d.keys())[:6]}')
