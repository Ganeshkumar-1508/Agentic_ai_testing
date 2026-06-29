"""GrepTool — search file contents by regex or literal string."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .base import BaseTool, ToolResult, ToolSpec


class GrepTool(BaseTool):
    name = "grep"
    concurrency_safe = True
    description = "Search file contents by regex or literal string. Returns matching file paths and line numbers."
    capabilities = ["can_read_fs"]

    async def run(self, pattern: str, include: str = "", path: str = "", literal: bool = False, max_results: int = 50) -> ToolResult:
        search_root = Path(path).resolve() if path else Path(os.environ.get("CWD", ".")).resolve()
        cmd = ["rg" if not literal else "rg", "--line-number", "--no-heading"]

        if literal:
            cmd.append("--fixed-strings")
        if include:
            cmd.extend(["--glob", include])

        cmd.append("--max-count", str(max_results))
        cmd.append(pattern)
        cmd.append(str(search_root))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")[:max_results]
                return ToolResult(success=True, output="\n".join(lines))
            elif result.returncode == 1:
                return ToolResult(success=True, output="No matches found.")
            else:
                return ToolResult(success=False, output=f"Grep error: {result.stderr[:200]}")
        except FileNotFoundError:
            # Fallback to Python grep if ripgrep not available
            try:
                matches = []
                for fpath in search_root.rglob("*"):
                    if not fpath.is_file():
                        continue
                    if include and not Path(fpath).match(include):
                        continue
                    try:
                        text = fpath.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue
                    for i, line in enumerate(text.split("\n"), 1):
                        if (literal and pattern in line) or (not literal and __import__("re").search(pattern, line)):
                            matches.append(f"{fpath.relative_to(search_root)}:{i}:{line[:120]}")
                            if len(matches) >= max_results:
                                break
                    if len(matches) >= max_results:
                        break
                if matches:
                    return ToolResult(success=True, output="\n".join(matches))
                return ToolResult(success=True, output="No matches found.")
            except Exception as e2:
                return ToolResult(success=False, output=f"Grep failed: {e2}")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="Grep timed out after 30s")
        except Exception as e:
            return ToolResult(success=False, output=f"Grep error: {e}")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or literal pattern to search for"},
                    "include": {"type": "string", "description": "Optional file glob filter (e.g. '*.ts', '*.py')"},
                    "path": {"type": "string", "description": "Optional root directory"},
                    "literal": {"type": "boolean", "description": "Treat pattern as literal string, not regex"},
                    "max_results": {"type": "integer", "description": "Max results (default 50)"},
                },
                "required": ["pattern"],
            },
        )


from harness.tools.registry import registry

registry.register(GrepTool(), toolset="read")
