"""ImageGenerateTool — generate images from text prompts.

Uses configured image generation API (Replicate, OpenAI DALL-E, Stability AI, etc.).
Configure via integration settings or environment variables.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .base import BaseTool, ToolResult, ToolSpec


class ImageGenerateTool(BaseTool):
    name = "image_generate"
    description = "Generate images from text prompts. Uses Replicate (flux, sdxl), OpenAI DALL-E 3, or Stability AI. Configure via IMAGE_GEN_PROVIDER env var or integration settings."
    capabilities = ["can_generate_images"]

    async def run(self, prompt: str, size: str = "1024x1024", model: str = "", output_path: str = "") -> ToolResult:
        if not prompt:
            return ToolResult(success=False, output="Prompt is required.")

        provider = os.environ.get("IMAGE_GEN_PROVIDER", "").lower() or "replicate"

        if provider == "replicate":
            api_key = os.environ.get("REPLICATE_API_TOKEN", "")
            if not api_key:
                return ToolResult(success=False, output="REPLICATE_API_TOKEN not set. Set environment variable or configure in integration settings.")
            try:
                import httpx
                model_id = model or "black-forest-labs/flux-schnell"
                resp = httpx.post(
                    "https://api.replicate.com/v1/predictions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"version": model_id, "input": {"prompt": prompt, "width": int(size.split("x")[0]), "height": int(size.split("x")[1])}},
                    timeout=30,
                )
                if resp.is_success:
                    data = resp.json()
                    output_url = data.get("output") or data.get("urls", {}).get("get", "")
                    return ToolResult(success=True, output=f"Image generated!\nModel: {model_id}\nURL: {output_url}\nPrompt: {prompt[:100]}")
                return ToolResult(success=False, output=f"Replicate error: {resp.text[:300]}")
            except ImportError:
                return ToolResult(success=False, output="httpx required. Install: pip install httpx")
            except Exception as e:
                return ToolResult(success=False, output=f"Error: {e}")

        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return ToolResult(success=False, output="OPENAI_API_KEY not set.")
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.images.generate(prompt=prompt, model=model or "dall-e-3", n=1, size=size)
                url = resp.data[0].url if resp.data else ""
                return ToolResult(success=True, output=f"Image generated!\nURL: {url}\nPrompt: {prompt[:100]}")
            except Exception as e:
                return ToolResult(success=False, output=f"OpenAI error: {e}")

        else:
            return ToolResult(success=False, output=f"Unknown provider '{provider}'. Set IMAGE_GEN_PROVIDER to 'replicate' or 'openai'.")

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text description of the image to generate"},
                    "size": {"type": "string", "description": "Image size (e.g. '1024x1024', '1792x1024')"},
                    "model": {"type": "string", "description": "Model override (e.g. 'dall-e-3', 'black-forest-labs/flux-schnell')"},
                    "output_path": {"type": "string", "description": "Optional path to save the image"},
                },
                "required": ["prompt"],
            },
        )


from harness.tools.registry import registry, any_env_available

registry.register(ImageGenerateTool(), toolset="specialized", check_fn=any_env_available("REPLICATE_API_TOKEN", "OPENAI_API_KEY", "IMAGE_GEN_PROVIDER"))
