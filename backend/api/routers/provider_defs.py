"""Provider Definitions API — DB-driven provider metadata.

Lets users add/edit providers from the Settings UI without writing Python code.
Built-in providers are seeded from harness/providers/*.py on first run.
Custom providers are stored as rows in the provider_definitions table.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings/provider-defs", tags=["provider-defs"])


class ProviderDefRequest(BaseModel):
    name: str
    api_mode: str = "chat_completions"
    display_name: str = ""
    description: str = ""
    signup_url: str = ""
    env_vars: str = ""
    base_url: str = ""
    auth_type: str = "api_key"
    fallback_models: str = ""
    default_headers: str = "{}"


@router.get("")
async def list_provider_defs(request: Request):
    """List all provider definitions (built-in + custom)."""
    db = get_db(request)
    rows = await db.fetch("SELECT * FROM provider_definitions ORDER BY is_builtin DESC, name ASC")
    defs = [dict(r) for r in rows]

    # Seed from Python files if table is empty
    if not defs:
        defs = await _seed_provider_defs(db)
    return {"definitions": defs}


@router.post("")
async def create_provider_def(request: Request, body: ProviderDefRequest):
    """Create a new custom provider definition."""
    db = get_db(request)
    try:
        # Validate JSON in default_headers
        if body.default_headers:
            json.loads(body.default_headers)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "default_headers must be valid JSON"})

    await db.execute(
        "INSERT INTO provider_definitions (name, api_mode, display_name, description, signup_url, "
        "env_vars, base_url, auth_type, fallback_models, default_headers, is_builtin) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, false)",
        body.name, body.api_mode, body.display_name, body.description, body.signup_url,
        body.env_vars, body.base_url, body.auth_type, body.fallback_models,
        body.default_headers,
    )
    return {"status": "ok"}


@router.put("/{name}")
async def update_provider_def(request: Request, name: str, body: ProviderDefRequest):
    """Update an existing provider definition."""
    db = get_db(request)
    await db.execute(
        "UPDATE provider_definitions SET api_mode=$1, display_name=$2, description=$3, "
        "signup_url=$4, env_vars=$5, base_url=$6, auth_type=$7, fallback_models=$8, "
        "default_headers=$9 WHERE name=$10",
        body.api_mode, body.display_name, body.description, body.signup_url,
        body.env_vars, body.base_url, body.auth_type, body.fallback_models,
        body.default_headers, name,
    )
    return {"status": "ok"}


@router.delete("/{name}")
async def delete_provider_def(request: Request, name: str):
    """Delete a custom provider definition. Built-in providers cannot be deleted."""
    db = get_db(request)
    row = await db.fetchrow("SELECT is_builtin FROM provider_definitions WHERE name=$1", name)
    if not row:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    if row["is_builtin"]:
        return JSONResponse(status_code=403, content={"error": "Cannot delete built-in providers"})
    await db.execute("DELETE FROM provider_definitions WHERE name=$1", name)
    return {"status": "deleted"}


async def _seed_provider_defs(db) -> list[dict[str, Any]]:
    """Seed the provider_definitions table from the provider registry.

    Sources (in priority order, later overrides earlier):
      1. DEFAULT_PROVIDERS config dict (built-in shallow providers)
      2. Filesystem provider modules (complex providers with custom logic)
    """
    from harness.providers import list_providers

    seeded = []
    for profile in list_providers():
        try:
            await db.execute(
                "INSERT INTO provider_definitions (name, api_mode, display_name, description, "
                "signup_url, env_vars, base_url, auth_type, fallback_models, default_headers, is_builtin) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true) "
                "ON CONFLICT (name) DO NOTHING",
                profile.name,
                profile.api_mode,
                profile.display_name or profile.name,
                profile.description or "",
                profile.signup_url or "",
                ",".join(profile.env_vars) if profile.env_vars else "",
                profile.base_url or "",
                profile.auth_type,
                ",".join(profile.fallback_models) if profile.fallback_models else "",
                json.dumps(profile.default_headers),
            )
            seeded.append(profile.name)
        except Exception as e:
            logger.warning("Failed to seed provider %s: %s", profile.name, e)

    logger.info("Seeded %d provider definitions from registry", len(seeded))
    rows = await db.fetch("SELECT * FROM provider_definitions ORDER BY name ASC")
    return [dict(r) for r in rows]
