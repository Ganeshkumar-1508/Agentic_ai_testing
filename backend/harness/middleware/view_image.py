"""View image middleware — ported from DeerFlow (MIT License, Bytedance Ltd).

Injects image data (base64) from view_image tool results into the conversation
before the next LLM call, enabling vision-capable models to see images.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)


class ViewImageMiddleware(AgentMiddleware):
    """Inject viewed image data as a human message before LLM calls."""

    def __init__(self) -> None:
        self._pending_images: dict[str, dict[str, Any]] = {}

    async def on_after_tool(self, name: str, result: str) -> str | None:
        if name == "view_image" and result:
            try:
                import json
                data = json.loads(result)
                path = data.get("path", data.get("file", ""))
                if path:
                    self._pending_images[path] = data
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        if not self._pending_images:
            return None

        blocks: list[dict[str, Any]] = [{"type": "text", "text": "Here are the images you viewed:"}]
        for path, data in self._pending_images.items():
            mime = data.get("mime_type", "image/png")
            b64 = data.get("base64", data.get("data", ""))
            blocks.append({"type": "text", "text": f"\n- **{path}** ({mime})"})
            if b64:
                blocks.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        self._pending_images.clear()
        from harness.core.events import ChatMessage
        return list(messages) + [ChatMessage(role="user", content=blocks,
                                             additional_kwargs={"hide_from_ui": True})]
