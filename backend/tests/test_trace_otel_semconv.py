"""Tests for C7.1: TestAI's OTel spans follow the OpenTelemetry GenAI
semantic conventions so traces flow into Datadog, Honeycomb, Tempo,
Grafana, Langfuse, and LangSmith without per-backend adapters.

Spec: https://opentelemetry.io/docs/specs/semconv/gen-ai/
       (now hosted in open-telemetry/semantic-conventions-genai)

We assert against the *attribute name strings* on the OTel span API,
not against the wire format, because the OTel SDK's export pipeline
is exercised in integration tests, not unit tests.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import harness.trace as trace_mod  # noqa: F401  (used implicitly via the helper's local import)
from harness.trace import (
    OTEL_AVAILABLE,
    OTEL_ATTR,
    TESTAI_ATTR,
    OTEL_OPERATION,
    OTelTraceHandler,
    _provider_name,
)


# If OTel isn't installed in the test env, skip the integration-style
# tests below. The constant-table and provider-inference tests still run.
pytestmark = pytest.mark.skipif(
    not OTEL_AVAILABLE,
    reason="opentelemetry SDK not installed; skipping span-attribute tests",
)


# ---------------------------------------------------------------------------
# OTel_ATTR — the attribute name table itself
# ---------------------------------------------------------------------------


class TestOTelAttrTable:
    """The mapping table MUST use the exact strings from the OTel
    GenAI semconv. Drift breaks compatibility with every observability
    backend."""

    def test_request_model_is_otel_standard(self):
        assert OTEL_ATTR["request_model"] == "gen_ai.request.model"

    def test_input_tokens_is_otel_standard(self):
        assert OTEL_ATTR["usage_input_tokens"] == "gen_ai.usage.input_tokens"

    def test_output_tokens_is_otel_standard(self):
        assert OTEL_ATTR["usage_output_tokens"] == "gen_ai.usage.output_tokens"

    def test_agent_id_is_otel_standard(self):
        assert OTEL_ATTR["agent_id"] == "gen_ai.agent.id"

    def test_tool_name_is_otel_standard(self):
        assert OTEL_ATTR["tool_name"] == "gen_ai.tool.name"

    def test_operation_name_is_otel_standard(self):
        assert OTEL_ATTR["operation_name"] == "gen_ai.operation.name"

    def test_provider_name_is_otel_standard(self):
        assert OTEL_ATTR["provider_name"] == "gen_ai.provider.name"

    def test_error_type_is_otel_standard(self):
        assert OTEL_ATTR["error_type"] == "error.type"

    def test_all_otel_keys_are_under_gen_ai_or_core(self):
        """OTel custom-attribute guidance: stick to the gen_ai.* namespace
        for GenAI spans; everything else goes under testai.* for TestAI-
        specific concerns. No bare llm.* / agent.* / tool.* keys."""
        for key, val in OTEL_ATTR.items():
            assert val.startswith(("gen_ai.", "error.")), (
                f"OTel attr {key!r} = {val!r} must be under gen_ai.* or a core OTel namespace"
            )

    def test_no_legacy_bare_names_in_otel_table(self):
        """The old TestAI names (llm.model, llm.prompt_tokens,
        agent.id, tool.name) must NOT appear in the OTel-standard
        table. They are superseded by the gen_ai.* keys."""
        legacy_names = {
            "llm.model",
            "llm.prompt_tokens",
            "llm.completion_tokens",
            "llm.total_tokens",
            "llm.round",
            "agent.id",
            "agent.parent_id",
            "agent.input",
            "tool.name",
            "tool.success",
            "content_preview",
            "error",  # not "error.type"
        }
        for key, val in OTEL_ATTR.items():
            assert val not in legacy_names, (
                f"OTel attr {key!r} = {val!r} is a pre-C7.1 TestAI name; "
                "use the OTel standard name instead"
            )


class TestTestAIAttrTable:
    """TestAI-specific attributes MUST be reverse-DNS namespaced under
    testai.* per OTel's custom-attribute guidance."""

    def test_all_testai_attrs_use_testai_namespace(self):
        for key, val in TESTAI_ATTR.items():
            assert val.startswith("testai."), (
                f"TestAI attr {key!r} = {val!r} must be under testai.* namespace"
            )

    def test_no_gen_ai_attrs_in_testai_table(self):
        """The OTel-standard attrs (gen_ai.*) live in OTEL_ATTR, not
        duplicated in TESTAI_ATTR."""
        for val in TESTAI_ATTR.values():
            assert not val.startswith("gen_ai."), (
                f"TestAI attr {val!r} uses the OTel namespace; move it to OTEL_ATTR"
            )


