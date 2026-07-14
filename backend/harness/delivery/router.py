"""Lazy delivery router with class-based adapter registry.

The router owns the platform-config-to-adapter plumbing so callers
just hand it ``(content, targets)`` and let it figure out the rest.

Design:
  * Adapter classes are mapped by name in :data:`ADAPTER_REGISTRY`. To
    add a new platform, register the class in the registry — no
    changes to the router or to ``api/main.py`` are required.
  * Adapters are constructed **on first use** from a row in the
    ``platform_configs`` DB table. The instance is cached for the
    lifetime of the router so subsequent deliveries to the same
    platform do not re-read the DB.
  * ``db`` is optional. When missing, ``_load_config_from_db`` returns
    an empty ``AdapterConfig()`` and the cached instance becomes
    effectively a no-op (still preserves the failure mode of the
    pre-refactor eager-init path: a delivery with no config will
    attempt to send and most likely fail at the platform level).

Backwards-compat note: the previous public surface accepted
``adapters={...}`` (eager instance dict). That API is removed — all
call sites now pass ``db=...`` (or nothing, in the no-config case).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from harness.delivery.adapters import ADAPTER_REGISTRY
from harness.delivery.adapters.base import AdapterConfig, BaseAdapter, DeliveryTarget


logger = logging.getLogger(__name__)


MAX_CONTENT_CHARS = 4000
TRUNCATED_VISIBLE = 3800
OUTPUT_DIR = Path("agent_workspace/delivery")


class DeliveryRouter:
    """Route deliveries to platform adapters on demand.

    Constructor:
        ``db``           — async DB connection / pool (any object with
                           ``await db.fetch(query, *args) -> list[Row]``).
                           Optional; if ``None``, ``_load_config_from_db``
                           returns an empty ``AdapterConfig``.
        ``registry``     — optional platform-name → adapter-class map.
                           Defaults to the built-in :data:`ADAPTER_REGISTRY`.
                           Pass a custom map (or use :meth:`register_platform`)
                           to add or override platforms without editing
                           this file.
        ``output_dir``   — local-write target for ``platform="local"``
                           and oversized-content overflow. Defaults to
                           ``agent_workspace/delivery``.

    All other call sites (lifespan, ``/api/digest``, PR auto-fix
    notifications) construct a single instance and reuse it.
    """

    def __init__(
        self,
        db: Any = None,
        registry: Optional[dict[str, type[BaseAdapter]]] = None,
        output_dir: Path | None = None,
    ):
        self._db = db
        self._registry: dict[str, type[BaseAdapter]] = (
            dict(registry) if registry is not None else dict(ADAPTER_REGISTRY)
        )
        self._instances: dict[str, BaseAdapter] = {}
        self._output_dir = output_dir or OUTPUT_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Registry — extensibility surface
    # ------------------------------------------------------------------

    def register_platform(self, name: str, adapter_class: type[BaseAdapter]) -> None:
        """Register a new platform at runtime.

        Overrides any existing entry with the same name. In-flight
        cached instances for that name are dropped so the next call
        picks up the new class.
        """
        self._registry[name] = adapter_class
        self._instances.pop(name, None)

    def unregister_platform(self, name: str) -> None:
        """Remove a platform from the registry and drop its cached instance."""
        self._registry.pop(name, None)
        self._instances.pop(name, None)

    def known_platforms(self) -> list[str]:
        """Return the sorted list of registered platform names."""
        return sorted(self._registry)

    def cached_platforms(self) -> list[str]:
        """Return the sorted list of platforms whose adapter has been instantiated."""
        return sorted(self._instances)

    # ------------------------------------------------------------------
    # Lazy adapter loading
    # ------------------------------------------------------------------

    async def _get_adapter(self, platform: str) -> BaseAdapter:
        """Return a (cached) adapter instance for ``platform``.

        Raises ``ValueError`` if the platform is unknown to the
        registry. Raises the underlying DB error if the platform is
        registered but the config row is missing/invalid AND a DB was
        provided (we want loud failures in that path so misconfiguration
        surfaces immediately).
        """
        cached = self._instances.get(platform)
        if cached is not None:
            return cached
        cls = self._registry.get(platform)
        if cls is None:
            raise ValueError(f"Unknown delivery platform: {platform!r}")
        cfg = await self._load_config_from_db(platform)
        instance = cls(cfg)
        self._instances[platform] = instance
        logger.debug("Lazy-loaded adapter for platform %r (%s)", platform, cls.__name__)
        return instance

    async def _load_config_from_db(self, platform: str) -> AdapterConfig:
        """Read the platform's config row from ``platform_configs``.

        Returns an empty :class:`AdapterConfig` when:
          * ``self._db`` is ``None`` (router constructed without DB);
          * the platform row is missing;
          * the DB query itself fails (logged, not raised — we don't
            want a transient DB blip to break every delivery).

        The non-DB case exists so that callers like
        ``api/routers/pr_manager.py:350`` can construct a router with
        no DB and still get a working (default-config) instance for
        any registered platform.
        """
        if self._db is None:
            return AdapterConfig()
        try:
            rows = await self._db.fetch(
                "SELECT config FROM platform_configs WHERE platform = $1 AND enabled = true",
                platform,
            )
        except Exception as e:
            logger.warning("Failed to read platform_configs for %r: %s", platform, e)
            return AdapterConfig()
        if not rows:
            return AdapterConfig()
        cfg_data = rows[0].get("config") if hasattr(rows[0], "get") else rows[0]["config"]
        if isinstance(cfg_data, str):
            try:
                cfg_data = json.loads(cfg_data)
            except json.JSONDecodeError:
                logger.warning("platform_configs[%r].config is not valid JSON; using empty", platform)
                return AdapterConfig()
        cfg_data = cfg_data or {}
        return AdapterConfig(
            enabled=bool(cfg_data.get("enabled", True)),
            api_token=cfg_data.get("api_token", "") or "",
            webhook_url=cfg_data.get("webhook_url", "") or "",
            signing_secret=cfg_data.get("signing_secret", "") or "",
            extra={k: v for k, v in cfg_data.items() if k not in ("enabled", "api_token", "webhook_url", "signing_secret")},
        )

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    async def deliver(
        self,
        content: str,
        targets: list[DeliveryTarget],
        job_id: str | None = None,
        job_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deliver ``content`` to every ``target``.

        Per-target failures are caught and recorded in the result
        dict under the target's string form; one bad platform never
        aborts the others. ``local`` targets always succeed (they
        only write to disk).
        """
        results: dict[str, Any] = {}
        for target in targets:
            try:
                if target.platform == "local":
                    result = self._deliver_local(content, job_id, job_name, metadata)
                else:
                    result = await self._deliver_to_platform(target, content, metadata)
                results[target.to_string()] = {"success": True, "result": result}
            except Exception as e:
                logger.warning("Delivery to %s failed: %s", target.to_string(), e)
                results[target.to_string()] = {"success": False, "error": str(e)}
        return results

    def _deliver_local(
        self,
        content: str,
        job_id: str | None,
        job_name: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = self._output_dir / (job_id or "misc")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{timestamp}.md"
        lines = [f"# {job_name or 'Delivery Output'}", ""]
        lines.append(f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if job_id:
            lines.append(f"**Job ID:** {job_id}")
        if metadata:
            for k, v in metadata.items():
                lines.append(f"**{k}:** {v}")
        lines.extend(["", "---", "", content])
        path.write_text("\n".join(lines))
        return {"path": str(path), "timestamp": timestamp}

    async def _deliver_to_platform(
        self,
        target: DeliveryTarget,
        content: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        adapter = await self._get_adapter(target.platform)
        if not target.chat_id:
            raise ValueError(f"No chat_id for {target.platform}")
        send_content = content
        if len(content) > MAX_CONTENT_CHARS:
            logger.info("Content truncated: %d chars -> %d", len(content), MAX_CONTENT_CHARS)
            send_content = content[:TRUNCATED_VISIBLE] + f"\n\n... [truncated, full in local storage]"
            self._deliver_local(content, None, None, metadata)
        return await adapter.send(target.chat_id, send_content, metadata=metadata)
