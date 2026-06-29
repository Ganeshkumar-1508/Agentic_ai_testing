from __future__ import annotations

import logging
from typing import Any

from .base import BaseAdapter, AdapterConfig

logger = logging.getLogger(__name__)


class TelegramAdapter(BaseAdapter):
    name = "telegram"

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__(config)
        self._bot = None

    async def _ensure_bot(self):
        if self._bot is not None:
            return
        token = self.config.api_token
        if not token:
            raise RuntimeError("Telegram adapter: no bot token configured")
        try:
            from aiogram import Bot
            self._bot = Bot(token=token)
        except ImportError:
            raise RuntimeError("aiogram not installed. Run: pip install aiogram")

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._ensure_bot()
        parse_mode = None
        if metadata:
            parse_mode = metadata.get("parse_mode")
        msg = await self._bot.send_message(chat_id=chat_id, text=content, parse_mode=parse_mode)
        return {"ok": True, "message_id": msg.message_id, "chat_id": str(chat_id)}

    async def health(self) -> bool:
        if not self.config.api_token:
            return False
        try:
            await self._ensure_bot()
            me = await self._bot.get_me()
            return me is not None
        except Exception:
            return False

    def validate_config(self) -> list[str]:
        missing = []
        if not self.config.api_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        return missing
