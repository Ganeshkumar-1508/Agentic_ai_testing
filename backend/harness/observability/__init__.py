"""Observability — optional EventBus sinks for agent telemetry.
Langfuse and OpenTelemetry backends. Fail-open if SDK/creds missing.
"""

from __future__ import annotations

import logging

from harness.events import EventBus

logger = logging.getLogger(__name__)


def register_observability_sinks(bus: EventBus) -> None:
    """Register available observability sinks on the shared event bus.
    Safe to call even if no SDK or credentials are configured.
    """
    # Langfuse sink
    try:
        from harness.observability.langfuse import LangfuseSink

        sink = LangfuseSink()
        bus.add_sink(sink)
        if sink.available:
            logger.info("observability: Langfuse sink registered")
    except Exception as exc:
        logger.debug("observability: Langfuse sink not available: %s", exc)

    # OpenTelemetry sink (future)
    # try:
    #     from harness.observability.otel import OTelSink
    #     bus.add_sink(OTelSink())
    #     ...
    # except Exception:
    #     pass
