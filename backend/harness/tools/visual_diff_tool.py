"""Visual diff tool — screenshot comparison for visual regression detection.

Uses pixelmatch-py (Python port of the library Playwright uses internally).
Same battle-tested algorithm as Playwright's toHaveScreenshot() + BackstopJS.

Browser automation uses Playwright (browser.py) for capture.
Visual comparison uses pixelmatch-py for diffing.
HTML report with slider overlay for human review.

Agent workflow:
  1. browser_navigate / computer_use → take "before" screenshot
  2. Make UI changes
  3. browser_navigate / computer_use → take "after" screenshot
  4. visual_diff(before, after) → pixelmatch diff + stats + HTML report
  5. If diff_pct > threshold, flag as visual regression
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.tools.registry import registry
from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)


def _diff_images(before_path: str, after_path: str, threshold: float = 0.1) -> dict:
    """Compare two images using pixelmatch-py (same engine Playwright uses).

    Args:
        threshold: Matching threshold 0-1 (default 0.1). Lower = more sensitive.
                   pixelmatch default is 0.1.

    Returns dict with diff stats + diff image bytes.
    """
    from PIL import Image
    from pixelmatch.contrib.PIL import pixelmatch

    img_a = Image.open(before_path).convert("RGBA")
    img_b = Image.open(after_path).convert("RGBA")

    # Match dimensions
    if img_a.size != img_b.size:
        w = max(img_a.width, img_b.width)
        h = max(img_a.height, img_b.height)
        img_a = img_a.resize((w, h), Image.LANCZOS)
        img_b = img_b.resize((w, h), Image.LANCZOS)

    img_diff = Image.new("RGBA", img_a.size)

    # pixelmatch returns number of mismatched pixels
    # includeAA=True enables anti-aliasing detection (Playwright's default)
    mismatched = pixelmatch(img_a, img_b, img_diff, threshold=threshold, includeAA=True, alpha=0.3)

    total = img_a.width * img_a.height
    diff_pct = round(mismatched / total * 100, 4) if total else 0.0

    buf = io.BytesIO()
    img_diff.save(buf, format="PNG")
    diff_bytes = buf.getvalue()

    return {
        "total_pixels": total,
        "changed_pixels": mismatched,
        "diff_pct": diff_pct,
        "diff_image_bytes": diff_bytes,
        "width": img_a.width,
        "height": img_a.height,
    }


def _build_html_report(before_b64: str, after_b64: str, diff_b64: str, stats: dict) -> str:
    """Interactive HTML comparison report with slider overlay (BackstopJS-style)."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Visual Diff Report</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#1a1a2e; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; padding:2rem; }}
