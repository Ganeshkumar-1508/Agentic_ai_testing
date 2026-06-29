"""Hardline command blocklist -- Hermes-inspired pattern matcher.

Blocks known-dangerous commands before they reach execution.
Every harness needs this: Hermes has 48 patterns, we start with the
non-negotiable ones and expand as needed.
"""

import re
from typing import Final

# Commands that are ALWAYS blocked regardless of LLM assessment.
# Matches Hermes approval.py hardline floor -- destructive ops
# that can cause irretrievable data loss or system damage.
_HARDLINE_PATTERNS: Final[list[tuple[str, str, str]]] = [
    (r'rm\s+-rf\s+/\s*', 'rm -rf /', 'Recursive root deletion'),
    (r'dd\s+if=.*\s+of=/dev/', 'dd to block device', 'Direct block device write'),
    (r'mkfs\..*', 'mkfs', 'Filesystem creation -- destructive'),
    (r'format\s+[a-z]:\s*/q', 'format drive', 'Drive format'),
    (r'(>|>>\s*)/dev/(sd[a-z]|nvme|vd)', 'write to block device', 'Direct block device write'),
    (r'chmod\s+-R\s+000\s+/', 'chmod -R 000 /', 'Permission lockout of root'),
    (r'pvcreate|vgcreate|lvcreate', 'LVM operation', 'LVM modification'),
    (r'(curl|wget)\s+.*\s*\|\s*(sh|bash)', 'pipe download to shell', 'Remote code execution via pipe'),
    (r'git\s+push\s+--force\s+origin\s+(main|master)\b', 'git push --force to main/master', 'Force push to primary branch'),
    (r'drop\s+(table|database)\s+', 'DROP TABLE/DATABASE', 'Destructive SQL operation'),
]

# Non-destructive but risky commands that should trigger smart_approval
_RISKY_PATTERNS: Final[list[tuple[str, str, str]]] = [
    (r'rm\s+-rf\s+~', 'rm -rf home', 'Recursive home deletion'),
    (r'kill\s+-9\s+', 'kill -9', 'Force kill process'),
    (r'sudo\s+', 'sudo', 'Elevated privilege command'),
    (r'pip\s+uninstall', 'pip uninstall', 'Package removal'),
    (r'npm\s+uninstall', 'npm uninstall', 'Package removal'),
    (r'git\s+push\s+--force\b(?!.*origin\s+(main|master)\b)', 'git push --force', 'Force push (non-primary branch)'),
    (r'>\s*[^/].*\.(json|yaml|yml|env|conf)\b', 'overwrite config file', 'Config file overwrite'),
]


def check_command(command: str) -> tuple[str, str | None]:
    """Check a command against blocklists.

    Returns (action, reason):
      - ('block', 'reason')  -- hardline match, do not execute
      - ('warn', 'reason')   -- risky, should trigger smart_approval
      - ('allow', None)      -- safe to execute
    """
    cmd_lower = command.lower().strip()
    for pattern, name, reason in _HARDLINE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return ('block', f'{name}: {reason}')
    for pattern, name, reason in _RISKY_PATTERNS:
        if re.search(pattern, cmd_lower):
            return ('warn', f'{name}: {reason}')
    return ('allow', None)
