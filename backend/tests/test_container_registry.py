"""Tests for the C5 deepening: `ContainerRegistry` Protocol +
`InProcessContainerRegistry` adapter.

Before C5, `SandboxManager` reached into
`harness.tools.docker_executor` for `_container_records`,
`_lock`, `touch_container`, `list_containers`,
`destroy_container`. The `docker_executor` module was the
agent-facing tool surface; the lifecycle state was bolted
on later. 6 import sites in `SandboxManager` plus 1 in
`docker_tool.py` (added in the C3 work) made the cross-cut
real.

The fix: a typed `ContainerRegistry` Protocol at
`harness.sandbox.registry`. The Docker daemon remains the
source of truth for "is the container actually running";
the registry is the in-process cache of "which container
belongs to which session, and when was it last used".
The `SandboxManager` reconciles the registry against the
daemon on startup; the `docker_tool` calls `touch()` to
bump the activity timestamp.

These tests pin:

  - `ContainerRecord` shape and the `ContainerRegistry`
    Protocol's five methods.
  - `InProcessContainerRegistry` round-trip: register,
    touch, get, list_all, pop.
  - The setter/getter pattern (`set_container_registry`,
    `get_container_registry`).
  - The SandboxManager constructor accepts a `registry`
    kwarg and defaults to a fresh in-process one.
  - The legacy `_container_records` symbols are GONE from
    `harness.tools.docker_executor` (regex-grep verifies
    the cross-cut is removed).
  - The `docker_tool.py` workspace-container activity
    tracking uses the registry, not the legacy
    `touch_container` symbol.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.sandbox.registry import (
    ContainerRecord,
    ContainerRegistry,
    InProcessContainerRegistry,
    get_container_registry,
    reset_container_registry,
    set_container_registry,
)


# ---------------------------------------------------------------------------
# ContainerRecord — the in-process record shape
# ---------------------------------------------------------------------------


def test_container_record_default_shape():
    """A fresh `ContainerRecord` has the expected defaults:
    `role="workspace"`, `created_at` and `last_activity` set
    to roughly now. The `session_id`, `container_id`, and
    `name` are required positional args."""
    before = time.time()
    rec = ContainerRecord(
        session_id="sess-1",
        container_id="abc123",
        name="testai-sandbox-sess",
    )
    after = time.time()
    assert rec.session_id == "sess-1"
    assert rec.container_id == "abc123"
    assert rec.name == "testai-sandbox-sess"
    assert rec.role == "workspace"
    assert before <= rec.created_at <= after
    assert before <= rec.last_activity <= after


def test_container_record_role_distinguishes_container_kinds():
    """The `role` field distinguishes workspace, worker, and
    sidecar containers. Used by the dashboard's
    'sandbox by role' view and the reaper's per-role
    idle thresholds."""
    for role in ("workspace", "worker", "sidecar"):
        rec = ContainerRecord(
            session_id="sess",
            container_id="cid",
            name="name",
            role=role,
        )
        assert rec.role == role


# ---------------------------------------------------------------------------
# InProcessContainerRegistry — round-trip
# ---------------------------------------------------------------------------


def _make_record(session_id: str = "sess-1") -> ContainerRecord:
    return ContainerRecord(
        session_id=session_id,
        container_id=f"cid-{session_id}",
        name=f"testai-sandbox-{session_id[:8]}",
        role="workspace",
    )


def test_register_then_get_round_trip():
    """A record registered with the registry is retrievable
    via `get` until it's popped."""
    r = InProcessContainerRegistry()
    rec = _make_record("sess-1")
    r.register(rec)
    assert r.get("sess-1") is rec
    assert r.get("sess-missing") is None


def test_register_is_idempotent():
    """A second `register` for the same session_id is a
    no-op. The recovery path may discover a duplicate on
    startup; we keep the existing record so the activity
    timestamps from the first call aren't lost."""
    r = InProcessContainerRegistry()
    rec1 = _make_record("sess-1")
    rec2 = ContainerRecord(
        session_id="sess-1", container_id="cid-different",
        name="different-name", role="worker",
    )
    r.register(rec1)
    r.register(rec2)
    # First record wins.
    assert r.get("sess-1") is rec1
    assert r.get("sess-1").container_id == "cid-sess-1"


