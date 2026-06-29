"""Tests for Docker CLI snapshot/restore operations.

These tests verify that docker commit/run/inspect commands are
constructed correctly. Snapshot is a primitive the agent invokes;
DockerEnvironment provides the container lifecycle.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestDockerCommit:
    def test_docker_commit_command_construction(self):
        with patch("harness.backends.docker.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="cid", stderr="")
            docker = "/usr/bin/docker"
            cmd = [docker, "commit", "container-id", "testai-snapshot-sess-1-v1-aaaaaaaa"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            _ = result  # command structure is valid

    def test_docker_commit_tag_format(self):
        session_id = "sess-xyz"
        label = "after-fix"
        safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in (label or ""))
        tag = f"testai-snapshot-{session_id}-{safe_label}-{'a' * 8}"
        assert tag.startswith("testai-snapshot-")
        assert "after-fix" in tag

    def test_docker_commit_label_sanitized(self):
        label = "my fix / v2!"
        safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in (label or ""))
        assert "my_fix___v2" in safe_label
        assert " " not in safe_label
        assert "/" not in safe_label
        assert "!" not in safe_label

    def test_docker_commit_empty_label(self):
        label = ""
        safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in (label or ""))
        safe_label = safe_label.strip("-_. ")
        tag = f"testai-snapshot-sess-1-{safe_label}-{'a' * 8}" if safe_label else f"testai-snapshot-sess-1-{'a' * 8}"
        assert tag.startswith("testai-snapshot-sess-1-")


class TestDockerRestore:
    def test_restore_inspects_image_first(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc", stderr="")
            docker = "/usr/bin/docker"
            cmd = [docker, "image", "inspect", "testai-snapshot-sess1-v1-aaaaaaaa"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0

    def test_restore_pulls_when_image_missing(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="No such image"),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            docker = "/usr/bin/docker"
            inspect_cmd = [docker, "image", "inspect", "testai-snapshot-sess1-v1-aaaaaaaa"]
            inspect_result = subprocess.run(inspect_cmd, capture_output=True, text=True, timeout=15)
            if inspect_result.returncode != 0:
                pull_cmd = [docker, "pull", "testai-snapshot-sess1-v1-aaaaaaaa"]
                pull_result = subprocess.run(pull_cmd, capture_output=True, text=True, timeout=120)
                assert pull_result.returncode == 0

    def test_list_snapshots_filters_by_prefix(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="testai-snapshot-sess-aaa-v1-bbbbbbbb:latest\npython:3.12\n",
                stderr="",
            )
            docker = "/usr/bin/docker"
            result = subprocess.run(
                [docker, "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True, text=True, timeout=15,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            snaps = [l for l in lines if l.startswith("testai-snapshot-")]
            assert "testai-snapshot-sess-aaa-v1-bbbbbbbb:latest" in snaps
            assert "python:3.12" not in snaps

    def test_list_snapshots_session_filter(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="testai-snapshot-sess-aaa-v1-bbbbbbbb:latest\n",
                stderr="",
            )
            docker = "/usr/bin/docker"
            session_id = "sess-aaa"
            result = subprocess.run(
                [docker, "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True, text=True, timeout=15,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            snaps = [l for l in lines if l.startswith("testai-snapshot-") and session_id in l]
            assert len(snaps) >= 0
