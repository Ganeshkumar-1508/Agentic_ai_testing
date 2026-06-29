from __future__ import annotations

from typing import Any

from harness.memory.database import Database


class PersistentStore:
    def __init__(self, db: Database):
        self.db = db

    async def store_interaction(self, user_input: str, response: str) -> None:
        await self.db.execute(
            "INSERT INTO interactions (user_input, response) VALUES ($1, $2)",
            user_input,
            response,
        )

    async def get_recent_context(self, limit: int = 5) -> str | None:
        rows = await self.db.fetch(
            "SELECT user_input, response FROM interactions ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        if not rows:
            return None
        return "\n\n".join(f"Q: {r['user_input']}\nA: {r['response']}" for r in rows)

    async def store_skill(self, name: str, content: str) -> None:
        await self.db.execute(
            "INSERT INTO skills (name, content) VALUES ($1, $2) "
            "ON CONFLICT (name) DO UPDATE SET content = $2",
            name,
            content,
        )

    async def get_skill(self, name: str) -> str | None:
        row = await self.db.fetchrow(
            "SELECT content FROM skills WHERE name = $1", name
        )
        return row["content"] if row else None

    async def store_value(self, key: str, value: str, category: str = "general") -> None:
        await self.db.execute(
            "INSERT INTO memory_entries (key, value, category) VALUES ($1, $2, $3) "
            "ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()",
            key, value, category,
        )

    async def get_value(self, key: str) -> str | None:
        row = await self.db.fetchrow(
            "SELECT value FROM memory_entries WHERE key = $1", key
        )
        return row["value"] if row else None

    async def delete_value(self, key: str) -> None:
        await self.db.execute(
            "DELETE FROM memory_entries WHERE key = $1", key,
        )

    async def list_by_category(self, category: str, limit: int = 50) -> list[dict]:
        rows = await self.db.fetch(
            "SELECT key, value, created_at, updated_at FROM memory_entries "
            "WHERE category = $1 ORDER BY updated_at DESC LIMIT $2",
            category, limit,
        )
        return [
            {
                "key": r["key"],
                "value": r["value"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]
