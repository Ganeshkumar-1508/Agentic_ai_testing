"""Agent tool for on-demand language detection.

Wraps detect_languages() for agent use.
Uses cascading detection: enry → scc → pathlib fallback.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.detect_languages import detect_languages, format_detection_for_prompt
from harness.tools.registry import registry


class DetectLanguagesTool(BaseTool):
    """Detect programming languages in a repository directory.

    Uses enry (GitHub Linguist compatible, 600+ languages) when available,
    falls back to scc (200+ languages), then pathlib extension counting.

    No hardcoded language maps — all detection is driven by OSS tools.
    """

    name = "detect_languages"
    description = (
        "Detect programming languages, frameworks, and file composition in a "
        "repository directory. Uses enry (GitHub Linguist compatible) or scc "
        "for accurate detection. Returns language breakdown by percentage."
    )
    default_level = "allow"
    capabilities = ["can_read_fs"]

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
                output="Could not detect any languages. Ensure enry or scc is installed, "
                       "or the directory contains recognizable source files.",
            )

        formatted = format_detection_for_prompt(detection)

        # Also return structured data for programmatic use
        return ToolResult(
            success=True,
            output=formatted,
            data={
                "languages": detection.languages,
                "source": detection.source,
                "detected_files": detection.detected_files,
            },
        )


registry.register(DetectLanguagesTool(), toolset="read")
