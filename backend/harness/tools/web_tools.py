from __future__ import annotations

import json
from typing import Any

import httpx

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry, any_env_available


class WebSearchTool(BaseTool):
    default_level = "allow"
    concurrency_safe = True
    concurrency_safe = True
    name = "web_search"
    description = "Search the web for information. Returns titles and URLs. Use when you need to find API documentation, test patterns, or troubleshooting information."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = min(kwargs.get("max_results", 5), 10)

        if not query:
            return ToolResult(success=False, output="No query provided", error="missing_query")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "TestAI/1.0"},
                )
                results = _parse_ddg_results(resp.text, max_results)
                if not results:
                    return ToolResult(success=True, output="No search results found.", data={"results": []})
                output = "\n\n".join(
                    f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet']}"
                    for i, r in enumerate(results)
                )
                return ToolResult(success=True, output=output, data={"results": results, "query": query})
        except Exception as e:
            return ToolResult(success=False, output=f"Search failed: {e}", error=str(e))


def _parse_ddg_results(html: str, max_results: int) -> list[dict[str, str]]:
    results = []
    import re
    for match in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([\s\S]*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)</a>',
        html, re.DOTALL,
    ):
        if len(results) >= max_results:
            break
        url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


class WebFetchTool(BaseTool):
    default_level = "allow"
    concurrency_safe = True
    concurrency_safe = True
    name = "web_fetch"
    description = "Fetch and extract the text content from a URL. Use to read API documentation, changelogs, or error solutions."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_length": {"type": "integer", "description": "Max characters to return (default 8000)", "default": 8000},
                },
                "required": ["url"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        max_length = kwargs.get("max_length", 8000)

        if not url:
            return ToolResult(success=False, output="No URL provided", error="missing_url")

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "TestAI/1.0"},
                )
                content = resp.text
                text = _extract_text(content)
                if len(text) > max_length:
                    text = text[:max_length] + "\n\n...[truncated]"
                return ToolResult(
                    success=True,
                    output=f"Fetched {url} ({len(text)} chars)\n\n{text}",
                    data={"url": url, "content_length": len(text)},
                )
        except Exception as e:
            return ToolResult(success=False, output=f"Fetch failed: {e}", error=str(e))


def _extract_text(html: str) -> str:
    import re
    for tag in ("script", "style", "nav", "footer", "header"):
        html = re.sub(rf"<{tag}[^>]*>[\s\S]*?</{tag}>", "", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return "\n".join(lines)


class TodoTool(BaseTool):
    default_level = "allow"
    concurrency_safe = True
    concurrency_safe = True
    name = "todo"
    description = "Manage a task list for multi-step workflows. Create, list, update, and mark tasks as complete."

    def __init__(self):
        super().__init__()
        self._tasks: list[dict[str, Any]] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "update", "complete"],
                        "description": "create: add tasks. list: show all. update: change description. complete: mark done.",
                    },
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of task descriptions (for create action)",
                    },
                    "id": {
                        "type": "integer",
                        "description": "Task ID (for update/complete actions)",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description (for update action)",
                    },
                },
                "required": ["action"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "create":
            tasks = kwargs.get("tasks", [])
            if not tasks:
                return ToolResult(success=False, output="Provide at least one task", error="missing_tasks")
            for t in tasks:
                self._tasks.append({"id": len(self._tasks) + 1, "description": t, "done": False})
            return ToolResult(
                success=True,
                output=f"Created {len(tasks)} task(s). Use todo list to see them.",
                data={"tasks": self._tasks},
            )

        if action == "list":
            if not self._tasks:
                return ToolResult(success=True, output="No tasks. Use todo create to add some.")
            lines = []
            for t in self._tasks:
                status = "x" if t["done"] else " "
                lines.append(f"[{status}] {t['id']}. {t['description']}")
            return ToolResult(success=True, output="\n".join(lines), data={"tasks": self._tasks})

        if action == "complete":
            task_id = kwargs.get("id")
            if not task_id:
                return ToolResult(success=False, output="Provide task id", error="missing_id")
            for t in self._tasks:
                if t["id"] == task_id:
                    t["done"] = True
                    return ToolResult(success=True, output=f"Task {task_id} completed.", data={"task": t})
            return ToolResult(success=False, output=f"Task {task_id} not found", error="not_found")

        if action == "update":
            task_id = kwargs.get("id")
            desc = kwargs.get("description", "")
            if not task_id or not desc:
                return ToolResult(success=False, output="Provide task id and description", error="missing_params")
            for t in self._tasks:
                if t["id"] == task_id:
                    t["description"] = desc
                    return ToolResult(success=True, output=f"Task {task_id} updated.", data={"task": t})
            return ToolResult(success=False, output=f"Task {task_id} not found", error="not_found")

        return ToolResult(success=False, output=f"Unknown action: {action}", error="bad_action")


registry.register(WebSearchTool(), toolset="read", check_fn=any_env_available("OPENAI_API_KEY", "TAVILY_API_KEY"))
registry.register(WebFetchTool(), toolset="read")
registry.register(TodoTool(), toolset="read")


