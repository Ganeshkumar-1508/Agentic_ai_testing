"""Tests for the F04 OTel extension: subagent.invoke, kanban.transition,
kanban_board, and budget.throttle spans.

The OTel SDK may not be installed in the test environment, so
these tests use the same patched-tracer pattern as
``test_trace_otel_semconv.py``: swap ``trace_mod._tracer``
for a MagicMock that records every ``set_attribute`` call.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest


def _capture_span_attributes() -> tuple[object, list[dict], MagicMock, object, object]:
    from harness import trace as trace_mod

    captured: list[dict] = []

    def make_fake_span():
        span = MagicMock()
        span.set_attribute.side_effect = lambda k, v: captured.append({k: v})
        return span

    fake_tracer = MagicMock()
    fake_tracer.start_span.side_effect = lambda name: make_fake_span()

    original_tracer = trace_mod._tracer
    original_available = trace_mod.OTEL_AVAILABLE
    trace_mod._tracer = fake_tracer
    trace_mod.OTEL_AVAILABLE = True
    original = (original_tracer, original_available)
    return trace_mod, captured, fake_tracer, trace_mod, original


def _restore_tracer(trace_mod, original) -> None:
    trace_mod._tracer = original[0]
    trace_mod.OTEL_AVAILABLE = original[1]


def _run(coro):
    return asyncio.run(coro)


class TestSubagentSpans:
    def test_subagent_spawned_creates_span_with_required_attrs(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            data = {
                "subagent_id": "sub-123",
                "role": "test-writer",
                "depth": 1,
                "parent_subagent_id": "sub-root",
                "model": "gpt-4o",
            }
            _run(handler.emit("subagent.spawned", data))
            span_name = fake_tracer.start_span.call_args[0][0]
            assert span_name == "subagent test-writer"
            attr_keys = {a for d in captured for a in d.keys()}
            assert "gen_ai.operation.name" in attr_keys
            assert "testai.subagent.id" in attr_keys
            assert "testai.subagent.role" in attr_keys
            assert "testai.subagent.depth" in attr_keys
            assert "testai.subagent.parent_id" in attr_keys
            assert "gen_ai.request.model" in attr_keys
        finally:
            _restore_tracer(_t, original)

    def test_subagent_completed_ends_span_with_status_attrs(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("subagent.spawned", {"subagent_id": "sub-1", "role": "r", "depth": 0}))
            captured.clear()
            _run(handler.emit("subagent.completed", {
                "subagent_id": "sub-1",
                "status": "ok",
                "duration_sec": 12.4,
                "cost_usd": 0.18,
            }))
            assert "testai.subagent.status" in {a for d in captured for a in d.keys()}
            assert "testai.subagent.duration_s" in {a for d in captured for a in d.keys()}
            assert "testai.subagent.cost_usd" in {a for d in captured for a in d.keys()}
        finally:
            _restore_tracer(_t, original)

    def test_subagent_completed_with_error_sets_error_type(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("subagent.spawned", {"subagent_id": "sub-1", "role": "r", "depth": 0}))
            captured.clear()
            _run(handler.emit("subagent.completed", {
                "subagent_id": "sub-1",
                "status": "error",
            }))
            attr_map = {a: v for d in captured for a, v in d.items()}
            assert attr_map.get("error.type") == "subagent_error"
        finally:
            _restore_tracer(_t, original)


class TestKanbanSpans:
    def test_board_task_completed_emits_kanban_transition(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("board.task.completed", {
                "task_id": "t-1",
                "board_id": "b-1",
                "role": "test-writer",
            }))
            attr_map = {a: v for d in captured for a, v in d.items()}
            assert attr_map.get("gen_ai.operation.name") == "kanban_transition"
            assert attr_map.get("testai.kanban.task_id") == "t-1"
            assert attr_map.get("testai.kanban.board_id") == "b-1"
            assert attr_map.get("testai.kanban.transition") == "completed"
            assert attr_map.get("testai.kanban.task_role") == "test-writer"
        finally:
            _restore_tracer(_t, original)

    def test_board_task_failed_emits_kanban_transition_with_error(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("board.task.failed", {
                "task_id": "t-2",
                "board_id": "b-1",
                "error": "compile failed",
            }))
            attr_map = {a: v for d in captured for a, v in d.items()}
            assert attr_map.get("testai.kanban.transition") == "failed"
            assert attr_map.get("testai.kanban.error") == "compile failed"
            assert attr_map.get("error.type") == "kanban_task_failed"
        finally:
            _restore_tracer(_t, original)

    def test_board_completed_emits_kanban_board(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("board.completed", {
                "board_id": "b-1",
                "task_count": 5,
                "duration_s": 42.7,
            }))
            attr_map = {a: v for d in captured for a, v in d.items()}
            assert attr_map.get("gen_ai.operation.name") == "kanban_board"
            assert attr_map.get("testai.kanban.transition") == "completed"
            assert attr_map.get("testai.kanban.task_count") == 5
            assert attr_map.get("testai.kanban.duration_s") == 42.7
        finally:
            _restore_tracer(_t, original)

    def test_board_failed_sets_error_attrs(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("board.failed", {
                "board_id": "b-1",
                "error": "stuck",
            }))
            attr_map = {a: v for d in captured for a, v in d.items()}
            assert attr_map.get("testai.kanban.transition") == "failed"
            assert attr_map.get("error.type") == "kanban_board_failed"
        finally:
            _restore_tracer(_t, original)


class TestBudgetSpans:
    def test_budget_throttled_emits_span_with_ladder_attrs(self):
        trace_mod, captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("budget.throttled", {
                "run_id": "r-1",
                "spent_usd": 1.5,
                "soft_cap_usd": 1.5,
                "new_step": 1,
                "hitl_active": True,
                "cheaper_model_active": False,
                "pause_requested": False,
            }))
            attr_map = {a: v for d in captured for a, v in d.items()}
            assert attr_map.get("gen_ai.operation.name") == "budget_throttle"
            assert attr_map.get("testai.budget.run_id") == "r-1"
            assert attr_map.get("testai.budget.throttle_step") == 1
            assert attr_map.get("testai.budget.hitl_active") is True
            assert attr_map.get("testai.budget.cheaper_model_active") is False
            assert attr_map.get("testai.budget.pause_requested") is False
        finally:
            _restore_tracer(_t, original)


class TestSpanCounts:
    def test_span_counts_accumulate_per_operation(self):
        trace_mod, _captured, fake_tracer, _t, original = _capture_span_attributes()
        try:
            handler = trace_mod.OTelTraceHandler()
            _run(handler.emit("llm:start", {"id": "1", "model": "gpt-4o"}))
            _run(handler.emit("llm:start", {"id": "2", "model": "gpt-4o"}))
            _run(handler.emit("tool:start", {"id": "3", "name": "bash"}))
            _run(handler.emit("subagent.spawned", {"subagent_id": "s1", "role": "r", "depth": 0}))
            snap = handler.get_counts_snapshot()
            assert snap["counts"]["chat"] == 2
            assert snap["counts"]["execute_tool"] == 1
            assert snap["counts"]["subagent_invoke"] == 1
            assert snap["last_span_at"] is not None
        finally:
            _restore_tracer(_t, original)
