"""WebExtractTool — structured content extraction from web pages.

Uses readability-lxml (Mozilla's Readability algorithm) for proper
content extraction — strips navigation, sidebars, footers, and returns
the main article content with title and metadata. Falls back to
html2text when readability is not available.

Adapted from the concept behind Hermes' web_extract_tool but simplified
for TestAI — single backend, no plugin system needed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry

logger = logging.getLogger(__name__)


class WebExtractTool(BaseTool):
    name = "web_extract"
    default_level = "allow"
    description = (
        "Extract the main content from a web page. Uses Mozilla's Readability "
        "algorithm to strip navigation, ads, sidebars, and footers — returns "
        "only the article content with title and metadata. Use instead of "
        "web_fetch when you need clean, readable content from documentation, "
        "blog posts, or articles."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to extract content from.",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Max characters (default 15000).",
                        "default": 15000,
                    },
                },
                "required": ["url"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        max_length = int(kwargs.get("max_length", 15000))

        if not url:
            return ToolResult(success=False, output="URL required", error="missing_url")

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    },
                )
                html = resp.text
        except Exception as e:
            return ToolResult(success=False, output=f"Fetch failed: {e}", error=str(e))

        # Try readability-lxml first (best extraction)
        title, text = await self._extract_readability(html, url)

        # Fallback to html2text or simple extraction
        if not text:
            title, text = self._extract_fallback(html, url)

        if not text:
            return ToolResult(
                success=False,
                output=f"Could not extract content from {url}.",
                error="extraction_failed",
            )

        if len(text) > max_length:
            text = text[:max_length] + "\n\n...[truncated]"

        output = f"# {title}\n\n" if title else ""
        output += f"Source: {url}\n\n{text.strip()}"

        return ToolResult(
            success=True,
            output=output,
            data={"url": url, "title": title, "content_length": len(text)},
        )

    async def _extract_readability(
        self, html: str, url: str,
    ) -> tuple[str | None, str | None]:
        """Extract using readability-lxml (Mozilla Readability algorithm)."""
        try:
            from readability import Document
            doc = Document(html, url=url)
            title = doc.title()
            content_html = doc.summary()
            # Convert HTML to plain text
            import re
            text = re.sub(r"<[^>]+>", " ", content_html)
            text = re.sub(r"\s+", " ", text).strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            return title, "\n".join(lines)
        except ImportError:
            logger.debug("readability-lxml not installed, trying html2text")
            return await self._extract_html2text(html, url)
        except Exception as e:
            logger.debug("readability extraction failed: %s", e)
            return None, None

    async def _extract_html2text(
        self, html: str, url: str,
    ) -> tuple[str | None, str | None]:
        """Extract using html2text (markdown converter)."""
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            markdown = h.handle(html)
            lines = markdown.split("\n")
            title = None
            for line in lines:
                if line.startswith("# ") or line.startswith("#"):
                    title = line.lstrip("#").strip()
                    break
            return title, markdown
        except ImportError:
            logger.debug("html2text not installed, using fallback")
            return self._extract_fallback(html, url)
        except Exception as e:
            logger.debug("html2text extraction failed: %s", e)
            return None, None

    def _extract_fallback(
        self, html: str, url: str,
    ) -> tuple[str | None, str | None]:
        """Simple regex-based fallback extraction."""
        import re

        # Extract title
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_match.group(1).strip() if title_match else None

        # Remove script, style, nav, footer, header
        for tag in ("script", "style", "nav", "footer", "header", "aside"):
            html = re.sub(rf"<{tag}[^>]*>[\s\S]*?</{tag}>", "", html, flags=re.I)

        # Get body content
        body_match = re.search(r"<body[^>]*>([\s\S]*)</body>", html, re.I)
        body = body_match.group(1) if body_match else html

        text = re.sub(r"<[^>]+>", " ", body)
        text = re.sub(r"\s+", " ", text).strip()
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        return title, "\n".join(lines) if lines else text


registry.register(WebExtractTool(), toolset="read")
