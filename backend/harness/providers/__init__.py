"""Provider module registry — adapted from Hermes Agent (MIT).

Provider profiles can live in three places (later overrides earlier):
1. Built-in config: DEFAULT_PROVIDERS dict in this file
2. Bundled files: harness/providers/<name>.py (complex providers with custom logic)
3. User plugins: $TESTAI_HOME/providers/<name>.py (user overrides)

Usage:
    from harness.providers import get_provider_profile
    profile = get_provider_profile("openrouter")
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from harness.providers.base import OMIT_TEMPERATURE, ProviderProfile  # noqa: F401

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, ProviderProfile] = {}
_ALIASES: dict[str, str] = {}
_discovered = False


# ── Built-in provider config —───────────────────────────────────────────
# Shallow providers (no custom logic) defined here instead of as separate
# .py files. Each entry is a dict of ProviderProfile kwargs.
# Complex providers (custom build_extra_body, fetch_models, etc.) remain
# as .py files in harness/providers/<name>.py.

DEFAULT_PROVIDERS: list[dict[str, Any]] = [
    dict(name="alibaba", aliases=("dashscope", "alibaba-cloud", "qwen-dashscope"),
         env_vars=("DASHSCOPE_API_KEY",),
         base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    dict(name="alibaba-coding-plan", aliases=("alibaba_coding_plan",),
         env_vars=("DASHSCOPE_API_KEY",),
         base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
         default_aux_model="qwen-max-2025-01-25"),
    dict(name="arcee", aliases=("arcee-ai", "arceeai"),
         env_vars=("ARCEE_API_KEY",),
         base_url="https://api.arcee.ai/v1"),
    dict(name="azure-foundry", aliases=("azure_foundry", "azurefoundry"),
         env_vars=("AZURE_FOUNDRY_API_KEY",),
         base_url="https://foundry.azure.com/v1"),
    dict(name="gmi", aliases=("gmi-cloud", "gmicloud"),
         display_name="GMI Cloud",
         description="GMI Cloud — multi-model direct API (slash-form model IDs)",
         signup_url="https://www.gmicloud.ai/",
         env_vars=("GMI_API_KEY", "GMI_BASE_URL"),
         base_url="https://api.gmi-serving.com/v1",
         auth_type="api_key",
         default_aux_model="google/gemini-3.1-flash-lite-preview",
         fallback_models=("zai-org/GLM-5.1-FP8", "deepseek-ai/DeepSeek-V3.2",
                          "moonshotai/Kimi-K2.5", "google/gemini-3.1-flash-lite-preview",
                          "anthropic/claude-sonnet-4.6", "openai/gpt-5.4")),
    dict(name="huggingface", aliases=("hf", "hugging-face", "huggingface-hub"),
         display_name="HuggingFace",
         description="HuggingFace Inference API",
         signup_url="https://huggingface.co/settings/tokens",
         env_vars=("HF_TOKEN",),
         fallback_models=("Qwen/Qwen3.5-72B-Instruct", "deepseek-ai/DeepSeek-V3.2"),
         base_url="https://router.huggingface.co/v1"),
    dict(name="kilocode", aliases=("kilo-code", "kilocode-ai"),
         env_vars=("KILOCODE_API_KEY",),
         base_url="https://api.kilocode.ai/v1"),
    dict(name="minimax", aliases=("mini-max",),
         api_mode="anthropic_messages",
         env_vars=("MINIMAX_API_KEY",),
         base_url="https://api.minimax.io/anthropic",
         auth_type="api_key",
         default_aux_model="MiniMax-M2.7"),
    dict(name="minimax-cn", aliases=("minimax-china", "minimax_cn"),
         api_mode="anthropic_messages",
         env_vars=("MINIMAX_CN_API_KEY",),
         base_url="https://api.minimaxi.com/anthropic",
         auth_type="api_key",
         default_aux_model="MiniMax-M2.7"),
    dict(name="minimax-oauth", aliases=("minimax_oauth", "minimax-oauth-io"),
         api_mode="anthropic_messages",
         display_name="MiniMax (OAuth)",
         description="MiniMax via OAuth browser flow — no API key required",
         signup_url="https://api.minimax.io/",
         env_vars=(),  # OAuth — tokens in auth.json, not env
         base_url="https://api.minimax.io/anthropic",
         auth_type="oauth_external",
         default_aux_model="MiniMax-M2.7-highspeed"),
    dict(name="novita", aliases=("novita-ai", "novitai"),
         display_name="Novita AI",
         description="Novita AI — LLM inference API",
         signup_url="https://novita.ai/",
         env_vars=("NOVITA_API_KEY",),
         fallback_models=("deepseek/deepseek-v3", "meta-llama/llama-3.1-70b-instruct"),
         base_url="https://api.novita.ai/v3/openai"),
    dict(name="nvidia", aliases=("nvidia-nim",),
         display_name="NVIDIA NIM",
         description="NVIDIA NIM — accelerated inference",
         signup_url="https://build.nvidia.com/",
         env_vars=("NVIDIA_API_KEY",),
         fallback_models=("nvidia/llama-3.1-nemotron-70b-instruct", "nvidia/llama-3.3-70b-instruct"),
         base_url="https://integrate.api.nvidia.com/v1",
         default_max_tokens=16384),
    dict(name="ollama-cloud", aliases=("ollama_cloud", "ollamacloud"),
         env_vars=("OLLAMA_CLOUD_API_KEY",),
         base_url="https://cloud.ollama.ai/v1"),
    dict(name="openai-codex", aliases=("openai_codex", "codex"),
         api_mode="codex_responses",
         env_vars=("OPENAI_API_KEY", "OPENAI_TOKEN"),
         base_url="https://api.openai.com/v1",
         auth_type="api_key"),
    dict(name="stepfun", aliases=("step-fun", "stepfun-ai"),
         env_vars=("STEPFUN_API_KEY",),
         base_url="https://api.stepfun.com/v1"),
    dict(name="xai", aliases=("grok", "x-ai", "x.ai"),
         api_mode="codex_responses",
         env_vars=("XAI_API_KEY",),
         base_url="https://api.x.ai/v1",
         auth_type="api_key"),
    dict(name="xiaomi", aliases=("xiaomi-mimo", "mimo"),
         env_vars=("XIAOMI_MIMO_API_KEY",),
         base_url="https://api.mimo.xiaomi.com/v1"),
    dict(name="zai", aliases=("zai-org", "zai-ai"),
         display_name="ZAI",
         description="ZAI — multi-model API",
         signup_url="https://zai.ord/",
         env_vars=("ZAI_API_KEY",),
         fallback_models=("zai-org/qwq-32b-preview", "zai-org/Qwen3-235B-A22B"),
         base_url="https://api.zai.ord/v1"),
]


def register_provider(profile: ProviderProfile) -> None:
    _REGISTRY[profile.name] = profile
    for alias in profile.aliases:
        _ALIASES[alias] = profile.name


def get_provider_profile(name: str) -> ProviderProfile | None:
    if not _discovered:
        _discover_providers()
    canonical = _ALIASES.get(name, name)
    return _REGISTRY.get(canonical)


def list_providers() -> list[ProviderProfile]:
    if not _discovered:
        _discover_providers()
    seen: set[int] = set()
    result: list[ProviderProfile] = []
    for profile in _REGISTRY.values():
        pid = id(profile)
        if pid not in seen:
            seen.add(pid)
            result.append(profile)
    return result


def _user_providers_dir() -> Path | None:
    """Return ``$TESTAI_HOME/providers/`` if it exists."""
    for candidate in ("TESTAI_HOME", "HOME", "HOMEPATH"):
        base = (Path.cwd() / ".testai") if candidate == "TESTAI_HOME" and not Path(candidate).exists() else Path(candidate)
        d = base / "providers"
        if d.is_dir():
            return d
    return None


def _load_config_providers() -> None:
    """Register providers from DEFAULT_PROVIDERS config dict.
    
    These are shallow providers with no custom logic — pure data.
    File-based providers with the same name will override these
    (last-writer-wins in register_provider).
    """
    for kwargs in DEFAULT_PROVIDERS:
        profile = ProviderProfile(**kwargs)
        register_provider(profile)


def _discover_providers() -> None:
    global _discovered
    if _discovered:
        return
    _discovered = True

    # 1. Built-in config providers (shallow — no custom logic)
    _load_config_providers()

    # 2. Bundled providers — harness/providers/<name>.py
    import pkgutil
    import harness.providers as _pkg
    for _importer, modname, _ispkg in pkgutil.iter_modules(_pkg.__path__):
        if modname.startswith("_") or modname == "base":
            continue
        try:
            importlib.import_module(f"harness.providers.{modname}")
        except ImportError as exc:
            logger.warning("Failed to import provider module %s: %s", modname, exc)
        except Exception:
            pass

    # 3. User plugins — under $TESTAI_HOME/providers/<name>.py
    user_dir = _user_providers_dir()
    if user_dir is not None:
        for child in sorted(user_dir.iterdir()):
            if child.suffix != ".py" or child.name.startswith(("_", ".")):
                continue
            safe_name = child.stem.replace("-", "_")
            module_name = f"_testai_user_provider_{safe_name}"
            if module_name in sys.modules:
                continue
            try:
                spec = importlib.util.spec_from_file_location(module_name, child)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            except Exception as exc:
                logger.warning("Failed to load user provider %s: %s", child.name, exc)
                sys.modules.pop(module_name, None)
