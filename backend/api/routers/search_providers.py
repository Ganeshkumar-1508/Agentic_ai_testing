"""Search provider configuration API.

Lets users enable/configure search providers from the Settings UI.
Each provider's API keys and config are stored in the search_providers DB table.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request

from harness.search.providers import list_all as list_search_providers
from ..deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search-providers"])


_DDL = """
CREATE TABLE IF NOT EXISTS search_providers (
    provider TEXT PRIMARY KEY,
    config TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


async def _ensure_table(db):
    try:
        await db.execute(_DDL)
    except Exception:
        pass


@router.get("/providers")
async def get_search_providers(request: Request):
    """List all available search providers with their configurations."""
    db = get_db(request)
    await _ensure_table(db)
    providers = list_search_providers()

    # Load stored configs from DB
    stored = {}
    try:
        rows = await db.fetch("SELECT provider, config FROM search_providers")
        for row in rows:
            stored[row["provider"]] = json.loads(row["config"]) if isinstance(row["config"], str) else (row["config"] or {})
    except Exception:
        pass

    result = []
    for p in providers:
        cfg = stored.get(p["name"], {})
        result.append({
            **p,
            "enabled": cfg.get("enabled", False),
            "config": {k: cfg.get(k) for k in [f["key"] for f in p["config_fields"]] if k in cfg},
        })

    return {"providers": result}


@router.post("/providers")
async def save_search_providers(request: Request, body: list[dict[str, Any]]):
    """Save search provider configurations."""
    db = get_db(request)
    for item in body:
        provider = item.get("provider", "")
        enabled = item.get("enabled", False)
        config = item.get("config", {})

        # Store API key in config
        payload = {"enabled": enabled}
        for k, v in config.items():
            if v is not None:
                payload[k] = v

        try:
            await db.execute(
                "INSERT INTO search_providers (provider, config) VALUES ($1, $2) "
                "ON CONFLICT (provider) DO UPDATE SET config = $2",
                provider, json.dumps(payload),
            )
        except Exception as e:
            logger.warning("Failed to save search provider %s: %s", provider, e)

    return {"status": "ok"}
