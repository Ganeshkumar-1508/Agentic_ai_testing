from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from harness.memory.db_context import get_db

from harness.tools.registry import registry

# ---------------------------------------------------------------------------
# Policy rule — ordered list, last match wins (tool-level permissions)
# ---------------------------------------------------------------------------


@dataclass
class PolicyRule:
    pattern: str
    level: str  # "allow" | "ask" | "deny"


def _parse_pattern(pattern: str) -> tuple[str, str | None]:
    if "(" in pattern and pattern.endswith(")"):
        name, _, rest = pattern.partition("(")
        arg_glob = rest.rstrip(")")
        return name.strip(), arg_glob
    return pattern.strip(), None


def _match_rule(tool: str, args_json: str, rule: PolicyRule) -> bool:
    tool_match, arg_glob = _parse_pattern(rule.pattern)
    if not fnmatch.fnmatch(tool, tool_match):
        return False
    if arg_glob:
        for val in _args_values(args_json):
            if fnmatch.fnmatch(val, arg_glob):
                return True
        return False
    return True


def _args_values(args_json: str) -> list[str]:
    try:
        d = json.loads(args_json)
    except json.JSONDecodeError:
        return []
    result = []
    stack = [d]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for v in item.values():
                stack.append(v)
        elif isinstance(item, (list, tuple)):
            for v in item:
                stack.append(v)
        elif isinstance(item, str):
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Hardline patterns — unconditional block, cannot be bypassed
# (mirrors Hermes HARDLINE_PATTERNS)
# ---------------------------------------------------------------------------

_HARDLINE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\brm\s+(-[^\s]*\s+)*/\s*(-rf|-r\b|--recursive\b)?', re.IGNORECASE), "delete in root path"),
    (re.compile(r'\bmkfs\b', re.IGNORECASE), "format filesystem"),
    (re.compile(r'\bdd\s+.*if=', re.IGNORECASE), "disk copy"),
    (re.compile(r'>\s*/dev/sd', re.IGNORECASE), "write to block device"),
    (re.compile(r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', re.IGNORECASE), "fork bomb"),
    (re.compile(r'\bshutdown\b', re.IGNORECASE), "system shutdown"),
    (re.compile(r'\breboot\b', re.IGNORECASE), "system reboot"),
    (re.compile(r'\bkill\s+-9\s+-1\b', re.IGNORECASE), "kill all processes"),
    (re.compile(r'\bDROP\s+(TABLE|DATABASE)\b', re.IGNORECASE), "SQL DROP"),
    (re.compile(r'\bchmod\s+(-[^\s]*\s+)*(777|666)\b', re.IGNORECASE), "world-writable permissions"),
]


def detect_hardline(command: str) -> tuple[bool, str]:
    for pattern, desc in _HARDLINE_PATTERNS:
        if pattern.search(command):
            return True, desc
    return False, ""


# ---------------------------------------------------------------------------
# Dangerous patterns — require user approval
# (mirrors Hermes DANGEROUS_PATTERNS)
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\brm\s+(-[^\s]*\s+)*r\b', re.IGNORECASE), "recursive delete"),
    (re.compile(r'\bchmod\s+(-[^\s]*\s+)*(777|666|o\+[rwx]*w|a\+[rwx]*w)\b', re.IGNORECASE), "world/other-writable permissions"),
    (re.compile(r'\bchown\s+(-[^\s]*)?R\s+root', re.IGNORECASE), "recursive chown to root"),
    (re.compile(r'\bDELETE\s+FROM\b(?![^\n]*\bWHERE\b)', re.IGNORECASE | re.DOTALL), "SQL DELETE without WHERE"),
    (re.compile(r'\bTRUNCATE\s+(TABLE)?\s*\w', re.IGNORECASE), "SQL TRUNCATE"),
    (re.compile(r'\bsystemctl\s+(-[^\s]+\s+)*(stop|restart|disable|mask)\b', re.IGNORECASE), "stop/restart system service"),
    (re.compile(r'\bpkill\s+-9\b', re.IGNORECASE), "force kill processes"),
    (re.compile(r'\b(curl|wget)\b.*\|\s*(ba)?sh\b', re.IGNORECASE), "pipe remote content to shell"),
    (re.compile(r'\bgit\s+reset\b[^;|&\n]*--hard', re.IGNORECASE), "git reset --hard (destroys uncommitted changes)"),
    (re.compile(r'\bgit\s+push\b.*--force\b', re.IGNORECASE), "git force push (rewrites remote history)"),
    (re.compile(r'\bgit\s+clean\s+-[^\s]*f', re.IGNORECASE), "git clean with force (deletes untracked files)"),
    (re.compile(r'\bbash\b.*\|\s*base64\s*-d\b', re.IGNORECASE), "base64 decode pipe (potential obfuscation)"),
]


