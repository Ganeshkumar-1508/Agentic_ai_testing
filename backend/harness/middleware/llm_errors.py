"""LLM error handling middleware — ported from DeerFlow's LLMErrorHandlingMiddleware.

MIT License, Copyright (c) 2025 Bytedance Ltd. and/or its affiliates.

Strategy (unchanged from DeerFlow):
  - Circuit breaker: N consecutive failures → open for M seconds.
  - Error classification: quota, auth, transient, busy, generic.
  - Retry with exponential backoff + jitter for transient errors.
  - Per-exception retry budget overrides (e.g. StreamChunkTimeoutError → 1 retry).
  - i18n error patterns (Chinese + English) for ByteDance-scale deployments.
  - User-facing fallback messages grouped by error category.

Adapted from DeerFlow's ``llm_error_handling_middleware.py`` (468 lines).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)

_RETRIABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

_BUSY_PATTERNS = (
    "server busy", "temporarily unavailable", "try again later",
    "please retry", "please try again", "overloaded", "high demand",
    "rate limit",
    "负载较高", "服务繁忙", "稍后重试", "请稍后重试",
)

_QUOTA_PATTERNS = (
    "insufficient_quota", "quota", "billing", "credit", "payment",
    "余额不足", "超出限额", "额度不足", "欠费",
)

_AUTH_PATTERNS = (
    "authentication", "unauthorized", "invalid api key",
    "invalid_api_key", "permission", "forbidden", "access denied",
    "无权", "未授权",
)

_STREAM_DROP_EXCEPTIONS = frozenset({"StreamChunkTimeoutError"})

_RETRY_OVERRIDES: dict[str, int] = {
    "StreamChunkTimeoutError": 2,
}


class LLMErrorHandlingMiddleware(AgentMiddleware):
    """Retry transient LLM errors, surface graceful fallback messages."""

    def __init__(
        self,
        max_retries: int = 3,
        circuit_failure_threshold: int = 5,
        circuit_recovery_seconds: int = 30,
    ) -> None:
        self.max_retries = max_retries
        self._failures = 0
        self._circuit_open_until = 0.0
        self._threshold = circuit_failure_threshold
        self._recovery_secs = circuit_recovery_seconds

    def _circuit_open(self) -> bool:
        if self._failures >= self._threshold:
            if time.time() < self._circuit_open_until:
                return True
            self._failures = self._threshold // 2
        return False

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._circuit_open_until = time.time() + self._recovery_secs

    def _classify(self, exc: BaseException) -> tuple[bool, str]:
        msg = str(exc).lower()
        code = getattr(exc, "status_code", getattr(exc, "status", None))
        exc_name = type(exc).__name__

        if any(p in msg for p in _QUOTA_PATTERNS):
            return False, "quota"
        if any(p in msg for p in _AUTH_PATTERNS):
            return False, "auth"
        if exc_name in {"APITimeoutError", "APIConnectionError", "InternalServerError",
                         "ReadError", "RemoteProtocolError", "StreamChunkTimeoutError"}:
            return True, "transient"
        if isinstance(code, int) and code in _RETRIABLE_STATUS_CODES:
            return True, "transient"
        if any(p in msg for p in _BUSY_PATTERNS):
            return True, "busy"

        return False, "generic"

    def _max_attempts(self, exc: BaseException) -> int:
        return min(_RETRY_OVERRIDES.get(type(exc).__name__, self.max_retries), self.max_retries)

    def _delay_ms(self, attempt: int) -> int:
        base = 1000 * (2 ** max(0, attempt - 1))
        return min(base, 8000)

    def _fallback_message(self, exc: BaseException, reason: str) -> str:
        if reason == "quota":
            return (
                "The configured LLM provider rejected the request because the account "
                "is out of quota or billing is unavailable. Please fix the provider "
                "account and try again."
            )
        if reason == "auth":
            return (
                "The configured LLM provider rejected the request because authentication "
                "is invalid. Please check the provider credentials and try again."
            )
        if reason == "transient":
            if type(exc).__name__ in _STREAM_DROP_EXCEPTIONS:
                return (
                    "The model's streaming response was interrupted mid-flight. "
                    "This usually happens when a single tool call is very large — "
                    "please split the work into smaller steps and try again."
                )
            return (
                "The configured LLM provider is temporarily unavailable after "
                "multiple retries. Please wait a moment and continue."
            )
        return f"LLM request failed: {str(exc)[:300]}"

    async def wrap_llm_call(self, messages: list, round_num: int, llm_call) -> tuple[list, str | None]:
        """Wrap an LLM call with retry + circuit breaker.
        
        Args:
            messages: The message list.
            round_num: Current round number.
            llm_call: Async callable that takes messages and returns (tool_calls, full_content).
            
        Returns:
            (tool_calls_or_empty, forced_text_or_None)
        """
        if self._circuit_open():
            logger.warning("LLM circuit breaker open, fast-failing")
            return [], (
                "The configured LLM provider is currently unavailable due to "
                "continuous failures. Please wait before trying again."
            )

        max_attempts = self.max_retries

        for attempt in range(1, max_attempts + 1):
            try:
                result = await llm_call(messages)
                self._failures = 0
                return result
            except Exception as exc:
                retriable, reason = self._classify(exc)
                effective_max = min(_RETRY_OVERRIDES.get(type(exc).__name__, max_attempts), max_attempts)

                if retriable and attempt < effective_max:
                    delay = self._delay_ms(attempt) / 1000
                    logger.warning(
                        "LLM transient error (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt, effective_max, reason, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.warning("LLM call failed after %d attempt(s): %s", attempt, reason)
                self._record_failure()
                return [], self._fallback_message(exc, reason)

        return [], "LLM request failed after all retries."