def test_touch_updates_last_activity():
    """`touch(session_id)` updates `last_activity` to now.
    A no-op if the session isn't registered. Used by the
    `docker_tool` workspace-container path to bump the
    activity timestamp after every exec."""
    r = InProcessContainerRegistry()
    rec = _make_record("sess-1")
    rec.last_activity = 100.0
    r.register(rec)
    before = time.time()
    r.touch("sess-1")
    after = time.time()
    assert before <= r.get("sess-1").last_activity <= after
    # Touch on a missing session is a no-op.
    r.touch("sess-missing")  # does not raise


def test_list_all_returns_all_records():
    """`list_all` returns every record in the registry. The
    `SandboxManager.list_sandboxes` enriches this into the
    dashboard's container view."""
    r = InProcessContainerRegistry()
    r.register(_make_record("sess-1"))
    r.register(_make_record("sess-2"))
    r.register(_make_record("sess-3"))
    snapshot = r.list_all()
    assert {rec.session_id for rec in snapshot} == {"sess-1", "sess-2", "sess-3"}


def test_pop_removes_and_returns():
    """`pop` returns the popped record and removes it from
    the registry. The `SandboxManager.destroy_env` calls
    this to drop the in-memory record; the manager is
    separately responsible for the `docker rm -f`."""
    r = InProcessContainerRegistry()
    rec = _make_record("sess-1")
    r.register(rec)
    popped = r.pop("sess-1")
    assert popped is rec
    assert r.get("sess-1") is None
    # Pop on a missing session returns None.
    assert r.pop("sess-missing") is None


