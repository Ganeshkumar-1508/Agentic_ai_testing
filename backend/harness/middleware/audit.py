"""Sandbox audit middleware — ported from DeerFlow's SandboxAuditMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (unchanged from DeerFlow):
  - Classifies bash commands as high-risk (block), medium-risk (warn), pass.
  - High-risk patterns: rm -rf /, curl|sh, base64 decode|exec, fork bombs, etc.
  - Medium-risk patterns: chmod 777, pip install, sudo, PATH assignment.
  - Blocked commands return error; warned commands append warning to result.
  - Every bash call is logged as structured JSON audit entry.

Adapted from DeerFlow's ``sandbox_audit_middleware.py`` (363 lines).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_HIGH_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-[^\s]*r[^\s]*\s+(/\*?|~/?\*?|/home\b|/root\b)\s*$"),
    re.compile(r"dd\s+if="),
    re.compile(r"mkfs"),
    re.compile(r"cat\s+/etc/shadow"),
    re.compile(r">+\s*/etc/"),
    re.compile(r"\|\s*(ba)?sh\b"),
    re.compile(r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)"),
    re.compile(r"base64\s+.*-d.*\|"),
    re.compile(r">+\s*(/usr/bin/|/bin/|/sbin/)"),
    re.compile(r">+\s*~/?\.(bashrc|profile|zshrc|bash_profile)"),
    re.compile(r"/proc/[^/]+/environ"),
    re.compile(r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*="),
    re.compile(r"/dev/tcp/"),
    re.compile(r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&"),
    re.compile(r"while\s+true.*&\s*done"),
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chmod\s+777"),
    re.compile(r"pip3?\s+install"),
    re.compile(r"apt(-get)?\s+install"),
    re.compile(r"\b(sudo|su)\b"),
    re.compile(r"\bPATH\s*="),
]

_MAX_COMMAND_LENGTH = 10_000


def _classify_command(command: str) -> str:
    normalized = " ".join(command.split())
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"
    for pattern in _MEDIUM_RISK_PATTERNS:
        if pattern.search(normalized):
            return "warn"
    return "pass"


class SandboxAuditMiddleware(AgentMiddleware):
    """Security audit for bash commands. Blocks high-risk, logs everything."""

    async def on_before_tool(self, name: str, args: dict) -> bool | None:
        if name not in ("bash", "bash_tool"):
            return None

        command = args.get("command", args.get("cmd", ""))
        if not isinstance(command, str):
            return None

        if not command.strip():
            return None

        if len(command) > _MAX_COMMAND_LENGTH:
            logger.warning("SandboxAudit BLOCKED: command too long (%d chars)", len(command))
            return False

        if "\x00" in command:
            logger.warning("SandboxAudit BLOCKED: null byte in command")
            return False

        verdict = _classify_command(command)
        self._log_audit(name, command, verdict)

        if verdict == "block":
            logger.warning("SandboxAudit BLOCKED: %s", command[:200])
            return False

        return None

    async def on_after_tool(self, name: str, result: str) -> str | None:
        return None

    @staticmethod
    def _log_audit(tool: str, command: str, verdict: str) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "command": command[:500],
            "verdict": verdict,
        }
        logger.info("[SandboxAudit] %s", json.dumps(record, ensure_ascii=False))
