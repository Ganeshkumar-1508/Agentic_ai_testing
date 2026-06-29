"""FakeLLMRouter — deterministic LLM responses for agent-loop tests.

Produces OpenAI-style streaming chunks from simple fixture definitions.
Lets tests assert on StreamEvent sequences without real API calls.

Usage:
    from tests.fake_llm import FakeLLMRouter, FakeChunk

    llm = FakeLLMRouter([
        FakeChunk(content="Hello "),
        FakeChunk(content="world"),
    ])
    # pass llm to AgentDependencies → Agent.run_stream() → assert on events
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock


@dataclass
class FakeChunk:
    """A single streaming chunk delta."""
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # tool_calls: [{"id": "tc1", "name": "bash", "arguments": "{}", "index": 0}, ...]


def _ns(**kwargs: Any) -> Any:
    """Build a SimpleNamespace from kwargs (concise chunk builder)."""
    from types import SimpleNamespace
    return SimpleNamespace(**kwargs)


def _build_chunk(chunk: FakeChunk) -> Any:
    """Build an OpenAI-style streaming chunk from a FakeChunk."""
    delta: dict[str, Any] = {}
    if chunk.content:
        delta["content"] = chunk.content
    if chunk.reasoning:
        delta["reasoning_content"] = chunk.reasoning
    if chunk.tool_calls:
        delta["tool_calls"] = [
            _ns(
                index=tc.get("index", 0),
                id=tc.get("id", ""),
                function=_ns(
                    name=tc.get("name", ""),
                    arguments=tc.get("arguments", "{}"),
                ),
            )
            for tc in chunk.tool_calls
        ]
    return _ns(choices=[_ns(delta=_ns(**delta), index=0)], model="fake-model", id="fake-id")


class FakeLLMRouter:
    """Deterministic LLM router for tests.

    Yields pre-defined chunk sequences for chat_stream() and returns
    a simple response for chat(). No real API calls.
    """

    def __init__(self, chunks: list[FakeChunk]) -> None:
        self._chunks = chunks
        self._call_count = 0

    async def chat_stream(
        self,
        messages: Any = None,
        tools: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        """Yields pre-configured FakeChunks as OpenAI-style streaming objects.
        Re-yields the same chunks on every call so multi-turn loops work."""
        for chunk in self._chunks:
            yield _build_chunk(chunk)
        self._call_count += 1

    async def chat(
        self,
        messages: Any = None,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Returns a CompletionResponse built from all chunks concatenated."""
        from harness.llm import CompletionResponse

        full_content = "".join(c.content for c in self._chunks if c.content)
        last_tc = [c for c in self._chunks if c.tool_calls]
        tool_calls: list[dict[str, Any]] | None = None
        if last_tc:
            tc = last_tc[-1]
            tool_calls = [
                {
                    "id": t["id"],
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "arguments": t.get("arguments", "{}"),
                    },
                }
                for t in tc.tool_calls
            ]
        self._call_count += 1
        return CompletionResponse(
            content=full_content,
            tool_calls=tool_calls,
            usage={"prompt_tokens": 10, "completion_tokens": len(full_content), "total_tokens": 10 + len(full_content)},
            model="fake-model",
        )

    @property
    def call_count(self) -> int:
        return self._call_count


def make_tool_chunks(text: str, tool_name: str, tool_args: str, tool_id: str = "tc1") -> list[FakeChunk]:
    """Convenience: build a multi-chunk sequence with content then a tool call."""
    return [
        FakeChunk(content=text),
        FakeChunk(tool_calls=[{"id": tool_id, "name": tool_name, "arguments": tool_args, "index": 0}]),
    ]
