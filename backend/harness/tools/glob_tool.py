"""GlobTool — find files by glob pattern.

Patterns: src/**/*.test.ts, *.py, **/*.{ts,tsx}
"""

from __future__ import annotations

import glob as _glob
import os
from pathlib import Path

from .base import BaseTool, ToolResult, ToolSpec


class GlobTool(BaseTool):
    name = "glob"
    concurrency_safe = True
    description = "Find files by glob pattern (e.g. 'src/**/*.test.ts', '**/*.py'). Returns matching file paths."
    capabilities = ["can_read_fs"]

    async def run(self, pattern: str, path: str = "") -> ToolResult:
        search_root = Path(path).resolve() if path else Path(os.environ.get("CWD", ".")).resolve()
        full_pattern = str(search_root / pattern) if not pattern.startswith("/") else pattern

        try:
            matches = _glob.glob(full_pattern, recursive=True)
            # Filter to only files (not directories)
            files = sorted(m for m in matches if os.path.isfile(m))
            if not files:
                return ToolResult(success=True, output="No files found matching the pattern.")
            # Return relative paths
            rel = [os.path.relpath(f, search_root) for f in files[:200]]
            output = "\n".join(rel)
            if len(files) > 200:
                output += f"\n\n... and {len(files) - 200} more files."
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output=f"Glob error: {e}")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. 'src/**/*.test.ts', '*.py', '**/*.{ts,tsx}')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional root directory. Defaults to current working directory.",
                    },
                },
                "required": ["pattern"],
            },
        )


from harness.tools.registry import registry

registry.register(GlobTool(), toolset="read")
