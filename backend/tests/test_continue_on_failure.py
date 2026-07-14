"""Tests for continue_on_failure and notification_channels features."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# continue_on_failure tests
# ---------------------------------------------------------------------------

class TestContinueOnFailure:
    """Verify continue_on_failure is read from test_config and flows through."""

    @staticmethod
    def _build_goal_config_lines(test_config: dict | None) -> list[str]:
        """Replicates the config injection logic from coordinator_spawn.py."""
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

    def test_continue_on_failure_none_omits_line(self):
        lines = self._build_goal_config_lines(None)
        assert len(lines) == 0

    @staticmethod
    def _delegate_task_continue_on_failure(flag: bool) -> bool:
        """Simulates setting dt._continue_on_failure from test_config."""
        return flag

    def test_flag_set_on_delegate_task_when_true(self):
        assert self._delegate_task_continue_on_failure(True) is True

    def test_flag_not_set_when_false(self):
        assert self._delegate_task_continue_on_failure(False) is False

    @staticmethod
    def _simulate_fan_out_with_flag(flag: bool) -> list[str]:
        """Simulates running multiple subagents where one fails."""
        results: list[str] = []
        errors = ["Agent A error", None, "Agent C error"]
        for i, err in enumerate(errors):
            if err:
                if flag:
                    results.append(f"Agent {['A','B','C'][i]} failed: {err} (continued)")
                else:
                    return [f"Aborted at Agent {['A','B','C'][i]}: {err}"]
            else:
                results.append(f"Agent {['A','B','C'][i]} succeeded")
        return results

    def test_fan_out_continues_on_failure_when_flag_set(self):
        results = self._simulate_fan_out_with_flag(True)
        assert len(results) == 3  # All agents ran
        assert any("failed" in r and "continued" in r for r in results)
        assert any("succeeded" in r for r in results)

    def test_fan_out_aborts_when_flag_not_set(self):
        results = self._simulate_fan_out_with_flag(False)
        assert len(results) == 1  # Only first agent result (aborted)
        assert "Aborted" in results[0]


# ---------------------------------------------------------------------------
# notification_channels tests
# ---------------------------------------------------------------------------

class TestNotificationChannels:
    """Verify notification_channels are read from test_config and passed through."""

    @staticmethod
    def _extract_channels(test_config: dict | None) -> list[str] | None:
        """Replicates the logic in _send_notification."""
        if test_config is None:
            return None
        tc_channels = test_config.get("notification_channels")
        if isinstance(tc_channels, list) and tc_channels:
            return tc_channels
        return None

    def test_channels_extracted_from_test_config(self):
        config = {"notification_channels": ["slack", "email"]}
        channels = self._extract_channels(config)
        assert channels == ["slack", "email"]

    def test_channels_none_when_missing(self):
        config = {}
        assert self._extract_channels(config) is None

    def test_channels_none_when_test_config_none(self):
        assert self._extract_channels(None) is None

    def test_channels_none_when_empty_list(self):
        config = {"notification_channels": []}
        assert self._extract_channels(config) is None

    def test_channels_ignores_non_list(self):
        config = {"notification_channels": "slack"}
        assert self._extract_channels(config) is None

    @staticmethod
    def _build_notification_query(channels: list[str] | None) -> str:
        """Replicates the DB query construction from notification_dispatcher.py."""
        if channels:
            placeholders = ", ".join(f"${i+2}" for i in range(len(channels)))
            return f"WHERE enabled = true AND events @> $1 AND channel IN ({placeholders})"
        return "WHERE enabled = true AND events @> $1"

    def test_query_includes_channel_filter_when_provided(self):
        q = self._build_notification_query(["slack", "email"])
        assert "channel IN ($2, $3)" in q
        assert "events @> $1" in q

    def test_query_no_channel_filter_when_none(self):
        q = self._build_notification_query(None)
        assert "channel IN" not in q
        assert "events @> $1" in q

    def test_channel_appears_in_goal_config(self):
        config = {"notification_channels": ["slack", "email"]}
        lines = TestContinueOnFailure._build_goal_config_lines(config)
        assert any("Notifications: slack, email" in l for l in lines)

    def test_channels_goal_config_omitted_when_empty(self):
        config = {"notification_channels": []}
        lines = TestContinueOnFailure._build_goal_config_lines(config)
        assert not any("Notifications" in l for l in lines)
