"""
TestAI Platform - Backend Package Init
"""

# Core modules
from app.core.config import get_settings, LLM_PROVIDERS, TEST_TYPES, AGENT_DEFINITIONS

__all__ = [
    "get_settings",
    "LLM_PROVIDERS",
    "TEST_TYPES",
    "AGENT_DEFINITIONS",
]
