"""Tests for the F04 OTel opt-in toggle (``OTEL_ENABLED``)."""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture
def reload_trace():
    """Reload the trace module so ``_init_otel`` re-runs."""
    from harness import trace as trace_mod
    importlib.reload(trace_mod)
    yield trace_mod
    importlib.reload(trace_mod)


class TestOptInToggle:
    def test_default_off(self, monkeypatch, reload_trace):
        monkeypatch.delenv("OTEL_ENABLED", raising=False)
        assert reload_trace._is_otel_enabled() is False
        assert reload_trace.OTEL_AVAILABLE is False

    def test_enabled_true(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "true")
        assert reload_trace._is_otel_enabled() is True

    def test_enabled_1(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "1")
        assert reload_trace._is_otel_enabled() is True

    def test_enabled_yes(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "yes")
        assert reload_trace._is_otel_enabled() is True

    def test_enabled_on(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "on")
        assert reload_trace._is_otel_enabled() is True

    def test_case_insensitive(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "True")
        assert reload_trace._is_otel_enabled() is True
        monkeypatch.setenv("OTEL_ENABLED", "YES")
        assert reload_trace._is_otel_enabled() is True

    def test_explicit_off(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "false")
        assert reload_trace._is_otel_enabled() is False

    def test_unrelated_value_is_off(self, monkeypatch, reload_trace):
        monkeypatch.setenv("OTEL_ENABLED", "maybe")
        assert reload_trace._is_otel_enabled() is False
