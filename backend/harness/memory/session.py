from __future__ import annotations

from typing import Any


class SessionMemory:
    def __init__(self, max_messages: int = 100):
        self._messages: list[dict[str, Any]] = []
        self.max_messages = max_messages

    def add(self, message: Any) -> None:
        if hasattr(message, "to_dict"):
            self._messages.append(message.to_dict())
        elif isinstance(message, dict):
            self._messages.append(message)
        elif hasattr(message, "role"):
            self._messages.append({
                "role": message.role,
                "content": getattr(message, "content", None),
                "tool_call_id": getattr(message, "tool_call_id", None),
                "tool_calls": getattr(message, "tool_calls", None),
            })

        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        return self._messages[-n:]
