"""Tests for BaseEnvironment, ExecResult, ProcessHandle, and helpers."""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from harness.backends.base import (
    BaseEnvironment,
    ExecResult,
    _ThreadedProcessHandle,
    _pipe_stdin,
    _wait_for_process,
)


class TestExecResult:
    def test_defaults(self):
        r = ExecResult()
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.exit_code == 0
        assert r.success
        assert r.output == ""

    def test_success_true_when_exit_code_zero(self):
        r = ExecResult(exit_code=0)
        assert r.success

    def test_success_false_when_exit_code_nonzero(self):
        r = ExecResult(exit_code=1)
        assert not r.success

    def test_output_merges_stdout_and_stderr(self):
        r = ExecResult(stdout="out", stderr="err")
        assert r.output == "outerr"

    def test_duration_ms_default(self):
        r = ExecResult()
        assert r.duration_ms == 0.0


class TestThreadedProcessHandle:
    def test_returns_output_and_exit_code(self):
        def exec_fn():
            return ("hello world", 0)

        handle = _ThreadedProcessHandle(exec_fn)
        handle.wait(timeout=5)
        assert handle.returncode == 0
        assert handle.poll() == 0
        out = handle.stdout.read()
        assert "hello world" in out

    def test_captures_exception_as_error(self):
        def exec_fn():
            raise ValueError("boom")

        handle = _ThreadedProcessHandle(exec_fn)
        handle.wait(timeout=5)
        assert handle.returncode == 1

    def test_kill_calls_cancel_fn(self):
        cancelled = False

        def cancel():
            nonlocal cancelled
            cancelled = True

        def exec_fn():
            return ("ok", 0)

        handle = _ThreadedProcessHandle(exec_fn, cancel_fn=cancel)
        handle.kill()
        assert cancelled

    def test_kill_handles_missing_cancel_fn(self):
        def exec_fn():
            return ("ok", 0)

        handle = _ThreadedProcessHandle(exec_fn)
        handle.kill()

    def test_poll_returns_none_before_completion(self):
        event = threading.Event()

        def exec_fn():
            event.wait(timeout=10)
            return ("done", 0)

        handle = _ThreadedProcessHandle(exec_fn)
        assert handle.poll() is None
        event.set()
        handle.wait(timeout=5)
        assert handle.poll() == 0

    def test_wait_timeout_returns_none(self):
        def exec_fn():
            import time
            time.sleep(30)
            return ("", 0)

        handle = _ThreadedProcessHandle(exec_fn)
        result = handle.wait(timeout=0.1)
        assert result is None or result == 0


class TestPipeStdin:
    def test_pipes_data_to_stdin(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _pipe_stdin(proc, "piped data\n")
        stdout, _ = proc.communicate(timeout=5)
        assert "piped data" in stdout

    def test_handles_broken_pipe(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.buffer.write.side_effect = BrokenPipeError
        _pipe_stdin(proc, "data")


class TestWaitForProcess:
    def test_returns_output_for_fast_command(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('fast')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = _wait_for_process(proc, timeout=10)
        assert result["returncode"] == 0
        assert "fast" in result["output"]

    def test_timeout_returns_124(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = _wait_for_process(proc, timeout=1)
        assert result["returncode"] == 124

    def test_timeout_includes_message(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = _wait_for_process(proc, timeout=1)
        assert "timed out" in result["output"]

    def test_interrupt_returns_130(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        from harness.backends.base import _InterruptEvent
        interrupt = _InterruptEvent()
        interrupt.is_set = lambda: True
        result = _wait_for_process(proc, timeout=30, interrupt=interrupt)
        assert result["returncode"] == 130
        assert "interrupted" in result["output"]

    def test_drains_stdout_before_returning(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('A' * 10000)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = _wait_for_process(proc, timeout=10)
        assert result["returncode"] == 0
        assert len(result["output"].strip()) >= 10000

    def test_returns_nonzero_exit_code(self):
        import subprocess
        import sys
        proc = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(7)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        result = _wait_for_process(proc, timeout=10)
        assert result["returncode"] == 7


class TestBaseEnvironmentABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            BaseEnvironment(session_id="test")

    def test_abstract_methods_raise(self):
        class Incomplete(BaseEnvironment):
            pass

        with pytest.raises(TypeError):
            Incomplete(session_id="test")

    class Minimal(BaseEnvironment):
        def _run_bash(self, cmd_string, **kw):
            import subprocess
            from harness.backends.local import _find_bash
            bash = _find_bash()
            return subprocess.Popen(
                [bash, "-c", cmd_string],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )

        def cleanup(self):
            pass

    def test_minimal_backend_can_execute(self):
        env = self.Minimal(session_id="test-abc", timeout=10)
        result = env.execute("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_execute_uses_custom_timeout(self):
        env = self.Minimal(session_id="test-abc", timeout=10)
        result = env.execute("echo fast", timeout=5)
        assert result.success

    def test_execute_uses_custom_cwd(self):
        env = self.Minimal(session_id="test-abc", timeout=10)
        result = env.execute("pwd", cwd="/")
        assert result.success

    def test_stop_calls_cleanup(self):
        cleaned = False

        class WithCleanup(BaseEnvironment):
            def _run_bash(self, cmd_string, **kw):
                import subprocess
                import sys
                return subprocess.Popen(
                    [sys.executable, "-c", "print('x')"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
            def cleanup(self):
                nonlocal cleaned
                cleaned = True

        env = WithCleanup(session_id="test-stop", timeout=10)
        env.stop()
        assert cleaned

    def test_session_id_stored(self):
        env = self.Minimal(session_id="my-session")
        assert env.session_id == "my-session"

    def test_env_dict_stored(self):
        env = self.Minimal(session_id="test", env={"A": "1"})
        assert env.env["A"] == "1"
