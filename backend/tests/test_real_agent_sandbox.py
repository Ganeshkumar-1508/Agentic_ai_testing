"""Real-agent sandbox smoke test.

Drives a real Agent (real LLM, real docker) through a multi-step task that
exercises the five file/shell tools inside a per-session sandbox container:

    bash, read_file, write_file, edit_file, list_files

The agent's task is concrete and verifiable:
  1. write_file  → create /workspace/agent_smoke.txt with content X
  2. read_file   → confirm file exists with content X
  3. bash        → run `wc -c` to report byte count
  4. edit_file   → replace X with Y
  5. read_file   → confirm Y

After the agent finishes, the test verifies (1) the file inside the
per-session docker volume (`testai-ws-<session>`) contains the
expected Y, and (2) the agent's final response mentions Y. Together
these prove the agent actually routed its tool calls through the live
sandbox — not the host filesystem.

Skips cleanly when:
  - plans/test_env.txt is missing
  - the docker daemon isn't reachable
  - MODEL/URL/API_KEY env vars aren't set

Runs as a pytest module (`pytest -m real_llm tests/test_real_agent_sandbox.py -v -s`)
or as a standalone script (`python tests/test_real_agent_sandbox.py`).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / "plans" / "test_env.txt"
TEST_IMAGE = "alpine:latest"
SESSION_ID = "real-agent-sandbox-smoke"
PROMPT = (
    "You have a sandboxed container with /workspace mounted as a per-session "
    "docker volume. Please complete this exact sequence using the file/shell "
    "tools available to you (use write_file, read_file, edit_file, bash — do "
    "NOT use host-only paths):\n\n"
    "1. Use write_file to create /workspace/agent_smoke.txt with the exact text "
    "'real-agent-sandbox-ok' (21 characters, no trailing newline, no extra characters).\n"
    "2. Use read_file to confirm the file contains 'real-agent-sandbox-ok'.\n"
    "3. Use bash to run `wc -c /workspace/agent_smoke.txt` and report the byte count.\n"
    "4. Use edit_file to replace the entire content with 'real-agent-sandbox-edited' "
    "(25 characters, no trailing newline).\n"
    "5. Use read_file to confirm the file now contains 'real-agent-sandbox-edited'.\n\n"
    "In your final answer, report:\n"
    "  - the byte count from step 3\n"
    "  - the final file contents from step 5\n"
    "  - the exact tool names you used in order"
)
EXPECTED_INITIAL = "real-agent-sandbox-ok"
EXPECTED_FINAL = "real-agent-sandbox-edited"


# ---------------------------------------------------------------------------
# Skip guards (clean exit, no stack traces)
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10,
        ).returncode == 0
    except Exception:
        return False


def _creds_available() -> bool:
    if not ENV_FILE.exists():
        return False
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(("MODEL=", "URL=", "API_KEY=")) and "=" in line and line.split("=", 1)[1].strip():
            return True
    return False


pytestmark = pytest.mark.skipif(
    not _creds_available(),
    reason=f"creds not available (need {ENV_FILE} with MODEL/URL/API_KEY)",
)


@pytest.fixture(scope="module")
def creds() -> dict[str, str]:
    """Load creds from plans/test_env.txt into os.environ once per test session."""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k and v and k not in os.environ:
            os.environ[k] = v
    return {
        "model": os.environ.get("MODEL", "deepseek-v4-flash"),
        "url": os.environ.get("URL", ""),
        "api_key": os.environ.get("API_KEY", ""),
    }


@pytest.fixture(scope="module")
def docker_ready() -> None:
    if not _docker_available():
        pytest.skip("docker daemon not reachable")


# ---------------------------------------------------------------------------
# The real test
# ---------------------------------------------------------------------------


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_real_agent_uses_sandbox_for_file_ops(creds, docker_ready):
    """End-to-end: real Agent + real SandboxManager + real LLM.

    The agent must use bash, read_file, write_file, edit_file inside the
    sandbox container. We verify the operations actually happened by
    inspecting the per-session docker volume with a one-off `alpine`
    container — the workspace data lives in a named docker volume
    (`testai-ws-<session>`), not on the host filesystem.
    """
    from harness.agent import Agent, AgentDependencies
    from harness.events import EventBus
    from harness.llm import LLMRouter, ProviderProfile
    from harness.permissions.manager import PermissionManager
    from harness.sandbox_manager import SandboxManager
    from harness.tools.registry import registry

    # Register all tools (file_tools, delegate_task, etc. self-register on import).
    # Hermes-equivalent: registry.discover_tools() scans the directory.
    registry.discover_tools()

    # Per-session workspace lives in a docker volume (testai-ws-<SESSION_ID>).
    volume_name = f"testai-ws-{SESSION_ID}"

    # Real LLM
    router = LLMRouter()
    profile = ProviderProfile(
        name="zen",
        model=creds["model"],
        api_key=creds["api_key"],
        base_url=creds["url"],
        api_mode="openai",
        options={},
    )
    router._profiles[profile.name] = profile
    router._profiles_by_model[profile.model] = profile
    router._roles[profile.name] = "default"

    # Real sandbox (real docker). Use alpine:latest to keep image pull fast (~5MB).
    # Workspace data is stored in a Docker named volume (testai-ws-<session_id>).
    sandbox_manager = SandboxManager(default_image=TEST_IMAGE)

    # Pre-pull so the first tool call doesn't stall the LLM round loop
    print(f"[setup] workspace volume will be created on first container start")
    print(f"[setup] image={TEST_IMAGE} (pre-pulling)...")
    print(f"[setup] image={TEST_IMAGE} (pre-pulling)...")
    pull = subprocess.run(
        ["docker", "pull", TEST_IMAGE], capture_output=True, text=True, timeout=120,
    )
    if pull.returncode != 0:
        pytest.skip(f"docker pull {TEST_IMAGE} failed: {pull.stderr.strip()}")
    print(f"[setup] image ready")

    # Minimal agent deps (no DB, no MCP, no memory store — pure LLM + sandbox)
    deps = AgentDependencies(
        llm=router,
        store=None,
        permissions=PermissionManager(mode="debug"),
        mcp=None,
        sandbox_manager=sandbox_manager,
        event_bus=EventBus(),
    )
    agent = Agent(
        deps=deps,
        mode="debug",
        allowed_tools=["bash", "read_file", "write_file", "edit_file", "list_files"],
        max_tool_rounds=12,
    )
    agent.session_id = SESSION_ID

    # ---- Run the agent ----
    print(f"[run] prompt: {PROMPT[:80]}...")
    response = await agent.run(PROMPT, model=creds["model"])
    print(f"[run] response length: {len(response)} chars")
    print(f"[run] response preview: {response[:300]}...")
    print(f"[run] tool calls made: {sum(1 for m in agent._messages if m.role == 'tool')}")

    # ---- Verify file in docker volume (proves sandbox + volume worked) ----
    # The workspace data lives in docker volume `testai-ws-<session_id>`.
    # Mount it into a one-off alpine container to read the file.
    inspect = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{volume_name}:/inspect", "alpine:latest",
         "cat", "/inspect/agent_smoke.txt"],
        capture_output=True, text=True, timeout=30,
    )
    if inspect.returncode != 0 or not inspect.stdout:
        pytest.fail(
            f"agent_smoke.txt not found in volume {volume_name}. "
            f"The agent did not create the file in the sandbox workspace. "
            f"stderr={inspect.stderr!r} "
            f"Tool calls made: {sum(1 for m in agent._messages if m.role == 'tool')}"
        )
    final_content = inspect.stdout.rstrip("\n")
    final_content = target.read_text(encoding="utf-8").rstrip("\n")
    assert final_content == EXPECTED_FINAL, (
        f"Expected final file content {EXPECTED_FINAL!r}, got {final_content!r}. "
        f"The agent did not complete the edit_file step in the sandbox."
    )

    # ---- Verify agent's response mentions the final content ----
    assert EXPECTED_FINAL in response, (
        f"Agent's final response did not mention {EXPECTED_FINAL!r}. "
        f"Response: {response[:500]}"
    )

    # ---- Cleanup ----
    await sandbox_manager.destroy_env(SESSION_ID)
    print(f"[cleanup] sandbox destroyed")

    print(f"\n[PASS] Real agent used the sandbox to:")
    print(f"  - write_file: created {target.name} with {EXPECTED_INITIAL!r}")
    print(f"  - read_file:  verified content")
    print(f"  - bash:       ran wc -c")
    print(f"  - edit_file:  changed to {EXPECTED_FINAL!r}")
    print(f"  - read_file:  verified edit")
    print(f"Final file: {target.read_text(encoding='utf-8')!r}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


async def _main() -> int:
    if not _creds_available():
        print(f"ERROR: {ENV_FILE} missing or empty", file=sys.stderr)
        return 2
    if not _docker_available():
        print("ERROR: docker daemon not reachable", file=sys.stderr)
        return 2

    import os
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k and v and k not in os.environ:
            os.environ[k] = v

    creds = {
        "model": os.environ.get("MODEL", "deepseek-v4-flash"),
        "url": os.environ.get("URL", ""),
        "api_key": os.environ.get("API_KEY", ""),
    }

    from harness.agent import Agent, AgentDependencies
    from harness.events import EventBus
    from harness.llm import LLMRouter, ProviderProfile
    from harness.permissions.manager import PermissionManager
    from harness.sandbox_manager import SandboxManager
    from harness.tools.registry import registry

    registry.discover_tools()

    sandbox_manager = SandboxManager(default_image=TEST_IMAGE)

    print(f"[llm] provider=zen model={creds['model']}")
    print(f"[setup] workspace volume: testai-ws-{SESSION_ID}")

    router = LLMRouter()
    profile = ProviderProfile(
        name="zen", model=creds["model"], api_key=creds["api_key"],
        base_url=creds["url"], api_mode="openai", options={},
    )
    router._profiles[profile.name] = profile
    router._profiles_by_model[profile.model] = profile
    router._roles[profile.name] = "default"

    deps = AgentDependencies(
        llm=router, store=None,
        permissions=PermissionManager(mode="debug"),
        mcp=None, sandbox_manager=sandbox_manager, event_bus=EventBus(),
    )
    agent = Agent(
        deps=deps, mode="debug",
        allowed_tools=["bash", "read_file", "write_file", "edit_file", "list_files"],
        max_tool_rounds=12,
    )
    agent.session_id = SESSION_ID

    response = await agent.run(PROMPT, model=creds["model"])

    inspect = subprocess.run(
        ["docker", "run", "--rm", "-v", f"testai-ws-{SESSION_ID}:/inspect", "alpine:latest",
         "cat", "/inspect/agent_smoke.txt"],
        capture_output=True, text=True, timeout=30,
    )
    final_content = inspect.stdout.rstrip("\n") if inspect.returncode == 0 else ""
    print(f"\n--- AGENT RESPONSE ---")
    print(response)
    print(f"--- FILE IN VOLUME testai-ws-{SESSION_ID} ---")
    print(f"exists:  {bool(final_content)}")
    if final_content:
        print(f"content: {final_content!r}")

    await sandbox_manager.destroy_env(SESSION_ID)
    return 0 if (final_content == EXPECTED_FINAL) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
