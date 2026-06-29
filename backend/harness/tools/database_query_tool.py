"""DatabaseQueryTool — run read-only SQL queries against configured databases.

Requires: A database configuration in integration_configs or env vars.
Only allows SELECT queries — no INSERT/UPDATE/DELETE/DDL.
"""

from __future__ import annotations

import json
import os

from .base import BaseTool, ToolResult, ToolSpec


class DatabaseQueryTool(BaseTool):
    name = "database_query"
    description = "Run read-only SQL queries against a configured database. Only SELECT queries are allowed. Supports PostgreSQL, MySQL, SQLite. Configure via integration settings."
    capabilities = ["can_query_databases"]

    async def run(self, query: str, database: str = "default", max_rows: int = 50) -> ToolResult:
        q = query.strip().upper()
        if not q.startswith("SELECT") and not q.startswith("WITH"):
            return ToolResult(success=False, output="Only SELECT queries are allowed. This tool is read-only.")

        # Try PostgreSQL first
        pg_dsn = os.environ.get(f"DATABASE_URL_{database.upper()}", os.environ.get("DATABASE_URL", ""))
        if pg_dsn:
            try:
                import asyncpg
                conn = await asyncpg.connect(pg_dsn, timeout=10)
                try:
                    rows = await conn.fetch(query, timeout=30)
                    if not rows:
                        return ToolResult(success=True, output="Query returned no results.")
                    # Format as text table
                    columns = list(rows[0].keys())
                    lines = [f"Results: {len(rows)} row(s), {len(columns)} column(s)\n"]
                    lines.append("  " + " | ".join(str(c)[:20] for c in columns))
                    lines.append("  " + "-" * min(80, len(columns) * 22))
                    for r in rows[:max_rows]:
                        vals = [str(r[c])[:30] if r[c] is not None else "NULL" for c in columns]
                        lines.append("  " + " | ".join(vals))
                    if len(rows) > max_rows:
                        lines.append(f"\n  ... and {len(rows) - max_rows} more rows")
                    return ToolResult(success=True, output="\n".join(lines))
                finally:
                    await conn.close()
            except ImportError:
                return ToolResult(success=False, output="asyncpg not installed. Install with: pip install asyncpg")
            except Exception as e:
                return ToolResult(success=False, output=f"Database error: {e}")

        # Try SQLite
        sqlite_path = os.environ.get(f"SQLITE_PATH_{database.upper()}", "")
        if sqlite_path:
            try:
                import sqlite3
                conn = sqlite3.connect(sqlite_path)
                conn.row_factory = sqlite3.Row
                cur = conn.execute(query)
                rows = cur.fetchmany(max_rows)
                if not rows:
                    return ToolResult(success=True, output="Query returned no results.")
                columns = rows[0].keys() if rows else []
                lines = [f"Results: {len(rows)} row(s), {len(columns)} column(s)\n"]
                lines.append("  " + " | ".join(str(c)[:20] for c in columns))
                for r in rows:
                    vals = [str(r[c])[:30] if r[c] is not None else "NULL" for c in columns]
                    lines.append("  " + " | ".join(vals))
                conn.close()
                return ToolResult(success=True, output="\n".join(lines))
            except Exception as e:
                return ToolResult(success=False, output=f"SQLite error: {e}")

        return ToolResult(success=False, output="No database configured. Set DATABASE_URL environment variable or configure in integration settings.")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL SELECT query (read-only)"},
                    "database": {"type": "string", "description": "Database connection name (default: 'default', uses DATABASE_URL env var)"},
                    "max_rows": {"type": "integer", "description": "Max rows to return (default 50)"},
                },
                "required": ["query"],
            },
        )


from harness.tools.registry import registry, any_env_available

registry.register(DatabaseQueryTool(), toolset="specialized", check_fn=any_env_available("DATABASE_URL", "DATABASE_URL_DEFAULT"))
