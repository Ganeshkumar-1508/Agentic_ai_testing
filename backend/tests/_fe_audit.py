"""Audit frontend: which pages exist and what API they call."""
import re
from pathlib import Path

SRC = Path(r"C:\Users\AswinPremnathChandra\Documents\testai-production\src\app\(dashboard)")

pages = {}
for p in SRC.iterdir():
    if p.is_dir() and not p.name.startswith("_"):
        tsx = p / "page.tsx"
        if tsx.exists():
            content = tsx.read_text(encoding="utf-8", errors="ignore")
            apis = re.findall(r'api\.(?:get|post)\s*\(\s*["`]([^"`]+)["`]', content)
            fetches = re.findall(r'fetch\(\s*["`](/api/[^"`]+)["`]', content)
            all_apis = list(set(apis + fetches))
            pages[p.name] = all_apis

print("=" * 70)
print("FRONTEND PAGE AUDIT")
print("=" * 70)
for route, apis in sorted(pages.items()):
    print(f"\n  /{route}")
    for a in apis[:6]:
        print(f"    -> {a}")
    if len(apis) > 6:
        print(f"    ... +{len(apis)-6} more")
