from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any


class ToolResult(BaseModel):
    success: bool
    output: str
    data: dict[str, Any] | None = None
    error: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class BaseTool(ABC):
    name: str
    description: str
    default_level: str = "ask"
    """Default permission level: 'allow', 'ask', or 'deny'. Each tool
    declares its own risk. Overridden by policy rules at runtime."""
    capabilities: list[str] = []
    """Semantic tags like 'can_write_fs', 'can_read_fs', 'can_search_web'.
    Used by the LLM to discover tools by capability instead of name."""
    concurrency_safe: bool = False
    """If True, multiple instances of this tool can execute in parallel
    without risk of data races (e.g. read/grep/glob). Default False for
    tools that write state or have side effects (bash, write_file, etc.)."""

    @abstractmethod
    def spec(self) -> ToolSpec:
        ...

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        s = self.spec()
        return {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.input_schema,
            },
        }
