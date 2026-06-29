from __future__ import annotations

import logging
from typing import Any

from .base import BaseAdapter, AdapterConfig

logger = logging.getLogger(__name__)


class SlackAdapter(BaseAdapter):
    name = "slack"

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__(config)
        self._client = None

    async def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from slack_sdk.web.async_client import AsyncWebClient
            self._client = AsyncWebClient(token=self.config.api_token)
        except ImportError:
            raise RuntimeError("slack-sdk not installed. Run: pip install slack-sdk")

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._ensure_client()
        blocks = None
        text = content
        if metadata and metadata.get("blocks"):
            blocks = metadata["blocks"]
            text = metadata.get("fallback", content)
        resp = await self._client.chat_postMessage(channel=chat_id, text=text, blocks=blocks)
        return {"ok": resp.get("ok", False), "ts": resp.get("ts", ""), "channel": chat_id}

    async def health(self) -> bool:
        if not self.config.api_token:
            return False
        try:
            await self._ensure_client()
            resp = await self._client.auth_test()
            return resp.get("ok", False)
        except Exception:
            return False

    def validate_config(self) -> list[str]:
        missing = []
        if not self.config.api_token:
            missing.append("SLACK_BOT_TOKEN (xoxb-...)")
        return missing
