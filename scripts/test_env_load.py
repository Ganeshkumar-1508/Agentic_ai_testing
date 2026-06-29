from pathlib import Path
import os

p = Path("/app/.testai/.env")
lines = p.read_text().splitlines()
for l in lines:
    if "=" in l:
        key, val = l.split("=", 1)
        os.environ[key.strip()] = val.strip().strip('"')

print("OPENCODE_API_KEY:", os.environ.get("OPENCODE_API_KEY", "?")[:30])
