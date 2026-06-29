from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request

from harness._compressor_utils import (
    COMPACTION_THRESHOLD_ENV,
    DEFAULT_COMPACTION_THRESHOLD,
    get_compaction_threshold,
)
from harness.context_compressor.compressor import get_compaction_state_snapshot
from harness.trace import OTEL_AVAILABLE, _is_otel_enabled, get_otel_handler

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/status")
async def get_status() -> dict:
    enabled = _is_otel_enabled()
    snapshot = get_otel_handler().get_counts_snapshot()
    return {
        "enabled": enabled,
        "available": OTEL_AVAILABLE,
        "endpoint": os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        "service_name": os.environ.get("OTEL_SERVICE_NAME", "testai-harness"),
        "service_version": os.environ.get("OTEL_SERVICE_VERSION", "1.0.0"),
        "span_counts": snapshot["counts"],
        "last_span_at": snapshot["last_span_at"],
    }


@router.get("/compaction")
async def get_compaction(request: Request) -> dict:
    state = get_compaction_state_snapshot()
    threshold = get_compaction_threshold()
    compressor = getattr(request.app.state, "context_compressor", None)
    context_length = getattr(compressor, "context_length", None)
    model = getattr(compressor, "model", None)
    threshold_tokens = (
        int(context_length * threshold) if context_length else None
    )
    saved_tokens: int | None = None
    if state.get("last_before_tokens") is not None and state.get("last_after_tokens") is not None:
        saved_tokens = int(state["last_before_tokens"]) - int(state["last_after_tokens"])
    return {
        "threshold_percent": threshold,
        "default_threshold_percent": DEFAULT_COMPACTION_THRESHOLD,
        "env_var": COMPACTION_THRESHOLD_ENV,
        "context_length": context_length,
        "model": model,
        "threshold_tokens": threshold_tokens,
        "compactions_total": state.get("compactions_total", 0),
        "last_before_tokens": state.get("last_before_tokens"),
        "last_after_tokens": state.get("last_after_tokens"),
        "last_saved_tokens": saved_tokens,
        "last_at": (
            __import__("datetime").datetime.fromtimestamp(
                state["last_at"], tz=__import__("datetime").timezone.utc,
            ).isoformat()
            if state.get("last_at")
            else None
        ),
    }


__all__ = ["router"]