def detect_dangerous(command: str) -> tuple[bool, str, str]:
    norm = command.lower().strip()
    for pattern, desc in _DANGEROUS_PATTERNS:
        if pattern.search(norm):
            return True, desc, f"dangerous:{desc}"
    return False, "", ""


# ---------------------------------------------------------------------------
# Smart approval — LLM-assisted risk assessment
# (mirrors Hermes _smart_approve)
# ---------------------------------------------------------------------------


async def smart_approve(command: str, description: str) -> str:
    """Use an LLM to assess command risk. Returns 'approve', 'deny', or 'escalate'."""
    try:
        from harness.llm import ChatMessage
        
        # Use shared LLM router if available
        from harness.api.state import get_llm
        router = get_llm()
        if router is None:
            # Fallback: create fresh router and configure from DB
            from harness.llm import LLMRouter
            router = LLMRouter()
            try:
                db = get_db()
                if db:
                    from harness.memory.settings_store import SettingsStore
                    store = SettingsStore(db)
                    providers = await store.get_all_providers()
                    if providers:
                        router.configure(providers)
            except Exception as e:
                logger.warning("Failed to configure LLM router: %s", e)
        prompt = (
            f"You are a security reviewer for an AI coding agent. "
            f"A command was flagged as potentially dangerous.\n\n"
            f"Command: {command}\n"
            f"Flagged reason: {description}\n\n"
            f"Assess the ACTUAL risk. Many flagged commands are false positives — "
            f"for example, `python -c \"print('hello')\"` is flagged but harmless.\n\n"
            f"Rules:\n"
            f"- APPROVE if clearly safe (benign execution, file operations, git, etc.)\n"
            f"- DENY if genuinely dangerous (system damage, data loss, etc.)\n"
            f"- ESCALATE if uncertain\n\n"
            f"Respond with exactly one word: APPROVE, DENY, or ESCALATE"
        )
        response = await router.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0,
            max_tokens=16,
        )
        answer = (response.content or "").strip().upper()
        if "APPROVE" in answer:
            return "approve"
        elif "DENY" in answer:
            return "deny"
        return "escalate"
    except Exception:
        return "escalate"


# ---------------------------------------------------------------------------
# Session approval state (thread-safe)
# (mirrors Hermes _session_approved, _permanent_approved, _session_yolo)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_session_approved: dict[str, set[str]] = {}
_permanent_approved: set[str] = set()
_session_yolo: set[str] = set()


def approve_session(session_key: str, pattern_key: str) -> None:
    with _lock:
        _session_approved.setdefault(session_key, set()).add(pattern_key)


def approve_permanent(pattern_key: str) -> None:
    with _lock:
        _permanent_approved.add(pattern_key)
    # Persist to database asynchronously
    asyncio.ensure_future(_persist_permanent_allowlist())


async def _persist_permanent_allowlist() -> None:
    """Save the permanent allowlist to the settings store."""
    try:
        from harness.memory.settings_store import SettingsStore

        db = get_db()
        if db is None:
            return
        store = SettingsStore(db)
        with _lock:
            patterns = sorted(_permanent_approved)
        await store.set("permissions.command_allowlist", patterns)
    except Exception:
        pass


def is_approved(session_key: str, pattern_key: str) -> bool:
    with _lock:
        if pattern_key in _permanent_approved:
            return True
        return pattern_key in _session_approved.get(session_key, set())


def enable_yolo(session_key: str) -> None:
    with _lock:
        _session_yolo.add(session_key)


def disable_yolo(session_key: str) -> None:
    with _lock:
        _session_yolo.discard(session_key)


def is_yolo(session_key: str) -> bool:
    with _lock:
        return session_key in _session_yolo


