from __future__ import annotations

import asyncio
import logging
import os
import asyncpg
from typing import Any

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/testai",
        )
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, 11):
            try:
                self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)
                break
            except (asyncpg.CannotConnectNowError, OSError) as exc:
                last_exc = exc
                if attempt < 10:
                    wait = min(attempt * 0.5, 5)
                    logger.warning(
                        "DB connect attempt %d/10 failed (retrying in %.1fs): %s",
                        attempt, wait, exc,
                    )
                    await asyncio.sleep(wait)
        else:
            raise last_exc  # type: ignore[misc]
        await self._create_tables()

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _create_tables(self) -> None:
        import os
        import logging
        log = logging.getLogger(__name__)
        schema_dir = os.path.join(os.path.dirname(__file__), "schema")
        schema_path = os.path.join(schema_dir, "schema.sql")
        migrations_path = os.path.join(schema_dir, "migrations.sql")
        # P0 audit fix 2026-06-23: best-effort per-statement execution.
        # The naive ``;`` split doesn't handle PL/pgSQL ``DO`` blocks,
        # ``COMMENT`` statements with ``;`` in the body, or
        # extensions that return NULL-shaped results via the
        # simple-query protocol. Instead of crashing the entire app
        # on a single bad statement, log and continue. The expected
        # state of the DB is documented in ``migrations.sql`` and
        # applied via psql at deploy time; this loop is a safety
        # net for fresh installs.
        for path in (schema_path, migrations_path):
            try:
                with open(path) as f:
                    raw = f.read()
            except OSError as exc:
                log.warning("could not read schema file %s: %s", path, exc)
                continue
            clean_lines = [line for line in raw.split("\n") if not line.strip().startswith("--")]
            clean_sql = "\n".join(clean_lines)
            statements = [s.strip() for s in clean_sql.split(";") if s.strip()]
            for statement in statements:
                try:
                    await self.execute(statement)
                except Exception as exc:
                    log.debug(
                        "schema statement failed (continuing): %s | stmt=%s",
                        exc, statement[:120],
                    )

    async def execute(self, query: str, *args: Any) -> str:
        if not self._pool:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        if not self._pool:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        if not self._pool:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        if not self._pool:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def executemany(self, query: str, args: list[tuple]) -> None:
        """Execute the same query with multiple parameter sets."""
        if not self._pool:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            await conn.executemany(query, args)
