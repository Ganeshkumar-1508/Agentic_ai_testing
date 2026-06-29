"""VisionAnalyzeTool — analyze images/screenshots with a vision-capable LLM.

Port of Hermes' vision_tools.py pattern (MIT license).
Downloads images from URLs or reads local files, converts to base64,
sends to a vision-capable LLM, and returns semantic analysis.

Semantic understanding (Mabl pattern):
  - Level 1: Recognize UI elements (buttons, inputs, nav, etc.)
  - Level 2: Understand patterns across states (logged-in vs guest, mobile vs desktop)
  - Level 3: Judge intent — "can the user still log in?" not "did pixels change?"
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry
from harness.tools.url_safety import is_safe_url

logger = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
_DOWNLOAD_TIMEOUT = 30.0
_DEFAULT_VISION_MODEL = "gpt-4o"  # fallback if none configured


def _detect_mime(path: Path) -> str | None:
    with path.open("rb") as f:
        header = f.read(64)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    return None


async def _download_image(url: str, dest: Path) -> Path:
    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        body = resp.content
        if len(body) > _MAX_IMAGE_BYTES:
            raise ValueError(f"Image too large ({len(body)} bytes, max {_MAX_IMAGE_BYTES})")
        dest.write_bytes(body)
    return dest


def _image_to_base64(path: Path, mime: str | None = None) -> str:
    mime = mime or _detect_mime(path) or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{data}"


class VisionAnalyzeTool(BaseTool):
    name = "vision_analyze"
    default_level = "allow"
    description = (
        "Analyze an image or screenshot using a vision-capable AI. "
        "Understands UI elements, layout, text, and visual intent. "
        "Use this to evaluate screenshots, check if a page looks correct, "
        "or understand visual test failures. "
        "Accepts image URLs or local file paths."
    )
    capabilities = ["can_analyze_images"]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL of the image to analyze (http/https)"},
                    "image_path": {"type": "string", "description": "Local file path of the image"},
                    "question": {
                        "type": "string", "description": "Specific question about the image. "
                        "Examples: 'Is the login button visible and clickable?', "
                        "'Does this page look correct compared to the expected layout?', "
                        "'What UI elements are missing or broken?'",
                    },
                    "detail": {
                        "type": "string", "enum": ["low", "high", "auto"],
                        "description": "Detail level for vision analysis (default: auto)",
                    },
                },
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        image_url = kwargs.get("image_url", "") or ""
        image_path = kwargs.get("image_path", "") or ""
        question = kwargs.get("question", "") or "Describe this image in detail, including any UI elements, text, layout, and visual state."
        detail = kwargs.get("detail", "auto")

        if not image_url and not image_path:
            return ToolResult(success=False, output="Provide image_url or image_path", error="missing_arg")

        # Resolve image to a local file + base64 data URL
        tmp: Path | None = None
        try:
            if image_url:
                if not _is_safe_url(image_url):
                    return ToolResult(success=False, output="Blocked: image URL points to a private/internal address")
                tmp = Path(tempfile.mkdtemp()) / "vision_input"
                await _download_image(image_url, tmp)
                local_path = tmp
            else:
                local_path = Path(image_path)
                if not local_path.exists():
                    return ToolResult(success=False, output=f"Image not found: {image_path}")

            mime = _detect_mime(local_path)
            if not mime:
                return ToolResult(success=False, output=f"Unsupported image format: {local_path.suffix}")

            data_url = _image_to_base64(local_path, mime)

            # Call vision-capable LLM
            analysis = await self._call_vision_llm(data_url, question, detail)
            if not analysis:
                analysis = "The image could not be analyzed. The vision model may not be available."

            # Basic image info for reference
            stats = f"Format: {mime}  |  Size: {local_path.stat().st_size:,} bytes  |  Analysis:\n\n{analysis}"
            return ToolResult(success=True, output=stats, data={"analysis": analysis, "mime": mime})

        except ValueError as e:
            return ToolResult(success=False, output=str(e), error="bad_request")
        except PermissionError as e:
            return ToolResult(success=False, output=str(e), error="blocked")
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, output=f"Download failed (HTTP {e.response.status_code})", error="http_error")
        except Exception as e:
            logger.warning("vision_analyze failed: %s", e)
            return ToolResult(success=False, output=f"Analysis failed: {e}", error="analysis_error")
        finally:
            if tmp and tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    async def _call_vision_llm(self, data_url: str, question: str, detail: str) -> str:
        """Call a vision-capable LLM with the image as a multimodal message."""
        from harness.llm import LLMRouter
        from harness.llm import ChatMessage

        llm = getattr(self, "_llm", None)
        if llm is None:
            try:
                from harness.api.state import get_llm
                llm = get_llm()
            except Exception:
                pass
        if llm is None:
            return "[vision LLM not available — configure a vision-capable provider]"

        messages = [
            ChatMessage(role="user", content=[
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url, "detail": detail}},
            ])
        ]
        model = os.environ.get("VISION_MODEL", "") or _DEFAULT_VISION_MODEL
        try:
            resp = await llm.chat(messages=messages, model=model)
            return resp.content or ""
        except Exception as e:
            logger.warning("Vision LLM call failed: %s", e)
            return ""


registry.register(VisionAnalyzeTool(), toolset="specialized")