def clear_session(session_key: str) -> None:
    with _lock:
        _session_approved.pop(session_key, None)
        _session_yolo.discard(session_key)


# ---------------------------------------------------------------------------
# Mode-level fallbacks per tool category
# ---------------------------------------------------------------------------

_MODE_DEFAULTS: dict[str, dict[str, str]] = {
    "auto": {"read": "allow", "write": "ask", "analyze": "allow", "delegate": "allow"},
    "ask": {"read": "allow", "write": "deny", "analyze": "deny", "delegate": "deny"},
    "architect": {"read": "allow", "write": "deny", "analyze": "allow", "delegate": "allow"},
    "debug": {"read": "allow", "write": "allow", "analyze": "deny", "delegate": "deny"},
    "custom": {},
}

_TOOL_CATEGORIES: dict[str, str] = {
    "repo_analyzer": "read", "tech_stack_detector": "read",
    "memory": "read", "skills_list": "read", "skill_view": "read",
    "web_search": "read", "web_fetch": "read", "todo": "read", "read_file": "read",
    "test_executor": "write", "bash": "write", "execute_code": "write",
    "coverage_analyzer": "analyze",
    "codegraph_explore": "read", "codegraph_node": "read",
    "codegraph_search": "read", "codegraph_callers": "read",
    "delegate_task": "delegate", "cronjob": "delegate", "skill_manage": "delegate",
}


# ---------------------------------------------------------------------------
# PermissionManager
# ---------------------------------------------------------------------------


