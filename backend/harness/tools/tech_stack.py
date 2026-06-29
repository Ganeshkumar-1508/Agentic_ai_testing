"""Tech stack detection — delegates to enry/scc/pathlib cascading detection.

No hardcoded LANGUAGE_EXTENSIONS or FRAMEWORK_HINTS maps.
Language detection is driven by OSS tools (enry → scc → pathlib fallback).
"""

from __future__ import annotations

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.detect_languages import detect_languages, format_detection_for_prompt
from harness.tools.registry import registry


class TechStackDetectorTool(BaseTool):
    """Detect languages and frameworks from project files.

    Uses cascading detection: enry (GitHub Linguist) → scc → pathlib fallback.
    No hardcoded language extension maps.
    """

    default_level = "allow"
    name = "tech_stack_detector"
    description = "Detect languages and frameworks from project files."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to scan. Defaults to current directory.",
                        "default": ".",
                    },
                },
            },
        )

    async def run(self, path: str = ".") -> ToolResult:
        detection = await detect_languages(path)

        if not detection.languages:
            return ToolResult(
                success=False,
                output="Could not detect any languages.",
            )

        formatted = format_detection_for_prompt(detection)

        return ToolResult(
            success=True,
            output=formatted,
            data={
                "languages": detection.languages,
                "primary_language": detection.languages[0]["name"] if detection.languages else None,
                "source": detection.source,
                "detected_files": detection.detected_files,
            },
        )


registry.register(TechStackDetectorTool(), toolset="read")
