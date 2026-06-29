"""Tests for LocalEnvironment — the subprocess execution backend."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.backends.local import (
    LocalEnvironment,
    _find_bash,
    _resolve_safe_cwd,
)

_IS_WINDOWS = sys.platform.startswith("win")


class TestFindBash:
    def test_find_bash_returns_string(self):
        bash = _find_bash()
        assert isinstance(bash, str)
        assert len(bash) > 0

    def test_find_bash_executable_exists(self):
        bash = _find_bash()
        assert os.path.isfile(bash) or shutil.which(bash)

    def test_find_bash_on_path(self):
        with patch("harness.backends.local.shutil.which", return_value="/usr/bin/bash"):
            with patch("harness.backends.local._IS_WINDOWS", False):
                assert _find_bash() == "/usr/bin/bash"

    def test_find_bash_falls_back_to_shell(self):
        with patch("harness.backends.local.shutil.which", return_value=None):
            with patch("harness.backends.local.os.path.isfile", return_value=False):
                with patch.dict(os.environ, {"SHELL": "/bin/zsh"}, clear=True):
                    with patch("harness.backends.local._IS_WINDOWS", False):
                        assert _find_bash() == "/bin/zsh"

    def test_find_bash_falls_back_to_sh(self):
        with patch("harness.backends.local.shutil.which", return_value=None):
            with patch("harness.backends.local.os.path.isfile", return_value=False):
                with patch.dict(os.environ, {}, clear=True):
                    with patch("harness.backends.local._IS_WINDOWS", False):
                        assert _find_bash() == "/bin/sh"

    def test_find_bash_windows_custom_env(self):
        custom = "C:\\tools\\bash.exe"
        with patch("harness.backends.local._IS_WINDOWS", True):
            with patch.dict(os.environ, {"TESTAI_BASH_PATH": custom}, clear=True):
                with patch("harness.backends.local.os.path.isfile", return_value=True):
                    assert _find_bash() == custom

    def test_find_bash_windows_program_files(self):
        with patch("harness.backends.local._IS_WINDOWS", True):
            with patch("harness.backends.local.shutil.which", return_value=None):
                with patch("harness.backends.local.os.path.isfile", return_value=True):
                    with patch.dict(os.environ, {"ProgramFiles": r"C:\Program Files"}, clear=True):
                        result = _find_bash()
                        assert "bash.exe" in result

    def test_find_bash_windows_raises_when_missing(self):
        with patch("harness.backends.local._IS_WINDOWS", True):
            with patch("harness.backends.local.shutil.which", return_value=None):
                with patch("harness.backends.local.os.path.isfile", return_value=False):
                    with patch.dict(os.environ, {}, clear=True):
                        with pytest.raises(RuntimeError, match="Bash not found"):
                            _find_bash()


class TestResolveSafeCwd:
    def test_existing_dir_returns_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            assert _resolve_safe_cwd(d) == d

    def test_missing_dir_walks_up(self):
        missing = os.path.join(tempfile.gettempdir(), "_testai_nonexistent_", "sub", "dir")
        safe = _resolve_safe_cwd(missing)
        assert os.path.isdir(safe)
        assert safe != missing

    def test_empty_string_returns_cwd(self):
        cwd = os.getcwd()
        assert _resolve_safe_cwd("") == cwd

    def test_root_fallback_to_cwd(self):
        fake = os.path.sep + "_testai_impossible_path_"
        safe = _resolve_safe_cwd(fake)
        assert os.path.isdir(safe) or safe == os.getcwd()


class TestLocalEnvironmentConstruction:
    def test_default_cwd_is_cwd(self):
        env = LocalEnvironment(session_id="test-s1")
        assert env.session_id == "test-s1"
        assert env.cwd == os.getcwd()
        assert env.timeout == 120

    def test_custom_cwd(self):
        cwd = os.getcwd()
        env = LocalEnvironment(session_id="test-s1", cwd=cwd)
        assert env.cwd == cwd

    def test_custom_timeout(self):
        env = LocalEnvironment(session_id="test-s1", timeout=60)
        assert env.timeout == 60

    def test_custom_env(self):
        env = LocalEnvironment(session_id="test-s1", env={"FOO": "bar"})
        assert env.env["FOO"] == "bar"

    def test_expanduser_in_cwd(self):
        home = os.path.expanduser("~")
        env = LocalEnvironment(session_id="test-s1", cwd="~")
        assert env.cwd == home

    def test_session_uuid_is_set(self):
        env = LocalEnvironment(session_id="test-s1")
        assert len(env._session_uuid) == 12


class TestLocalEnvironmentExecute:
    def test_echo(self):
        env = LocalEnvironment(session_id="test-exec", timeout=10)
        result = env.execute("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_exit_code_propagated(self):
        env = LocalEnvironment(session_id="test-exec", timeout=10)
        result = env.execute("exit 42")
        assert not result.success
        assert result.exit_code == 42

    def test_stderr_in_output(self):
        env = LocalEnvironment(session_id="test-exec", timeout=10)
        result = env.execute("echo out && echo err >&2")
        assert result.success
        assert "out" in result.output
        assert "err" in result.output

    def test_cwd_changes_directory(self):
        env = LocalEnvironment(session_id="test-exec", timeout=10)
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "_testai_marker_")
            result = env.execute(f"touch '{marker}' && echo done", cwd=d)
            assert result.success
            assert os.path.isfile(marker)

    def test_env_vars_passed(self):
        marker = "TESTAI_VAR_PRESENT"
        env = LocalEnvironment(session_id="test-exec", timeout=10, env={"TESTAI_VAR": marker})
        result = env.execute("echo $TESTAI_VAR")
        assert result.success
        assert marker in result.stdout

    def test_timeout_kills_long_running(self):
        env = LocalEnvironment(session_id="test-exec", timeout=1)
        result = env.execute("sleep 10")
        assert not result.success
        assert result.exit_code == 124

    def test_stdin_piped(self):
        env = LocalEnvironment(session_id="test-exec", timeout=10)
        result = env.execute("cat", stdin_data="hello stdin\n")
        assert result.success
        assert "hello stdin" in result.stdout

    def test_multiple_commands_in_sequence(self):
        env = LocalEnvironment(session_id="test-exec", timeout=30)
        r1 = env.execute("echo first")
        assert r1.success
        assert "first" in r1.stdout
        r2 = env.execute("echo second")
        assert r2.success
        assert "second" in r2.stdout

    def test_long_output_not_truncated(self):
        env = LocalEnvironment(session_id="test-exec", timeout=30)
        data_len = 10_000
        result = env.execute(f"python -c \"import sys; sys.stdout.write('x' * {data_len})\"")
        assert result.success
        assert len(result.stdout) == data_len

    def test_duration_ms_set(self):
        env = LocalEnvironment(session_id="test-exec", timeout=30)
        result = env.execute("echo fast")
        assert result.success
        assert result.duration_ms > 0


class TestLocalEnvironmentAsync:
    @pytest.mark.asyncio
    async def test_run_returns_completed_process(self):
        env = LocalEnvironment(session_id="test-async", timeout=10)
        proc = await env.run("echo hello")
        assert proc.returncode == 0
        assert "hello" in proc.stdout

    @pytest.mark.asyncio
    async def test_read_file(self):
        env = LocalEnvironment(session_id="test-async", timeout=10)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("file content\n")
            f.flush()
            content = await env.read_file(f.name)
            assert content.strip() == "file content"

    @pytest.mark.asyncio
    async def test_write_file(self):
        env = LocalEnvironment(session_id="test-async", timeout=10)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "test.txt")
            content = "written content"
            await env.write_file(path, content)
            with open(path) as f:
                assert content in f.read()

    @pytest.mark.asyncio
    async def test_file_exists(self):
        env = LocalEnvironment(session_id="test-async", timeout=10)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("x")
            f.flush()
            assert await env.file_exists(f.name)
            assert not await env.file_exists(f.name + ".nonexistent")

    @pytest.mark.asyncio
    async def test_run_timeout(self):
        env = LocalEnvironment(session_id="test-async", timeout=1)
        proc = await env.run("sleep 10", timeout=1)
        assert proc.returncode == 124


class TestLocalEnvironmentCleanup:
    def test_cleanup_does_not_raise(self):
        env = LocalEnvironment(session_id="test-clean")
        env.cleanup()

    def test_stop_calls_cleanup(self):
        env = LocalEnvironment(session_id="test-clean")
        env.stop()

    def test_del_does_not_raise(self):
        env = LocalEnvironment(session_id="test-clean")
        env.__del__()


class TestLocalEnvironmentBashRun:
    def test_run_bash_returns_process_handle(self):
        env = LocalEnvironment(session_id="test-bash", timeout=10)
        proc = env._run_bash("echo hello")
        assert proc is not None
        assert hasattr(proc, "poll")
        assert hasattr(proc, "wait")
        out, err = proc.communicate(timeout=5)
        assert "hello" in out

    def test_run_bash_with_cwd(self):
        env = LocalEnvironment(session_id="test-bash", timeout=10)
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "_testai_marker_")
            env.cwd = d
            proc = env._run_bash(f"touch '{marker}'")
            proc.communicate(timeout=5)
            assert os.path.isfile(marker)

    def test_run_bash_cwd_fallback_on_missing(self):
        env = LocalEnvironment(session_id="test-bash", timeout=10)
        env.cwd = os.path.join(tempfile.gettempdir(), "_testai_missing_")
        proc = env._run_bash("echo ok")
        out, _ = proc.communicate(timeout=5)
        assert "ok" in out
