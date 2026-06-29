"""Glob-based permission rules (Claude Code pattern).

Supports allow/ask/deny rules with glob patterns for tool names and arguments.
Pattern matching follows Claude Code's permission rule syntax.

Examples:
    "bash(git diff *)"           — Allow git diff but not other bash commands
    "read_file(./secrets/**)"    — Deny reading secrets
    "write_file(./src/**/*.py)"  — Allow writing Python files in src/
    "*"                          — Deny everything (catch-all)
    "mcp__github__*"             — Deny all GitHub MCP tools
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any


def matches_pattern(tool_name: str, args: dict[str, Any], pattern: str) -> bool:
    """Check if a tool call matches a permission pattern.
    
    Pattern syntax (Claude Code compatible):
        tool_name                    — Exact tool name match
        tool_name(arg_pattern)       — Tool name + argument pattern
        tool_name(*)                 — Tool name, any arguments
        mcp__server__*               — MCP tool prefix match
        *                            — Catch-all (matches everything)
    
    Args:
        tool_name: Name of the tool being called
        args: Dictionary of tool arguments
        pattern: Permission pattern string
    
    Returns:
        True if the tool call matches the pattern
    """
    pattern = pattern.strip()
    
    # Catch-all pattern
    if pattern == "*":
        return True
    
    # MCP prefix pattern (mcp__server__*)
    if pattern.startswith("mcp__") and pattern.endswith("__*"):
        prefix = pattern[:-2]  # Remove __*
        return tool_name.startswith(prefix)
    
    # Pattern with arguments: tool_name(arg_pattern)
    paren_match = re.match(r"^([^(]+)\((.+)\)$", pattern)
    if paren_match:
        pattern_tool = paren_match.group(1).strip()
        arg_pattern = paren_match.group(2).strip()
        
        # Check tool name
        if not fnmatch.fnmatch(tool_name, pattern_tool):
            return False
        
        # Check arguments
        return _matches_args(args, arg_pattern)
    
    # Simple tool name pattern (supports globs)
    return fnmatch.fnmatch(tool_name, pattern)


def _matches_args(args: dict[str, Any], pattern: str) -> bool:
    """Check if arguments match a pattern.
    
    Patterns can be:
        *                    — Any arguments
        key=value            — Exact key=value match
        key=value*           — Key with value glob
        path:./src/**/*.py   — Check specific key
    """
    if pattern == "*":
        return True
    
    # Parse key=value patterns
    for part in pattern.split(","):
        part = part.strip()
        if "=" in part:
            key, _, val = part.partition("=")
            key = key.strip()
            val = val.strip()
            
            # Get the argument value
            arg_val = args.get(key, "")
            if isinstance(arg_val, dict):
                arg_val = json.dumps(arg_val)
            elif not isinstance(arg_val, str):
                arg_val = str(arg_val)
            
            # Check pattern match
            if not fnmatch.fnmatch(arg_val, val):
                return False
        elif ":" in part:
            # Special patterns like path:./src/**/*.py
            key, _, val = part.partition(":")
            key = key.strip()
            val = val.strip()
            
            arg_val = args.get(key, "")
            if isinstance(arg_val, dict):
                arg_val = json.dumps(arg_val)
            elif not isinstance(arg_val, str):
                arg_val = str(arg_val)
            
            if not fnmatch.fnmatch(arg_val, val):
                return False
    
    return True


import json


class PermissionMode:
    """Permission modes following Claude Code pattern."""
    
    DEFAULT = "default"      # Ask for dangerous operations
    PLAN = "plan"            # Read-only, no mutations
    AUTO = "auto"            # Auto-approve all
    BYPASS = "bypass"        # Bypass all permissions
    ACCEPT_EDITS = "accept_edits"  # Auto-approve edits, ask for bash


class PermissionRule:
    """A single permission rule."""
    
    def __init__(self, pattern: str, action: str = "allow", description: str = ""):
        self.pattern = pattern
        self.action = action  # "allow", "ask", "deny"
        self.description = description
    
    def matches(self, tool_name: str, args: dict[str, Any]) -> bool:
        return matches_pattern(tool_name, args, self.pattern)


class PermissionManager:
    """Claude Code-style permission manager with glob patterns."""
    
    def __init__(self, mode: str = PermissionMode.DEFAULT):
        self.mode = mode
        self.rules: list[PermissionRule] = []
        self.always_allow: set[str] = set()  # User-accepted permissions
        self.always_deny: set[str] = set()   # User-denied permissions
    
    def add_rule(self, pattern: str, action: str = "allow", description: str = ""):
        """Add a permission rule."""
        self.rules.append(PermissionRule(pattern, action, description))
    
    def check(self, tool_name: str, args: dict[str, Any]) -> str:
        """Check permission for a tool call.
        
        Returns:
            "allow" — Auto-approve
            "ask"   — Ask user for confirmation
            "deny"  — Block the tool call
        """
        # Mode-based overrides
        if self.mode == PermissionMode.AUTO:
            return "allow"
        if self.mode == PermissionMode.BYPASS:
            return "allow"
        if self.mode == PermissionMode.PLAN:
            if tool_name in ("write_file", "edit_file", "apply_patch", "bash"):
                return "deny"
            return "allow"
        if self.mode == PermissionMode.ACCEPT_EDITS:
            if tool_name in ("write_file", "edit_file", "apply_patch"):
                return "allow"
            if tool_name == "bash":
                return "ask"
        
        # Check always-deny first
        if tool_name in self.always_deny:
            return "deny"
        
        # Check always-allow
        if tool_name in self.always_allow:
            return "allow"
        
        # Check rules in order (last match wins)
        result = "ask"  # Default: ask
        for rule in self.rules:
            if rule.matches(tool_name, args):
                result = rule.action
        
        return result
    
    def approve_tool(self, tool_name: str, args: dict[str, Any]) -> None:
        """User approved a tool call — add to always-allow."""
        self.always_allow.add(tool_name)
    
    def deny_tool(self, tool_name: str, args: dict[str, Any]) -> None:
        """User denied a tool call — add to always-deny."""
        self.always_deny.add(tool_name)
    
    def get_rules_for_display(self) -> list[dict]:
        """Get rules formatted for display."""
        return [
            {"pattern": r.pattern, "action": r.action, "description": r.description}
            for r in self.rules
        ]
    
    @classmethod
    def from_config(cls, config: dict) -> "PermissionManager":
        """Create from configuration dict."""
        mode = config.get("mode", PermissionMode.DEFAULT)
        manager = cls(mode=mode)
        
        for rule_config in config.get("rules", []):
            manager.add_rule(
                pattern=rule_config.get("pattern", "*"),
                action=rule_config.get("action", "allow"),
                description=rule_config.get("description", ""),
            )
        
        return manager
