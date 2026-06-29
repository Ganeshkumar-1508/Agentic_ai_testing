"""Tests for foreground_background_guidance — detect long-lived commands."""

from __future__ import annotations

from harness.backends.base import foreground_background_guidance


class TestForegroundBackgroundGuidance:
    def test_server_detected(self):
        msg = foreground_background_guidance("python -m http.server 8080")
        assert msg is not None
        assert "long-lived" in msg

    def test_dev_server_detected(self):
        msg = foreground_background_guidance("npm run dev")
        assert msg is not None

    def test_watch_detected(self):
        msg = foreground_background_guidance("pytest --watch")
        assert msg is not None

    def test_docker_up_detected(self):
        msg = foreground_background_guidance("docker compose up")
        assert msg is not None

    def test_tail_f_detected(self):
        msg = foreground_background_guidance("tail -f /var/log/syslog")
        assert msg is not None

    def test_simple_command_returns_none(self):
        msg = foreground_background_guidance("ls -la")
        assert msg is None

    def test_echo_returns_none(self):
        msg = foreground_background_guidance("echo hello")
        assert msg is None

    def test_git_commit_returns_none(self):
        msg = foreground_background_guidance("git commit -m 'fix'")
        assert msg is None

    def test_python_script_returns_none(self):
        msg = foreground_background_guidance("python script.py --input data.csv")
        assert msg is None

    def test_empty_string(self):
        msg = foreground_background_guidance("")
        assert msg is None

    def test_pip_install_dev_detected(self):
        msg = foreground_background_guidance("pip install -e . && npm run dev")
        assert msg is not None
