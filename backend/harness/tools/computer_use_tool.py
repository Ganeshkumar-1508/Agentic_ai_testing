"""ComputerUseTool — browser automation using agent-browser CLI.

Requires: `npm install -g agent-browser` then `agent-browser install`
Or: `pip install agent-browser-cli`

Commands: open, click, fill, type, screenshot, snapshot, scroll, close
See https://agent-browser.dev for full docs.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .base import BaseTool, ToolResult, ToolSpec


def _run_agent_browser(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run an agent-browser command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["agent-browser"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", "agent-browser not installed. Run: npm install -g agent-browser && agent-browser install"
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


class ComputerUseTool(BaseTool):
    name = "computer_use"
    description = "Browser automation: open URLs, click elements, fill forms, take screenshots, scroll, and navigate. Uses agent-browser CLI with accessibility tree for element selection."
    capabilities = ["can_browse_web", "can_interact_with_browser"]

    async def run(self, action: str, url: str = "", selector: str = "", text: str = "", file: str = "", direction: str = "", pixels: int = 100) -> ToolResult:
        if action == "open":
            if url:
                code, out, err = _run_agent_browser(["open", url])
                if code != 0:
                    return ToolResult(success=False, output=err[:500])
                # Also snapshot the page
                code2, snap, _ = _run_agent_browser(["snapshot", "-i", "-c"])
                return ToolResult(success=True, output=f"Opened {url}\n\nAccessibility tree:\n{snap[:2000]}")
            code, out, err = _run_agent_browser(["open"])
            return ToolResult(success=code == 0, output=out or err[:500])

        elif action == "snapshot":
            code, out, err = _run_agent_browser(["snapshot", "-i", "-c"])
            return ToolResult(success=code == 0, output=out[:3000] or err[:500])

        elif action == "click":
            if not selector:
                return ToolResult(success=False, output="Selector required for click (e.g. @e1, #button, a.link)")
            code, out, err = _run_agent_browser(["click", selector])
            return ToolResult(success=code == 0, output=out[:1000] or "Clicked" if code == 0 else err[:500])

        elif action == "fill":
            if not selector or not text:
                return ToolResult(success=False, output="Selector and text required for fill")
            code, out, err = _run_agent_browser(["fill", selector, text])
            return ToolResult(success=code == 0, output="Filled" if code == 0 else err[:500])

        elif action == "type":
            if not selector or not text:
                return ToolResult(success=False, output="Selector and text required for type")
            code, out, err = _run_agent_browser(["type", selector, text])
            return ToolResult(success=code == 0, output="Typed" if code == 0 else err[:500])

        elif action == "screenshot":
            tmp = Path(tempfile.mkdtemp()) / "screenshot.png"
            code, out, err = _run_agent_browser(["screenshot", str(tmp)])
            if code == 0 and tmp.exists():
                return ToolResult(success=True, output=f"Screenshot saved to {tmp} ({tmp.stat().st_size} bytes)")
            return ToolResult(success=False, output=err[:500])

        elif action == "scroll":
            if not direction:
                return ToolResult(success=False, output="Direction required: up, down, left, right")
            cmd = ["scroll", direction]
            if pixels != 100:
                cmd.append(str(pixels))
            code, out, err = _run_agent_browser(cmd)
            return ToolResult(success=code == 0, output=f"Scrolled {direction}" if code == 0 else err[:500])

        elif action == "close":
            code, out, err = _run_agent_browser(["close"])
            return ToolResult(success=code == 0, output="Browser closed" if code == 0 else err[:500])

        elif action == "get_text":
            if not selector:
                return ToolResult(success=False, output="Selector required")
            code, out, err = _run_agent_browser(["get", "text", selector])
            return ToolResult(success=code == 0, output=out[:2000] or err[:500])

        else:
            return ToolResult(success=False, output=f"Unknown action: {action}. Try: open, snapshot, click, fill, type, screenshot, scroll, close, get_text")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: open (URL), snapshot (get page structure), click (@ref), fill (@ref text), type (@ref text), screenshot, scroll (up/down/left/right), close, get_text (@ref)"},
                    "url": {"type": "string", "description": "URL to navigate to (for open action)"},
                    "selector": {"type": "string", "description": "Element selector: @e1 (from snapshot), #id, .class, CSS selector"},
                    "text": {"type": "string", "description": "Text to type or fill"},
                    "file": {"type": "string", "description": "File path (for upload action)"},
                    "direction": {"type": "string", "description": "Scroll direction: up, down, left, right"},
                    "pixels": {"type": "integer", "description": "Pixels to scroll (default 100)"},
                },
                "required": ["action"],
            },
        )


from harness.tools.registry import registry, check_any, env_available, binary_available

registry.register(ComputerUseTool(), toolset="specialized", check_fn=check_any(binary_available("playwright"), env_available("BROWSER_USE_ENABLED")))
