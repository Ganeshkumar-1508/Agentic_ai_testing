from __future__ import annotations

import json
import os
from typing import Any


def build_patch_query(
    table: str,
    id_column: str,
    id_value: str,
    req: dict[str, Any],
    fields: dict[str, str],
    json_fields: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Build a parameterized UPDATE query from a partial request dict.

    Args:
        table: SQL table name.
        id_column: Primary key column.
        id_value: Primary key value.
        req: The incoming PATCH body (dict).
        fields: Maps JSON key to DB column name.
        json_fields: Subset of fields that should be JSON-serialized.

    Returns:
        (sql, params) or ("", []) if no fields to update.
    """
    sets: list[str] = []
    vals: list[Any] = []
    i = 1
    jf = set(json_fields or [])
    for json_key, db_col in fields.items():
        if json_key not in req:
            continue
        val = req[json_key]
        if json_key in jf:
            val = json.dumps(val) if isinstance(val, (dict, list)) else val
        sets.append(f"{db_col} = ${i}")
        vals.append(val)
        i += 1
    if not sets:
        return "", []
    sets.append("updated_at = NOW()")
    vals.append(id_value)
    sql = f"UPDATE {table} SET {', '.join(sets)} WHERE {id_column} = ${i}"
    return sql, vals


_db_instance = None


async def get_db_direct():
    """Get a database connection without a FastAPI request object.
    Used by background tasks and webhook handlers.

    First checks the global db_context (set at startup). If not available,
    creates its own connection as a fallback.
    """
    global _db_instance
    # Prefer the global instance set at startup
    from harness.memory.db_context import get_db
    db = get_db()
    if db is not None:
        return db
    # Fallback: create own connection (background tasks started before lifespan)
    if _db_instance is None:
        from harness.memory.database import Database
        dsn = os.environ.get("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/testai")
        _db_instance = Database(dsn)
        await _db_instance.connect()
    return _db_instance
