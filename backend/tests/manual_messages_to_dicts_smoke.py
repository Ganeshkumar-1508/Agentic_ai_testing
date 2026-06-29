"""Smoke test for messages_to_dicts metadata stripping."""
from __future__ import annotations

import sys

from harness.llm import ChatMessage, _strip_private_metadata, messages_to_dicts


def main() -> int:
    failures = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        marker = "ok" if cond else "FAIL"
        print(f"  {marker} {label}  {detail}")
        if not cond:
            failures += 1

    print("[1] basic message")
    msgs = [ChatMessage(role="user", content="hi")]
    out = messages_to_dicts(msgs)
    check("count=1", len(out) == 1)
    check("role=user", out[0]["role"] == "user")
    check("content=hi", out[0]["content"] == "hi")

    print("[2] internal _compressed_summary key stripped")
    msgs = [ChatMessage(
        role="user",
        content="[Summary of earlier turns]",
        metadata={"_compressed_summary": True},
    )]
    out = messages_to_dicts(msgs)
    check("count=1", len(out) == 1)
    check("role=user", out[0]["role"] == "user")
    check("_compressed_summary gone", "_compressed_summary" not in out[0])
    check("content preserved", out[0]["content"] == "[Summary of earlier turns]")

    print("[3] multiple _-prefixed keys all stripped")
    msgs = [ChatMessage(
        role="user",
        content="x",
        metadata={
            "_compressed_summary": True,
            "_pending_steer": "queued text",
            "_internal_marker": 42,
        },
    )]
    out = messages_to_dicts(msgs)
    leaked = [k for k in out[0] if k.startswith("_")]
    check("no leaked keys", len(leaked) == 0, f"leaked={leaked}")

    print("[4] public keys preserved")
    msgs = [ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[{"id": "tc1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
    )]
    out = messages_to_dicts(msgs)
    check("role=assistant", out[0]["role"] == "assistant")
    check("tool_calls preserved", "tool_calls" in out[0])
    check("reasoning_content present", "reasoning_content" in out[0])

    print("[5] tool message with tool_call_id")
    msgs = [ChatMessage(role="tool", content="result", tool_call_id="tc1")]
    out = messages_to_dicts(msgs)
    check("tool_call_id preserved", out[0].get("tool_call_id") == "tc1")

    print("[6] empty messages list")
    out = messages_to_dicts([])
    check("empty result", out == [])

    print("[7] _strip_private_metadata direct — passthrough for clean dict")
    out = _strip_private_metadata({"role": "user", "content": "hi"})
    check("clean dict unchanged", out == {"role": "user", "content": "hi"})

    print("[8] _strip_private_metadata — strip underscore keys")
    out = _strip_private_metadata({"role": "user", "_x": 1, "y": 2})
    check("underscore gone", "_x" not in out)
    check("non-underscore kept", out["y"] == 2)

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s)")
        return 1
    print("ALL MESSAGES_TO_DICTS SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
