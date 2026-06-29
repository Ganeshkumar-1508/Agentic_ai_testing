"""End-to-end LLM test: drive Agent.run() with a real deepseek-v4-flash call.

Loads credentials from plans/test_env.txt (never committed), configures a
real LLMRouter, builds a minimal Agent, and runs a simple prompt.

Usage:
    python tests/manual_real_llm.py "Say hello in one short sentence."
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 1. Load credentials from plans/test_env.txt (NEVER hardcode)
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / "plans" / "test_env.txt"
if not ENV_FILE.exists():
    print(f"ERROR: {ENV_FILE} not found", file=sys.stderr)
    sys.exit(1)

for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    k, v = k.strip(), v.strip()
    if k and v and k not in os.environ:
        os.environ[k] = v

MODEL = os.environ.get("MODEL", "deepseek-v4-flash")
URL = os.environ.get("URL", "")
API_KEY = os.environ.get("API_KEY", "")

# 2. Build the LLMRouter
from harness.llm import LLMRouter, ProviderProfile  # noqa: E402

router = LLMRouter()
profile = ProviderProfile(
    name="zen",
    model=MODEL,
    api_key=API_KEY,
    base_url=URL,
    api_mode="openai",
    options={},
)
router._profiles[profile.name] = profile
router._profiles_by_model[profile.model] = profile
router._roles[profile.name] = "default"

print(f"[llm] provider=zen model={MODEL} base_url={URL} key_len={len(API_KEY)}")

# 3. Minimal AgentDependencies (no store, no MCP, no sandbox)
from harness.agent import Agent, AgentDependencies  # noqa: E402
from harness.events import EventBus  # noqa: E402
from harness.permissions.manager import PermissionManager  # noqa: E402

deps = AgentDependencies(
    llm=router,
    store=None,
    permissions=PermissionManager(mode="ask"),
    mcp=None,
    sandbox_manager=MagicMock(),
    event_bus=EventBus(),
)
agent = Agent(deps=deps, mode="ask", max_tool_rounds=2, allowed_tools=[])
agent.session_id = "manual-real-llm"

# 4. Run a simple prompt
prompt = sys.argv[1] if len(sys.argv) > 1 else "Say hello in one short sentence."
print(f"[prompt] {prompt}")
print("[running] ...")


async def main():
    result = await agent.run(prompt, model=MODEL)
    print("---")
    print(f"[response] {result}")
    print("---")
    print(f"[messages] {len(agent._messages)} total in conversation")
    for i, m in enumerate(agent._messages):
        content_preview = (m.content or "")[:80] if m.content else "<empty>"
        print(f"  {i}. role={m.role} content={content_preview!r}")


asyncio.run(main())
