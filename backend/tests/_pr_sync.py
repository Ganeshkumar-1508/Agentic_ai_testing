import json, urllib.request
data = json.dumps({"repo_url": "https://github.com/rails/rails"}).encode()
req = urllib.request.Request(
    "http://localhost:8000/api/prs/sync", data=data,
    headers={"Content-Type": "application/json"}, method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print(r.read().decode()[:600])
except Exception as e:
    print(f"ERR: {e}")
    try:
        print(e.read().decode()[:600])
    except: pass