class PermissionManager:
    """Three-level permission engine: hardline → dangerous → tool policy.

    1. Hardline — unconditional block, cannot be bypassed (rm -rf /, etc.)
    2. Dangerous — command-level approval (session/permanent/smart)
    3. Tool policy — tool-level allow/ask/deny with glob patterns
    """

    def __init__(
        self,
        mode: str = "auto",
        policy: list[PolicyRule] | None = None,
    ):
        self.mode = mode
        self._policy: list[PolicyRule] | None = list(policy) if policy else None
        self._shield_active: bool = False
        self._force_approval: bool = False
        self._pending_approvals: dict[str, ApprovalWaiter] = {}

    def set_policy(self, policy: list[PolicyRule]) -> None:
        self._policy = list(policy)

    def set_allowed_tools(self, tools: list[str]) -> None:
        rules = [PolicyRule(pattern=t, level="deny") for t in _TOOL_CATEGORIES if t not in tools]
        rules.append(PolicyRule(pattern="*", level="ask"))
        self._policy = rules

    def set_shield(self, active: bool) -> None:
        self._shield_active = active

    def set_force_approval(self, active: bool) -> None:
        self._force_approval = bool(active)

    # -- Tool-level resolution (existing PolicyRule system) --

    def resolve_level(self, tool: str, args: dict[str, Any] | None = None) -> str:
        if self._shield_active:
            return "allow"

        if self._force_approval:
            return "ask"

        args_json = _dump_args(args)

        if self._policy:
            for rule in self._policy:
                if _match_rule(tool, args_json, rule):
                    return rule.level
            return "ask"

        tool_obj = registry.get(tool)
        if tool_obj and tool_obj.default_level:
            return tool_obj.default_level

        category = _TOOL_CATEGORIES.get(tool, "read")
        mode_defaults = _MODE_DEFAULTS.get(self.mode, {})
        return mode_defaults.get(category, "ask")

    async def check(self, tool: str, args: dict[str, Any] | None = None) -> bool:
        return self.resolve_level(tool, args) == "allow"

    # -- Command-level approval (dangerous patterns + smart) --

    async def check_command(
        self,
        command: str,
        session_key: str = "",
        use_smart: bool = False,
    ) -> dict[str, Any]:
        """Check a shell command against all three security levels.

        Returns {"approved": bool, "message": str, ...} matching Hermes format.
        """
        # Level 1: Hardline — unconditional block
        is_hard, hard_desc = detect_hardline(command)
        if is_hard:
            return {
                "approved": False,
                "hardline": True,
                "message": (
                    f"BLOCKED (hardline): {hard_desc}. This command is on the "
                    f"unconditional blocklist and cannot be executed."
                ),
            }

        # YOLO bypass: skip dangerous pattern checks
        if session_key and is_yolo(session_key):
            return {"approved": True, "message": None}

        # Level 2: Dangerous patterns
        is_dangerous, desc, pattern_key = detect_dangerous(command)
        if not is_dangerous:
            return {"approved": True, "message": None}

        # Check session/permanent approval
        if session_key and is_approved(session_key, pattern_key):
            return {"approved": True, "message": None}

        # Level 2.5: Smart approval (LLM-assisted)
        if use_smart:
            verdict = await smart_approve(command, desc)
            if verdict == "approve":
                if session_key:
                    approve_session(session_key, pattern_key)
                return {"approved": True, "message": None, "smart_approved": True}
            if verdict == "deny":
                return {
                    "approved": False,
                    "message": f"BLOCKED by smart approval: {desc}. Do NOT retry.",
                    "smart_denied": True,
                }

        # Return approval_required — caller handles UX (SSE event, etc.)
        return {
            "approved": False,
            "pattern_key": pattern_key,
            "status": "approval_required",
            "command": command,
            "description": desc,
            "message": f"Command flagged as potentially dangerous ({desc}). Approval required.",
        }

    # -- Approval flow (async event-based) --

    def request_approval(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        session_key: str = "",
        pattern_key: str = "",
    ) -> str:
        approval_id = str(uuid.uuid4())
        self._pending_approvals[approval_id] = ApprovalWaiter(
            id=approval_id, tool=tool, args=args or {},
            session_key=session_key, pattern_key=pattern_key,
        )
        asyncio.ensure_future(self._fire_pre_approval(tool, args or {}, approval_id))
        return approval_id

    async def _fire_pre_approval(self, tool: str, args: dict[str, Any], approval_id: str) -> None:
        try:
            from harness.hooks import hooks as _hooks_fn
            await _hooks_fn().invoke("pre_approval_request", tool=tool, args=args, approval_id=approval_id)
        except Exception:
            pass

    async def await_approval(self, approval_id: str, timeout: float = 120.0) -> bool:
        waiter = self._pending_approvals.get(approval_id)
        if not waiter:
            return False
        try:
            await asyncio.wait_for(waiter.event.wait(), timeout=timeout)
            self._pending_approvals.pop(approval_id, None)
            return waiter.approved
        except asyncio.TimeoutError:
            self._pending_approvals.pop(approval_id, None)
            return False

    def resolve_approval(self, approval_id: str, approved: bool, scope: str = "once") -> bool:
        waiter = self._pending_approvals.get(approval_id)
        if not waiter:
            return False
        waiter.approved = approved
        waiter.approval_scope = scope
        waiter.event.set()

        # Store the decision based on scope
        if approved and scope in ("session", "always"):
            session_key = getattr(waiter, "session_key", "")
            if waiter.pattern_key:
                if scope == "always":
                    approve_permanent(waiter.pattern_key)
                if session_key:
                    approve_session(session_key, waiter.pattern_key)

        asyncio.ensure_future(self._fire_post_approval(approval_id, approved, waiter.tool, waiter.args))
        return True

    async def _fire_post_approval(self, approval_id: str, approved: bool, tool: str, args: dict[str, Any]) -> None:
        try:
            from harness.hooks import hooks as _hooks_fn
            await _hooks_fn().invoke("post_approval_response", approval_id=approval_id, approved=approved, tool=tool, args=args)
        except Exception:
            pass

    def approve_command(self, session_key: str, pattern_key: str, permanent: bool = False) -> None:
        if permanent:
            approve_permanent(pattern_key)
        approve_session(session_key, pattern_key)

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [
            {"id": w.id, "tool": w.tool, "args": w.args, "status": "pending"}
            for w in self._pending_approvals.values()
            if not w.event.is_set()
        ]


@dataclass
class ApprovalWaiter:
    id: str
    tool: str
    args: dict[str, Any]
    approved: bool = False
    approval_scope: str = "once"
    session_key: str = ""
    pattern_key: str = ""
    event: asyncio.Event = field(default_factory=asyncio.Event)


def _dump_args(args: dict[str, Any] | None) -> str:
    if not args:
        return "{}"
    return json.dumps(args, sort_keys=True)
