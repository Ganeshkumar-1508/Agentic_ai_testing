"""Model pricing cache — MCP-first, DB-backed, refreshed every 7 days (168 hours).

Resolution order:
  1. MCP get_model(slug) — live pricing for the specific model
  2. DB cache — last known pricing, refreshed every 7 days (168 hours) from get_all_models
  3. Built-in fallback — when both MCP and DB are unavailable
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

PRICE_MCP_URL = "https://api.pricepertoken.com/mcp/mcp"
_MCP_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
_CACHE_TTL_HOURS = 168  # 7 days
_DEFAULT_RATES = {"input": 0.002, "output": 0.008, "cache_read": 0.001}
# No hardcoded model overrides — prices come from PricePerToken MCP.


class PricingCache:
    """Model pricing cache backed by Postgres + MCP refresh."""

    def __init__(self, db: Any | None = None):
        self.db = db
        self._last_refresh: float = 0
        self._in_memory: dict[str, dict[str, float]] = {}
        self._refresh_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_rate(self, model: str) -> dict[str, float] | None:
        """Get pricing for a model. Returns None if no pricing found."""
        # 1. Try MCP get_model(slug) — live, most accurate
        mcp_rate = await self._mcp_lookup(model)
        if mcp_rate:
            return mcp_rate

        # 2. Check in-memory cache (loaded from DB on first use)
        if not self._in_memory:
            await self._load_from_db()

        model_key = model.lower().strip()
        if model_key in self._in_memory:
            return self._in_memory[model_key]

        # Fuzzy match against cached slugs
        for slug, rates in self._in_memory.items():
            if model_key.replace("-", " ") in slug.replace("-", " ") or slug.replace("-", " ") in model_key.replace("-", " "):
                return rates

        # 3. No pricing found
        logger.warning("No pricing found for model '%s' — cost will not be tracked", model)
        return None

    async def refresh_if_stale(self) -> bool:
        """Refresh the model cache from MCP if older than 7 days (168 hours). Returns True if refreshed."""
        async with self._refresh_lock:
            if time.time() - self._last_refresh < _CACHE_TTL_HOURS * 3600:
                return False
            return await self._refresh_from_mcp()

    # ------------------------------------------------------------------
    # MCP lookups
    # ------------------------------------------------------------------

    async def _mcp_lookup(self, model: str) -> dict[str, float] | None:
        """Try get_model MCP tool for a specific model slug.

        PricePerToken uses slugs like 'provider-model' (e.g. 'deepseek-deepseek-v4-flash').
        We try: (1) direct slug, (2) provider-prefixed slug if model contains a dash.
        """
        import httpx
        slug = model.lower().strip().replace("/", "-").replace(" ", "-")
        # Build candidate slugs: direct + provider-prefixed
        candidates = [slug]
        parts = slug.split("-", 1)
        if len(parts) == 2 and parts[0] not in parts[1]:
            candidates.append(f"{parts[0]}-{slug}")
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                async with httpx.AsyncClient(timeout=10.0) as c:
                    r = await c.post(PRICE_MCP_URL, headers=_MCP_HEADERS,
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "get_model", "arguments": {"slug": candidate}}})
                    content = r.json().get("result", {}).get("content", [])
                    for entry in content:
                        if isinstance(entry, dict) and entry.get("type") == "text":
                            data = json.loads(entry["text"]) if isinstance(entry["text"], str) else entry["text"]
                            # Pricing may be nested under "pricing" key or at top level
                            pricing = data.get("pricing", data)
                            inp = pricing.get("input_per_1m")
                            out = pricing.get("output_per_1m")
                            if inp is not None and out is not None and float(inp) > 0:
                                logger.info("MCP pricing found for '%s' via slug '%s'", model, candidate)
                                return {
                                    "input": float(inp) / 1000,
                                    "output": float(out) / 1000,
                                    "cache_read": float(inp) / 1000 * 0.5,
                                }
            except Exception as e:
                logger.debug("MCP lookup failed for '%s': %s", candidate, e)
        return None

    async def _fetch_models_for_provider(self, client, author: str) -> list[dict]:
        """Fetch models for a single provider/author from MCP."""
        try:
            r = await client.post(PRICE_MCP_URL, headers=_MCP_HEADERS,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "get_all_models", "arguments": {"author": author}}})
            content = r.json().get("result", {}).get("content", [])
            raw = ""
            for e in content:
                if isinstance(e, dict) and e.get("type") == "text":
                    raw = e.get("text", "")
                    break
            if not raw:
                return []
            models = json.loads(raw) if isinstance(raw, str) else raw
            return models if isinstance(models, list) else []
        except Exception:
            return []

    async def _get_all_providers(self, client) -> list[str]:
        """Get list of all provider slugs from MCP."""
        try:
            r = await client.post(PRICE_MCP_URL, headers=_MCP_HEADERS,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "get_providers", "arguments": {}}})
            content = r.json().get("result", {}).get("content", [])
            raw = ""
            for e in content:
                if isinstance(e, dict) and e.get("type") == "text":
                    raw = e.get("text", "")
                    break
            if not raw:
                return []
            providers = json.loads(raw) if isinstance(raw, str) else raw
            slugs = []
            for p in providers:
                if isinstance(p, dict):
                    slug = p.get("author") or p.get("slug") or p.get("id") or ""
                    if slug:
                        slugs.append(str(slug).strip().lower())
            return slugs
        except Exception:
            return []

    async def _refresh_from_mcp(self) -> bool:
        """Fetch ALL models from MCP by iterating providers, persist to DB."""
        import httpx
        import asyncio as _asyncio
        try:
            async with httpx.AsyncClient(timeout=30.0) as c:
                # Get all provider slugs
                providers = await self._get_all_providers(c)
                if not providers:
                    return False

                all_entries: list[dict[str, Any]] = []
                seen_slugs: set[str] = set()

                for author in providers:
                    models = await self._fetch_models_for_provider(c, author)
                    for m in models:
                        if not isinstance(m, dict):
                            continue
                        slug = m.get("slug", "").strip().lower()
                        if not slug or slug in seen_slugs:
                            continue
                        inp = m.get("input_per_1m")
                        out = m.get("output_per_1m")
                        if inp is None or out is None:
                            continue
                        seen_slugs.add(slug)
                        all_entries.append({
                            "slug": slug,
                            "input_per_1m": round(float(inp), 6),
                            "output_per_1m": round(float(out), 6),
                            "cached_input_per_1m": round(float(m.get("cached_input_per_1m", 0) or inp) * 0.5, 6),
                            "context_length": m.get("context_length"),
                            "supports_vision": bool(m.get("supports_vision")),
                            "supports_reasoning": bool(m.get("supports_reasoning")),
                            "supports_tool_calls": bool(m.get("supports_tool_calls")),
                        })
                    # Small delay between providers to be polite
                    await _asyncio.sleep(0.05)

                if not all_entries:
                    logger.warning("MCP refresh returned 0 models")
                    return False

                # Persist to DB
                if self.db:
                    try:
                        await self.db.execute("DELETE FROM model_pricing_cache")
                        for e in all_entries:
                            await self.db.execute(
                                """INSERT INTO model_pricing_cache
                                   (slug, input_per_1m, output_per_1m, cached_input_per_1m,
                                    context_length, supports_vision, supports_reasoning, supports_tool_calls)
                                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                                e["slug"], e["input_per_1m"], e["output_per_1m"], e["cached_input_per_1m"],
                                e["context_length"], e["supports_vision"], e["supports_reasoning"], e["supports_tool_calls"],
                            )
                    except Exception as db_err:
                        logger.warning("Failed to persist pricing cache: %s", db_err)

                # Update in-memory cache
                self._in_memory = {e["slug"]: {
                    "input": e["input_per_1m"] / 1000,
                    "output": e["output_per_1m"] / 1000,
                    "cache_read": e["cached_input_per_1m"] / 1000,
                    "context_length": e["context_length"],
                    "supports_vision": e["supports_vision"],
                    "supports_reasoning": e["supports_reasoning"],
                    "supports_tool_calls": e["supports_tool_calls"],
                } for e in all_entries}
                self._last_refresh = time.time()
                logger.info("Refreshed pricing cache: %d models across %d providers", len(all_entries), len(providers))
                return True

        except Exception as e:
            logger.warning("MCP refresh failed: %s", e)
            return False

    async def _load_from_db(self) -> None:
        """Load cached pricing from DB into memory."""
        if not self.db:
            return
        try:
            rows = await self.db.fetch(
                "SELECT slug, input_per_1m, output_per_1m, cached_input_per_1m, "
                "context_length, supports_vision, supports_reasoning, supports_tool_calls, updated_at "
                "FROM model_pricing_cache ORDER BY slug"
            )
            self._in_memory = {}
            for row in rows:
                slug = row["slug"]
                inp = float(row.get("input_per_1m", 0))
                out = float(row.get("output_per_1m", 0))
                cached = float(row.get("cached_input_per_1m", inp * 0.5))
                if inp > 0:
                    self._in_memory[slug] = {
                        "input": inp / 1000,
                        "output": out / 1000,
                        "cache_read": cached / 1000,
                        "context_length": row.get("context_length"),
                        "supports_vision": bool(row.get("supports_vision")),
                        "supports_reasoning": bool(row.get("supports_reasoning")),
                        "supports_tool_calls": bool(row.get("supports_tool_calls")),
                    }

            # Check if cache is stale (>7 days / 168 hours) and trigger background refresh
            if rows:
                latest = max(r["updated_at"] for r in rows)
                age_hours = (time.time() - latest.timestamp()) / 3600
                if age_hours >= _CACHE_TTL_HOURS:
                    asyncio.ensure_future(self.refresh_if_stale())

            logger.info("Loaded %d models from DB pricing cache", len(self._in_memory))
        except Exception as e:
            logger.warning("Failed to load pricing cache from DB: %s", e)
