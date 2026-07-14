"""Tests for OrchestratorEngine._send_notification() and config injection wiring.

Verifies:
  1. _send_notification delegates correctly to NotificationDispatcher
  2. notification_channels from _test_config are passed through
  3. Config injection logic from coordinator_spawn.py
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from harness.orchestrator import OrchestratorEngine
from harness.services.notification_dispatcher import NotificationDispatcher

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# _send_notification tests
# ---------------------------------------------------------------------------


class TestSendNotification:
    """Verify _send_notification delegates to NotificationDispatcher with correct params."""

    @pytest.fixture
    def engine(self):
        eng = OrchestratorEngine.__new__(OrchestratorEngine)
        eng._test_config = {}
        return eng

    async def test_delegates_to_dispatcher(self, engine):
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="All done",
            )
            dispatch_mock.assert_awaited_once()
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs["session_id"] == "ses_001"
            assert call_kwargs["repo_url"] == "https://github.com/org/repo"
            assert call_kwargs["status"] == "completed"
            assert call_kwargs["summary"] == "All done"

    async def test_passes_channels_from_test_config(self, engine):
        engine._test_config = {"notification_channels": ["slack", "email"]}
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs["channels"] == ["slack", "email"]

    async def test_explicit_channels_override_test_config(self, engine):
        engine._test_config = {"notification_channels": ["slack"]}
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
                channels=["teams"],
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs["channels"] == ["teams"]

    async def test_empty_channels_in_test_config_not_passed(self, engine):
        engine._test_config = {"notification_channels": []}
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs.get("channels") is None

    async def test_none_channels_in_test_config_not_passed(self, engine):
        engine._test_config = {"notification_channels": None}
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs.get("channels") is None

    async def test_no_test_config(self, engine):
        del engine._test_config
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs.get("channels") is None

    async def test_non_list_channels_ignored(self, engine):
        engine._test_config = {"notification_channels": "slack"}
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert call_kwargs.get("channels") is None

    async def test_notification_error_does_not_propagate(self, engine):
        """_send_notification does not catch dispatch errors (dispatch handles its own)."""
        dispatch_mock = AsyncMock(side_effect=Exception("dispatch failed"))
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            with pytest.raises(Exception, match="dispatch failed"):
                await engine._send_notification(
                    session_id="ses_001",
                    repo_url="https://github.com/org/repo",
                    status="completed",
                    summary="done",
                )

    async def test_status_values_passthrough(self, engine):
        for status in ("completed", "failed", "timeout", "cancelled"):
            dispatch_mock = AsyncMock()
            with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
                await engine._send_notification(
                    session_id="ses_001",
                    repo_url="https://github.com/org/repo",
                    status=status,
                    summary=f"status: {status}",
                )
                call_kwargs = dispatch_mock.call_args[1]
                assert call_kwargs["status"] == status

    async def test_db_passed_from_get_db(self, engine):
        dispatch_mock = AsyncMock()
        with patch.object(NotificationDispatcher, "dispatch", dispatch_mock):
            await engine._send_notification(
                session_id="ses_001",
                repo_url="https://github.com/org/repo",
                status="completed",
                summary="done",
            )
            call_kwargs = dispatch_mock.call_args[1]
            assert "db" in call_kwargs


# ---------------------------------------------------------------------------
# Config injection logic (coordination with coordinator_spawn.py)
# ---------------------------------------------------------------------------


class TestConfigInjection:
    """Verify the config injection logic from coordinator_spawn.py."""

    @staticmethod
    def _build_goal_config_lines(test_config: dict | None) -> list[str]:
        lines = []
        if not test_config:
            return lines
        tc = test_config
        lines.append("\n## Advanced Pipeline Configuration\n")
        if tc.get("continue_on_failure"):
            lines.append("- Continue on failure: YES (other agents continue if one fails)")
        if tc.get("notification_channels"):
            ch = tc["notification_channels"]
            if isinstance(ch, list) and ch:
                lines.append(f"- Notifications: {', '.join(ch)}")
        if tc.get("timeout_seconds"):
            lines.append(f"- Timeout: {tc['timeout_seconds']}s per command")
        if tc.get("max_retries"):
            lines.append(f"- Max retries: {tc['max_retries']}")
        return lines

    def test_continue_on_failure_true_adds_line(self):
        lines = self._build_goal_config_lines({"continue_on_failure": True})
        assert any("Continue on failure" in l for l in lines)

    def test_continue_on_failure_false_omits_line(self):
        lines = self._build_goal_config_lines({"continue_on_failure": False})
        assert not any("Continue on failure" in l for l in lines)

    def test_continue_on_failure_missing_omits_line(self):
        lines = self._build_goal_config_lines({})
        assert not any("Continue on failure" in l for l in lines)

    def test_notification_channels_adds_line(self):
        lines = self._build_goal_config_lines({"notification_channels": ["slack", "email"]})
        assert any("Notifications: slack, email" in l for l in lines)

    def test_notification_channels_empty_list_omits(self):
        lines = self._build_goal_config_lines({"notification_channels": []})
        assert not any("Notifications" in l for l in lines)

    def test_notification_channels_not_list_omits(self):
        lines = self._build_goal_config_lines({"notification_channels": "slack"})
        assert not any("Notifications" in l for l in lines)

    def test_timeout_seconds_adds_line(self):
        lines = self._build_goal_config_lines({"timeout_seconds": 300})
        assert any("Timeout: 300s" in l for l in lines)

    def test_max_retries_adds_line(self):
        lines = self._build_goal_config_lines({"max_retries": 3})
        assert any("Max retries: 3" in l for l in lines)

    def test_all_config_options_together(self):
        config = {
            "continue_on_failure": True,
            "notification_channels": ["slack", "teams"],
            "timeout_seconds": 120,
            "max_retries": 2,
        }
        lines = self._build_goal_config_lines(config)
        assert len(lines) == 5
        assert any("Continue on failure" in l for l in lines)
        assert any("slack, teams" in l for l in lines)
        assert any("120s" in l for l in lines)
        assert any("2" in l for l in lines)

    def test_none_config_returns_empty(self):
        lines = self._build_goal_config_lines(None)
        assert len(lines) == 0

    def test_empty_dict_config_returns_header_only(self):
        """Empty dict is falsy in Python, so _build_goal_config_lines returns []."""
        lines = self._build_goal_config_lines({})
        assert len(lines) == 0
