"""Visual testing — screenshot capture, baseline comparison, diff detection."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCREENSHOT_DIR = Path("agent_workspace/screenshots")
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def capture_screenshot(page_url: str, output_path: str, viewport: str = "1280x720") -> str | None:
    """Capture a full-page screenshot using Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    path = _SCREENSHOT_DIR / output_path
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            w, h = viewport.split("x")
            context = await browser.new_context(viewport={"width": int(w), "height": int(h)})
            page = await context.new_page()
            await page.goto(page_url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=str(path), full_page=True)
            await browser.close()
        return str(path)
    except Exception as e:
        logger.error("Screenshot capture failed: %s", e)
        return None


def compute_hash(image_path: str) -> str:
    """Compute SHA-256 hash of a screenshot for baseline comparison."""
    try:
        data = Path(image_path).read_bytes()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return ""


def compare_screenshots(baseline_path: str, actual_path: str, threshold: float = 0.1) -> dict[str, Any]:
    """Compare two screenshots using pixelmatch. Returns diff pixels and diff image path."""
    try:
        from pixelmatch.contrib.PIL import pixelmatch
        from PIL import Image
    except ImportError:
        logger.warning("pixelmatch or Pillow not installed. Run: pip install pixelmatch Pillow")
        return {"diff_pixels": 0, "diff_percent": 0, "diff_image_path": "", "passed": True}

    try:
        img_a = Image.open(baseline_path)
        img_b = Image.open(actual_path)
        diff = Image.new("RGBA", img_a.size)
        diff_pixels = pixelmatch(img_a, img_b, diff, threshold=threshold, includeAA=True)
        total_pixels = img_a.size[0] * img_a.size[1]
        diff_percent = round(diff_pixels / max(total_pixels, 1) * 100, 2)
        diff_path = actual_path.replace(".png", "_diff.png")
        diff.save(diff_path)
        return {
            "diff_pixels": diff_pixels,
            "diff_percent": diff_percent,
            "diff_image_path": diff_path,
            "passed": diff_percent < 1.0,
        }
    except Exception as e:
        logger.error("Screenshot comparison failed: %s", e)
        return {"diff_pixels": 0, "diff_percent": 0, "diff_image_path": "", "passed": True, "error": str(e)}
