"""Credential scanner — detects and redacts secrets in tool output.

Two layers:
  Pre-execution: Blocks dangerous commands that would expose secrets.
  Post-execution: Scans tool output for credential patterns and redacts them.
"""

from __future__ import annotations

import re
from typing import Tuple

# ── Pre-execution blocked patterns ──────────────────────────────────

BLOCKED_COMMAND_PATTERNS: list[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bcat\s+\S*\.env\b'), "Reading .env files exposes secrets"),
    (re.compile(r'\bprintenv\b'), "Printing all env vars exposes secrets"),
    (re.compile(r'\benv\b'), "Printing env vars exposes secrets"),
    (re.compile(r'\bset\b'), "Printing shell variables may expose secrets"),
    (re.compile(r'\bexport\b'), "Exporting variables may leak secrets"),
    (re.compile(r'\baws\s+configure\b'), "AWS credentials should not be read via bash"),
    (re.compile(r'\bgcloud\s+auth\b'), "GCP credentials should not be read via bash"),
    (re.compile(r'\bpasswd\b'), "Password files should not be read"),
    (re.compile(r'\bshadow\b'), "Shadow files should not be read"),
    (re.compile(r'~/\..*credentials'), "Credential files should not be read"),
]

# ── Post-execution credential patterns ─────────────────────────────

CREDENTIAL_PATTERNS: list[Tuple[re.Pattern, str]] = [
    (re.compile(r'(?i)(sk-[a-zA-Z0-9]{20,})'), "sk-..."),           # OpenAI
    (re.compile(r'(?i)(sk-ant-[a-z0-9]{20,})'), "sk-ant-..."),       # Anthropic
    (re.compile(r'(?i)(ghp_[a-zA-Z0-9]{36})'), "ghp_..."),           # GitHub PAT
    (re.compile(r'(?i)(gho_[a-zA-Z0-9]{36})'), "gho_..."),           # GitHub OAuth
    (re.compile(r'(?i)(github_pat_[a-zA-Z0-9_]{36,})'), "github_pat_..."),
    (re.compile(r'(?i)(xox[baprs]-[a-zA-Z0-9-]{24,})'), "xox*-..."), # Slack
    (re.compile(r'(?i)(AKIA[0-9A-Z]{16})'), "AKIA..."),              # AWS AK
    (re.compile(r'(?i)(eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,})'), "JWT..."),
    (re.compile(r'(?i)(-----BEGIN\s+(RSA|EC|OPENSSH|PGP)\s+PRIVATE KEY-----)'), "PRIVATE KEY..."),
    (re.compile(r'(?i)(sqlite:\/\/\/.*\.db)'), "sqlite://..."),
    (re.compile(r'(?i)(postgres(ql)?:\/\/\S+:\S+@)'), "postgres://...:@"),  # DB URLs with passwords
    (re.compile(r'(?i)(redis:\/\/:\S+@)'), "redis://...@"),
    (re.compile(r'(?i)(mongodb(?:\+srv)?:\/\/\S+:\S+@)'), "mongodb://...:@"),
    (re.compile(r'(?i)(sntrys_[a-zA-Z0-9]{20,})'), "sntrys_..."),    # Sentry
    (re.compile(r'(?i)(lin_api_[a-zA-Z0-9]{20,})'), "lin_api_..."),  # Linear
    (re.compile(r'(?i)(hf_[a-zA-Z0-9]{20,})'), "hf_..."),           # HuggingFace
]


# ── Pre‑execution check ─────────────────────────────────────────────


def check_command_safety(command: str) -> str | None:
    """Check a bash command for dangerous patterns.

    Returns an error message if blocked, or None if safe.
    """
    for pattern, reason in BLOCKED_COMMAND_PATTERNS:
        if pattern.search(command):
            return f"[BLOCKED] {reason}: `{command[:120]}`"
    return None


# ── Post‑execution scan ─────────────────────────────────────────────


def redact_credentials(text: str) -> str:
    """Scan text for credential patterns and replace them with [REDACTED].

    Returns the redacted text.
    """
    if not text:
        return text
    for pattern, label in CREDENTIAL_PATTERNS:
        text = pattern.sub(f"[REDACTED {label}]", text)
    return text


def has_credentials(text: str) -> bool:
    """Check if text contains any credential patterns without redacting."""
    for pattern, _ in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            return True
    return False
