from __future__ import annotations

import json
from typing import Any

from harness.memory.database import Database


class SettingsStore:
    def __init__(self, db: Database):
        self.db = db

    async def get_all_providers(self) -> list[dict[str, Any]]:
        rows = await self.db.fetch("SELECT provider, config FROM provider_configs")
        results = []
        for row in rows:
            config = json.loads(row["config"])
            config["provider"] = row["provider"]
            results.append(config)
        return results

    async def get_provider(self, provider: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT config FROM provider_configs WHERE provider = $1", provider
        )
        if not row:
            return None
        config = json.loads(row["config"])
        config["provider"] = provider
        return config

    async def upsert_provider(self, provider: str, config: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO provider_configs (provider, config, updated_at) VALUES ($1, $2, NOW()) "
            "ON CONFLICT (provider) DO UPDATE SET config = $2, updated_at = NOW()",
            provider,
            json.dumps(config),
        )

    async def delete_provider(self, provider: str) -> None:
        await self.db.execute(
            "DELETE FROM provider_configs WHERE provider = $1", provider
        )
