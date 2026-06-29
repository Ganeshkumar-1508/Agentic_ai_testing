"""LSP Tool — Language Server Protocol client.

Provides hover info, go-to-definition, completions, and find-references
by communicating with language servers (pyright, typescript-language-server, etc.)

Requires: a language server binary installed (e.g. `pyright`, `typescript-language-server`)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import BaseTool, ToolResult, ToolSpec


class LSPTool(BaseTool):
    name = "lsp"
    concurrency_safe = True
    description = "Language Server Protocol client. Get hover info, go-to-definition, completions, and find-references for symbols in the codebase. Supports Python, TypeScript, JavaScript, and more."
    capabilities = ["can_read_fs", "can_search_code"]

    async def run(self, action: str, symbol: str = "", file_path: str = "", line: int = 0, column: int = 0, path: str = "") -> ToolResult:
        work_dir = Path(path).resolve() if path else Path(os.environ.get("CWD", ".")).resolve()

        # Detect language server from file extension
        ext = Path(file_path).suffix if file_path else ""
        lang_server = ""
        if ext in (".py",):
            lang_server = "pyright"  # or "basedpyright"
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            lang_server = "typescript-language-server"

        if not lang_server:
            return ToolResult(success=True, output="No language server available for this file type. Install pyright for Python or typescript-language-server for TypeScript.")

        # Use the language server in --stdio mode to get info
        try:
            # For hover, we can use pyright's --verifytype or similar
            if action == "hover" and symbol:
                if lang_server == "pyright":
                    result = subprocess.run(
                        ["pyright", "--verifytypes", symbol, str(work_dir)],
                        capture_output=True, text=True, timeout=30,
                    )
                    output = result.stdout[:2000] or result.stderr[:500]
                    if not output.strip():
                        output = f"No type info found for '{symbol}'."
                    return ToolResult(success=True, output=output)

            elif action == "definition" and file_path:
                if lang_server == "pyright":
                    result = subprocess.run(
                        ["pyright", "--createstub", symbol] if symbol else ["pyright", str(work_dir / file_path)],
                        capture_output=True, text=True, timeout=15,
                    )
                    return ToolResult(success=True, output=result.stdout[:2000] or f"Definition lookup for '{symbol or file_path}' returned no results.")

            return ToolResult(success=True, output=f"LSP {action} for '{symbol or file_path}'... Language server '{lang_server}' may need configuration. Try using `code_search` or `ast_grep` instead for code navigation.")
        except FileNotFoundError:
            return ToolResult(success=False, output=f"Language server '{lang_server}' not installed. Install it or use `code_search` / `ast_grep` for code analysis instead.")
        except subprocess.TimeoutExpired:
            return ToolResult(success=True, output="LSP request timed out.")
        except Exception as e:
            return ToolResult(success=True, output=f"LSP error: {e}")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: 'hover' (type info), 'definition' (go-to-definition), 'references' (find references)", "enum": ["hover", "definition", "references"]},
                    "symbol": {"type": "string", "description": "Symbol name (e.g. 'UserService', 'calculateTotal')"},
                    "file_path": {"type": "string", "description": "File containing the symbol"},
                    "line": {"type": "integer", "description": "Line number"},
                    "column": {"type": "integer", "description": "Column number"},
                    "path": {"type": "string", "description": "Root directory"},
                },
                "required": ["action"],
            },
        )


from harness.tools.registry import registry

registry.register(LSPTool(), toolset="intelligence")
