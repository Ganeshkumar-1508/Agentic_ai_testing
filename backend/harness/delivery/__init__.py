"""Delivery package — content routing to platform adapters.

Adapters (slack, teams, telegram, email, custom_notifier) are loaded
lazily by :class:`DeliveryRouter` on first use via the class registry
in :data:`ADAPTER_REGISTRY`.
"""
from harness.delivery.router import (
    DeliveryRouter,
    MAX_CONTENT_CHARS,
    OUTPUT_DIR,
    TRUNCATED_VISIBLE,
)


__all__ = [
    "DeliveryRouter",
    "MAX_CONTENT_CHARS",
    "OUTPUT_DIR",
    "TRUNCATED_VISIBLE",
]