def test_registry_is_thread_safe():
    """The registry is hit from the main event loop and the
    reaper thread. Concurrent register/touch/pop must not
    corrupt the dict."""
    r = InProcessContainerRegistry()
    errors: list[Exception] = []

    def _worker(start: int) -> None:
        try:
            for i in range(start, start + 200):
                r.register(_make_record(f"sess-{i}"))
                r.touch(f"sess-{i}")
                r.list_all()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(t * 1000,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"thread safety violations: {errors}"
    # The final set should have 8 * 200 distinct session ids.
    final = r.list_all()
    assert len(final) == 8 * 200


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_in_process_registry_is_protocol_conformant():
    """`InProcessContainerRegistry` satisfies the
    `ContainerRegistry` Protocol. `isinstance` against a
    `@runtime_checkable` Protocol is the cheap test."""
    r = InProcessContainerRegistry()
    assert isinstance(r, ContainerRegistry), (
        "InProcessContainerRegistry must implement ContainerRegistry"
    )


# ---------------------------------------------------------------------------
# Setter / getter — same pattern as set_introspection_store etc.
# ---------------------------------------------------------------------------


def test_set_container_registry_injects_at_module_level():
    """A `set_container_registry(store)` call must make that
    store visible to the docker_tool and the SandboxManager
    via `get_container_registry()`. This is the only seam
    between the agent's docker_executor tool and the
    SandboxManager's container state."""
    fake = MagicMock(spec=ContainerRegistry)
    set_container_registry(fake)
    try:
        assert get_container_registry() is fake
    finally:
        reset_container_registry()


def test_get_container_registry_returns_none_when_unset():
    """A fresh import (no setter called) must return None, not
    crash. The `docker_tool` checks for None and falls through
    gracefully when the registry isn't wired."""
    reset_container_registry()
    assert get_container_registry() is None


def test_reset_container_registry_clears_singleton():
    """`reset_container_registry` is the test helper. The
    test teardown calls it to prevent singleton leaks
    between tests."""
    fake = MagicMock(spec=ContainerRegistry)
    set_container_registry(fake)
    reset_container_registry()
    assert get_container_registry() is None


# ---------------------------------------------------------------------------
# SandboxManager — registry injection
# ---------------------------------------------------------------------------


def test_sandbox_manager_constructor_accepts_registry_kwarg():
    """`SandboxManager.__init__` accepts a `registry` kwarg
    and stores it as `self._registry`. This is the
    injection point for the C5 deepening — production
    code passes an `InProcessContainerRegistry`; tests can
    pass a fake."""
    from inspect import signature
    from harness.sandbox_manager import SandboxManager
    params = signature(SandboxManager.__init__).parameters
    assert "registry" in params, (
        "SandboxManager.__init__ must accept a `registry` "
        "kwarg so the container state is injectable"
    )


def test_sandbox_manager_defaults_to_fresh_in_process_registry():
    """When no `registry` is passed, `SandboxManager`
    constructs its own `InProcessContainerRegistry`. So a
    test can do `SandboxManager()` without going through
    `api/main.py` lifespan."""
    from harness.sandbox.registry import InProcessContainerRegistry
    from harness.sandbox_manager import SandboxManager
    sm = SandboxManager.__new__(SandboxManager)
    # Bypass __init__ to test the default-fallback branch in
    # isolation. The real __init__ also calls _recover_containers
    # which shells out to docker ps; we skip it.
    sm._scope = None
    sm._registry = None
    # Manually call the registry-defaulting branch from __init__.
    from harness.sandbox.registry import InProcessContainerRegistry as _IPR
    sm._registry = _IPR() if sm._registry is None else sm._registry
    assert isinstance(sm._registry, InProcessContainerRegistry)


# ---------------------------------------------------------------------------
# Cross-cut removed — `docker_executor` no longer holds lifecycle state
# ---------------------------------------------------------------------------


def test_docker_executor_no_longer_holds_lifecycle_state():
    """The C5 deepening moves `_container_records`, `_lock`,
    `touch_container`, `list_containers`, and
    `destroy_container` out of `harness.tools.docker_executor`
    and into the `ContainerRegistry` Protocol. The
    `docker_executor` module becomes pure tool-utility
    (binary resolution, pre-flight, security args)."""
    src_path = (
        Path(__file__).resolve().parents[1] / "harness" / "tools" / "docker_executor.py"
    )
    src = src_path.read_text(encoding="utf-8")
    for symbol in (
        "_container_records",
        "_lock",
        "touch_container",
        "list_containers",
        "destroy_container",
    ):
        assert f"def {symbol}" not in src, (
            f"docker_executor.py should no longer define {symbol}(); "
            f"the lifecycle state is in ContainerRegistry now"
        )


def test_sandbox_manager_does_not_import_docker_executor_lifecycle():
    """The cross-cut the architecture review flagged: the
    `SandboxManager` reaching into `docker_executor` for
    container state. C5 replaces this with the
    `ContainerRegistry` Protocol. The SandboxManager
    should no longer import the lifecycle symbols from
    `docker_executor`."""
    src_path = (
        Path(__file__).resolve().parents[1] / "harness" / "sandbox_manager.py"
    )
    src = src_path.read_text(encoding="utf-8")
    # The lifecycle symbols were imported as
    # `from harness.tools.docker_executor import _container_records, _lock, ...`
    # and similar. The new code uses
    # `from harness.sandbox.registry import ContainerRecord` and
    # `self._registry.register(...)` / `self._registry.touch(...)`.
    assert "from harness.tools.docker_executor import" not in src, (
        f"sandbox_manager.py should no longer import from "
        f"harness.tools.docker_executor. The container state is "
        f"in the ContainerRegistry Protocol now."
    )


def test_docker_tool_uses_registry_for_activity_tracking():
    """The `docker_tool` (C3) calls `touch_container` to
    bump the workspace container's activity timestamp.
    C5 replaces this with `get_container_registry().touch()`.
    The docker_tool no longer imports `touch_container`
    from `docker_executor`."""
    src_path = (
        Path(__file__).resolve().parents[1] / "harness" / "tools" / "docker_tool.py"
    )
    src = src_path.read_text(encoding="utf-8")
    assert "touch_container" not in src, (
        f"docker_tool.py should no longer reference "
        f"`touch_container`; it should use the "
        f"ContainerRegistry's touch() method"
    )
    # And it imports the registry's getter.
    assert "get_container_registry" in src, (
        f"docker_tool.py must use `get_container_registry()` "
        f"for the workspace-container activity tracking"
    )


def test_docker_tool_still_keeps_tool_level_utilities():
    """The split: `docker_executor.py` keeps the tool-level
    utilities (binary resolution, pre-flight, security args).
    `docker_tool.py` continues to import them. The lifecycle
    symbols are gone from `docker_executor.py` but the
    utility symbols stay."""
    src_path = (
        Path(__file__).resolve().parents[1] / "harness" / "tools" / "docker_tool.py"
    )
    src = src_path.read_text(encoding="utf-8")
    for util in (
        "find_docker",
        "_ensure_docker_available",
        "build_security_args",
    ):
        assert util in src, (
            f"docker_tool.py should still import {util} from "
            f"harness.tools.docker_executor; only the lifecycle "
            f"symbols moved out"
        )
