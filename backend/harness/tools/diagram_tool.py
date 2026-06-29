"""DiagramTool — generate Mermaid diagrams.

Generates Mermaid.js syntax for flowcharts, sequence diagrams, ERDs,
architecture diagrams, class diagrams, and more.
Returns the Mermaid code that can be rendered by any Mermaid renderer.
"""

from __future__ import annotations

from .base import BaseTool, ToolResult, ToolSpec


MERMAID_TEMPLATES = {
    "flowchart": """flowchart TD
  A[Start] --> B{Decision?}
  B -->|Yes| C[Process]
  B -->|No| D[Skip]
  C --> E((End))
  D --> E""",

    "sequence": """sequenceDiagram
  participant User
  participant System
  User->>System: Request
  System-->>User: Response
  Note right of System: Processing""",

    "erd": """erDiagram
  ENTITY ||--o{ RELATED : has
  ENTITY {
    string id PK
    string name
  }""",

    "class": """classDiagram
  class Animal {
    +String name
    +int age
    +makeSound() void
  }
  class Dog
  Animal <|-- Dog""",

    "gantt": """gantt
  title Project Timeline
  dateFormat YYYY-MM-DD
  section Phase 1
  Task 1 :a1, 2025-01-01, 7d""",

    "architecture": """architecture-beta
  group cloud(cloud)[Cloud]
  service api(server)[API] in cloud
  service db(database)[DB] in cloud
  api:R --> L:db""",
}


class DiagramTool(BaseTool):
    name = "diagram"
    description = "Generate Mermaid diagrams (flowcharts, sequence diagrams, ERDs, class diagrams, architecture diagrams, Gantt charts). Returns Mermaid syntax ready to render."
    capabilities = ["can_generate_diagrams"]

    async def run(self, diagram_type: str = "flowchart", title: str = "", description: str = "") -> ToolResult:
        dtype = diagram_type.lower().replace(" ", "_")
        template = MERMAID_TEMPLATES.get(dtype)
        if not template:
            types = ", ".join(MERMAID_TEMPLATES.keys())
            return ToolResult(success=False, output=f"Unsupported diagram type '{diagram_type}'. Supported: {types}")

        output_parts = [f"```mermaid"]
        if title:
            output_parts.append(f"---")
            output_parts.append(f"title: {title}")
            output_parts.append(f"---")
        output_parts.append(template)
        output_parts.append("```")
        if description:
            output_parts.append(f"\nDescription: {description}")

        return ToolResult(success=True, output="\n".join(output_parts), data={
            "type": dtype,
            "mermaid": template,
            "title": title or "",
            "render_url": f"https://mermaid.live/edit#pako:{_encode_mermaid(template)}",
        })

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "diagram_type": {"type": "string", "description": "Type of diagram", "enum": list(MERMAID_TEMPLATES.keys())},
                    "title": {"type": "string", "description": "Optional diagram title"},
                    "description": {"type": "string", "description": "Optional description of what the diagram represents"},
                },
                "required": ["diagram_type"],
            },
        )


def _encode_mermaid(code: str) -> str:
    """Encode Mermaid code for the live editor URL."""
    import zlib
    import base64
    compressed = zlib.compress(code.encode("utf-8"), level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii")


from harness.tools.registry import registry

registry.register(DiagramTool(), toolset="specialized")
