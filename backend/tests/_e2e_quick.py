"""E2E with longer timeout + diagnostics."""
import json, time, urllib.request, urllib.error, sys, http.client

def post(path, body, timeout=180):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:8000{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body_text[:300]}")
        raise
    except Exception as e:
        print(f"REQ ERROR: {e!r}")
        raise

# 1. Health
with urllib.request.urlopen("http://localhost:8000/health", timeout=10) as r:
    print(f"health: {r.read().decode()}")

# 2. Submit job — print timing at each step
print("\nPOST /api/jobs (rails/rails) — long timeout ...")
t0 = time.monotonic()
spec = {
    "prompt": "List top-level dirs of this repo and briefly describe each",
    "repo_url": "https://github.com/rails/rails",
    "branch": "main",
    "tier": 1,
    "source": "api",
    "capabilities": [],
}
try:
    resp = post("/api/jobs", spec, timeout=180)
    elapsed = time.monotonic() - t0
    print(f"  ({elapsed:.1f}s) response: {json.dumps(resp, indent=2)[:400]}")
except Exception as e:
    elapsed = time.monotonic() - t0
    print(f"  FAILED after {elapsed:.1f}s: {e!r}")
    print("\nCheck the backend logs now.")
    sys.exit(1)

spec_id = resp.get("spec_id", "")
run_id = resp.get("run_id", "")
thread_id = resp.get("thread_id", "")
print(f"  spec_id={spec_id}")
print(f"  run_id={run_id}")
print(f"  thread_id={thread_id}")

# 3. SSE
if thread_id:
    print(f"\nSSE stream for {thread_id} ...")
    t1 = time.monotonic()
    events = []
    try:
        conn = http.client.HTTPConnection("localhost", 8000, timeout=130)
        conn.request("GET", f"/api/chat/threads/{thread_id}/stream")
        r = conn.getresponse()
        print(f"  HTTP {r.status}")
        if r.status == 200:
            buf = b""
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    chunk = r.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n\n" in buf:
                        raw, buf = buf.split(b"\n\n", 1)
                        text = raw.decode("utf-8", errors="replace")
                        event_type = ""
                        data_str = ""
                        for line in text.splitlines():
                            if line.startswith("event: "): event_type = line[7:].strip()
                            elif line.startswith("data: "): data_str = line[6:].strip()
                        if event_type:
                            payload = {}
                            if data_str:
                                try: payload = json.loads(data_str)
                                except: payload = {"raw": data_str}
                            events.append({"event": event_type, "data": payload})
                        if event_type in ("chat.run.completed", "chat.run.cancelled", "chat.error"):
                            break
                except Exception as e:
                    print(f"  read err: {e!r}")
                    break
        conn.close()
    except Exception as e:
        print(f"  SSE err: {e!r}")
    elapsed = time.monotonic() - t1
    print(f"  ({elapsed:.1f}s) {len(events)} events")
    types = {}
    for e in events:
        types[e["event"]] = types.get(e["event"], 0) + 1
    print(f"  types: {types}")
    print(f"  connected:  {'chat.connected' in types}")
    print(f"  completed:  {'chat.run.completed' in types}")
