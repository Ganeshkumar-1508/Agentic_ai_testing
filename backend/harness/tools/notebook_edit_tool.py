"""Notebook edit tool — create or edit Jupyter notebook cells.
Port of OpenHarness notebook_edit_tool (MIT license)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry


class NotebookEditTool(BaseTool):
    name = "notebook_edit"
    description = "Create or edit a Jupyter notebook cell without requiring nbformat."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the .ipynb file"},
                    "cell_index": {"type": "integer", "description": "Zero-based cell index"},
                    "new_source": {"type": "string", "description": "Replacement or appended source for the target cell"},
                    "mode": {"type": "string", "enum": ["replace", "append"], "description": "replace or append to existing cell"},
                    "create_if_missing": {"type": "boolean", "description": "Create notebook if not found"},
                },
                "required": ["path", "cell_index", "new_source"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        path = Path(kwargs.get("path", ""))
        cell_index = int(kwargs.get("cell_index", 0))
        new_source = kwargs.get("new_source", "")
        mode = kwargs.get("mode", "replace")
        create = bool(kwargs.get("create_if_missing", True))
        if not path.exists() and not create:
            return ToolResult(success=False, output=f"Notebook not found: {path}")
        notebook = json.loads(path.read_text("utf-8")) if path.exists() else {
            "cells": [], "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5,
        }
        cells = notebook.setdefault("cells", [])
        while len(cells) <= cell_index:
            cells.append({"cell_type": "code", "metadata": {}, "source": "", "outputs": [], "execution_count": None})
        cell = cells[cell_index]
        existing = cell.get("source", "")
        if isinstance(existing, list):
            existing = "".join(existing)
        cell["source"] = new_source if mode == "replace" else f"{existing}{new_source}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(notebook, indent=2) + "\n", "utf-8")
        return ToolResult(success=True, output=f"Updated notebook cell {cell_index} in {path}")


registry.register(NotebookEditTool(), toolset="specialized")
