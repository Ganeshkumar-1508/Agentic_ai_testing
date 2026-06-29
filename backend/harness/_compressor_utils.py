"""Replacement utilities for Hermes imports used by context_compressor.py.

Provides drop-in replacements for:
  - agent.context_engine.ContextEngine
  - agent.model_metadata (MINIMUM_CONTEXT_LENGTH, get_model_context_length, estimate_messages_tokens_rough)
  - agent.redact.redact_sensitive_text
  - agent.auxiliary_client._is_connection_error
"""

import os
import re
from typing import Any


DEFAULT_COMPACTION_THRESHOLD: float = 0.85
COMPACTION_THRESHOLD_ENV: str = "TESTAI_COMPACTION_THRESHOLD"
COMPACTION_THRESHOLD_MIN: float = 0.0
COMPACTION_THRESHOLD_MAX: float = 1.0


def get_compaction_threshold(default: float = DEFAULT_COMPACTION_THRESHOLD) -> float:
    raw = os.environ.get(COMPACTION_THRESHOLD_ENV)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        return default
    if value < COMPACTION_THRESHOLD_MIN or value > COMPACTION_THRESHOLD_MAX:
        return default
    return value


_CHARS_PER_TOKEN = 4


class ContextEngine:
    def on_session_reset(self) -> None:
        pass


MINIMUM_CONTEXT_LENGTH = 8192

_KNOWN_CONTEXT_LENGTHS: dict[str, int] = {
    "deepseek-v4-flash": 131072,
    "deepseek-v3": 131072,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16384,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-4": 200000,
    "claude-4-sonnet": 200000,
    "claude-4-opus": 200000,
    "claude-4-opus-1m": 1048576,
    "gemini-1.5-pro": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-2.0-flash": 1048576,
    "hermes-grok-4.3": 1048576,
    "hermes-grok-4.3-1m": 1048576,
    "grok-4.3": 1048576,
    "grok-4": 131072,
    "llama-3.1-8b": 131072,
    "llama-3.1-70b": 131072,
    "llama-3.1-405b": 131072,
    "mixtral-8x7b": 32768,
    "command-r": 131072,
    "command-r-plus": 131072,
}


def get_model_context_length(model: str, **kwargs: Any) -> int:
    """Resolve model context length.
    
    Priority:
      1. config_context_length kwarg (caller resolved via PricingCache)
      2. Known model dict (static fallback)
      3. Default 131072
    """
    config_length = kwargs.get("config_context_length")
    if config_length is not None:
        return int(config_length)
    return _KNOWN_CONTEXT_LENGTHS.get(model, 131072)


def estimate_messages_tokens_rough(messages: list) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        total += len(content) // _CHARS_PER_TOKEN + 10
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                args = tc.get("function", {}).get("arguments", "")
                total += len(args) // _CHARS_PER_TOKEN
    return total


def _redact_sensitive_text(text: str) -> str:
    patterns: list[tuple[str, str]] = [
        (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}", "[REDACTED]"),
        (r"token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{20,}", "[REDACTED]"),
        (r"secret['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}", "[REDACTED]"),
        (r"password['\"]?\s*[:=]\s*['\"]?[^\s'\"']{6,}", "[REDACTED]"),
        (r"sk-[A-Za-z0-9_\-]{20,}", "[REDACTED]"),
        (r"xox[baprs]-[A-Za-z0-9_\-]{10,}", "[REDACTED]"),
        (r"gh[pousr]_[A-Za-z0-9_\-]{20,}", "[REDACTED]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _is_connection_error(e: Exception) -> bool:
    err_str = str(e).lower()
    triggers = [
        "connectionerror",
        "connection refused",
        "connection reset",
        "incomplete chunked",
        "peer closed",
        "ended prematurely",
        "unexpected eof",
        "eof",
        "stream closed",
    ]
    return any(t in err_str for t in triggers)
