"""ApplyPatchTool — apply multi-file diffs in a single call.

Accepts a unified diff format with file markers and applies all changes atomically.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .base import BaseTool, ToolResult, ToolSpec


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "Apply a multi-file diff/patch to the codebase. Accepts unified diff format with file paths."
    capabilities = ["can_write_fs"]

    async def run(self, patch_text: str, path: str = "") -> ToolResult:
        work_dir = Path(path).resolve() if path else Path(os.environ.get("CWD", ".")).resolve()

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False, encoding="utf-8") as f:
                f.write(patch_text)
                patch_path = f.name

            result = subprocess.run(
                ["git", "apply", "--check", patch_path],
                capture_output=True, text=True, timeout=15, cwd=str(work_dir),
            )
            if result.returncode != 0:
                os.unlink(patch_path)
                return ToolResult(success=False, output=f"Patch check failed:\n{result.stderr[:500]}")

            result = subprocess.run(
                ["git", "apply", patch_path],
                capture_output=True, text=True, timeout=15, cwd=str(work_dir),
            )
            os.unlink(patch_path)

            if result.returncode == 0:
                return ToolResult(success=True, output="Patch applied successfully.")
            return ToolResult(success=False, output=f"Patch apply failed:\n{result.stderr[:500]}")
        except FileNotFoundError:
            return ToolResult(success=False, output="git not available. apply_patch requires git.")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="Patch apply timed out.")
        except Exception as e:
            return ToolResult(success=False, output=f"Patch error: {e}")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "patch_text": {
                        "type": "string",
                        "description": "Unified diff/patch text with file paths (e.g. '--- a/file.ts\\n+++ b/file.ts\\n@@ ... @@' )",
                    },
                    "path": {"type": "string", "description": "Optional root directory of the repo"},
                },
                "required": ["patch_text"],
            },
        )


from harness.tools.registry import registry

registry.register(ApplyPatchTool(), toolset="write")
