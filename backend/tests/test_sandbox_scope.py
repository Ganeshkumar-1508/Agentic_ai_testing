"""Tests for harness.sandbox_scope (SandboxScope dataclass + FULL_ACCESS)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import ClassVar

import pytest

from harness.sandbox_scope import MountSpec, SandboxScope


# ---------------------------------------------------------------------------
# SandboxScope.FULL_ACCESS — the canonical "full permissive" profile
# ---------------------------------------------------------------------------


class TestFullAccess:
    def test_full_access_constant_exists(self):
        assert isinstance(SandboxScope.FULL_ACCESS, SandboxScope)

    def test_full_access_cap_add_is_all(self):
        assert SandboxScope.FULL_ACCESS.cap_add == ("ALL",)

    def test_full_access_cap_drop_is_empty(self):
        assert SandboxScope.FULL_ACCESS.cap_drop == ()

    def test_full_security_opt_is_empty(self):
        assert SandboxScope.FULL_ACCESS.security_opt == ()

    def test_full_access_resource_caps_present(self):
        s = SandboxScope.FULL_ACCESS
        assert s.memory == "4g"
        assert s.cpus == "2.0"
        assert s.pids_limit == 512

    def test_full_access_user_is_root(self):
        assert SandboxScope.FULL_ACCESS.user == "0:0"

    def test_full_access_network_is_bridge(self):
        assert SandboxScope.FULL_ACCESS.network == "bridge"

    def test_full_access_workdir_is_workspace(self):
        assert SandboxScope.FULL_ACCESS.workdir == "/workspace"

    def test_full_access_read_only_rootfs_is_false(self):
        assert SandboxScope.FULL_ACCESS.read_only_rootfs is False

    def test_full_access_uses_nikolaik_default_image(self):
        assert "python" in SandboxScope.FULL_ACCESS.image.lower()
        assert "node" in SandboxScope.FULL_ACCESS.image.lower()

    def test_full_access_is_classvar_not_field(self):
        """FULL_ACCESS is a ClassVar — it must not be a dataclass field."""
        from dataclasses import fields
        field_names = {f.name for f in fields(SandboxScope)}
        assert "FULL_ACCESS" not in field_names

    def test_full_access_appears_in_class_dict(self):
        assert "FULL_ACCESS" in SandboxScope.__dict__


# ---------------------------------------------------------------------------
# SandboxScope.RESTRICTED — the default restricted profile (C4.2)
# ---------------------------------------------------------------------------


class TestRestricted:
    """The RESTRICTED profile aligns TestAI with the industry
    default-restricted convention (Modal, E2B, Daytona): no new
    privileges, all Linux capabilities dropped, non-root user,
    read-only rootfs."""

    def test_restricted_constant_exists(self):
        assert isinstance(SandboxScope.RESTRICTED, SandboxScope)

    def test_restricted_cap_add_is_empty(self):
        """RESTRICTED adds no capabilities back after dropping ALL."""
        assert SandboxScope.RESTRICTED.cap_add == ()

    def test_restricted_cap_drop_is_all(self):
        assert SandboxScope.RESTRICTED.cap_drop == ("ALL",)

    def test_restricted_no_new_privileges(self):
        assert "no-new-privileges:true" in SandboxScope.RESTRICTED.security_opt

    def test_restricted_user_is_non_root(self):
        """Non-root UID:GID — Modal/E2B convention."""
        user = SandboxScope.RESTRICTED.user
        assert user != "0:0"
        assert ":" in user
        # Both UID and GID must be non-zero
        uid, gid = user.split(":")
        assert uid != "0"
        assert gid != "0"

    def test_restricted_rootfs_is_read_only(self):
        assert SandboxScope.RESTRICTED.read_only_rootfs is True

    def test_restricted_is_classvar_not_field(self):
        """RESTRICTED is a ClassVar — it must not be a dataclass field."""
        from dataclasses import fields
        field_names = {f.name for f in fields(SandboxScope)}
        assert "RESTRICTED" not in field_names

    def test_restricted_appears_in_class_dict(self):
        assert "RESTRICTED" in SandboxScope.__dict__

    def test_restricted_keeps_per_session_subnet(self):
        """RESTRICTED preserves the per-session bridge network so
        inter-container communication (orchestrator <-> sidecar,
        sibling workers) still works. This is a TestAI architectural
        detail, not a deviation from the restricted-by-default
        principle — the network is internal, not public internet."""
        assert SandboxScope.RESTRICTED.network == "bridge"

    def test_restricted_resource_caps_present(self):
        """Resource caps are inherited from the default dataclass — same as FULL_ACCESS."""
        s = SandboxScope.RESTRICTED
        assert s.memory == "4g"
        assert s.cpus == "2.0"
        assert s.pids_limit == 512

    def test_restricted_workdir_is_workspace(self):
        assert SandboxScope.RESTRICTED.workdir == "/workspace"

    def test_restricted_uses_nikolaik_default_image(self):
        assert "python" in SandboxScope.RESTRICTED.image.lower()
        assert "node" in SandboxScope.RESTRICTED.image.lower()

    def test_restricted_to_run_args_emits_drop_and_security_opt(self):
        """The rendered `docker run` args must show the restricted posture:
        --cap-drop ALL, --security-opt no-new-privileges:true, --read-only,
        --user 1000:1000, and NO --cap-add flags."""
        args = SandboxScope.RESTRICTED.to_run_args("test-c")
        assert "--cap-drop" in args
        assert args[args.index("--cap-drop") + 1] == "ALL"
        assert "--security-opt" in args
        assert "no-new-privileges:true" in args
        assert "--read-only" in args
        assert "--user" in args
        assert args[args.index("--user") + 1] == "1000:1000"
        # No --cap-add flags are emitted because cap_add is empty
        assert "--cap-add" not in args

    def test_restricted_to_run_args_keeps_tmpfs_and_workdir(self):
        """Even though the rootfs is read-only, the workspace volume
        (added by the manager) and the /tmp tmpfs stay writable so the
        agent can still run tests and edit its workspace."""
        args = SandboxScope.RESTRICTED.to_run_args("test-c")
        assert "--tmpfs" in args
        assert "/tmp:rw,nosuid,size=512m" in args
        assert "-w" in args
        assert args[args.index("-w") + 1] == "/workspace"

    def test_restricted_is_distinct_from_full_access(self):
        """RESTRICTED and FULL_ACCESS are intentionally different singletons
        with the same base image but different security posture."""
        assert SandboxScope.RESTRICTED is not SandboxScope.FULL_ACCESS
        assert SandboxScope.RESTRICTED.cap_add != SandboxScope.FULL_ACCESS.cap_add
        assert SandboxScope.RESTRICTED.user != SandboxScope.FULL_ACCESS.user
        assert SandboxScope.RESTRICTED.read_only_rootfs != SandboxScope.FULL_ACCESS.read_only_rootfs


# ---------------------------------------------------------------------------
# SandboxScope — immutability (frozen=True)
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_frozen_blocks_field_assignment(self):
        s = SandboxScope()
        with pytest.raises(FrozenInstanceError):
            s.image = "changed"

    def test_frozen_blocks_cap_add_mutation(self):
        s = SandboxScope()
        with pytest.raises(FrozenInstanceError):
            s.cap_add = ()

    def test_hashable(self):
        # Hashable because all fields are immutable (tuple/frozenset/str/int/bool).
        s = SandboxScope()
        assert hash(s) is not None

    def test_equal_scopes_have_equal_hashes(self):
        a = SandboxScope()
        b = SandboxScope()
        assert a == b
        assert hash(a) == hash(b)

    def test_set_of_scopes(self):
        # Frozen + hashable → usable in sets
        s = {SandboxScope(), SandboxScope(), SandboxScope(memory="8g")}
        assert len(s) == 2


# ---------------------------------------------------------------------------
# SandboxScope.with_overrides — derive a new instance
# ---------------------------------------------------------------------------


class TestWithOverrides:
    def test_override_single_field(self):
        s = SandboxScope().with_overrides(memory="8g")
        assert s.memory == "8g"
        assert s.cap_add == ("ALL",)  # unchanged

    def test_override_preserves_original(self):
        orig = SandboxScope()
        s2 = orig.with_overrides(memory="8g")
        assert orig.memory == "4g"
        assert s2.memory == "8g"

    def test_override_mounts(self):
        m = MountSpec("/host/ws", "/workspace", "rw")
        s = SandboxScope().with_overrides(mounts=(m,))
        assert s.mounts == (m,)

    def test_override_network(self):
        s = SandboxScope().with_overrides(network="my-net")
        assert s.network == "my-net"

    def test_override_returns_sandboxscope(self):
        s = SandboxScope().with_overrides(memory="16g")
        assert isinstance(s, SandboxScope)

    def test_override_unknown_field_raises(self):
        with pytest.raises(TypeError):
            SandboxScope().with_overrides(unknown_field="x")


# ---------------------------------------------------------------------------
# SandboxScope — env coercion
# ---------------------------------------------------------------------------


class TestEnvCoercion:
    def test_env_default_is_empty(self):
        assert SandboxScope().env == ()

    def test_env_from_dict(self):
        s = SandboxScope().with_overrides(env={"FOO": "bar", "BAZ": "qux"})
        assert dict(s.env) == {"FOO": "bar", "BAZ": "qux"}

    def test_env_from_tuple_of_pairs(self):
        s = SandboxScope().with_overrides(env=(("FOO", "bar"),))
        assert dict(s.env) == {"FOO": "bar"}

    def test_env_rejects_list(self):
        with pytest.raises(TypeError, match="env must be"):
            SandboxScope().with_overrides(env=[("FOO", "bar")])

    def test_env_rejects_int(self):
        with pytest.raises(TypeError, match="env must be"):
            SandboxScope().with_overrides(env=42)

    def test_env_dict_helper(self):
        s = SandboxScope().with_overrides(env={"A": "1"})
        assert s.env_dict() == {"A": "1"}

    def test_env_empty_dict_helper(self):
        assert SandboxScope().env_dict() == {}


# ---------------------------------------------------------------------------
# SandboxScope.to_run_args — render to docker run args
# ---------------------------------------------------------------------------


class TestToRunArgs:
    def test_basic_args_present(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "-d" in args
        assert "--name" in args
        assert "test-c" in args
        assert "--network" in args
        assert "bridge" in args

    def test_cap_add_all_present(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "--cap-add" in args
        idx = args.index("--cap-add")
        assert args[idx + 1] == "ALL"

    def test_no_cap_drop_in_full_access(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "--cap-drop" not in args

    def test_resource_caps_present(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        for flag, val in [("--pids-limit", "512"), ("--memory", "4g"), ("--cpus", "2.0")]:
            assert flag in args
            assert args[args.index(flag) + 1] == val

    def test_user_root(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "--user" in args
        assert args[args.index("--user") + 1] == "0:0"

    def test_workdir_workspace(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "-w" in args
        assert args[args.index("-w") + 1] == "/workspace"

    def test_tmpfs_present(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "--tmpfs" in args
        idx = args.index("--tmpfs")
        assert args[idx + 1] == "/tmp:rw,nosuid,size=512m"

    def test_no_read_only_flag(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "--read-only" not in args

    def test_no_security_opt(self):
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "--security-opt" not in args

    def test_mounts_render_as_v_flags(self):
        m = MountSpec("/host/ws", "/workspace", "rw")
        s = SandboxScope().with_overrides(mounts=(m,))
        args = s.to_run_args("test-c")
        assert "-v" in args
        idx = args.index("-v")
        assert args[idx + 1] == "/host/ws:/workspace:rw"

    def test_read_only_rootfs_emits_flag(self):
        s = SandboxScope().with_overrides(read_only_rootfs=True)
        args = s.to_run_args("test-c")
        assert "--read-only" in args

    def test_cap_drop_emits_flag(self):
        s = SandboxScope().with_overrides(cap_drop=("MKNOD",))
        args = s.to_run_args("test-c")
        assert "--cap-drop" in args
        assert "MKNOD" in args

    def test_security_opt_emits_flag(self):
        s = SandboxScope().with_overrides(security_opt=("seccomp=unconfined",))
        args = s.to_run_args("test-c")
        assert "--security-opt" in args
        assert "seccomp=unconfined" in args

    def test_env_emits_e_flags(self):
        s = SandboxScope().with_overrides(env={"FOO": "bar", "BAZ": "qux"})
        args = s.to_run_args("test-c")
        assert "-e" in args
        # Order matches the sorted env tuple
        assert "BAZ=qux" in args
        assert "FOO=bar" in args

    def test_image_not_in_args(self):
        # Image and command are appended by the caller, not by to_run_args.
        args = SandboxScope.FULL_ACCESS.to_run_args("test-c")
        assert "nikolaik" not in " ".join(args)
        assert "sleep" not in args

    def test_container_name_in_args(self):
        args = SandboxScope().to_run_args("my-specific-name-123")
        assert "my-specific-name-123" in args


# ---------------------------------------------------------------------------
# MountSpec — simple value object
# ---------------------------------------------------------------------------


class TestMountSpec:
    def test_default_mode_is_rw(self):
        m = MountSpec("/host", "/container")
        assert m.mode == "rw"

    def test_explicit_mode(self):
        m = MountSpec("/host", "/container", "ro")
        assert m.mode == "ro"

    def test_namedtuple_unpacking(self):
        m = MountSpec("/host", "/container", "rw")
        src, tgt, mode = m
        assert src == "/host"
        assert tgt == "/container"
        assert mode == "rw"

    def test_equality(self):
        assert MountSpec("/a", "/b") == MountSpec("/a", "/b")
        assert MountSpec("/a", "/b") != MountSpec("/a", "/c")
