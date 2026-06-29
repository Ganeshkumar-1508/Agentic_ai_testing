from __future__ import annotations

import logging
from typing import Any

from .base import BaseAdapter, AdapterConfig

logger = logging.getLogger(__name__)


class TeamsAdapter(BaseAdapter):
    name = "teams"

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__(config)
        self._app = None

    async def _ensure_app(self):
        if self._app is not None:
            return
        if not self.config.api_token:
            raise RuntimeError("Teams adapter: no API token configured")
        self._app = True

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._ensure_app()
        import httpx
        headers = {"Authorization": f"Bearer {self.config.api_token}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {"text": content}
        if metadata:
            card = metadata.get("adaptive_card")
            if card:
                payload["attachments"] = [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]
        async with httpx.AsyncClient() as client:
            url = f"https://smba.trafficmanager.net/amer/v3/conversations/{chat_id}/activities"
            resp = await client.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            return {"ok": True, "chat_id": chat_id}

    async def health(self) -> bool:
        return bool(self.config.api_token)

    def validate_config(self) -> list[str]:
        missing = []
        if not self.config.api_token:
            missing.append("TEAMS_BOT_TOKEN")
        if not self.config.webhook_url:
            missing.append("TEAMS_WEBHOOK_URL")
        return missing
