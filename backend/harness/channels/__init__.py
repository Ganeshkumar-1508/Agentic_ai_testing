"""IM channels — ported from DeerFlow (MIT License, Bytedance Ltd.).

Currently only Slack is ported. Other platforms (Telegram, Discord,
Feishu, DingTalk, WeChat, WeCom) can be added from reference/deer-flow/
when needed.
"""

from harness.channels.base import Channel
from harness.channels.message_bus import MessageBus, InboundMessage, OutboundMessage
from harness.channels.service import ChannelService
from harness.channels.slack import SlackChannel
from harness.channels.store import ChannelStore

__all__ = [
    "Channel", "MessageBus", "InboundMessage", "OutboundMessage",
    "ChannelService", "SlackChannel", "ChannelStore",
]
