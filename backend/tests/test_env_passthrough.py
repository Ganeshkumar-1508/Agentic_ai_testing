"""Tests for env_passthrough — session-scoped env var allowlist."""

from __future__ import annotations

import pytest

from harness.tools.env_passthrough import (
    add_env_passthrough,
    clear_env_passthrough,
    get_all_passthrough,
    is_env_passthrough,
    remove_env_passthrough,
)


class TestEnvPassthrough:
    def setup_method(self):
        clear_env_passthrough()

    def test_is_passthrough_returns_false_by_default(self):
        assert not is_env_passthrough("OPENAI_API_KEY")

    def test_add_single_var(self):
        add_env_passthrough("MY_VAR")
        assert is_env_passthrough("MY_VAR")

    def test_add_multiple_vars(self):
        add_env_passthrough(["VAR_A", "VAR_B", "VAR_C"])
        assert is_env_passthrough("VAR_A")
        assert is_env_passthrough("VAR_B")
        assert is_env_passthrough("VAR_C")

    def test_remove_var(self):
        add_env_passthrough("TEMP_VAR")
        assert is_env_passthrough("TEMP_VAR")
        remove_env_passthrough("TEMP_VAR")
        assert not is_env_passthrough("TEMP_VAR")

    def test_remove_multiple(self):
        add_env_passthrough(["A", "B", "C"])
        remove_env_passthrough(["A", "C"])
        assert not is_env_passthrough("A")
        assert is_env_passthrough("B")
        assert not is_env_passthrough("C")

    def test_clear_all(self):
        add_env_passthrough(["X", "Y", "Z"])
        clear_env_passthrough()
        assert not is_env_passthrough("X")
        assert not is_env_passthrough("Y")
        assert not is_env_passthrough("Z")

    def test_get_all_passthrough(self):
        add_env_passthrough(["A", "B"])
        result = get_all_passthrough()
        assert "A" in result
        assert "B" in result

    def test_session_isolation(self):
        """Each test should get a fresh ContextVar."""
        pass

    @pytest.mark.asyncio
    async def test_integration_with_sanitize_env(self):
        """Verify env_passthrough integrates with local.py _sanitize_env."""
        from harness.backends.local import _sanitize_env

        clear_env_passthrough()
        env = {"OPENAI_API_KEY": "sk-test", "MY_VAR": "value"}
        result = _sanitize_env(env)
        assert "MY_VAR" in result
        assert "OPENAI_API_KEY" not in result

        add_env_passthrough("OPENAI_API_KEY")
        result2 = _sanitize_env(env)
        assert "OPENAI_API_KEY" in result2
        assert "MY_VAR" in result2
