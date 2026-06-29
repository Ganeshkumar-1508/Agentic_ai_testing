"""Hook phases and event names.

Phase ordering (numerical value = execution order):
  0  DETERMINISTIC_GATE  — JSON-file rules (allow/block/ask)
  1  MIDDLEWARE           — Ordered middleware chain (16 classes)
  2  PLUGIN               — Plugin hooks from _hook_system

Pattern follows Hermes Agent's single HookRegistry with named events
(reference/hermes-agent/gateway/hooks.py), extended with phase ordering
so the three existing systems merge without behavioural change.
"""

from __future__ import annotations

import enum


class HookType(enum.IntEnum):
    """Execution phase for a hook handler. Lower value = earlier execution."""

    DETERMINISTIC_GATE = 0
    MIDDLEWARE = 1
    PLUGIN = 2


# ── Event names ───────────────────────────────────────────────────────
# These match the existing MiddlewareChain hook methods exactly so the
# Agent class can switch to the unified pipeline without changing call sites.

BEFORE_RUN = "before_run"
AFTER_RUN = "after_run"
BEFORE_LLM = "before_llm"
AFTER_LLM = "after_llm"
BEFORE_TOOL = "before_tool"
AFTER_TOOL = "after_tool"
END_OF_ROUND = "end_of_round"

# Plugin lifecycle events (from _hook_system VALID_HOOKS)
PRE_LLM_CALL = "pre_llm_call"
POST_LLM_CALL = "post_llm_call"
PRE_TOOL_CALL = "pre_tool_call"
POST_TOOL_CALL = "post_tool_call"
ON_SESSION_START = "on_session_start"
ON_SESSION_END = "on_session_end"
TRANSFORM_LLM_OUTPUT = "transform_llm_output"
TRANSFORM_TOOL_RESULT = "transform_tool_result"
TRANSFORM_TERMINAL_OUTPUT = "transform_terminal_output"
SUBAGENT_STOP = "subagent_stop"
PRE_APPROVAL_REQUEST = "pre_approval_request"
POST_APPROVAL_RESPONSE = "post_approval_response"

# All pipeline event names
ALL_EVENTS: frozenset[str] = frozenset({
    BEFORE_RUN, AFTER_RUN, BEFORE_LLM, AFTER_LLM,
    BEFORE_TOOL, AFTER_TOOL, END_OF_ROUND,
    PRE_LLM_CALL, POST_LLM_CALL, PRE_TOOL_CALL, POST_TOOL_CALL,
    ON_SESSION_START, ON_SESSION_END,
    TRANSFORM_LLM_OUTPUT, TRANSFORM_TOOL_RESULT, TRANSFORM_TERMINAL_OUTPUT,
    SUBAGENT_STOP, PRE_APPROVAL_REQUEST, POST_APPROVAL_RESPONSE,
})
