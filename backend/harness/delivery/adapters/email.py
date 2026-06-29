from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any

from .base import BaseAdapter, AdapterConfig

logger = logging.getLogger(__name__)


class EmailAdapter(BaseAdapter):
    name = "email"

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__(config)
        self._smtp_host = config.extra.get("smtp_host", "") if config else ""
        self._smtp_port = int(config.extra.get("smtp_port", "587")) if config else 587
        self._smtp_user = config.extra.get("smtp_user", "") if config else ""
        self._smtp_pass = config.extra.get("smtp_pass", "") if config else ""
        self._from_addr = config.extra.get("from_addr", "testai@localhost") if config else "testai@localhost"

    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        subject = (metadata or {}).get("subject", "TestAI Notification")
        msg = MIMEText(content, _charset="utf-8")
        msg["Subject"] = subject
        msg["To"] = chat_id
        msg["From"] = self._from_addr
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_sync, msg)
        return {"ok": True, "to": chat_id, "subject": subject}

    def _send_sync(self, msg: MIMEText) -> None:
        import asyncio
        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=15) as server:
            server.starttls()
            if self._smtp_user and self._smtp_pass:
                server.login(self._smtp_user, self._smtp_pass)
            server.send_message(msg)

    async def health(self) -> bool:
        return bool(self._smtp_host and self._smtp_user)

    def validate_config(self) -> list[str]:
        missing = []
        if not self._smtp_host:
            missing.append("SMTP_HOST")
        if not self._smtp_user:
            missing.append("SMTP_USER")
        if not self._smtp_pass:
            missing.append("SMTP_PASS")
        return missing
