"""Shared test fixtures for all backend tests."""
from __future__ import annotations

import pytest

pytest_plugins = ["pytest_asyncio"]


class FakeStore:
    """Fake store that returns None for context and no-ops store_interaction.
    Replaces duplicated definitions in test_agent_capabilities.py
    and test_agent_streaming.py.
    """

    async def get_recent_context(self):
        return None

    async def store_interaction(self, *args, **kwargs):
        pass


class FakePermissions:
    """Fake permission manager that always resolves to "allowed".
    Replaces duplicated definitions in test_agent_capabilities.py
    and test_agent_streaming.py.
    """

    def resolve_level(self, name, args):
        return "allowed"


@pytest.fixture
def fake_store():
    """Shared FakeStore fixture."""
    return FakeStore()


@pytest.fixture
def fake_permissions():
    """Shared FakePermissions fixture."""
    return FakePermissions()
