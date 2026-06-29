"""Hooks registry (Q11-E — deterministic pre/post-tool-call gates).

A `HookRule` is a *deterministic* gate that runs *before* (or *after*)
every tool call. The agent consults the registry; the registry
returns one of:
  - `{"action": "allow"}`           — proceed
  - `{"action": "block", "reason": "..."}` — refuse the tool call
  - `{"action": "ask", "reason": "..."}`   — surface an approval
                                          modal to the human

Rules are *regex / glob matched*, not LLM-judged. This is the
deliberate design choice from the autonomy roadmap: deterministic
gates are auditable, predictable, and immune to prompt injection.
Reference: `reference/hermes-agent/hermes_cli/builtin_hooks/` is the
hermes pattern; ours is the simplified single-process version.

Persistence: rules are loaded from a JSON file at startup
(``~/.testai/hooks.json``) and edited via the dashboard (or by
hand). The format is intentionally simple — a list of rule
dicts with ``when`` and ``action`` keys.

Example hook file:
    [
      {
        "name": "block-rm-rf",
        "when": {"tool": "bash", "input.command_matches": "rm\\\\s+-rf"},
        "action": "block",
        "reason": "destructive `rm -rf` not allowed without approval"
      },
      {
        "name": "ask-kanban-create-prod",
        "when": {"tool": "kanban_create", "input.board_matches": "prod-.*"},
        "action": "ask",
        "reason": "kanban changes to prod-* require human approval"
      }
    ]

Wiring: `ToolDispatcher._handle_regular_tool` (in
`backend/harness/agent/tool_dispatch.py:361`) calls
`hooks.check_pre(tool_name, args)` before each tool execution.
The returned ``action`` is then enforced.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HookRule:
    """A single pre/post-tool-call rule.

    Attributes:
      name: short identifier (used in audit logs)
      tool: tool name to match (exact match)
      when_input: dict of ``input.<key>`` -> regex pattern. ALL
        patterns must match for the rule to fire. Patterns are
        compiled as case-insensitive regex.
      action: "allow" | "block" | "ask"
      reason: human-readable explanation; surfaced to the LLM (for
        "block") or the dashboard approval modal (for "ask").
    """

    name: str
    tool: str
    when_input: dict[str, str] = field(default_factory=dict)
    action: str = "allow"
    reason: str = ""

    def matches(self, tool_name: str, args: dict[str, Any]) -> bool:
        """True if this rule fires for the given (tool, args)."""
        if self.tool != tool_name:
            return False
        if not self.when_input:
            return True
        for key, pattern in self.when_input.items():
            if not key.startswith("input."):
                continue
            input_key = key[len("input."):]
            value = args.get(input_key, "")
            if not isinstance(value, str):
                value = str(value) if value is not None else ""
            try:
                if not re.search(pattern, value, re.IGNORECASE):
                    return False
            except re.error:
                # Bad regex — fail open (rule doesn't match)
                logger.warning("hook rule %s: bad regex %r", self.name, pattern)
                return False
        return True


class HookRegistry:
    """In-memory list of pre-tool-call rules.

    Single-process (one global registry). Loads rules from a JSON
    file on init; the dashboard editor calls ``add``/``remove``
    to mutate it; ``save()`` writes back to disk.

    Concurrency: the registry is read on every tool call (hot
    path), and rarely written (only on dashboard edits). The
    rules list is replaced atomically (Python's GIL guarantees
    that a list-assignment is atomic) so readers see a consistent
    snapshot.
    """

    def __init__(self, rules: list[HookRule] | None = None) -> None:
        self._rules: list[HookRule] = list(rules or [])

    # ── rule management ───────────────────────────────────────────────

    def add(self, rule: HookRule) -> None:
        # De-dupe by name: replace existing rule with the same name
        self._rules = [r for r in self._rules if r.name != rule.name]
        self._rules.append(rule)

    def remove(self, name: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def all(self) -> list[HookRule]:
        return list(self._rules)

    # ── enforcement ───────────────────────────────────────────────────

    def check_pre(self, tool_name: str, args: dict[str, Any]) -> dict[str, str]:
        """Consult all pre-tool-call rules. Returns the first match's action.

        Returns ``{"action": "allow"}`` if no rule matches. The
        first match wins (insertion order); if two rules conflict,
        the one added earlier takes precedence. This makes the
        semantics predictable: an operator can layer a "block
        everything" rule on top of an earlier "allow specific"
        rule by adding it last, and the more specific rule fires
        first because it was added first.

        For v1 we only consult *pre* rules; *post* rules (run
        after the tool returns) are a follow-up. The structure
        is in place to add them.
        """
        for rule in self._rules:
            try:
                if rule.matches(tool_name, args):
                    logger.info(
                        "hook fired: rule=%s tool=%s action=%s reason=%s",
                        rule.name, tool_name, rule.action, rule.reason,
                    )
                    return {
                        "action": rule.action,
                        "reason": rule.reason,
                        "rule": rule.name,
                    }
            except Exception as exc:
                logger.warning("hook rule %s raised: %s", rule.name, exc)
        return {"action": "allow"}

    # ── persistence ────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Write the current rules to a JSON file (atomic via temp+rename)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "name": r.name,
                "tool": r.tool,
                "when": {"input." + k: v for k, v in r.when_input.items()},
                "action": r.action,
                "reason": r.reason,
            }
            for r in self._rules
        ]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: str | Path) -> "HookRegistry":
        """Load rules from a JSON file. Returns an empty registry
        if the file doesn't exist or is malformed (fail-open;
        operators start with NO rules and add them deliberately).
        """
        path = Path(path)
        if not path.exists():
            return cls([])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("hooks load failed from %s: %s", path, exc)
            return cls([])
        if not isinstance(data, list):
            return cls([])
        rules: list[HookRule] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                when_input = {
                    k[len("input."):]: v
                    for k, v in (entry.get("when") or {}).items()
                    if isinstance(k, str) and k.startswith("input.")
                }
                rules.append(HookRule(
                    name=entry["name"],
                    tool=entry["tool"],
                    when_input=when_input,
                    action=entry.get("action", "allow"),
                    reason=entry.get("reason", ""),
                ))
            except KeyError as exc:
                logger.warning("hooks load: skipping malformed entry (missing %s): %s", exc, entry)
        return cls(rules)


# ── process-global singleton ───────────────────────────────────────

_GLOBAL: HookRegistry | None = None
_GLOBAL_PATH: Path | None = None


def get_hooks() -> HookRegistry:
    """Lazily initialise the process-global hooks registry.

    The default path is ``~/.testai/hooks.json`` (computed via
    ``get_testai_home``). The first call loads; subsequent calls
    return the cached instance.
    """
    global _GLOBAL, _GLOBAL_PATH
    if _GLOBAL is None:
        from harness.testai_constants import get_testai_home
        path = get_testai_home() / "hooks.json"
        _GLOBAL_PATH = path
        _GLOBAL = HookRegistry.load(path)
    return _GLOBAL


def reset_hooks_for_tests() -> None:
    """Drop the cached registry (test helper)."""
    global _GLOBAL
    _GLOBAL = None
