"""Guardrail system — ported from DeerFlow (MIT License, Bytedance Ltd).

Three files consolidated:
  - guardrails/provider.py: GuardrailRequest, GuardrailDecision, GuardrailReason, GuardrailProvider protocol
  - guardrails/builtin.py: AllowlistProvider
  - guardrails/middleware.py: GuardrailMiddleware

Strategy (unchanged): evaluate every tool call against a pluggable provider.
Denied calls return error; fail_closed blocks on provider errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from harness.middleware.base import AgentMiddleware

logger = logging.getLogger(__name__)


@dataclass
class GuardrailRequest:
    tool_name: str
    tool_input: dict[str, Any]
    agent_id: str | None = None
    session_id: str | None = None
    is_subagent: bool = False
    user_id: str | None = None
    tool_call_id: str | None = None


@dataclass
class GuardrailReason:
    code: str
    message: str = ""


@dataclass
class GuardrailDecision:
    allow: bool
    reasons: list[GuardrailReason] = field(default_factory=list)
    policy_id: str | None = None


class GuardrailProvider(Protocol):
    name: str
    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision: ...
    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision: ...


class AllowlistProvider:
    name = "allowlist"

    def __init__(self, *, allowed_tools: list[str] | None = None, denied_tools: list[str] | None = None):
        self._allowed = set(allowed_tools) if allowed_tools else None
        self._denied = set(denied_tools) if denied_tools else set()

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        if self._allowed is not None and request.tool_name not in self._allowed:
            return GuardrailDecision(allow=False, reasons=[GuardrailReason(code="tool_not_allowed", message=f"tool '{request.tool_name}' not in allowlist")])
        if request.tool_name in self._denied:
            return GuardrailDecision(allow=False, reasons=[GuardrailReason(code="tool_denied", message=f"tool '{request.tool_name}' is denied")])
        return GuardrailDecision(allow=True, reasons=[GuardrailReason(code="allowed")])

    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        return self.evaluate(request)


class GuardrailMiddleware(AgentMiddleware):
    """Evaluate tool calls against a GuardrailProvider before execution."""

    def __init__(self, provider: GuardrailProvider, *, fail_closed: bool = True, passport: str | None = None):
        self._provider = provider
        self._fail_closed = fail_closed
        self._passport = passport

    def _build_request(self, name: str, args: dict) -> GuardrailRequest:
        return GuardrailRequest(
            tool_name=name,
            tool_input=args,
            agent_id=self._passport,
        )

    async def on_before_tool(self, name: str, args: dict) -> bool | None:
        gr = self._build_request(name, args)
        try:
            decision = self._provider.evaluate(gr)
        except Exception:
            logger.exception("Guardrail provider error")
            if self._fail_closed:
                decision = GuardrailDecision(allow=False, reasons=[GuardrailReason(code="evaluator_error", message="guardrail provider error (fail-closed)")])
            else:
                return None

        if not decision.allow:
            reason = decision.reasons[0].message if decision.reasons else "blocked by guardrail"
            logger.warning("Guardrail denied: tool=%s reason=%s", name, reason)
            return False
        return None
