"""Quick LLM connectivity check via the running backend."""
import asyncio
import sys
sys.path.insert(0, "/app")

from harness.api.state import get_llm
from harness.llm import ChatMessage


async def main():
    llm = get_llm()
    if llm is None:
        print("ERROR: no LLM")
        return 1
    print("LLM providers:", len(getattr(llm, "_profiles", {})))
    try:
        resp = await llm.chat([ChatMessage(role="user", content="Reply with just the word 'ok'")])
        content = resp.content if hasattr(resp, "content") else str(resp)
        print(f"LLM response: {content!r}")
        return 0
    except Exception as e:
        print(f"LLM error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
