from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar, NamedTuple


class MountSpec(NamedTuple):
    """A bind mount entry rendered as `-v {source}:{target}:{mode}`."""

    source: str
    target: str
    mode: str = "rw"


def _coerce_env(value) -> tuple[tuple[str, str], ...]:
    if isinstance(value, tuple) and all(
        isinstance(p, tuple)
        and len(p) == 2
        and isinstance(p[0], str)
        and isinstance(p[1], str)
        for p in value
    ):
        return value
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    raise TypeError(
        f"env must be a mapping or a tuple of (key, value) pairs, got {type(value).__name__}"
    )


# ── Sandbox size presets (Daytona pattern) ──────────────────────────

SANDBOX_SIZES: dict[str, dict[str, str]] = {
    "small":  {"cpus": "1.0", "memory": "2g",  "description": "Quick edits, linting"},
    "medium": {"cpus": "2.0", "memory": "4g",  "description": "Default — most tasks"},
    "large":  {"cpus": "4.0", "memory": "8g",  "description": "Heavy builds, test suites"},
    "xlarge": {"cpus": "8.0", "memory": "16g", "description": "ML workloads, large repos"},
}

DEFAULT_SANDBOX_SIZE = "medium"


def apply_size_preset(size: str) -> dict[str, str]:
    """Return CPU/memory limits for a named size preset.

    Returns empty dict for "auto" (use defaults from SandboxScope).
    """
    if size == "auto" or size not in SANDBOX_SIZES:
        return {}
    return SANDBOX_SIZES[size]


@dataclass(frozen=True, slots=True)
class SandboxNetworkConfig:
    """Network isolation config for a sandbox container.

    Three modes (matches Daytona's API):
      - block_all=True: all outbound blocked
      - allow_list: CIDR IP ranges + domain/wildcard allowlist
      - Default: unrestricted

    Format (Daytona-compatible):
      network_allow_list: "208.80.154.232/32,10.0.0.0/24"  (CIDR, max 10)
      domain_allow_list: "github.com,*.pypi.org"             (domains/wildcards, max 10)
    """
    block_all: bool = False
    network_allow_list: str = ""
    domain_allow_list: str = ""


@dataclass(frozen=True, slots=True)
class SandboxScope:
    """Configuration for a single per-session sandbox container.

    A scope captures every knob that `docker run` accepts that affects the
    sandbox environment. The same dataclass is used for the primary session
    container, per-worker bridge containers, and sidecar services — they
    differ only in which fields are overridden.

    Render to `docker run` arguments with `to_run_args`. Override fields with
    `with_overrides` to derive a per-session scope from a baseline (e.g.
    `FULL_ACCESS`).

    Two named profiles are exposed as class-level singletons:

    - `RESTRICTED` (the default): no-new-privileges, every Linux
      capability dropped, non-root user, read-only rootfs. The
      per-session workspace volume and `/tmp` tmpfs stay writable so
      the agent can still run tests and edit its workspace. Aligns
      with Modal's "secure-by-default" sandbox posture and E2B's
      "least-privilege by default" convention.
    - `FULL_ACCESS`: permissive profile (`cap-add=ALL`, root user,
      writable rootfs, default bridge network). Opt-in via
      `SandboxManager(scope=SandboxScope.FULL_ACCESS)`.
    """

    image: str = "nikolaik/python-nodejs:python3.11-nodejs20"
    mounts: tuple[MountSpec, ...] = ()
    memory: str = "4g"
    cpus: str = "2.0"
    pids_limit: int = 512
    cap_add: tuple[str, ...] = ("ALL",)
    cap_drop: tuple[str, ...] = ()
    security_opt: tuple[str, ...] = ()
    network: str = "bridge"
    network_config: "SandboxNetworkConfig" = SandboxNetworkConfig()
    user: str = "0:0"
    workdir: str = "/workspace"
    tmpfs: tuple[tuple[str, str], ...] = (
        ("/tmp", "rw,nosuid,size=512m"),
    )
    read_only_rootfs: bool = False
    env: tuple[tuple[str, str], ...] = ()
    labels: tuple[tuple[str, str], ...] = ()

    FULL_ACCESS: ClassVar["SandboxScope"]
    RESTRICTED: ClassVar["SandboxScope"]

    def __post_init__(self) -> None:
        object.__setattr__(self, "env", _coerce_env(self.env))

    def with_overrides(self, **kwargs) -> "SandboxScope":
        return replace(self, **kwargs)

    def env_dict(self) -> dict[str, str]:
        return dict(self.env)

    def _network_args(self) -> list[str]:
        """Return Docker network args based on the network isolation config.

        Matches Daytona's three-mode API:
          - block_all=True: --network none (no outbound)
          - network_allow_list/domain_allow_list: bridge + iptables rules
          - Default: standard bridge network
        """
        cfg = self.network_config
        if cfg.block_all:
            return ["--network", "none"]
        if cfg.network_allow_list or cfg.domain_allow_list:
            return ["--network", "bridge"]
        return ["--network", self.network]

    def to_run_args(self, container_name: str) -> list[str]:
        """Render this scope as the flag list passed to `docker run`.

        Excludes `image` and the trailing command (`sleep infinity`) — the
        caller supplies those.
        """
        args: list[str] = ["-d", "--name", container_name]
        args.extend(self._network_args())
        for cap in self.cap_add:
            args.extend(["--cap-add", cap])
        for cap in self.cap_drop:
            args.extend(["--cap-drop", cap])
        for opt in self.security_opt:
            args.extend(["--security-opt", opt])
        args.extend(["--pids-limit", str(self.pids_limit)])
        args.extend(["--memory", self.memory])
        args.extend(["--cpus", self.cpus])
        for mount in self.mounts:
            args.extend(["-v", f"{mount.source}:{mount.target}:{mount.mode}"])
        for target, opts in self.tmpfs:
            args.extend(["--tmpfs", f"{target}:{opts}"])
        if self.read_only_rootfs:
            args.append("--read-only")
        if self.user:
            args.extend(["--user", self.user])
        if self.workdir:
            args.extend(["-w", self.workdir])
        for k, v in self.env:
            args.extend(["-e", f"{k}={v}"])
        for k, v in self.labels:
            args.extend(["--label", f"{k}={v}"])
        return args


SandboxScope.FULL_ACCESS = SandboxScope()
SandboxScope.RESTRICTED = SandboxScope(
    cap_add=(),
    cap_drop=("ALL",),
    security_opt=("no-new-privileges:true",),
    user="1000:1000",
    read_only_rootfs=True,
)


__all__ = ["MountSpec", "SandboxScope"]
