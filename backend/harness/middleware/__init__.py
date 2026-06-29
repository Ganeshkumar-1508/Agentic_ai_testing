"""Middleware chain — structured hooks for TestAI's agent loop.

Ported patterns from DeerFlow (MIT License, Copyright Bytedance Ltd.):
  1. InputSanitizeMiddleware    Escape prompt-injection tags
  2. DanglingToolCallMiddleware  Fix interrupted tool calls
  3. DynamicContextMiddleware    Inject date/memory as system-reminder
  4. TokenBudgetMiddleware       Per-run token hard limits
  5. ToolBudgetMiddleware        Oversized results → disk + preview
  6. GuardrailMiddleware         Pre-tool authorization (pluggable provider)
  7. SandboxAuditMiddleware      Bash command security classification
  8. ToolErrorHandlingMiddleware Exceptions → error strings
  9. LoopDetectionMiddleware     Hash-based stuck loop detection
 10. SubagentLimitMiddleware     Concurrent subagent cap (5-8)
 11. LLMErrorHandlingMiddleware  Retry/backoff + circuit breaker
 12. ClarificationMiddleware     Interrupt on ask_clarification
 13. ViewImageMiddleware         Inject viewed images for vision models
 14. SafetyFinishReasonMiddleware Strip tool_calls on provider safety signal
 15. SkillActivationMiddleware   /skill-name syntax activation
 16. TitleMiddleware             Auto-title conversations
"""

from __future__ import annotations

from harness.middleware.base import AgentMiddleware

from harness.middleware.input_sanitize import InputSanitizeMiddleware
from harness.middleware.loop_detection import LoopDetectionMiddleware
from harness.middleware.tool_budget import ToolBudgetMiddleware
from harness.middleware.subagent_limit import SubagentLimitMiddleware
from harness.middleware.dangling import DanglingToolCallMiddleware
from harness.middleware.audit import SandboxAuditMiddleware
from harness.middleware.token_budget import TokenBudgetMiddleware, TokenBudgetConfig
from harness.middleware.tool_errors import ToolErrorHandlingMiddleware
from harness.middleware.llm_errors import LLMErrorHandlingMiddleware
from harness.middleware.guardrails import GuardrailMiddleware, GuardrailRequest, GuardrailDecision, GuardrailProvider, AllowlistProvider
from harness.middleware.dynamic_context import DynamicContextMiddleware
from harness.middleware.title_gen import TitleMiddleware
from harness.middleware.clarification import ClarificationMiddleware
from harness.middleware.view_image import ViewImageMiddleware
from harness.middleware.safety import SafetyFinishReasonMiddleware
from harness.middleware.skill_activation import SkillActivationMiddleware

__all__ = [
    "AgentMiddleware",
    "InputSanitizeMiddleware", "LoopDetectionMiddleware",
    "ToolBudgetMiddleware", "SubagentLimitMiddleware",
    "DanglingToolCallMiddleware", "SandboxAuditMiddleware",
    "TokenBudgetMiddleware", "TokenBudgetConfig",
    "ToolErrorHandlingMiddleware", "LLMErrorHandlingMiddleware",
    "GuardrailMiddleware", "GuardrailRequest", "GuardrailDecision",
    "GuardrailProvider", "AllowlistProvider",
    "DynamicContextMiddleware", "TitleMiddleware",
    "ClarificationMiddleware", "ViewImageMiddleware",
    "SafetyFinishReasonMiddleware", "SkillActivationMiddleware",
]
