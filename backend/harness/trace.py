from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable


TraceCallback = Callable[[str, dict[str, Any]], None]

OTEL_AVAILABLE = False
_tracer = None


# ---------------------------------------------------------------------------
# OpenTelemetry GenAI semantic conventions
# ---------------------------------------------------------------------------
# Span attribute names follow the OTel GenAI semconv
# (https://opentelemetry.io/docs/specs/semconv/gen-ai/) so traces flow
# into Datadog, Honeycomb, Tempo, Grafana, Langfuse, LangSmith without
# per-backend adapters. TestAI-specific attributes (cost, agent
# metadata, etc.) are namespaced under `testai.*` per OTel's
# reverse-DNS guidance for custom attributes.
#
# Mapping (per semconv-genai "Spans" spec, 2026):
#   llm.model              → gen_ai.request.model
#   llm.prompt_tokens      → gen_ai.usage.input_tokens
#   llm.completion_tokens  → gen_ai.usage.output_tokens
#   agent.id               → gen_ai.agent.id
#   tool.name              → gen_ai.tool.name
#   new: gen_ai.operation.name  (Required on every GenAI span)
#   new: gen_ai.provider.name   (Required when known; e.g. "openai", "anthropic")
# ---------------------------------------------------------------------------

OTEL_ATTR = {
    "request_model": "gen_ai.request.model",
    "usage_input_tokens": "gen_ai.usage.input_tokens",
    "usage_output_tokens": "gen_ai.usage.output_tokens",
    "agent_id": "gen_ai.agent.id",
    "tool_name": "gen_ai.tool.name",
    "operation_name": "gen_ai.operation.name",
    "provider_name": "gen_ai.provider.name",
    "error_type": "error.type",
}

# TestAI-specific attributes (reverse-DNS namespaced per OTel guidance)
TESTAI_ATTR = {
    "agent_parent_id": "testai.agent.parent_id",
    "agent_input": "testai.agent.input",
    "llm_round": "testai.llm.round",
    "llm_total_tokens": "testai.llm.total_tokens",
    "tool_success": "testai.tool.success",
    "content_preview": "testai.content_preview",
    "subagent_id": "testai.subagent.id",
    "subagent_role": "testai.subagent.role",
    "subagent_depth": "testai.subagent.depth",
    "subagent_parent_id": "testai.subagent.parent_id",
    "subagent_duration_s": "testai.subagent.duration_s",
    "subagent_cost_usd": "testai.subagent.cost_usd",
    "subagent_status": "testai.subagent.status",
    "kanban_task_id": "testai.kanban.task_id",
    "kanban_board_id": "testai.kanban.board_id",
    "kanban_transition": "testai.kanban.transition",
    "kanban_task_role": "testai.kanban.task_role",
    "kanban_task_count": "testai.kanban.task_count",
    "kanban_duration_s": "testai.kanban.duration_s",
    "kanban_error": "testai.kanban.error",
    "budget_run_id": "testai.budget.run_id",
    "budget_spent_usd": "testai.budget.spent_usd",
    "budget_soft_cap_usd": "testai.budget.soft_cap_usd",
    "budget_throttle_step": "testai.budget.throttle_step",
    "budget_hitl_active": "testai.budget.hitl_active",
    "budget_cheaper_model_active": "testai.budget.cheaper_model_active",
    "budget_pause_requested": "testai.budget.pause_requested",
}

OTEL_OPERATION = {
    "chat": "chat",
    "execute_tool": "execute_tool",
    "agent_run": "agent_run",
    "agent_round": "agent_round",
    "agent_reasoning": "agent_reasoning",
    "subagent_invoke": "subagent_invoke",
    "kanban_transition": "kanban_transition",
    "kanban_board": "kanban_board",
    "budget_throttle": "budget_throttle",
}


def _is_otel_enabled() -> bool:
    raw = os.environ.get("OTEL_ENABLED", "false").lower().strip()
    return raw in ("true", "1", "yes", "on")


def _otel_protocol() -> str:
    """Return the OTLP protocol to use.

    Follows the OTel SDK env-var convention:
      ``OTEL_EXPORTER_OTLP_TRACES_PROTOCOL`` (traces-specific, highest priority)
      ``OTEL_EXPORTER_OTLP_PROTOCOL`` (general, fallback)
      default: ``grpc``

    Returns ``"grpc"`` or ``"http/protobuf"``.
    """
    raw = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL")
        or os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL")
        or "grpc"
    )
    return raw.lower().strip()


