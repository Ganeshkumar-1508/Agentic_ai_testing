"""Tests for sessions page fixes — source mapping, error handling, API responses."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Source mapping tests (mirrors the logic in sessions/page.tsx line 177)
# ---------------------------------------------------------------------------

def _map_source(source: str) -> str:
    """Replicates the fixed source mapping from sessions/page.tsx."""
    if source in ("pipeline", "api"):
        return "pipeline"
    if source == "delegation":
        return "delegation"
    return "chat"


class TestSourceMapping:
    """Verify source mapping handles all backend source values."""

    def test_api_maps_to_pipeline(self):
        assert _map_source("api") == "pipeline"

    def test_pipeline_maps_to_pipeline(self):
        assert _map_source("pipeline") == "pipeline"

    def test_delegation_maps_to_delegation(self):
        assert _map_source("delegation") == "delegation"

    def test_chat_maps_to_chat(self):
        assert _map_source("chat") == "chat"

    def test_unknown_source_falls_back_to_chat(self):
        assert _map_source("unknown") == "chat"

    def test_empty_source_falls_back_to_chat(self):
        assert _map_source("") == "chat"

    def test_none_source_falls_back_to_chat(self):
        assert _map_source(None) == "chat"

    def test_system_source_falls_back_to_chat(self):
        assert _map_source("system") == "chat"

    def test_pr_source_falls_back_to_chat(self):
        assert _map_source("pr") == "chat"


# ---------------------------------------------------------------------------
# SessionRow mapping tests (mirrors the mapping in fetchData)
# ---------------------------------------------------------------------------

class TestSessionRowMapping:
    """Verify raw API session → SessionRow mapping handles all fields."""

    def _map_session(self, raw: dict) -> dict:
        return {
            "id": raw.get("session_id") or raw.get("id"),
            "title": (raw.get("goal") or "")[:80] or raw.get("title", "") or (raw.get("session_id") or raw.get("id") or "")[:12],
            "status": "completed" if raw.get("status") == "ok" else (raw.get("status") or "completed"),
            "source": _map_source(raw.get("source", "")),
            "goal": raw.get("goal", ""),
            "agentRole": raw.get("agent_role", ""),
            "depth": raw.get("depth", 0),
            "model": raw.get("model", ""),
            "cost": raw.get("cost") or raw.get("estimated_cost_usd") or 0,
            "tokens": raw.get("tokens", 0),
            "createdAt": raw.get("created_at") or raw.get("createdAt", ""),
            "endedAt": raw.get("ended_at") or None,
            "parentId": raw.get("parent_session_id") or None,
        }

    def test_handles_api_session_with_all_fields(self):
        raw = {
            "session_id": "api-test-123",
            "status": "running",
            "source": "api",
            "goal": "Write a test",
            "agent_role": "orchestrator",
            "depth": 0,
            "model": "deepseek-v4-flash",
            "cost": 0.5,
            "tokens": 100,
            "created_at": "2026-07-10T12:00:00Z",
        }
        result = self._map_session(raw)
        assert result["id"] == "api-test-123"
        assert result["source"] == "pipeline"
        assert result["status"] == "running"
        assert result["model"] == "deepseek-v4-flash"

    def test_handles_subagent_session(self):
        raw = {
            "session_id": "subagent-sa-abc123",
            "status": "failed",
            "source": "delegation",
        }
        result = self._map_session(raw)
        assert result["source"] == "delegation"
        assert result["status"] == "failed"

    def test_handles_ok_status_as_completed(self):
        raw = {"session_id": "s1", "status": "ok", "source": "chat"}
        result = self._map_session(raw)
        assert result["status"] == "completed"

    def test_handles_missing_session_id(self):
        raw = {"id": "direct-id", "source": "chat"}
        result = self._map_session(raw)
        assert result["id"] == "direct-id"

    def test_handles_missing_cost_uses_estimated_cost(self):
        raw = {"session_id": "s1", "estimated_cost_usd": 1.23, "source": "chat"}
        result = self._map_session(raw)
        assert result["cost"] == 1.23

    def test_handles_missing_cost_and_estimated_cost(self):
        raw = {"session_id": "s1", "source": "chat"}
        result = self._map_session(raw)
        assert result["cost"] == 0

    def test_handles_missing_tokens(self):
        raw = {"session_id": "s1", "source": "chat"}
        result = self._map_session(raw)
        assert result["tokens"] == 0

    def test_handles_ended_at_null(self):
        raw = {"session_id": "s1", "source": "chat", "ended_at": None}
        result = self._map_session(raw)
        assert result["endedAt"] is None

    def test_handles_parent_session_id(self):
        raw = {"session_id": "child", "parent_session_id": "parent-123", "source": "delegation"}
        result = self._map_session(raw)
        assert result["parentId"] == "parent-123"


# ---------------------------------------------------------------------------
# Events filter tests (mirrors the logic in sessions/page.tsx lines 498-500)
# ---------------------------------------------------------------------------

class TestEventTypeClassification:
    """Verify events are correctly classified as user/assistant/tool."""

    @staticmethod
    def _classify(ev: dict) -> str:
        etype = ev.get("type", "")
        payload = ev.get("payload", {}) or {}
        role = payload.get("role", "")
        tool_name = payload.get("tool_name") or payload.get("name")

        if etype in ("user_message", "user") or role == "user":
            return "user"
        if etype in ("assistant_message", "assistant", "llmcall.completed", "LLMCallCompleted") or role == "assistant":
            return "assistant"
        if etype in ("tool.execution.started", "tool.execution.completed", "ToolExecutionStarted", "ToolExecutionCompleted", "tool_call", "tool_result") or tool_name:
            return "tool"
        return "unknown"

    def test_user_message_classified_as_user(self):
        assert self._classify({"type": "user_message"}) == "user"

    def test_assistant_message_classified_as_assistant(self):
        assert self._classify({"type": "assistant_message"}) == "assistant"

    def test_tool_execution_started_classified_as_tool(self):
        assert self._classify({"type": "tool.execution.started"}) == "tool"

    def test_tool_execution_completed_classified_as_tool(self):
        assert self._classify({"type": "tool.execution.completed"}) == "tool"

    def test_llmcall_completed_classified_as_assistant(self):
        assert self._classify({"type": "llmcall.completed"}) == "assistant"

    def test_payload_with_tool_name_classified_as_tool(self):
        assert self._classify({"type": "unknown", "payload": {"tool_name": "bash"}}) == "tool"

    def test_payload_with_role_user_classified_as_user(self):
        assert self._classify({"type": "unknown", "payload": {"role": "user"}}) == "user"

    def test_payload_with_role_assistant_classified_as_assistant(self):
        assert self._classify({"type": "unknown", "payload": {"role": "assistant"}}) == "assistant"

    def test_unknown_event_classified_as_unknown(self):
        assert self._classify({"type": "some.random.event"}) == "unknown"

    def test_events_without_type_or_payload(self):
        assert self._classify({}) == "unknown"
