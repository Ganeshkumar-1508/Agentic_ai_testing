"""Tests for process_tool — background process lifecycle."""

from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from harness.tools.process_tool import (
    ProcessTool,
    _get,
    _kill,
    _kill_all,
    _list,
    _poll,
    _read_log,
    _spawn,
    _wait,
    _write_stdin,
)


class TestProcessSpawn:
    def test_spawn_creates_process(self):
        session = _spawn(f"{sys.executable} -c \"print('hello')\"")
        assert session.id.startswith("proc_")
        assert session.proc is not None
        session.proc.wait(timeout=10)
        assert session.proc.returncode == 0

    def test_spawn_captures_stdout(self):
        session = _spawn(f"{sys.executable} -c \"print('hello world')\"")
        session.proc.wait(timeout=10)
        _read_log(session.id)
        output = _read_log(session.id)["output"]
        assert "hello world" in output

    def test_spawn_uses_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                session = _spawn(
                    f"{sys.executable} -c \"open('cwd_test.txt','w').close()\"",
                )
                session.proc.wait(timeout=10)
                assert os.path.isfile(os.path.join(d, "cwd_test.txt"))
            finally:
                os.chdir(cwd)

    @pytest.mark.asyncio
    async def test_spawn_returns_session_id(self):
        tool = ProcessTool()
        result = await tool.run(action="spawn", command=f"{sys.executable} -c \"print('x')\"")
        assert result.success
        assert "session_id" in (result.data or {})


class TestProcessPoll:
    def test_poll_running(self):
        session = _spawn(f"{sys.executable} -c \"import time; time.sleep(5)\"")
        try:
            result = _poll(session.id)
            assert result["status"] == "running"
            assert result["running"]
        finally:
            _kill(session.id)

    def test_poll_completed(self):
        session = _spawn(f"{sys.executable} -c \"print('done')\"")
        session.proc.wait(timeout=10)
        result = _poll(session.id)
        assert result["status"] == "completed"
        assert not result["running"]

    def test_poll_not_found(self):
        result = _poll("nonexistent")
        assert result["status"] == "not_found"

    def test_poll_includes_uptime(self):
        session = _spawn(f"{sys.executable} -c \"import time; time.sleep(1)\"")
        import time as _t
        _t.sleep(0.1)
        try:
            result = _poll(session.id)
            assert result["uptime_seconds"] >= 0
        finally:
            _kill(session.id)


class TestProcessWait:
    def test_wait_blocks_until_completion(self):
        session = _spawn(f"{sys.executable} -c \"print('done')\"")
        result = _wait(session.id, timeout=10)
        assert result["status"] == "completed"
        assert result["returncode"] == 0

    def test_wait_timeout(self):
        session = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        try:
            result = _wait(session.id, timeout=0.5)
            assert result["status"] == "timeout"
        finally:
            _kill(session.id)

    def test_wait_not_found(self):
        result = _wait("nonexistent")
        assert result["status"] == "not_found"


class TestProcessLog:
    def test_log_returns_output(self):
        session = _spawn(f"{sys.executable} -c \"print('line1'); print('line2')\"")
        session.proc.wait(timeout=10)
        result = _read_log(session.id)
        assert "line1" in result["output"]
        assert "line2" in result["output"]

    def test_log_tail(self):
        session = _spawn(
            f"{sys.executable} -c \"for i in range(10): print('line' + str(i))\""
        )
        session.proc.wait(timeout=10)
        result = _read_log(session.id, tail=3)
        lines = result["output"].strip().splitlines()
        assert len(lines) <= 3

    def test_log_not_found(self):
        result = _read_log("nonexistent")
        assert result["status"] == "not_found"


class TestProcessKill:
    def test_kill_terminates(self):
        session = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        result = _kill(session.id)
        assert result["status"] == "killed"
        session.proc.wait(timeout=5)
        assert session.proc.returncode is not None

    def test_kill_not_found(self):
        result = _kill("nonexistent")
        assert result["status"] == "not_found"

    def test_kill_all(self):
        s1 = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        s2 = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        count = _kill_all()
        assert count >= 2
        assert _poll(s1.id)["status"] == "completed"
        assert _poll(s2.id)["status"] == "completed"


class TestProcessWriteStdin:
    def test_write_stdin(self):
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; print(sys.stdin.readline())"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )
        from harness.tools.process_tool import ProcessSession
        session = ProcessSession(
            id="write_test", proc=proc, created_at=0,
            stdout_chunks=[], lock=__import__('threading').Lock(),
        )
        from harness.tools.process_tool import _processes, _processes_lock
        with _processes_lock:
            _processes["write_test"] = session
        import time as _t
        _t.sleep(0.2)
        result = _write_stdin("write_test", "hello\n")
        assert result["status"] == "ok"
        session.proc.wait(timeout=5)
        from harness.tools.process_tool import _processes, _processes_lock
        with _processes_lock:
            _processes.pop("write_test", None)

    def test_write_stdin_not_found(self):
        result = _write_stdin("nonexistent", "data")
        assert result["status"] == "not_found"


class TestProcessList:
    def test_list_returns_processes(self):
        _kill_all()
        s1 = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        s2 = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        try:
            result = _list()
            assert result["count"] >= 2
            ids = [p["id"] for p in result["processes"]]
            assert s1.id in ids
            assert s2.id in ids
        finally:
            _kill_all()

    def test_list_running_status(self):
        _kill_all()
        session = _spawn(f"{sys.executable} -c \"import time; time.sleep(30)\"")
        try:
            result = _list()
            proc_info = [p for p in result["processes"] if p["id"] == session.id][0]
            assert proc_info["running"]
        finally:
            _kill_all()


class TestProcessToolActions:
    @pytest.mark.asyncio
    async def test_spawn_action(self):
        tool = ProcessTool()
        result = await tool.run(action="spawn", command=f"{sys.executable} -c \"print('ok')\"")
        assert result.success
        sid = (result.data or {}).get("session_id", "")
        _wait(sid, timeout=10)

    @pytest.mark.asyncio
    async def test_list_action(self):
        tool = ProcessTool()
        result = await tool.run(action="list")
        assert result.success

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        tool = ProcessTool()
        result = await tool.run(action="bogus")
        assert not result.success
        assert "Unknown action" in result.output
