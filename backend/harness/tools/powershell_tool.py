"""PowerShell tool — cross-platform shell execution with security validation.

Port of OpenClaude's PowerShellTool security patterns (MIT license).
Runs PowerShell on Windows, falls back to bash on macOS/Linux.
Validates commands against known dangerous patterns before execution.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shlex
import subprocess
import sys
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)

# Dangerous PowerShell patterns (port of OpenClaude's powershellSecurity.ts)
DANGEROUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'invoke-expression|iex\b', re.I), "Invoke-Expression executes arbitrary code"),
    (re.compile(r'-e(ncodedcommand)?\b', re.I), "Encoded commands obscure intent"),
    (re.compile(r'invoke-webrequest|iwr\b.*\|.*iex\b', re.I), "Download cradle downloads and executes remote code"),
    (re.compile(r'start-bitstransfer\b', re.I), "BITS transfer downloads files"),
    (re.compile(r'certutil.*-urlcache\b', re.I), "certutil downloads from URLs"),
    (re.compile(r'add-type\b', re.I), "Add-Type compiles and loads .NET code"),
    (re.compile(r'new-object.*-comobject\b', re.I), "COM object instantiation may have execution capabilities"),
    (re.compile(r'start-process.*-verb\s+runas\b', re.I), "Start-Process with RunAs requests elevated privileges"),
    (re.compile(r'register-scheduledtask|schtasks.*/create\b', re.I), "Scheduled task creation (persistence primitive)"),
    (re.compile(r'foreach-object.*-membername\b', re.I), "ForEach-Object -MemberName invokes methods by string name"),
    (re.compile(r'invoke-item\b', re.I), "Invoke-Item opens files with default handler (ShellExecute)"),
    (re.compile(r'invoke-wmimethod|invoke-cimmethod\b', re.I), "WMI/CIM can spawn arbitrary processes"),
]

# Blocked file/directory mutations outside the workspace
BLOCKED_PATH_PATTERNS = [
    re.compile(r'\$env:systemroot|\$env:windir|\\windows\\', re.I),
]


class PowerShellTool(BaseTool):
    name = "powershell"
    default_level = "allow"
    description = (
        "Execute PowerShell commands (Windows) or shell commands (macOS/Linux). "
        "On Windows, runs through PowerShell with security validation. "
        "On macOS/Linux, delegates to bash with the same interface."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell or shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
                    "workdir": {"type": "string", "description": "Working directory (default: current)"},
                },
                "required": ["command"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "").strip()
        timeout = int(kwargs.get("timeout", 30))
        workdir = kwargs.get("workdir", "") or os.getcwd()

        if not command:
            return ToolResult(success=False, output="No command provided", error="missing_command")

        is_windows = platform.system() == "Windows"

        if is_windows:
            # Security validation for PowerShell commands
            violation = self._check_security(command)
            if violation:
                return ToolResult(success=False, output=f"Blocked by security policy: {violation}", error="security_block")

        try:
            if is_windows:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", command],
                    cwd=workdir, capture_output=True, text=True, timeout=timeout,
                )
            else:
                proc = subprocess.run(
                    ["bash", "-c", command],
                    cwd=workdir, capture_output=True, text=True, timeout=timeout,
                )

            output = proc.stdout or ""
            if proc.stderr:
                output += f"\n[stderr]\n{proc.stderr[:2000]}"
            if proc.returncode != 0:
                return ToolResult(success=False, output=output[:10000] or f"Exit code: {proc.returncode}", error="non_zero_exit")

            return ToolResult(success=True, output=output[:10000])

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output=f"Command timed out after {timeout}s", error="timeout")
        except FileNotFoundError:
            return ToolResult(success=False, output="PowerShell not found. Install PowerShell Core (pwsh) for Windows support.", error="not_found")
        except Exception as e:
            return ToolResult(success=False, output=f"Execution failed: {e}", error="execution_error")

    def _check_security(self, command: str) -> str | None:
        """Check a PowerShell command against dangerous patterns.
        Port of OpenClaude's powershellCommandIsSafe() logic."""
        for pattern, message in DANGEROUS_PATTERNS:
            if pattern.search(command):
                return message

        for bp in BLOCKED_PATH_PATTERNS:
            if bp.search(command):
                return "Command targets system-protected paths"

        return None


registry.register(PowerShellTool(), toolset="specialized")