def _init_otel():
    global OTEL_AVAILABLE, _tracer
    if not _is_otel_enabled():
        OTEL_AVAILABLE = False
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        protocol = _otel_protocol()
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        service_name = os.environ.get("OTEL_SERVICE_NAME", "testai-harness")
        service_version = os.environ.get("OTEL_SERVICE_VERSION", "1.0.0")
        resource = Resource.create({
            "service.name": service_name,
            "service.version": service_version,
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        OTEL_AVAILABLE = True
    except Exception:
        OTEL_AVAILABLE = False


_init_otel()


class DatabaseTraceHandler:
    def __init__(self, db: Any, run_id: str, agent_id: str = "", parent_id: str = ""):
        self.db = db
        self.run_id = run_id
        self.agent_id = agent_id
        self.parent_id = parent_id
        self._stack: list[str] = []

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        parent_id = self._stack[-1] if self._stack else (self.parent_id or None)
        event_id = str(uuid.uuid4())
        entry = {
            "event_type": event_type,
            "data": data,
            "parent_id": parent_id,
        }
        try:
            await self.db.execute(
                "INSERT INTO trace_events (id, run_id, agent_id, event_type, event_data, parent_id) VALUES ($1, $2, $3, $4, $5, $6)",
                event_id, self.run_id, self.agent_id, event_type, json.dumps(entry), parent_id or "",
            )
        except Exception:
            pass
        if event_type.startswith("start:") or event_type in ("round.started", "agent.started", "llmcall.started", "tool.execution.started"):
            self._stack.append((event_type, time.monotonic(), data))
        elif event_type in ("round.completed", "agent.completed", "llmcall.completed", "tool.execution.completed", "error") and self._stack:
            self._stack.pop()


_otel_handler: OTelTraceHandler | None = None


def get_otel_handler() -> OTelTraceHandler:
    """Return the singleton OTelTraceHandler.

    The handler is created lazily on first call so the
    process doesn't pay the singleton cost when OTel is
    disabled (the default). The trace callback in
    ``api/state.py`` and the status endpoint in
    ``api/routers/observability.py`` both go through this
    function so span counts accumulate in one place.
    """
    global _otel_handler
    if _otel_handler is None:
        _otel_handler = OTelTraceHandler()
    return _otel_handler


class OTelTraceHandler:
    def __init__(self):
        self._spans: dict[str, Any] = {}
        self._span_counts: dict[str, int] = {}
        self._last_span_at: float | None = None

    def _bump(self, operation: str) -> None:
        import time as _time
        self._span_counts[operation] = self._span_counts.get(operation, 0) + 1
        self._last_span_at = _time.time()

    def get_counts_snapshot(self) -> dict[str, Any]:
        import datetime as _dt
        return {
            "counts": dict(self._span_counts),
            "last_span_at": (
                _dt.datetime.fromtimestamp(self._last_span_at, tz=_dt.timezone.utc).isoformat()
                if self._last_span_at is not None
                else None
            ),
        }

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        if not OTEL_AVAILABLE or not _tracer:
            return

        span_name_map = {
            ("agent:start", "agent:end"): OTEL_OPERATION["agent_run"],
            ("round:start", "round:end"): OTEL_OPERATION["agent_round"],
        }
        if event_type in ("llm:start", "llm:end"):
            model = data.get("model", "unknown")
            span_name = f"{OTEL_OPERATION['chat']} {model}"
        elif event_type in ("tool:start", "tool:end", "tool:error"):
            tool_name = data.get("name", "unknown")
            span_name = f"{OTEL_OPERATION['execute_tool']} {tool_name}"
        elif event_type == "agent:start" or event_type == "agent:end":
            span_name = OTEL_OPERATION["agent_run"]
        elif event_type == "round:start" or event_type == "round:end":
            span_name = OTEL_OPERATION["agent_round"]
        elif event_type == "reasoning":
            span_name = OTEL_OPERATION["agent_reasoning"]
        elif event_type == "subagent.spawned" or event_type == "subagent.completed":
            role = data.get("role", "agent")
            span_name = f"subagent {role}"
        elif event_type in ("board.task.completed", "board.task.failed"):
            span_name = OTEL_OPERATION["kanban_transition"]
        elif event_type in ("board.completed", "board.failed"):
            span_name = OTEL_OPERATION["kanban_board"]
        elif event_type == "budget.throttled":
            span_name = OTEL_OPERATION["budget_throttle"]
        else:
            span_name = event_type

        if event_type == "llm:start":
            span = _tracer.start_span(span_name)
            span_id = data.get("id", "")
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["chat"])
            provider = _provider_name(data.get("model", ""))
            if provider:
                span.set_attribute(OTEL_ATTR["provider_name"], provider)
            span.set_attribute(OTEL_ATTR["request_model"], data.get("model", "unknown"))
            span.set_attribute(TESTAI_ATTR["llm_round"], data.get("round", 0))
            if data.get("_scope_agent_id"):
                span.set_attribute(OTEL_ATTR["agent_id"], data["_scope_agent_id"])
            if data.get("_scope_parent_id"):
                span.set_attribute(TESTAI_ATTR["agent_parent_id"], data["_scope_parent_id"])
            self._spans[span_id] = span
            self._bump(OTEL_OPERATION["chat"])

        elif event_type == "llm:end":
            span_id = data.get("id", "")
            span = self._spans.pop(span_id, None)
            if span:
                span.set_attribute(OTEL_ATTR["usage_input_tokens"], data.get("prompt_tokens", 0))
                span.set_attribute(OTEL_ATTR["usage_output_tokens"], data.get("completion_tokens", 0))
                span.set_attribute(TESTAI_ATTR["llm_total_tokens"], data.get("total_tokens", 0))
                span.end()

        elif event_type == "tool:start":
            span = _tracer.start_span(span_name)
            span_id = data.get("id", "")
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["execute_tool"])
            span.set_attribute(OTEL_ATTR["tool_name"], data.get("name", "unknown"))
            if data.get("_scope_agent_id"):
                span.set_attribute(OTEL_ATTR["agent_id"], data["_scope_agent_id"])
            self._spans[span_id] = span
            self._bump(OTEL_OPERATION["execute_tool"])

        elif event_type in ("tool:end", "tool:error"):
            span_id = data.get("id", "")
            span = self._spans.pop(span_id, None)
            if span:
                if event_type == "tool:error":
                    span.set_attribute(OTEL_ATTR["error_type"], data.get("error", "unknown"))
                span.set_attribute(TESTAI_ATTR["tool_success"], data.get("success", False))
                span.end()

        elif event_type == "agent:start":
            span = _tracer.start_span(span_name)
            span.set_attribute(TESTAI_ATTR["agent_input"], str(data.get("input", ""))[:200])
            if data.get("_scope_agent_id"):
                span.set_attribute(OTEL_ATTR["agent_id"], data["_scope_agent_id"])
            if data.get("_scope_parent_id"):
                span.set_attribute(TESTAI_ATTR["agent_parent_id"], data["_scope_parent_id"])
            self._spans["root"] = span
            self._bump(OTEL_OPERATION["agent_run"])

        elif event_type == "agent:end":
            span = self._spans.pop("root", None)
            if span:
                if data.get("error"):
                    span.set_attribute(OTEL_ATTR["error_type"], data["error"])
                span.end()

        elif event_type == "reasoning":
            span = _tracer.start_span(span_name)
            span.set_attribute(TESTAI_ATTR["content_preview"], str(data.get("content_preview", ""))[:200])
            span.end()
            self._bump(OTEL_OPERATION["agent_reasoning"])

        elif event_type == "subagent.spawned":
            span = _tracer.start_span(span_name)
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["subagent_invoke"])
            span.set_attribute(TESTAI_ATTR["subagent_id"], str(data.get("subagent_id", "")))
            span.set_attribute(TESTAI_ATTR["subagent_role"], str(data.get("role", "agent")))
            span.set_attribute(TESTAI_ATTR["subagent_depth"], int(data.get("depth", 0)))
            if data.get("parent_subagent_id"):
                span.set_attribute(TESTAI_ATTR["subagent_parent_id"], str(data["parent_subagent_id"]))
            if data.get("model"):
                span.set_attribute(OTEL_ATTR["request_model"], str(data["model"]))
            self._spans[str(data.get("subagent_id", ""))] = span
            self._bump(OTEL_OPERATION["subagent_invoke"])

        elif event_type == "subagent.completed":
            sub_id = str(data.get("subagent_id", ""))
            span = self._spans.pop(sub_id, None)
            if span:
                span.set_attribute(TESTAI_ATTR["subagent_status"], str(data.get("status", "ok")))
                if data.get("duration_sec") is not None:
                    span.set_attribute(TESTAI_ATTR["subagent_duration_s"], float(data["duration_sec"]))
                if data.get("cost_usd") is not None:
                    span.set_attribute(TESTAI_ATTR["subagent_cost_usd"], float(data["cost_usd"]))
                if data.get("status") == "error":
                    span.set_attribute(OTEL_ATTR["error_type"], "subagent_error")
                span.end()

        elif event_type == "board.task.completed":
            span = _tracer.start_span(span_name)
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["kanban_transition"])
            span.set_attribute(TESTAI_ATTR["kanban_task_id"], str(data.get("task_id", "")))
            span.set_attribute(TESTAI_ATTR["kanban_board_id"], str(data.get("board_id", "")))
            span.set_attribute(TESTAI_ATTR["kanban_transition"], "completed")
            if data.get("role"):
                span.set_attribute(TESTAI_ATTR["kanban_task_role"], str(data["role"]))
            span.end()
            self._bump(OTEL_OPERATION["kanban_transition"])

        elif event_type == "board.task.failed":
            span = _tracer.start_span(span_name)
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["kanban_transition"])
            span.set_attribute(TESTAI_ATTR["kanban_task_id"], str(data.get("task_id", "")))
            span.set_attribute(TESTAI_ATTR["kanban_board_id"], str(data.get("board_id", "")))
            span.set_attribute(TESTAI_ATTR["kanban_transition"], "failed")
            if data.get("role"):
                span.set_attribute(TESTAI_ATTR["kanban_task_role"], str(data["role"]))
            if data.get("error"):
                span.set_attribute(TESTAI_ATTR["kanban_error"], str(data["error"])[:200])
                span.set_attribute(OTEL_ATTR["error_type"], "kanban_task_failed")
            span.end()
            self._bump(OTEL_OPERATION["kanban_transition"])

        elif event_type == "board.completed":
            span = _tracer.start_span(span_name)
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["kanban_board"])
            span.set_attribute(TESTAI_ATTR["kanban_board_id"], str(data.get("board_id", "")))
            span.set_attribute(TESTAI_ATTR["kanban_transition"], "completed")
            if data.get("task_count") is not None:
                span.set_attribute(TESTAI_ATTR["kanban_task_count"], int(data["task_count"]))
            if data.get("duration_s") is not None:
                span.set_attribute(TESTAI_ATTR["kanban_duration_s"], float(data["duration_s"]))
            span.end()
            self._bump(OTEL_OPERATION["kanban_board"])

        elif event_type == "board.failed":
            span = _tracer.start_span(span_name)
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["kanban_board"])
            span.set_attribute(TESTAI_ATTR["kanban_board_id"], str(data.get("board_id", "")))
            span.set_attribute(TESTAI_ATTR["kanban_transition"], "failed")
            if data.get("error"):
                span.set_attribute(TESTAI_ATTR["kanban_error"], str(data["error"])[:200])
                span.set_attribute(OTEL_ATTR["error_type"], "kanban_board_failed")
            span.end()
            self._bump(OTEL_OPERATION["kanban_board"])

        elif event_type == "budget.throttled":
            span = _tracer.start_span(span_name)
            span.set_attribute(OTEL_ATTR["operation_name"], OTEL_OPERATION["budget_throttle"])
            span.set_attribute(TESTAI_ATTR["budget_run_id"], str(data.get("run_id", "")))
            if data.get("spent_usd") is not None:
                span.set_attribute(TESTAI_ATTR["budget_spent_usd"], float(data["spent_usd"]))
            if data.get("soft_cap_usd") is not None:
                span.set_attribute(TESTAI_ATTR["budget_soft_cap_usd"], float(data["soft_cap_usd"]))
            if data.get("new_step") is not None:
                span.set_attribute(TESTAI_ATTR["budget_throttle_step"], int(data["new_step"]))
            span.set_attribute(TESTAI_ATTR["budget_hitl_active"], bool(data.get("hitl_active", False)))
            span.set_attribute(TESTAI_ATTR["budget_cheaper_model_active"], bool(data.get("cheaper_model_active", False)))
            span.set_attribute(TESTAI_ATTR["budget_pause_requested"], bool(data.get("pause_requested", False)))
            span.end()
            self._bump(OTEL_OPERATION["budget_throttle"])


def _provider_name(model: str) -> str | None:
    """Map a model name to the OTel-standard provider.name discriminator.

    Returns None when the provider can't be inferred — the OTel spec says
    `gen_ai.provider.name` is Required only when known. We avoid setting
    a wrong value rather than guessing.
    """
    if not model:
        return None
    m = model.lower()
    if m.startswith(("gpt-", "o1", "o3", "o4", "text-embedding-", "dall-e")):
        return "openai"
    if m.startswith(("claude-",)):
        return "anthropic"
    if m.startswith(("gemini-", "palm-")):
        return "gcp.gemini"
    if m.startswith(("deepseek-",)):
        return "deepseek"
    if m.startswith(("kimi-", "moonshot-")):
        return "moonshot"
    if m.startswith(("command-",)):
        return "cohere"
    if m.startswith(("mistral-", "mixtral-")):
        return "mistral_ai"
    if "/" in model:
        # Convention: "provider/model" — use the prefix
        return model.split("/", 1)[0].lower()
    return None
