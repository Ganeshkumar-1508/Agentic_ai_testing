from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from .base import BaseAdapter, AdapterConfig

logger = logging.getLogger(__name__)


class CustomNotifierAdapter(BaseAdapter):
    name = "custom_notifier"

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"
        if self.config.signing_secret:
            signature = hmac.new(self.config.signing_secret.encode(), content.encode(), hashlib.sha256).hexdigest()
            headers["X-Signature-256"] = signature
        payload: dict[str, Any] = {"text": content, "source": "testai"}
        if metadata:
            payload["metadata"] = metadata
        async with httpx.AsyncClient() as client:
            resp = await client.post(chat_id, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            return {"ok": True, "status": resp.status_code, "url": chat_id}

    async def health(self) -> bool:
        return bool(self.config.webhook_url)

    def validate_config(self) -> list[str]:
        missing = []
        if not self.config.webhook_url:
            missing.append("Notification URL")
        return missing
