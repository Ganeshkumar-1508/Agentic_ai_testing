"""Environment probe -- Hermes-inspired toolchain state detection.

Auto-detects Python/Node/Go/Rust state at session start and emits a
one-line system prompt annotation when something is off. Zero tokens
when everything is healthy.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


def probe_environment() -> dict[str, Any]:
    """Check toolchain availability and return a status dict.

    Returns a dict with tool names as keys and their status:
      - 'ok': Available and working
      - 'missing': Not installed
      - 'version_mismatch': Installed but version is off
    """
    result: dict[str, Any] = {}
    checks = [
        ("python3", ["python3", "--version"]),
        ("node", ["node", "--version"]),
        ("npm", ["npm", "--version"]),
        ("go", ["go", "version"]),
        ("rustc", ["rustc", "--version"]),
        ("cargo", ["cargo", "--version"]),
        ("git", ["git", "--version"]),
        ("docker", ["docker", "--version"]),
        ("make", ["make", "--version"]),
    ]

    for name, cmd in checks:
        path = shutil.which(name)
        if not path:
            result[name] = "missing"
            continue
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            result[name] = "ok"
        except Exception:
            result[name] = "error"

    return result


def environment_summary(result: dict[str, Any] | None = None) -> str:
    """Return a one-line summary for system prompt injection.
    Empty string when everything is healthy (zero token cost).
    """
    if result is None:
        result = probe_environment()
    missing = [k for k, v in result.items() if v == "missing"]
    if not missing:
        return ""
    return f"Note: {', '.join(missing)} not found in environment."


class EnvironmentProbeTool(BaseTool):
    name = "env_probe"
    description = (
        "Probe the environment for available toolchains (Python, Node, Go, Rust, etc.). "
        "Use this before running commands to check if required tools are installed."
    )

    async def run(self, **kwargs: Any) -> ToolResult:
        result = probe_environment()
        ok = [k for k, v in result.items() if v == "ok"]
        missing = [k for k, v in result.items() if v == "missing"]
        lines = [f"Available: {', '.join(ok)}"]
        if missing:
            lines.append(f"Missing: {', '.join(missing)}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data=result,
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={"type": "object", "properties": {}},
        )


# Register tool at module level
from harness.tools.registry import register as _register  # noqa: E402
_register(EnvironmentProbeTool())
