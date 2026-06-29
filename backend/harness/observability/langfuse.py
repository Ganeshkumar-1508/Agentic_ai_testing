"""LangfuseSink — optional EventBus subscriber for Langfuse observability.

Translates typed StreamEvent sequences into Langfuse traces.
Fail-open: silently no-ops when the langfuse SDK or credentials are missing.

Event → Langfuse mapping:
  AgentStarted         → create trace + root span
  TokenGenerated       → updates current generation with content
  ToolExecutionStarted → starts a nested tool observation
  ToolExecutionCompleted → ends tool observation
  AgentCompleted       → ends root span + flush
  ErrorEvent           → sets error status on current span
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from harness.core.events import (
    AgentCompleted,
    AgentStarted,
    ErrorEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
    TokenGenerated,
    ReasoningGenerated,
)
from harness.events import EventSink

logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse

    _LANGFUSE_AVAILABLE = True
except Exception:
    Langfuse = None  # type: ignore[assignment]
    _LANGFUSE_AVAILABLE = False


@dataclass
class TraceState:
    """In-memory state for one active Langfuse trace (one agent run)."""
    trace_id: str
    root_span: Any
    current_generation: Any = None
    tool_spans: dict[str, Any] = field(default_factory=dict)
    pending_tool_spans: list[Any] = field(default_factory=list)
    last_updated_at: float = field(default_factory=time.time)


_TRACE_STATE: dict[str, TraceState] = {}
_TRACE_LOCK = threading.Lock()
_LANGFUSE_CLIENT = None
_INIT_FAILED = object()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_client() -> Any | None:
    """Return cached Langfuse client, or None if unavailable.

    Fail-open: returns None if SDK missing, credentials missing, or
    init fails. Result is cached so subsequent calls are fast.
    """
    global _LANGFUSE_CLIENT
    if _LANGFUSE_CLIENT is _INIT_FAILED:
        return None
    if _LANGFUSE_CLIENT is not None:
        return _LANGFUSE_CLIENT
    if not _LANGFUSE_AVAILABLE:
        _LANGFUSE_CLIENT = _INIT_FAILED
        return None

    public_key = _env("LANGFUSE_PUBLIC_KEY") or _env("HERMES_LANGFUSE_PUBLIC_KEY")
    secret_key = _env("LANGFUSE_SECRET_KEY") or _env("HERMES_LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        _LANGFUSE_CLIENT = _INIT_FAILED
        return None

    base_url = (
        _env("LANGFUSE_BASE_URL")
        or _env("HERMES_LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    )
    try:
        _LANGFUSE_CLIENT = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
        )
    except Exception as exc:
        logger.debug("Langfuse init failed: %s", exc)
        _LANGFUSE_CLIENT = _INIT_FAILED
        return None
    return _LANGFUSE_CLIENT


def _trace_key(event: StreamEvent) -> str:
    """Derive a stable trace key from a StreamEvent.

    Uses session_id if available, falls back to agent_id.
    """
    sid = getattr(event, "session_id", None) or ""
    aid = getattr(event, "agent_id", None) or ""
    return sid or aid or f"anon-{threading.get_ident()}"


def _truncate(text: str, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated {len(text) - max_chars} chars]"


class LangfuseSink:
    """EventSink that translates StreamEvent sequences into Langfuse traces.

    Usage:
        bus.add_sink(LangfuseSink())

    The sink is fail-open — if the langfuse SDK or credentials are
    unavailable, ``emit()`` is a no-op.
    """

    name = "langfuse"

    def __init__(self) -> None:
        self._client: Any = None
        self._available: bool = False
        client = _get_client()
        if client is not None:
            self._client = client
            self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def emit(self, event: StreamEvent) -> None:
        if not self._available or self._client is None:
            return
        try:
            self._dispatch(event)
        except Exception as exc:
            logger.debug("Langfuse emit failed: %s", exc)

    def _dispatch(self, event: StreamEvent) -> None:
        if isinstance(event, AgentStarted):
            self._on_agent_started(event)
        elif isinstance(event, TokenGenerated):
            self._on_token(event)
        elif isinstance(event, ReasoningGenerated):
            self._on_reasoning(event)
        elif isinstance(event, ToolExecutionStarted):
            self._on_tool_started(event)
        elif isinstance(event, ToolExecutionCompleted):
            self._on_tool_completed(event)
        elif isinstance(event, AgentCompleted):
            self._on_agent_completed(event)
        elif isinstance(event, ErrorEvent):
            self._on_error(event)

    def _on_agent_started(self, event: AgentStarted) -> None:
        key = _trace_key(event)
        client = self._client
        trace_id = client.create_trace_id(seed=key)
        metadata = {
            "source": "testai",
            "agent_id": event.agent_id,
            "model": event.model,
            "mode": event.mode,
        }
        trace_ctx = {"trace_id": trace_id}
        if hasattr(event, "session_id") and event.session_id:
            trace_ctx["session_id"] = event.session_id

        root_span = client.start_as_current_observation(
            trace_context=trace_ctx,
            name="TestAI Agent",
            as_type="span",
            input=_truncate(event.input),
            metadata=metadata,
            end_on_exit=False,
        )
        root_ctx = root_span.__enter__()

        state = TraceState(trace_id=trace_id, root_span=root_ctx)
        with _TRACE_LOCK:
            _TRACE_STATE[key] = state

    def _on_token(self, event: TokenGenerated) -> None:
        key = _trace_key(event)
        with _TRACE_LOCK:
            state = _TRACE_STATE.get(key)
        if state is None:
            return
        if state.current_generation is None:
            gen = state.root_span.start_observation(
                name="LLM response",
                as_type="generation",
                input=None,
            )
            state.current_generation = gen
        state.current_generation.update(
            output=state.current_generation.output + event.content
            if getattr(state.current_generation, "output", None)
            else event.content,
        )
        state.last_updated_at = time.time()

    def _on_reasoning(self, event: ReasoningGenerated) -> None:
        # Append to current generation's metadata
        key = _trace_key(event)
        with _TRACE_LOCK:
            state = _TRACE_STATE.get(key)
        if state is None:
            return
        if state.current_generation is not None:
            meta = getattr(state.current_generation, "metadata", None) or {}
            reasoning = meta.get("reasoning", "") + event.content
            meta["reasoning"] = reasoning
            state.current_generation.update(metadata=meta)
        state.last_updated_at = time.time()

    def _on_tool_started(self, event: ToolExecutionStarted) -> None:
        key = _trace_key(event)
        with _TRACE_LOCK:
            state = _TRACE_STATE.get(key)
        if state is None:
            return
        tool_input = _truncate(getattr(event, "tool_input", "") or str(getattr(event, "tool_name", "")))
        obs = state.root_span.start_observation(
            name=f"Tool: {event.tool_name}",
            as_type="tool",
            input=tool_input,
            metadata={
                "tool_name": event.tool_name,
                "trace_id": getattr(event, "trace_id", ""),
            },
        )
        trace_id_val = getattr(event, "trace_id", None) or str(id(obs))
        state.tool_spans[trace_id_val] = obs
        state.last_updated_at = time.time()

    def _on_tool_completed(self, event: ToolExecutionCompleted) -> None:
        key = _trace_key(event)
        with _TRACE_LOCK:
            state = _TRACE_STATE.get(key)
            if state is None:
                return
            trace_id_val = getattr(event, "trace_id", None)
            obs = state.tool_spans.pop(trace_id_val, None) if trace_id_val else None
            if obs is None and state.pending_tool_spans:
                obs = state.pending_tool_spans.pop(0)
        if obs is None:
            return
        output = _truncate(
            getattr(event, "output_preview", "") or str(getattr(event, "tool_name", ""))
        )
        success = getattr(event, "success", True)
        obs_end_meta: dict[str, Any] = {"success": success}
        if not success:
            obs_end_meta["error"] = getattr(event, "output_preview", "")
        obs.update(output=output, metadata=obs_end_meta)
        obs.end()
        state.last_updated_at = time.time()

    def _on_agent_completed(self, event: AgentCompleted) -> None:
        key = _trace_key(event)
        with _TRACE_LOCK:
            state = _TRACE_STATE.pop(key, None)
        if state is None:
            return
        # End any hanging generations
        if state.current_generation is not None:
            try:
                state.current_generation.end()
            except Exception:
                pass
        # End any hanging tool spans
        for _tid, obs in state.tool_spans.items():
            try:
                obs.end()
            except Exception:
                pass
        for obs in state.pending_tool_spans:
            try:
                obs.end()
            except Exception:
                pass
        # End root span
        output = _truncate(getattr(event, "output_preview", ""))
        state.root_span.update(output=output)
        try:
            state.root_span.end()
        except Exception:
            pass
        # Flush to Langfuse
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:
                pass

    def _on_error(self, event: ErrorEvent) -> None:
        key = _trace_key(event)
        with _TRACE_LOCK:
            state = _TRACE_STATE.get(key)
        if state is None:
            return
        state.root_span.update(
            metadata={"error": _truncate(event.message), "recoverable": event.recoverable},
        )
