"""Skill activation middleware — ported from DeerFlow (MIT License, Bytedance Ltd).

Detects /skill-name syntax in user messages and injects the skill's full
SKILL.md content as hidden context for the current turn.
"""

from __future__ import annotations

import html
import logging
import re
from pathlib import Path

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_SLASH_RE = re.compile(r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$")
_ACTIVATION_KEY = "slash_skill_activation"
_CHANNEL_COMMANDS = frozenset({"/new", "/help", "/status", "/models", "/memory"})


class SkillActivationMiddleware(AgentMiddleware):
    """Inject SKILL.md content when user types /skill-name."""

    def __init__(self, skills_dir: str | None = None) -> None:
        self._skills_dir = skills_dir
        self._activated_in_turn: set[str] = set()

    async def on_before_run(self, user_input: str) -> None:
        self._activated_in_turn = set()

    async def on_end_of_round(self, round_num: int) -> None:
        self._activated_in_turn = set()

    def _find_skill_md(self, name: str) -> str | None:
        base = self._skills_dir or "skills"
        candidates = [
            Path(base) / "public" / name / "SKILL.md",
            Path(base) / "custom" / name / "SKILL.md",
        ]
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8")
        return None

    async def on_before_llm(self, messages: list, round_num: int) -> list | None:
        if round_num > 0:
            return None

        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if getattr(msg, "role", "") != "user":
                continue
            content = str(getattr(msg, "content", "") or "").strip()
            m = _SLASH_RE.match(content)
            if not m:
                continue

            skill_name = m.group(1)
            if f"/{skill_name}" in _CHANNEL_COMMANDS:
                continue
            if skill_name in self._activated_in_turn:
                continue

            skill_content = self._find_skill_md(skill_name)
            if not skill_content:
                logger.warning("SkillActivation: skill /%s not found", skill_name)
                continue

            remaining = m.group(2) or ""
            self._activated_in_turn.add(skill_name)

            ctx = (
                f"<slash_skill_activation>\n"
                f"The user activated the `{skill_name}` skill.\n"
                f"<user_request>\n{html.escape(remaining)}\n</user_request>\n"
                f"<skill_content>\n{html.escape(skill_content)}\n</skill_content>\n"
                f"</slash_skill_activation>"
            )

            from harness.core.events import ChatMessage
            new_msgs = list(messages)
            new_msgs.insert(i, ChatMessage(
                role="system",
                content=ctx,
                additional_kwargs={_ACTIVATION_KEY: True, "hide_from_ui": True},
            ))
            logger.info("SkillActivation: activated /%s", skill_name)
            return new_msgs

        return None
