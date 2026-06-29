"""Delivery platform adapter registry.

Maps platform name to adapter class. Adding a new platform means
adding one entry here and one import — no changes to ``DeliveryRouter``
or ``api/main.py`` are required.

Adapters are constructed lazily by ``DeliveryRouter`` on first use, so
importing the registry is cheap. Platform-specific deps (e.g. ``httpx``
for Slack, ``smtplib`` for email) are only paid for when the platform
is actually invoked.
"""
from harness.delivery.adapters.base import AdapterConfig, BaseAdapter, DeliveryTarget
from harness.delivery.adapters.custom_notifier import CustomNotifierAdapter
from harness.delivery.adapters.email import EmailAdapter
from harness.delivery.adapters.slack import SlackAdapter
from harness.delivery.adapters.teams import TeamsAdapter
from harness.delivery.adapters.telegram import TelegramAdapter


ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "slack": SlackAdapter,
    "teams": TeamsAdapter,
    "telegram": TelegramAdapter,
    "email": EmailAdapter,
    "custom_notifier": CustomNotifierAdapter,
}


__all__ = [
    "AdapterConfig",
    "ADAPTER_REGISTRY",
    "BaseAdapter",
    "CustomNotifierAdapter",
    "DeliveryTarget",
    "EmailAdapter",
    "SlackAdapter",
    "TeamsAdapter",
    "TelegramAdapter",
]
