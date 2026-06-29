"""Browser automation for TestAI using Playwright with persistent sessions.

Adapted from the pattern in Hermes' browser_tool.py (session-based, element
refs like @e5) but simplified — single Playwright backend, no cloud providers.

Key improvements over the previous browser.py:
- Persistent browser sessions (no launch/close per call)
- Element interaction via Playwright selectors (text, CSS, aria)
- Click, type, scroll, back support
- Page snapshot with accessibility tree
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry, check_any, env_available, binary_available

logger = logging.getLogger(__name__)

# Persistent browser sessions per task_id
_sessions: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


async def _get_session(task_id: str = "default") -> dict[str, Any]:
    """Get or create a persistent browser session for a task."""
    async with _lock:
        if task_id not in _sessions:
            try:
                from playwright.async_api import async_playwright
                p = await async_playwright().start()
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                _sessions[task_id] = {
                    "playwright": p,
                    "browser": browser,
                    "context": context,
                    "page": page,
                    "task_id": task_id,
                }
            except ImportError:
                raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return _sessions[task_id]


async def _close_session(task_id: str = "default") -> None:
    """Close a browser session."""
    async with _lock:
        session = _sessions.pop(task_id, None)
        if session:
            try:
                await session["browser"].close()
                await session["playwright"].stop()
            except Exception:
                pass


# ── Tools ─────────────────────────────────────────────────────────────

class BrowserNavigateTool(BaseTool):
    name = "browser_navigate"
    description = "Navigate to a URL in the browser and return the page title and text content."
    capabilities = ["can_browse_web"]
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object", "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            }, "required": ["url"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        if not url:
            return ToolResult(success=False, output="URL required", error="missing_url")
        try:
            session = await _get_session()
            page = session["page"]
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await page.title()
            body_text = await page.inner_text("body")
            text = body_text[:8000]
            if len(body_text) > 8000:
                text += "\n\n...[truncated]"
            return ToolResult(success=True, output=f"Title: {title}\n\n{text}")
        except Exception as e:
            return ToolResult(success=False, output=str(e), error=str(e))


class BrowserSnapshotTool(BaseTool):
    name = "browser_snapshot"
    description = "Get the current page content as text. Use after navigate to see what's on the page."
    capabilities = ["can_browse_web"]
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object", "properties": {
                "full": {"type": "boolean", "description": "Return full page (default true)", "default": True},
            },
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        full = kwargs.get("full", True)
        try:
            session = _sessions.get("default")
            if not session:
                return ToolResult(success=False, output="No active session. Navigate to a URL first.", error="no_session")
            page = session["page"]
            title = await page.title()
            content = await page.inner_text("body")
            if not full and len(content) > 4000:
                content = content[:4000] + "\n\n...[truncated]"
            return ToolResult(success=True, output=f"Title: {title}\n\n{content}")
        except Exception as e:
            return ToolResult(success=False, output=str(e), error=str(e))


class BrowserClickTool(BaseTool):
    name = "browser_click"
    description = "Click an element on the page. Use text content to identify what to click."
    capabilities = ["can_browse_web"]
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object", "properties": {
                "selector": {"type": "string", "description": "Text of the element to click, CSS selector, or 'text=Button Name'"},
            }, "required": ["selector"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        selector = kwargs.get("selector", "")
        if not selector:
            return ToolResult(success=False, output="Selector required", error="missing_selector")
        try:
            session = _sessions.get("default")
            if not session:
                return ToolResult(success=False, output="No active session. Navigate first.", error="no_session")
            page = session["page"]
            from playwright.async_api import expect
            # Try Playwright's built-in text selectors
            locator = page.locator(selector)
            if await locator.count() == 0:
                # Fallback: try text match
                locator = page.get_by_role("button", name=selector)
                if await locator.count() == 0:
                    locator = page.get_by_text(selector, exact=False).first
            await locator.click(timeout=5000)
            await page.wait_for_timeout(500)
            return ToolResult(success=True, output=f"Clicked '{selector}'")
        except Exception as e:
            return ToolResult(success=False, output=f"Click failed: {e}", error=str(e))


class BrowserTypeTool(BaseTool):
    name = "browser_type"
    description = "Type text into an input field. Use label text or placeholder to identify the field."
    capabilities = ["can_browse_web"]
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object", "properties": {
                "selector": {"type": "string", "description": "Label, placeholder, or CSS selector for the input"},
                "text": {"type": "string", "description": "Text to type"},
            }, "required": ["selector", "text"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        selector = kwargs.get("selector", "")
        text = kwargs.get("text", "")
        if not selector or text is None:
            return ToolResult(success=False, output="Selector and text required", error="missing_args")
        try:
            session = _sessions.get("default")
            if not session:
                return ToolResult(success=False, output="No active session. Navigate first.", error="no_session")
            page = session["page"]
            locator = page.locator(selector)
            if await locator.count() == 0:
                locator = page.get_by_label(selector)
                if await locator.count() == 0:
                    locator = page.get_by_placeholder(selector)
            await locator.fill(text, timeout=5000)
            return ToolResult(success=True, output=f"Typed '{text[:50]}' into '{selector}'")
        except Exception as e:
            return ToolResult(success=False, output=f"Type failed: {e}", error=str(e))


class BrowserScrollTool(BaseTool):
    name = "browser_scroll"
    description = "Scroll the page up or down by ~500px."
    capabilities = ["can_browse_web"]
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object", "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
            }, "required": ["direction"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        direction = kwargs.get("direction", "down")
        if direction not in ("up", "down"):
            return ToolResult(success=False, output="Direction must be 'up' or 'down'", error="bad_direction")
        try:
            session = _sessions.get("default")
            if not session:
                return ToolResult(success=False, output="No active session", error="no_session")
            page = session["page"]
            delta = -500 if direction == "up" else 500
            await page.evaluate(f"window.scrollBy(0, {delta})")
            await page.wait_for_timeout(300)
            return ToolResult(success=True, output=f"Scrolled {direction}")
        except Exception as e:
            return ToolResult(success=False, output=f"Scroll failed: {e}", error=str(e))


class BrowserBackTool(BaseTool):
    name = "browser_back"
    description = "Navigate back to the previous page."
    capabilities = ["can_browse_web"]
    default_level = "allow"

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object", "properties": {}, "required": [],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            session = _sessions.get("default")
            if not session:
                return ToolResult(success=False, output="No active session", error="no_session")
            page = session["page"]
            await page.go_back()
            title = await page.title()
            return ToolResult(success=True, output=f"Navigated back to: {title}")
        except Exception as e:
            return ToolResult(success=False, output=f"Back failed: {e}", error=str(e))


# Register all tools
_check = check_any(binary_available("playwright"), env_available("PLAYWRIGHT_BROWSERS_PATH"))

registry.register(BrowserNavigateTool(), toolset="read", check_fn=_check)
registry.register(BrowserSnapshotTool(), toolset="read", check_fn=_check)
registry.register(BrowserClickTool(), toolset="read", check_fn=_check)
registry.register(BrowserTypeTool(), toolset="read", check_fn=_check)
registry.register(BrowserScrollTool(), toolset="read", check_fn=_check)
registry.register(BrowserBackTool(), toolset="read", check_fn=_check)
