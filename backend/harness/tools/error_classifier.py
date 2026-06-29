"""Classify API errors for provider fallback and retry decisions."""

from __future__ import annotations

from typing import Any

_ERROR_CATEGORIES = {
    "rate_limit": ["rate limit", "429", "too many requests", "retry after"],
    "auth": ["401", "403", "unauthorized", "forbidden", "invalid api key", "authentication"],
    "timeout": ["timeout", "timed out", "deadline exceeded", "504", "502", "503"],
    "context_length": ["context length", "too many tokens", "maximum context", "prompt too long"],
    "server_error": ["500", "internal server error", "service unavailable"],
    "quota": ["quota", "insufficient_quota", "billing limit"],
    "stream_error": ["stream", "chunk", "SSE"],
    "invalid_request": [
        "400",
        "invalid_request_error",
        "bad request",
        "invalid request",
        "tool_calls",
        "must be followed by tool messages",
        "malformed",
    ],
    "model_overload": [
        "529",
        "overloaded",
        "capacity",
        "server is overloaded",
    ],
    "circuit_open": [
        "circuit_open:",
        "circuit breaker",
        "provider unavailable",
    ],
}


def classify_error(error_message: str) -> dict[str, Any]:
    """Classify an API error into a category for fallback decisions."""
    msg_lower = (error_message or "").lower()

    for category, patterns in _ERROR_CATEGORIES.items():
        for pattern in patterns:
            if pattern in msg_lower:
                retryable = category in (
                    "rate_limit",
                    "timeout",
                    "server_error",
                    "stream_error",
                    "model_overload",
                )
                return {
                    "category": category,
                    "retryable": retryable,
                    "message": error_message,
                }

    return {"category": "unknown", "retryable": False, "message": error_message}


def should_fallback(error_message: str) -> bool:
    """Determine if a provider error should trigger a fallback."""
    cls = classify_error(error_message)
    return cls["category"] in ("auth", "quota", "server_error", "invalid_request") or (
        cls["category"] == "rate_limit" and not cls.get("retryable", False)
    )
