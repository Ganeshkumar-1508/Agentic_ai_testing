from __future__ import annotations

import asyncio
import logging
import os
import random
import asyncpg
from typing import Any

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/testai",
        )
        # Fix Windows/Docker networking: use 127.0.0.1 instead of localhost
        # to avoid IPv6 resolution issues
        if "localhost" in self.dsn:
            self.dsn = self.dsn.replace("localhost", "127.0.0.1")
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, 11):
            try:
                self._pool = await asyncpg.create_pool(
                    self.dsn,
                    min_size=2,
                    max_size=10,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300,  # 5 min recycle
                    server_settings={"tcp_keepalives_idle": "60"},
                )
                break
            except (asyncpg.CannotConnectNowError, OSError, asyncpg.InvalidPasswordError) as exc:
                last_exc = exc
                if attempt < 10:
                    wait = min(2 ** attempt, 60) + random.uniform(0, 1)
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
        for attempt in range(5):
            try:
                async with self._pool.acquire() as conn:
                    return await conn.execute(query, *args)
            except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, OSError, asyncpg.TooManyConnectionsError) as exc:
                if attempt < 4:
                    wait = min(2 ** attempt, 10) + random.uniform(0, 0.5)
                    logger.warning("DB execute retry %d/5: %s", attempt + 1, exc)
                    await asyncio.sleep(wait)
                    # Force pool recycling on connection errors
                    if isinstance(exc, (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError)):
                        try:
                            self._pool.expire_connections()
                        except Exception:
                            pass
                else:
                    raise

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        if not self._pool:
            raise RuntimeError("Database not connected")
        for attempt in range(5):
            try:
                async with self._pool.acquire() as conn:
                    return await conn.fetch(query, *args)
            except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, OSError, asyncpg.TooManyConnectionsError) as exc:
                if attempt < 4:
                    wait = min(2 ** attempt, 10) + random.uniform(0, 0.5)
                    logger.warning("DB fetch retry %d/5: %s", attempt + 1, exc)
                    await asyncio.sleep(wait)
                    if isinstance(exc, (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError)):
                        try:
                            self._pool.expire_connections()
                        except Exception:
                            pass
                else:
                    raise

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        if not self._pool:
            raise RuntimeError("Database not connected")
        for attempt in range(5):
            try:
                async with self._pool.acquire() as conn:
                    return await conn.fetchrow(query, *args)
            except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, OSError, asyncpg.TooManyConnectionsError) as exc:
                if attempt < 4:
                    wait = min(2 ** attempt, 10) + random.uniform(0, 0.5)
                    logger.warning("DB fetchrow retry %d/5: %s", attempt + 1, exc)
                    await asyncio.sleep(wait)
                    if isinstance(exc, (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError)):
                        try:
                            self._pool.expire_connections()
                        except Exception:
                            pass
                else:
                    raise

    async def fetchval(self, query: str, *args: Any) -> Any:
        if not self._pool:
            raise RuntimeError("Database not connected")
        for attempt in range(5):
            try:
                async with self._pool.acquire() as conn:
                    return await conn.fetchval(query, *args)
            except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, OSError, asyncpg.TooManyConnectionsError) as exc:
                if attempt < 4:
                    wait = min(2 ** attempt, 10) + random.uniform(0, 0.5)
                    logger.warning("DB fetchval retry %d/5: %s", attempt + 1, exc)
                    await asyncio.sleep(wait)
                    if isinstance(exc, (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError)):
                        try:
                            self._pool.expire_connections()
                        except Exception:
                            pass
                else:
                    raise

    async def executemany(self, query: str, args: list[tuple]) -> None:
        """Execute the same query with multiple parameter sets."""
        if not self._pool:
            raise RuntimeError("Database not connected")
        for attempt in range(5):
            try:
                async with self._pool.acquire() as conn:
                    await conn.executemany(query, args)
                return
            except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, OSError, asyncpg.TooManyConnectionsError) as exc:
                if attempt < 4:
                    wait = min(2 ** attempt, 10) + random.uniform(0, 0.5)
                    logger.warning("DB executemany retry %d/5: %s", attempt + 1, exc)
                    await asyncio.sleep(wait)
                    if isinstance(exc, (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError)):
                        try:
                            self._pool.expire_connections()
                        except Exception:
                            pass
                else:
                    raise
