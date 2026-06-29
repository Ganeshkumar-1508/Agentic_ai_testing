"""Structured retry tokens (SWE-agent pattern).

Provides clear signals for retry behavior:
- RETRY_WITH_CONTEXT: Retry with context from previous failure
- RETRY_WITHOUT_CONTEXT: Retry fresh
- EXIT_FORFEIT: Give up after max retries
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Retry tokens (SWE-agent pattern)
RETRY_WITH_CONTEXT = "###RETRY-WITH-CONTEXT###"
RETRY_WITHOUT_CONTEXT = "###RETRY-WITHOUT-CONTEXT###"
EXIT_FORFEIT = "###EXIT-FORFEIT###"


@dataclass
class RetryState:
    """Tracks retry state for a tool execution."""
    tool_name: str
    attempt: int = 0
    max_retries: int = 3
    errors: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    should_exit: bool = False
    
    def add_attempt(self, error: str, context: str = "") -> None:
        """Record a failed attempt."""
        self.attempt += 1
        self.errors.append(error)
        if context:
            self.contexts.append(context)
        
        if self.attempt >= self.max_retries:
            self.should_exit = True
            logger.warning(
                "Max retries (%d) reached for %s: %s",
                self.max_retries, self.tool_name, error[:100]
            )
    
    def should_retry(self) -> bool:
        """Check if we should retry."""
        return not self.should_exit and self.attempt < self.max_retries
    
    def get_retry_token(self) -> str:
        """Get the appropriate retry token."""
        if self.should_exit:
            return EXIT_FORFEIT
        if self.contexts:
            return RETRY_WITH_CONTEXT
        return RETRY_WITHOUT_CONTEXT
    
    def build_retry_context(self) -> str:
        """Build context string for retry with context."""
        if not self.errors:
            return ""
        
        lines = ["## Previous Attempts\n"]
        for i, (error, context) in enumerate(zip(self.errors, self.contexts), 1):
            lines.append(f"### Attempt {i}")
            lines.append(f"Error: {error[:200]}")
            if context:
                lines.append(f"Context: {context[:200]}")
            lines.append("")
        
        lines.append("## Retry Instructions")
        lines.append("Analyze the errors above and try a different approach.")
        lines.append("Consider:")
        lines.append("- Is the tool name correct?")
        lines.append("- Are the arguments valid?")
        lines.append("- Would a different approach avoid this error?")
        
        return "\n".join(lines)


class RetryManager:
    """Manages retry logic for tool executions."""
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._states: dict[str, RetryState] = {}
    
    def get_state(self, tool_name: str) -> RetryState:
        """Get or create retry state for a tool."""
        if tool_name not in self._states:
            self._states[tool_name] = RetryState(
                tool_name=tool_name,
                max_retries=self.max_retries,
            )
        return self._states[tool_name]
    
    def record_failure(self, tool_name: str, error: str, context: str = "") -> RetryState:
        """Record a failure and return updated state."""
        state = self.get_state(tool_name)
        state.add_attempt(error, context)
        return state
    
    def should_retry(self, tool_name: str) -> bool:
        """Check if we should retry a tool."""
        return self.get_state(tool_name).should_retry()
    
    def get_retry_instruction(self, tool_name: str) -> str:
        """Get retry instruction for the LLM."""
        state = self.get_state(tool_name)
        token = state.get_retry_token()
        
        if token == EXIT_FORFEIT:
            return (
                f"{EXIT_FORFEIT}\n\n"
                f"Max retries reached for {tool_name}. "
                "Try a completely different approach or skip this step."
            )
        
        if token == RETRY_WITH_CONTEXT:
            context = state.build_retry_context()
            return f"{RETRY_WITH_CONTEXT}\n\n{context}"
        
        return RETRY_WITHOUT_CONTEXT
    
    def reset(self, tool_name: str) -> None:
        """Reset retry state for a tool."""
        self._states.pop(tool_name, None)
    
    def reset_all(self) -> None:
        """Reset all retry states."""
        self._states.clear()
