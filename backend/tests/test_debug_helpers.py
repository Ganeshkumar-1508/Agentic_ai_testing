"""Tests for debug_helpers — debug session infrastructure."""

from __future__ import annotations

import json
import os
from pathlib import Path

from harness.tools.debug_helpers import DebugSession


class TestDebugSession:
    def test_disabled_by_default(self):
        session = DebugSession("test_tool", env_var="NONEXISTENT_DEBUG")
        assert not session.active
        info = session.get_session_info()
        assert not info["enabled"]

    def test_enabled_via_env(self):
        os.environ["TEST_DEBUG"] = "true"
        try:
            session = DebugSession("test_tool", env_var="TEST_DEBUG")
            assert session.active
            info = session.get_session_info()
            assert info["enabled"]
            assert info["session_id"] is not None
        finally:
            os.environ.pop("TEST_DEBUG", None)

    def test_log_call_does_nothing_when_disabled(self):
        session = DebugSession("test_tool", env_var="NONEXISTENT")
        session.log_call("test", {"key": "val"})
        assert len(session._calls) == 0

    def test_log_call_records_when_enabled(self):
        os.environ["TEST_DEBUG2"] = "true"
        try:
            session = DebugSession("test_tool2", env_var="TEST_DEBUG2")
            session.log_call("search", {"query": "hello"})
            assert len(session._calls) == 1
            assert session._calls[0]["tool_name"] == "search"
            assert session._calls[0]["query"] == "hello"
        finally:
            os.environ.pop("TEST_DEBUG2", None)

    def test_save_creates_file_when_enabled(self):
        os.environ["TEST_DEBUG3"] = "true"
        try:
            session = DebugSession("test_tool3", env_var="TEST_DEBUG3")
            session.log_call("op", {"result": "ok"})
            session.save()
            log_dir = Path.home() / ".testai" / "logs"
            expected = log_dir / f"test_tool3_debug_{session.session_id}.json"
            assert expected.exists()
            with open(expected) as f:
                data = json.load(f)
            assert data["total_calls"] == 1
            assert data["tool_calls"][0]["tool_name"] == "op"
            expected.unlink(missing_ok=True)
        finally:
            os.environ.pop("TEST_DEBUG3", None)

    def test_get_session_info_returns_path_when_enabled(self):
        os.environ["TEST_DEBUG4"] = "true"
        try:
            session = DebugSession("test_tool4", env_var="TEST_DEBUG4")
            info = session.get_session_info()
            assert info["log_path"] is not None
            assert "test_tool4_debug_" in info["log_path"]
        finally:
            os.environ.pop("TEST_DEBUG4", None)

    def test_get_session_info_disabled(self):
        session = DebugSession("test_tool", env_var="NONEXISTENT")
        info = session.get_session_info()
        assert info["log_path"] is None
        assert info["session_id"] is None
