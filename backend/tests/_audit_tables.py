"""Strict: parse SQL strings via ast, extract table names."""
import ast, asyncio, asyncpg, re
from pathlib import Path

DB_URL = "postgresql://testai:testai@testai-db:5432/testai"
ROOT = Path("/app")


def extract_string_literals(node):
    """Walk an AST and yield all string-literal Const nodes (or their joined parts)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            yield sub.value
        elif isinstance(sub, ast.JoinedStr):  # f-string
            for v in sub.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    yield v.value


TABLE_RE = re.compile(
    r'\b(FROM|JOIN|INTO|UPDATE)\s+(?:public\.)?"?([a-z_][a-z0-9_]+)"?',
    re.IGNORECASE
)
ALTER_RE = re.compile(r'\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-z_][a-z0-9_]+)', re.IGNORECASE)


async def main():
    conn = await asyncpg.connect(DB_URL)
    existing = {r["tablename"] for r in await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )}

    print(f"DB has {len(existing)} tables\n")

    # Only scan prod code
    scan_dirs = [ROOT / "harness", ROOT / "api", ROOT / "scripts"]
    referenced: set[str] = set()
    locations: dict[str, set[str]] = {}

    for base in scan_dirs:
        if not base.exists(): continue
        for py in base.rglob("*.py"):
            try:
                source = py.read_text(encoding="utf-8", errors="ignore")
            except: continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            rel = str(py.relative_to(ROOT))
            for s in extract_string_literals(tree):
                # Match FROM/JOIN/INTO/UPDATE/ALTER TABLE
                for m in TABLE_RE.finditer(s):
                    name = m.group(2).lower()
                    # Skip Python keywords and builtins that snuck through
                    if name in {"select", "values", "set", "table"}: continue
                    referenced.add(name)
                    locations.setdefault(name, set()).add(rel)
                for m in ALTER_RE.finditer(s):
                    name = m.group(1).lower()
                    referenced.add(name)
                    locations.setdefault(name, set()).add(rel)

    missing = sorted(referenced - existing - {"information_schema", "pg_class", "pg_namespace"})
    print(f"Referenced in SQL strings but MISSING from DB: {len(missing)}\n")
    for t in missing:
        rels = sorted(locations.get(t, set()))
        print(f"  - {t}  ({len(rels)} files)")
        for r in rels[:5]:
            print(f"      {r}")
        if len(rels) > 5:
            print(f"      ... and {len(rels)-5} more")

    # Bonus: tables that exist but are EMPTY (likely legacy/unused)
    print("\n--- Existing tables with 0 rows (sample first 30) ---")
    rows = []
    for t in sorted(existing):
        if t.startswith("pg_") or t.startswith("sql_"): continue
        try:
            n = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
        except: continue
        if n == 0:
            rows.append(t)
    for t in rows[:30]:
        print(f"  {t}")
    print(f"  (total: {len(rows)} empty tables)")

    await conn.close()


asyncio.run(main())
