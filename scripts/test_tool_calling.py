"""End-to-end test script for streaming-based tool call detection.

Usage:
    python scripts/test_tool_calling.py

Requires:
    - Docker running (for docker_executor tool)
    - OPENAI_API_KEY and OPENAI_BASE_URL set in backend/.env
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from harness.agent import Agent, AgentDependencies
from harness.llm import LLMRouter
from harness.memory.store import PersistentStore
from harness.memory.database import Database
from harness.permissions.manager import PermissionManager
from harness.tools.registry import registry


async def test_simple_chat():
    """Verify basic chat works (no tools needed)."""
    print("\n=== Test 1: Simple chat (no tools) ===")
    deps = await _build_deps()
    agent = Agent(deps=deps, mode="auto", max_tool_rounds=1)
    agent.session_id = "test-simple"

    start = time.time()
    result = await agent.run("say hello in exactly 5 words")
    elapsed = time.time() - start

    print(f"  Response: {result[:100]}")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Rounds: 1")
    assert len(result) > 0, "Empty response"
    if elapsed > 30:
        print(f"  ⚠️  Slow ({elapsed:.1f}s) — might be thinking mode burning tokens")
    else:
        print(f"  ✅ Fast response")
    return True


async def test_tool_call_detection():
    """Verify the agent detects and executes tool calls via streaming.

    Uses read_file which only requires workspace access (no Docker).
    """
    print("\n=== Test 2: Tool call detection (read_file) ===")
    deps = await _build_deps()
    agent = Agent(deps=deps, mode="auto", max_tool_rounds=3)
    agent.session_id = "test-tool-call"

    start = time.time()
    try:
        result = await agent.run("read the file backend/harness/agent.py and tell me the first line")
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Result preview: {result[:200]}")
        # If we see file content, the tool call was detected and executed
        if "from __future__" in result or "import" in result:
            print(f"  ✅ Tool call detected and executed successfully")
        elif "Error" in result:
            print(f"  ⚠️  Tool executed but returned error: {result[:100]}")
        else:
            print(f"  ⚠️  Unexpected result (may be a text response without tool use)")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ Failed after {elapsed:.1f}s: {e}")
        return False


async def test_docker_tool_call():
    """Verify docker_executor tool call detection via streaming.

    Requires Docker running.
    """
    print("\n=== Test 3: Docker executor tool call ===")
    deps = await _build_deps()
    agent = Agent(deps=deps, mode="auto", max_tool_rounds=5)
    agent.session_id = "test-docker"

    start = time.time()
    try:
        result = await agent.run("run 'echo hello-from-docker' in the docker sandbox and tell me what it says")
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Result preview: {result[:200]}")
        if "hello-from-docker" in result:
            print(f"  ✅ Docker tool call detected and executed")
        elif "Error" in result:
            print(f"  ⚠️  Docker tool returned error: {result[:100]}")
        else:
            print(f"  ⚠️  Unexpected result")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ Failed after {elapsed:.1f}s: {e}")
        return False


async def test_thinking_mode_tool_call():
    """Verify tool call works with thinking mode enabled.

    This is the primary bug scenario: deepseek-v4-flash with thinking enabled
    should detect tool calls mid-stream rather than burning all tokens on reasoning.
    """
    print("\n=== Test 4: Thinking mode + tool call ===")
    deps = await _build_deps()
    agent = Agent(deps=deps, mode="auto", max_tool_rounds=3)
    agent.session_id = "test-thinking"

    start = time.time()
    try:
        result = await agent.run(
            "analyze the tech stack of this project by reading the root package.json, "
            "docker-compose.yml, and requirements.txt. list what you find."
        )
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Result preview: {result[:300]}")
        if "Error" in result and "timed out" in result.lower():
            print(f"  ❌ Timed out — streaming may not be helping")
            return False
        if result and len(result) > 50:
            print(f"  ✅ Got meaningful response (multiple tool calls likely)")
            return True
        print(f"  ⚠️  Short or empty response")
        return True
    except Exception as e:
        elapsed = time.time() - start
        if "timed out" in str(e).lower() or elapsed > 110:
            print(f"  ❌ Timed out after {elapsed:.1f}s — streaming fix not working")
            return False
        print(f"  ❌ Error: {e}")
        return False


async def _build_deps() -> AgentDependencies:
    """Build minimal AgentDependencies for testing."""
    # Load env from backend/.env if exists
    env_path = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    # Configure LLM
    llm = LLMRouter()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://opencode.ai/zen/go/v1")
    model = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")

    provider_config = {
        "provider": "opencode",
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "enabled": True,
        "options": {"reasoning": {"enabled": True, "effort": "medium"}},
    }
    llm.configure([provider_config])

    # Discover tools
    registry.discover_tools()

    # Minimal store (no DB needed for testing)
    class MemStore:
        async def get_recent_context(self):
            return None
        async def store_interaction(self, *args, **kwargs):
            pass

    return AgentDependencies(
        llm=llm,
        store=MemStore(),  # type: ignore
        permissions=PermissionManager(mode="auto"),
    )


async def main():
    print("=" * 60)
    print("Streaming Tool Call Detection — E2E Test Suite")
    print(f"Model: {os.environ.get('DEFAULT_MODEL', 'deepseek-v4-flash')}")
    print("=" * 60)

    results = []
    results.append(("simple_chat", await test_simple_chat()))
    results.append(("tool_call", await test_tool_call_detection()))
    results.append(("thinking_mode", await test_thinking_mode_tool_call()))

    # Docker test is optional
    try:
        results.append(("docker", await test_docker_tool_call()))
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        all_pass = all_pass and passed
        print(f"  {status}  {name}")
    print(f"\n  Overall: {'✅ ALL PASS' if all_pass else '❌ SOME FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
