"""E2E check — verify pipeline was created and run."""
import asyncio
import httpx


async def main():
    base = "http://localhost:8001"

    # Check runs
    r = await httpx.AsyncClient().get(f"{base}/api/runs", timeout=10)
    runs = r.json().get("runs", [])
    print(f"Runs found: {len(runs)}")
    for run in runs:
        rid = str(run.get("id", "?"))[:12]
        status = run.get("status", "?")
        repo = str(run.get("repoUrl", "") or "")[:40]
        print(f"  Run {rid}: status={status} repo={repo}")

    # Check sessions
    r = await httpx.AsyncClient().get(f"{base}/api/sessions", timeout=10)
    sessions = r.json().get("sessions", [])
    print(f"\nSessions found: {len(sessions)}")

    # Check job specs
    try:
        r = await httpx.AsyncClient().get(f"{base}/api/jobs-specs", timeout=10)
        print(f"\nJob specs: {r.status_code}")
        if r.status_code == 200:
            print(r.text[:500])
    except Exception:
        pass
    print("\nDone")


asyncio.run(main())
