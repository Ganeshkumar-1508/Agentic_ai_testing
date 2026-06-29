"""ChannelService — manages lifecycle of IM channels (without LangGraph dependency).

Ported from DeerFlow's ChannelService but simplified to use TestAI's
existing agent loop instead of LangGraph SDK.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from harness.channels.base import Channel
from harness.channels.message_bus import MessageBus
from harness.channels.store import ChannelStore

logger = logging.getLogger(__name__)

_CHANNEL_REGISTRY: dict[str, str] = {
    "dingtalk": "harness.channels.dingtalk:DingTalkChannel",
    "discord": "harness.channels.discord:DiscordChannel",
    "feishu": "harness.channels.feishu:FeishuChannel",
    "slack": "harness.channels.slack:SlackChannel",
    "telegram": "harness.channels.telegram:TelegramChannel",
    "wechat": "harness.channels.wechat:WechatChannel",
    "wecom": "harness.channels.wecom:WeComChannel",
}

_CHANNEL_CREDENTIAL_KEYS: dict[str, list[str]] = {
    "dingtalk": ["client_id", "client_secret"],
    "discord": ["bot_token"],
    "feishu": ["app_id", "app_secret"],
    "slack": ["bot_token", "app_token"],
    "telegram": ["bot_token"],
    "wecom": ["bot_id", "bot_secret"],
    "wechat": ["bot_token"],
}


def _channel_has_credentials(name: str, config: dict[str, Any]) -> bool:
    cred_keys = _CHANNEL_CREDENTIAL_KEYS.get(name, [])
    return any(
        not isinstance(config.get(key), bool)
        and config.get(key) is not None
        and str(config[key]).strip()
        for key in cred_keys
    )


def _resolve_class(import_path: str):
    module_path, class_name = import_path.rsplit(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class ChannelService:
    """Manages lifecycle of all configured IM channels."""

    def __init__(self, channels_config: dict[str, Any] | None = None) -> None:
        self.bus = MessageBus()
        self.store = ChannelStore()
        self._channels: dict[str, Any] = {}
        self._config = dict(channels_config or {})
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        ready = await self.ensure_ready_channels(attempts=2)
        ready_count = sum(1 for r in ready.values() if r)
        logger.info("ChannelService started: %d/%d ready", ready_count, len(ready))

    async def stop(self) -> None:
        for name, channel in list(self._channels.items()):
            try:
                await channel.stop()
            except Exception:
                logger.exception("Error stopping channel %s", name)
        self._channels.clear()
        self._running = False
        logger.info("ChannelService stopped")

    async def ensure_ready_channels(self, *, attempts: int = 1) -> dict[str, bool]:
        status: dict[str, bool] = {}
        for name, config in self._config.items():
            if not isinstance(config, dict):
                continue
            if not config.get("enabled", False):
                continue
            status[name] = await self.ensure_channel_ready(name, attempts=attempts)
        return status

    async def ensure_channel_ready(self, name: str, config: dict | None = None, *, attempts: int = 1) -> bool:
        if config is not None:
            self._config[name] = dict(config)

        channel_config = self._config.get(name)
        if not channel_config or not isinstance(channel_config, dict):
            return False
        if not channel_config.get("enabled", False):
            return False

        channel = self._channels.get(name)
        if channel is not None and channel.is_running:
            return True

        if channel is not None:
            try:
                await channel.stop()
            except Exception:
                pass
            self._channels.pop(name, None)

        for attempt in range(max(1, attempts)):
            if await self._start_channel(name, channel_config):
                return True
        return False

    async def _start_channel(self, name: str, config: dict) -> bool:
        import_path = _CHANNEL_REGISTRY.get(name)
        if not import_path:
            logger.warning("Unknown channel type: %s", name)
            return False

        try:
            channel_cls = _resolve_class(import_path)
        except Exception:
            logger.exception("Failed to import channel class for %s", name)
            return False

        try:
            config = dict(config)
            config["channel_store"] = self.store
            channel = channel_cls(bus=self.bus, config=config)
            self._channels[name] = channel
            await channel.start()
            if not channel.is_running:
                self._channels.pop(name, None)
                return False
            logger.info("Channel %s started", name)
            return True
        except Exception:
            self._channels.pop(name, None)
            logger.exception("Failed to start channel %s", name)
            return False

    def get_status(self) -> dict[str, Any]:
        channels_status = {}
        for name in _CHANNEL_REGISTRY:
            config = self._config.get(name, {})
            enabled = isinstance(config, dict) and config.get("enabled", False)
            running = name in self._channels and self._channels[name].is_running
            channels_status[name] = {"enabled": enabled, "running": running}
        return {"service_running": self._running, "channels": channels_status}

    def get_channel(self, name: str) -> Channel | None:
        return self._channels.get(name)