class TestOTelOperationTable:
    """OTel GenAI semconv defines specific operation.name values:
    'chat', 'generate_content', 'text_completion', 'embeddings',
    'execute_tool'. We use 'chat' for inference and 'execute_tool'
    for tool spans (the two current TestAI operation types)."""

    def test_chat_operation(self):
        assert OTEL_OPERATION["chat"] == "chat"

    def test_execute_tool_operation(self):
        assert OTEL_OPERATION["execute_tool"] == "execute_tool"

    def test_agent_run_value(self):
        """Agent spans use a TestAI-defined operation.name. It is not
        a standard OTel value, but it is namespaced under testai by
        convention. We document it here for clarity."""
        assert OTEL_OPERATION["agent_run"] == "agent_run"

    def test_agent_round_value(self):
        assert OTEL_OPERATION["agent_round"] == "agent_round"

    def test_agent_reasoning_value(self):
        assert OTEL_OPERATION["agent_reasoning"] == "agent_reasoning"


# ---------------------------------------------------------------------------
# _provider_name — maps model name to OTel gen_ai.provider.name
# ---------------------------------------------------------------------------


class TestProviderName:
    """gen_ai.provider.name is Required on inference spans when known.
    Returning a wrong value is worse than returning None."""

    @pytest.mark.parametrize("model,expected", [
        ("gpt-4o", "openai"),
        ("gpt-4o-mini", "openai"),
        ("gpt-3.5-turbo", "openai"),
        ("o1-preview", "openai"),
        ("o3-mini", "openai"),
        ("text-embedding-3-small", "openai"),
        ("dall-e-3", "openai"),
        ("claude-3-5-sonnet-20241022", "anthropic"),
        ("claude-opus-4-20250514", "anthropic"),
        ("gemini-1.5-pro", "gcp.gemini"),
        ("gemini-2.0-flash", "gcp.gemini"),
        ("palm-2", "gcp.gemini"),
        ("deepseek-v3", "deepseek"),
        ("deepseek-r1", "deepseek"),
        ("kimi-k2", "moonshot"),
        ("moonshot-v1-128k", "moonshot"),
        ("command-r-plus", "cohere"),
        ("mistral-large", "mistral_ai"),
        ("mixtral-8x7b", "mistral_ai"),
    ])
    def test_known_providers(self, model, expected):
        assert _provider_name(model) == expected

    def test_provider_prefix_convention(self):
        """Model names of the form "provider/model" use the prefix."""
        assert _provider_name("openai/gpt-4o") == "openai"
        assert _provider_name("Anthropic/Claude-3") == "anthropic"

    def test_unknown_model_returns_none(self):
        """Unknown model → None (NOT a guessed value)."""
        assert _provider_name("some-future-model") is None

    def test_empty_string_returns_none(self):
        assert _provider_name("") is None

    def test_none_returns_none(self):
        assert _provider_name(None) is None


# ---------------------------------------------------------------------------
# OTelTraceHandler.emit — sets the OTel-standard attribute names
# ---------------------------------------------------------------------------


def _capture_span_attributes() -> tuple[OTelTraceHandler, list[dict], MagicMock, "trace_mod", object]:
    """Patch the global _tracer to capture every set_attribute call,
    so the tests can assert that the OTel-standard keys are used."""
    import harness.trace as trace_mod

    captured: list[dict] = []

    def make_fake_span():
        span = MagicMock()
        span.set_attribute.side_effect = lambda k, v: captured.append({k: v})
        return span

    fake_tracer = MagicMock()
    fake_tracer.start_span.side_effect = lambda name: make_fake_span()

    original_tracer = trace_mod._tracer
    trace_mod._tracer = fake_tracer
    return OTelTraceHandler(), captured, fake_tracer, trace_mod, original_tracer


def _restore_tracer(trace_mod, original):
    trace_mod._tracer = original


class TestOTelLLMSpanAttributes:
    """The LLM inference span (llm:start / llm:end) MUST carry
    gen_ai.operation.name, gen_ai.request.model, and the usage attrs."""

    def test_llm_start_sets_operation_name(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "gpt-4o", "round": 0}))
        finally:
            _restore_tracer(trace_mod, original)
        keys = [list(d.keys())[0] for d in captured]
        assert "gen_ai.operation.name" in keys
        assert {"gen_ai.operation.name": "chat"} in captured

    def test_llm_start_sets_request_model(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "gpt-4o"}))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.request.model": "gpt-4o"} in captured

    def test_llm_start_sets_provider_name_when_known(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "claude-3-5-sonnet"}))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.provider.name": "anthropic"} in captured

    def test_llm_start_omits_provider_when_unknown(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "unknown-model"}))
        finally:
            _restore_tracer(trace_mod, original)
        for d in captured:
            assert "gen_ai.provider.name" not in d

    def test_llm_start_sets_agent_id(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {
                "id": "x1", "model": "gpt-4o", "_scope_agent_id": "agent-42",
            }))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.agent.id": "agent-42"} in captured

    def test_llm_end_sets_input_output_tokens(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "gpt-4o"}))
            captured.clear()
            asyncio.run(handler.emit("llm:end", {
                "id": "x1", "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            }))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.usage.input_tokens": 100} in captured
        assert {"gen_ai.usage.output_tokens": 50} in captured

    def test_llm_span_name_is_chat_model(self):
        """OTel: span name SHOULD be '{gen_ai.operation.name} {gen_ai.request.model}'."""
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "gpt-4o"}))
        finally:
            _restore_tracer(trace_mod, original)
        span_name = fake_tracer.start_span.call_args[0][0]
        assert span_name == "chat gpt-4o"

    def test_no_pre_c71_bare_names_on_llm_span(self):
        """The pre-C7.1 TestAI names (llm.model, llm.prompt_tokens)
        must NOT appear on an LLM span."""
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("llm:start", {"id": "x1", "model": "gpt-4o"}))
            asyncio.run(handler.emit("llm:end", {
                "id": "x1", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
            }))
        finally:
            _restore_tracer(trace_mod, original)
        for d in captured:
            for k in d:
                assert not k.startswith("llm."), f"pre-C7.1 name {k!r} still in use"