h1 {{ font-size:1.5rem; margin-bottom:0.5rem; }}
.stats {{ display:flex; gap:1.5rem; margin-bottom:1.5rem; flex-wrap:wrap; }}
.stat {{ background:#16213e; padding:1rem 1.5rem; border-radius:12px; min-width:120px; }}
.stat .num {{ font-size:1.8rem; font-weight:700; }}
.stat .num.pass {{ color:#4ade80; }} .stat .num.fail {{ color:#f87171; }}
.stat .label {{ font-size:0.75rem; text-transform:uppercase; color:#888; margin-top:0.25rem; }}
.comparison {{ position:relative; width:100%; max-width:1200px; }}
.comparison img {{ width:100%; display:block; user-select:none; }}
.slider {{ position:absolute; top:0; bottom:0; left:50%; width:4px; background:#fff; cursor:ew-resize; z-index:10; }}
.after {{ position:absolute; top:0; left:0; width:50%; overflow:hidden; }}
.after img {{ max-width:none; }}
.labels {{ display:flex; justify-content:space-between; margin-top:0.5rem; font-size:0.8rem; color:#888; }}
.diff {{ margin-top:1.5rem; border-radius:12px; overflow:hidden; max-width:1200px; }}
.verdict {{ margin-top:1rem; padding:0.75rem 1rem; border-radius:8px; font-weight:600; }}
.verdict.pass {{ background:#064e3b; color:#4ade80; }}
.verdict.fail {{ background:#450a0a; color:#f87171; }}
</style></head><body>
<h1>Visual Regression Report</h1>
<div class="stats">
  <div class="stat"><div class="num {'pass' if stats['diff_pct'] < 1 else 'fail'}">{stats['diff_pct']}%</div><div class="label">Changed</div></div>
  <div class="stat"><div class="num">{stats['changed_pixels']:,}</div><div class="label">Pixels changed</div></div>
  <div class="stat"><div class="num">{stats['total_pixels']:,}</div><div class="label">Total pixels</div></div>
  <div class="stat"><div class="num">{stats['width']}x{stats['height']}</div><div class="label">Dimensions</div></div>
</div>
<div class="comparison">
  <div class="before"><img src="data:image/png;base64,{before_b64}" alt="Before"></div>
  <div class="after" id="after"><img src="data:image/png;base64,{after_b64}" alt="After"></div>
  <div class="slider" id="slider"></div>
</div>
<div class="labels"><span>Before</span><span>After</span></div>
<div class="diff"><img src="data:image/png;base64,{diff_b64}" alt="Diff"></div>
<div class="verdict {'pass' if stats['diff_pct'] < 1 else 'fail'}">
  {'PASS' if stats['diff_pct'] < 1 else 'FAIL'} — {stats['diff_pct']}% of pixels changed
</div>
<script>
(function() {{
  const slider = document.getElementById('slider');
  const after = document.getElementById('after');
  let dragging = false;
  const move = (x) => {{
    const rect = slider.parentElement.getBoundingClientRect();
    const pct = Math.max(0, Math.min(100, (x - rect.left) / rect.width * 100));
    after.style.width = pct + '%';
    slider.style.left = pct + '%';
  }};
  slider.addEventListener('mousedown', () => dragging = true);
  document.addEventListener('mousemove', e => {{ if (dragging) move(e.clientX); }});
  document.addEventListener('mouseup', () => dragging = false);
  slider.addEventListener('touchstart', () => dragging = true);
  document.addEventListener('touchmove', e => {{ if (dragging) move(e.touches[0].clientX); }});
  document.addEventListener('touchend', () => dragging = false);
}})();
</script>
</body></html>"""


import io


class VisualDiffTool(BaseTool):
    name = "visual_diff"
    description = (
        "Compare two screenshots and detect visual regressions. "
        "Uses pixelmatch (the same engine Playwright uses internally). "
        "Generates a diff image + interactive HTML report with slider overlay. "
        "Use after making UI changes to catch visual regressions."
    )
    default_level = "allow"
    capabilities = ["can_visual_diff"]

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema={
            "type": "object",
            "properties": {
                "before": {
                    "type": "string",
                    "description": "Path to 'before' screenshot in sandbox (PNG)",
                },
                "after": {
                    "type": "string",
                    "description": "Path to 'after' screenshot in sandbox (PNG)",
                },
                "threshold": {
                    "type": "number",
                    "description": "pixelmatch threshold 0-1 (default 0.1). Lower = more sensitive.",
                },
            },
            "required": ["before", "after"],
        })

    async def run(self, **kwargs: Any) -> ToolResult:
        before = kwargs.get("before", "")
        after = kwargs.get("after", "")
        threshold = float(kwargs.get("threshold", 0.1))

        if not before or not after:
            return ToolResult(success=False, output="before and after paths required", error="missing_args")

        env = await self._get_env()
        if not env:
            return ToolResult(success=False, output="No sandbox available", error="no_sandbox")

        tmp_dir = f"/tmp/visual_diff_{int(time.time())}"
        os.makedirs(tmp_dir, exist_ok=True)
        host_before = os.path.join(tmp_dir, "before.png")
        host_after = os.path.join(tmp_dir, "after.png")

        try:
            for sp, hp in [(before, host_before), (after, host_after)]:
                r = await env.run(
                    f"base64 {_q(sp)} 2>/dev/null || python3 -c "
                    f"\"import base64,sys; print(base64.b64encode(open('{sp}','rb').read()).decode())\" 2>/dev/null",
                    timeout=30,
                )
                if not r or not r.stdout:
                    return ToolResult(success=False, output=f"Cannot read {sp}", error="read_failed")
                with open(hp, "wb") as f:
                    f.write(base64.b64decode(r.stdout.strip()))

            diff = _diff_images(host_before, host_after, threshold)
            diff_pct = diff["diff_pct"]
            changed = diff["changed_pixels"]

            # Save artifacts
            from harness.testai_constants import get_testai_home
            art_root = os.environ.get("ARTIFACT_ROOT", str(get_testai_home() / "artifacts"))
            ts = int(time.time())
            diff_path = os.path.join(art_root, f"visual_diff_{ts}.png")
            report_path = os.path.join(art_root, f"visual_diff_{ts}.html")
            os.makedirs(art_root, exist_ok=True)

            with open(diff_path, "wb") as f:
                f.write(diff["diff_image_bytes"])

            with open(host_before, "rb") as f:
                b64_before = base64.b64encode(f.read()).decode()
            with open(host_after, "rb") as f:
                b64_after = base64.b64encode(f.read()).decode()
            b64_diff = base64.b64encode(diff["diff_image_bytes"]).decode()
            report_html = _build_html_report(b64_before, b64_after, b64_diff, diff)
            with open(report_path, "w") as f:
                f.write(report_html)

            db = await self._get_db()
            if db:
                try:
                    from harness.context import manager as scope_manager
                    scope = scope_manager.current
                    sid = scope.session_id if scope else "unknown"
                    meta = json.dumps({"tags": "visual-diff", "diff_pct": diff_pct})
                    for path, desc in [(diff_path, f"visual_diff_{ts}.png"),
                                       (report_path, "Visual diff HTML report")]:
                        await db.execute(
                            "INSERT INTO artifacts (session_id, path, size_bytes, mime_type, description, meta) "
                            "VALUES ($1,$2,$3,$4,$5,$6)",
                            sid, path, os.path.getsize(path),
                            "image/png" if path.endswith(".png") else "text/html",
                            desc, meta,
                        )
                except Exception:
                    pass

            verdict = "PASS" if diff_pct < 1.0 else "FAIL"
            return ToolResult(
                success=diff_pct < 5.0,
                output=(
                    f"Visual diff: {diff_pct}% pixels changed ({changed:,}/{diff['total_pixels']:,}) — {verdict}\n"
                    f"Engine: pixelmatch (threshold: {threshold}, AA filter: on)\n"
                    f"Report: {report_path}"
                ),
                data={
                    "diff_pct": diff_pct,
                    "changed_pixels": changed,
                    "total_pixels": diff["total_pixels"],
                    "width": diff["width"],
                    "height": diff["height"],
                    "diff_image": diff_path,
                    "report": report_path,
                    "verdict": verdict,
                },
            )

        except Exception as e:
            logger.warning("visual_diff failed: %s", e)
            return ToolResult(success=False, output=str(e), error="diff_failed")
        finally:
            for p in [host_before, host_after]:
                try:
                    os.remove(p)
                except Exception:
                    pass
            try:
                os.rmdir(tmp_dir)
            except Exception:
                pass

    async def _get_env(self):
        try:
            from harness.context import manager as scope_manager
            scope = scope_manager.current
            if scope is None:
                return None
            from harness.backends.factory import get_backend
            from harness.memory.db_context import get_db
            _db = get_db()
            if _db is None:
                return None
            return get_backend(_db, scope.session_id)
        except Exception:
            return None

    async def _get_db(self):
        try:
            return get_db()
        except Exception:
            return None


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


registry.register(VisualDiffTool(), toolset="specialized")
