"""Single ProviderProfile definition used by both metadata (Settings UI)
and runtime (LLMRouter). Replaces the old dual-profile pattern where
harness/providers/ and harness/llm.py each defined their own."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

OMIT_TEMPERATURE = object()


@dataclass
class ProviderProfile:
    """Single provider profile used by Settings UI (metadata) and LLMRouter (runtime).

    Metadata fields (display_name, signup_url, etc.) are for the UI.
    Runtime fields (api_key, model, options) are for LLMRouter dispatch.
    Hook methods (build_api_kwargs_extras, etc.) are for provider-specific quirks.
    """
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()
    display_name: str = ""
    description: str = ""
    signup_url: str = ""
    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""
    auth_type: str = "api_key"
    supports_health_check: bool = True
    fallback_models: tuple = ()
    hostname: str = ""
    default_headers: dict[str, str] = field(default_factory=dict)
    fixed_temperature: Any = None
    default_max_tokens: int | None = None
    default_aux_model: str = ""

    # Runtime fields (set by LLMRouter.configure, not by provider files)
    api_key: str = ""
    model: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    def get_hostname(self) -> str:
        if self.hostname:
            return self.hostname
        if self.base_url:
            from urllib.parse import urlparse
            return urlparse(self.base_url).hostname or ""
        return ""

    def prepare_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages

    def build_extra_body(
        self, *, session_id: str | None = None, **context: Any
    ) -> dict[str, Any]:
        return {}

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: dict | None = None,
        **context: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return {}, {}

    def get_max_tokens(self, model: str | None) -> int | None:
        """Return the default max_tokens cap for *model*.
        Override in subclasses for per-model caps.
        Default: return self.default_max_tokens, ignoring model name.
        """
        return self.default_max_tokens

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        url = (self.models_url or "").strip()
        if not url:
            if not self.base_url:
                return None
            url = self.base_url.rstrip("/") + "/models"
        import json
        import urllib.request
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "harness")
        for k, v in self.default_headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            items = data if isinstance(data, list) else data.get("data", [])
            return [m["id"] for m in items if isinstance(m, dict) and "id" in m]
        except Exception as exc:
            logger.debug("fetch_models(%s): %s", self.name, exc)
            return None
