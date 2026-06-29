"""Tests for DockerEnvironment + backend-aware file/shell tools.

Covers:
- DockerEnvironment construction and container lifecycle
- File/shell tools: host vs backend routing via _backend_factory
- POSIX path normalization for container paths
- Registry wiring for backend_factory injection
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.backends.docker import DockerEnvironment, find_docker
from harness.tools.file_tools import (
    BashTool, EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool,
    _posix_norm, _sandbox_path,
)


class TestDockerEnvironmentConstruction:
    def test_find_docker_returns_none_when_not_available(self):
        with patch("harness.backends.docker.shutil.which", return_value=None):
            with patch("harness.backends.docker.os.path.isfile", return_value=False):
                assert find_docker() is None

    def test_find_docker_uses_env_override(self):
        with patch.dict(os.environ, {"TESTAI_DOCKER_BINARY": "/usr/local/bin/docker"}, clear=True):
            with patch("harness.backends.docker.os.path.isfile", return_value=True):
                with patch("harness.backends.docker.os.access", return_value=True):
                    assert find_docker() == "/usr/local/bin/docker"

    def test_init_raises_when_docker_not_available(self):
        with patch("harness.backends.docker.find_docker", return_value=None):
            with pytest.raises(RuntimeError, match="Docker executable not found"):
                DockerEnvironment(session_id="s1")

    def test_custom_image_passed_to_container(self):
        with patch("harness.backends.docker._ensure_docker_available"):
            with patch("harness.backends.docker.find_docker", return_value="/usr/bin/docker"):
                with patch("harness.backends.docker.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(stdout="container-id-123", returncode=0)
                    env = DockerEnvironment(session_id="s1", image="python:3.12-slim")
                    env._container_id = None
                    run_cmds = [c.args[0] for c in mock_run.call_args_list]
                    run_cmd = next(c for c in run_cmds if "run" in c)
                    assert "python:3.12-slim" in run_cmd

    def test_resource_args_passed_to_docker(self):
        with patch("harness.backends.docker._ensure_docker_available"):
            with patch("harness.backends.docker.find_docker", return_value="/usr/bin/docker"):
                with patch("harness.backends.docker.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(stdout="cid", returncode=0)
                    env = DockerEnvironment(session_id="s1", cpu=2.0, memory_mb=1024)
                    env._container_id = None  # prevent cleanup
                    run_cmds = [c.args[0] for c in mock_run.call_args_list]
                    run_cmd = next(c for c in run_cmds if "run" in c)
                    assert "--cpus" in run_cmd
                    assert "2.0" in run_cmd
                    assert "--memory" in run_cmd
                    assert "1024m" in run_cmd

    def test_container_name_has_testai_prefix(self):
        with patch("harness.backends.docker._ensure_docker_available"):
            with patch("harness.backends.docker.find_docker", return_value="/usr/bin/docker"):
                with patch("harness.backends.docker.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(stdout="cid", returncode=0)
                    env = DockerEnvironment(session_id="s1")
                    env._container_id = None
                    assert env._container_name.startswith("testai-")

    def test_security_args_in_run_cmd(self):
        with patch("harness.backends.docker._ensure_docker_available"):
            with patch("harness.backends.docker.find_docker", return_value="/usr/bin/docker"):
                with patch("harness.backends.docker.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(stdout="cid", returncode=0)
                    env = DockerEnvironment(session_id="s1")
                    env._container_id = None
                    run_cmds = [c.args[0] for c in mock_run.call_args_list]
                    run_cmd = next(c for c in run_cmds if "run" in c)
                    assert "--cap-drop" in run_cmd
                    assert "ALL" in run_cmd
                    assert "--security-opt" in run_cmd
                    assert "no-new-privileges" in str(run_cmd)

    def test_container_cleanup_stops_and_removes(self):
        with patch("harness.backends.docker._ensure_docker_available"):
            with patch("harness.backends.docker.find_docker", return_value="/usr/bin/docker"):
                with patch("harness.backends.docker.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(stdout="cid", returncode=0)
                    env = DockerEnvironment(session_id="s1", persist_across_processes=False)
                    env._container_id = "test-container-id"
                    mock_run.reset_mock()
                    env.cleanup()
                    import time
                    time.sleep(0.05)
                    rm_calls = [c for c in mock_run.call_args_list if "rm" in str(c)]
                    assert len(rm_calls) >= 1


class TestPosixNorm:
    def test_absolute_stays_absolute(self):
        assert _posix_norm("/workspace/foo.py") == "/workspace/foo.py"

    def test_resolves_dotdot(self):
        assert _posix_norm("/workspace/sub/../foo.py") == "/workspace/foo.py"

    def test_resolves_dot(self):
        assert _posix_norm("/workspace/./foo.py") == "/workspace/foo.py"

    def test_relative_preserved(self):
        assert _posix_norm("foo.py") == "foo.py"

    def test_relative_dotdot_preserved(self):
        assert _posix_norm("../foo.py") == "../foo.py"

    def test_root(self):
        assert _posix_norm("/") == "/"

    def test_empty_becomes_dot(self):
        assert _posix_norm("") == "."

    def test_backslash_converted_to_forward(self):
        assert _posix_norm("\\workspace\\foo.py") == "/workspace/foo.py"

    def test_mixed_separators(self):
        assert _posix_norm("/workspace\\sub/foo.py") == "/workspace/sub/foo.py"


class TestSandboxPath:
    def test_absolute_stays_absolute(self):
        assert _sandbox_path("/workspace/foo.py") == "/workspace/foo.py"

    def test_relative_resolved_against_workdir(self):
        assert _sandbox_path("foo.py") == "/workspace/foo.py"

    def test_nested_relative(self):
        assert _sandbox_path("tests/test_foo.py") == "/workspace/tests/test_foo.py"

    def test_custom_workdir(self):
        assert _sandbox_path("foo.py", workdir="/opt") == "/opt/foo.py"

    def test_dotdot_in_absolute(self):
        assert _sandbox_path("/workspace/sub/../foo.py") == "/workspace/foo.py"


class TestHostFallback:
    @pytest.fixture
    def workdir(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            yield d
            os.chdir(cwd)

    @pytest.mark.asyncio
    async def test_write_file_host(self, workdir):
        tool = WriteFileTool()
        r = await tool.run(path="hello.txt", content="hi\n")
        assert r.success
        with open(os.path.join(workdir, "hello.txt")) as f:
            assert f.read() == "hi\n"

    @pytest.mark.asyncio
    async def test_read_file_host(self, workdir):
        with open(os.path.join(workdir, "hi.txt"), "w") as f:
            f.write("line1\nline2\n")
        tool = ReadFileTool()
        r = await tool.run(path="hi.txt")
        assert r.success
        assert "line1" in r.output
        assert "line2" in r.output

    @pytest.mark.asyncio
    async def test_edit_file_host(self, workdir):
        with open(os.path.join(workdir, "code.py"), "w") as f:
            f.write("x = 1\n")
        tool = EditFileTool()
        r = await tool.run(path="code.py", old_text="x = 1", new_text="y = 2")
        assert r.success
        with open(os.path.join(workdir, "code.py")) as f:
            assert f.read() == "y = 2\n"

    @pytest.mark.asyncio
    async def test_list_files_host(self, workdir):
        for name in ("a.py", "b.py", "c.txt"):
            open(os.path.join(workdir, name), "w").close()
        tool = ListFilesTool()
        r = await tool.run(path=workdir, pattern="*.py")
        assert r.success
        files = r.data["files"] if r.data else []
        assert any("a.py" in f for f in files)
        assert any("b.py" in f for f in files)
        assert not any("c.txt" in f for f in files)

    @pytest.mark.asyncio
    async def test_bash_host(self):
        tool = BashTool()
        r = await tool.run(command='python -c "print(42)"')
        assert r.success
        assert "42" in r.output


class TestBackendRouting:
    @pytest.fixture(autouse=True)
    def setup_factory(self):
        from harness.tools.file_tools import set_backend_factory, _deps_ref
        old = dict(_deps_ref)
        _deps_ref.clear()
        yield
        _deps_ref.update(old)

    @pytest.fixture
    def backend(self):
        backend = MagicMock()
        backend.run = AsyncMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        backend.file_exists = AsyncMock(return_value=True)
        backend.read_file = AsyncMock(return_value="")
        return backend

    @pytest.fixture
    def factory(self, backend):
        return MagicMock(return_value=backend)

    @pytest.mark.asyncio
    async def test_bash_routes_through_backend(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        tool = BashTool()
        r = await tool.run(command="ls /workspace", _session_id="s1")
        assert r.success
        backend.run.assert_awaited()

    @pytest.mark.asyncio
    async def test_bash_no_backend_falls_back_to_host(self, backend, factory):
        tool = BashTool()
        r = await tool.run(command='python -c "print(1)"')
        backend.run.assert_not_awaited()
        assert r.success
        assert "1" in r.output

    @pytest.mark.asyncio
    async def test_write_file_routes_through_backend(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        tool = WriteFileTool()
        r = await tool.run(path="/workspace/test.py", content="x = 1\n", _session_id="s1")
        assert r.success
        backend.run.assert_awaited()
        cmd = backend.run.await_args.args[0]
        assert "mkdir -p" in cmd
        assert "base64 -d" in cmd
        assert "/workspace/test.py" in cmd

    @pytest.mark.asyncio
    async def test_read_file_routes_through_backend(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        backend.file_exists.return_value = True
        backend.run = AsyncMock(side_effect=lambda cmd, **kw: MagicMock(
            returncode=0,
            stdout="sed output" if "sed" in cmd else "3" if "wc" in cmd else "",
            stderr="",
        ))
        tool = ReadFileTool()
        r = await tool.run(path="/workspace/test.py", _session_id="s1")
        assert r.success
        assert r.data["total_lines"] == 3

    @pytest.mark.asyncio
    async def test_read_file_backend_not_found(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        backend.file_exists.return_value = False
        tool = ReadFileTool()
        r = await tool.run(path="/workspace/missing.py", _session_id="s1")
        assert not r.success
        assert r.error == "not_found"

    @pytest.mark.asyncio
    async def test_edit_file_routes_through_backend(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        backend.read_file.return_value = "line1\nline2\nline3\n"
        tool = EditFileTool()
        r = await tool.run(
            path="/workspace/test.py", old_text="line2", new_text="LINE2",
            _session_id="s1",
        )
        assert backend.read_file.await_count == 1
        assert backend.run.await_count >= 1
        assert r.success

    @pytest.mark.asyncio
    async def test_edit_file_ambiguous_match(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        backend.read_file.return_value = "x = 1\nx = 1\n"
        tool = EditFileTool()
        r = await tool.run(
            path="/workspace/code.py", old_text="x = 1", new_text="y = 1",
            _session_id="s1",
        )
        assert not r.success
        assert r.error == "ambiguous_match"

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        backend.file_exists.return_value = False
        tool = EditFileTool()
        r = await tool.run(
            path="/workspace/missing.py", old_text="foo", new_text="bar",
            _session_id="s1",
        )
        assert not r.success
        assert r.error == "not_found"

    @pytest.mark.asyncio
    async def test_list_files_routes_through_backend(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        backend.run = AsyncMock(return_value=MagicMock(
            returncode=0,
            stdout="/workspace/a.py\n/workspace/b.py\n",
            stderr="",
        ))
        tool = ListFilesTool()
        r = await tool.run(path="/workspace", _session_id="s1")
        assert r.success
        assert r.data["count"] == 2
        cmd = backend.run.await_args.args[0]
        assert "find" in cmd
        assert "/workspace" in cmd

    @pytest.mark.asyncio
    async def test_relative_path_resolved_against_workspace(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        tool = WriteFileTool()
        await tool.run(path="foo.py", content="x", _session_id="s1")
        cmd = backend.run.await_args.args[0]
        assert "/workspace/foo.py" in cmd

    @pytest.mark.asyncio
    async def test_windows_style_path_normalized(self, backend, factory):
        from harness.tools.file_tools import set_backend_factory
        set_backend_factory(factory)
        tool = WriteFileTool()
        await tool.run(path="\\workspace\\foo.py", content="x", _session_id="s1")
        cmd = backend.run.await_args.args[0]
        assert "\\workspace" not in cmd
        assert "/workspace/foo.py" in cmd

    @pytest.mark.asyncio
    async def test_backend_factory_failure_falls_back_to_host(self):
        tool = BashTool()
        r = await tool.run(command='python -c "print(99)"')
        assert r.success
        assert "99" in r.output


class TestRegistryWiring:
    @pytest.mark.asyncio
    async def test_registry_strips_internal_kwargs(self):
        from harness.tools.registry import registry

        received: dict[str, Any] = {}

        from harness.tools.base import BaseTool, ToolSpec
        class _T(BaseTool):
            name = "capture_strip_tool"
            def spec(self): return ToolSpec(name="capture_strip_tool", description="", input_schema={})
            async def run(self, **kwargs):
                received.update(kwargs)
                from harness.tools.base import ToolResult
                return ToolResult(success=True, output="ok", data={})

        registry.register_tool(_T(), toolset="test")
        try:
            factory = MagicMock(name="backend_factory")
            r = await registry.execute("capture_strip_tool", {"foo": "bar"}, backend_factory=factory)
            assert r.success
            assert "_backend_factory" not in received
            assert "_session_id" not in received
            assert "_tool_call_id" not in received
            assert received.get("foo") == "bar"
        finally:
            registry.deregister("capture_strip_tool")


class TestDescriptions:
    def test_all_5_tools_have_backend_in_description(self):
        for tool_cls in (BashTool, ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool):
            d = tool_cls().spec().description.lower()
            assert "backend" in d or "sandbox" in d, f"{tool_cls.__name__} description should mention backend or sandbox"


class TestRegistration:
    def test_all_5_tools_registered(self):
        from harness.tools.registry import registry
        registry.discover_tools()
        for name in ("read_file", "write_file", "edit_file", "list_files", "bash"):
            assert name in registry._tools, f"{name} not registered"