class TestOTelToolSpanAttributes:
    """The tool execution span (tool:start / tool:end / tool:error)
    MUST carry gen_ai.operation.name=execute_tool and gen_ai.tool.name."""

    def test_tool_start_sets_operation_name(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("tool:start", {"id": "t1", "name": "bash"}))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.operation.name": "execute_tool"} in captured

    def test_tool_start_sets_tool_name(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("tool:start", {"id": "t1", "name": "bash"}))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.tool.name": "bash"} in captured

    def test_tool_start_sets_agent_id(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("tool:start", {
                "id": "t1", "name": "bash", "_scope_agent_id": "agent-1",
            }))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.agent.id": "agent-1"} in captured

    def test_tool_error_sets_error_type(self):
        """OTel: errors are recorded via the standard error.type attribute."""
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("tool:start", {"id": "t1", "name": "bash"}))
            captured.clear()
            asyncio.run(handler.emit("tool:error", {"id": "t1", "error": "TimeoutError"}))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"error.type": "TimeoutError"} in captured

    def test_tool_span_name_is_execute_tool_name(self):
        """OTel: span name SHOULD be 'execute_tool {gen_ai.tool.name}'."""
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("tool:start", {"id": "t1", "name": "bash"}))
        finally:
            _restore_tracer(trace_mod, original)
        span_name = fake_tracer.start_span.call_args[0][0]
        assert span_name == "execute_tool bash"

    def test_no_pre_c71_bare_names_on_tool_span(self):
        """The pre-C7.1 'tool.name' key should not be the only tool attr
        (it should be the OTel 'gen_ai.tool.name')."""
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("tool:start", {"id": "t1", "name": "bash"}))
        finally:
            _restore_tracer(trace_mod, original)
        for d in captured:
            for k in d:
                # The pre-C7.1 bare "tool.name" key is what we renamed away from
                if k == "tool.name":
                    assert False, "pre-C7.1 bare 'tool.name' is still being set"


class TestOTelAgentSpanAttributes:
    """Agent spans use TestAI-defined operation names; agent.id is OTel standard."""

    def test_agent_start_sets_agent_id(self):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("agent:start", {
                "input": "hello", "_scope_agent_id": "agent-9",
            }))
        finally:
            _restore_tracer(trace_mod, original)
        assert {"gen_ai.agent.id": "agent-9"} in captured

    def test_agent_start_uses_testai_namespace_for_input(self):
        """agent.input is TestAI-specific; lives under testai.* namespace."""
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit("agent:start", {"input": "hello world"}))
        finally:
            _restore_tracer(trace_mod, original)
        for d in captured:
            for k in d:
                if k == "testai.agent.input":
                    assert d[k] == "hello world"
                    return
        assert False, "testai.agent.input not set on agent:start"


class TestNoPreC71NamesAnywhere:
    """The OTel standard names have been adopted. Pre-C7.1 TestAI names
    (llm.model, agent.id, tool.name as bare keys) must not appear."""

    @pytest.mark.parametrize("event_type,data", [
        ("llm:start", {"id": "x", "model": "gpt-4o"}),
        ("llm:end", {"id": "x", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
        ("tool:start", {"id": "x", "name": "bash"}),
        ("tool:end", {"id": "x", "success": True}),
        ("tool:error", {"id": "x", "error": "boom"}),
        ("agent:start", {"input": "hi", "_scope_agent_id": "a1"}),
        ("agent:end", {}),
        ("reasoning", {"content_preview": "thinking..."}),
    ])
    def test_no_bare_pre_c71_names(self, event_type, data):
        handler, captured, fake_tracer, trace_mod, original = _capture_span_attributes()
        try:
            asyncio.run(handler.emit(event_type, data))
        finally:
            _restore_tracer(trace_mod, original)
        bare_keys = {
            "llm.model", "llm.round", "llm.prompt_tokens", "llm.completion_tokens", "llm.total_tokens",
            "agent.id", "agent.parent_id", "agent.input",
            "tool.name", "tool.success",
            "content_preview",
            "error",  # pre-C7.1; C7.1 uses error.type
        }
        for d in captured:
            for k in d:
                assert k not in bare_keys, (
                    f"pre-C7.1 bare attribute {k!r} still being set on {event_type!r}"
                )
