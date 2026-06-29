"""QuestionTool — pause and ask the user for clarification or approval.

When the agent is uncertain, needs more information, or requires
permission to proceed, it uses this tool to ask the user.
"""

from __future__ import annotations

from .base import BaseTool, ToolResult, ToolSpec


class QuestionTool(BaseTool):
    name = "question"
    description = "Pause and ask the user for clarification, approval, or additional information. Use when requirements are ambiguous or you need permission to proceed."
    capabilities = ["can_communicate"]

    async def run(self, question: str, options: list[str] | None = None) -> ToolResult:
        """Ask the user a question.

        Args:
            question: The question or request to present to the user.
            options: Optional list of suggested answers/options.
        """
        output = f"[QUESTION] {question}"
        if options:
            output += "\n\nOptions:\n" + "\n".join(f"  {i + 1}. {o}" for i, o in enumerate(options))
        output += "\n\n(Awaiting user response...)"

        return ToolResult(success=True, output=output, data={"question": question, "options": options or []})

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question or request for the user"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of suggested answer options",
                    },
                },
                "required": ["question"],
            },
        )


from harness.tools.registry import registry

registry.register(QuestionTool(), toolset="delegate")
