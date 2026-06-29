from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeliveryTarget:
    platform: str
    chat_id: str | None = None
    thread_id: str | None = None
    is_origin: bool = False
    is_explicit: bool = False

    @classmethod
    def parse(cls, target: str, origin: str | None = None) -> DeliveryTarget:
        t = target.strip().lower()
        if t == "origin":
            return cls(platform=origin or "local", is_origin=True)
        if t == "local":
            return cls(platform="local")
        if ":" in target:
            parts = target.split(":", 2)
            return cls(
                platform=parts[0].lower(),
                chat_id=parts[1] if len(parts) > 1 else None,
                thread_id=parts[2] if len(parts) > 2 else None,
                is_explicit=True,
            )
        return cls(platform=t)

    def to_string(self) -> str:
        if self.is_origin:
            return "origin"
        if self.chat_id and self.thread_id:
            return f"{self.platform}:{self.chat_id}:{self.thread_id}"
        if self.chat_id:
            return f"{self.platform}:{self.chat_id}"
        return self.platform


@dataclass
class AdapterConfig:
    enabled: bool = True
    api_token: str = ""
    webhook_url: str = ""
    signing_secret: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    name: str = ""

    def __init__(self, config: AdapterConfig | None = None):
        self.config = config or AdapterConfig()

    @abstractmethod
    async def send(self, chat_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    @abstractmethod
    async def health(self) -> bool:
        ...

    def validate_config(self) -> list[str]:
        missing: list[str] = []
        return missing
