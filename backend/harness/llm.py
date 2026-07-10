from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from collections import deque
from typing import Any, AsyncGenerator

import httpx

from harness.providers.base import OMIT_TEMPERATURE, ProviderProfile

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "deepseek-v4-flash")


# ---------------------------------------------------------------------------
# Message types (unchanged — shared between router and callers)
# ---------------------------------------------------------------------------


class ChatMessage:
    def __init__(
        self,
        role: str,
        content: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.role = role
        self.content = content
        self.tool_call_id = tool_call_id
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        # DeepSeek v4 thinking mode requires reasoning_content on assistant
        # tool-call messages; omit it causes HTTP 400 on replay. Include even
        # when empty (use a single space to satisfy non-empty checks).
        rc = self.reasoning_content
        if rc is not None:
            d["reasoning_content"] = rc if rc else " "
        elif self.tool_calls:
            d["reasoning_content"] = " "
        for k, v in self.metadata.items():
            d[k] = v
        return d


class CompletionResponse:
    def __init__(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, int] | None = None,
        model: str = "",
        reasoning_content: str | None = None,
    ):
        self.content = content
        self.tool_calls = tool_calls
        self.usage = usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.model = model
        self.reasoning_content = reasoning_content


def messages_to_dicts(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    result = []
    for m in messages:
        result.append(_strip_private_metadata(m.to_dict()))
    return result


def _strip_private_metadata(msg: dict[str, Any]) -> dict[str, Any]:
    """Strip top-level keys prefixed with ``_`` before sending to the provider.

    Internal metadata keys (``_compressed_summary``, ``_pending_steer``,
    ``_tool_call_id`` aliases, etc.) must NEVER leak to the wire.
    Strict gateways (opencode-go, Fireworks, Mistral, Moonshot) reject
    unknown keys with ``"Extra inputs are not permitted"``, poisoning
    every subsequent request in the session. Prefix with ``_`` on the
    way in, strip here on the way out. Pattern from hermes-agent
    `agent/transports/chat_completions.py`.
    """
    return {k: v for k, v in msg.items() if not k.startswith("_")}


def _to_tool_call_dict(tc: Any) -> dict[str, Any]:
    return {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.function.name if tc.function else "",
            "arguments": tc.function.arguments if tc.function else "",
        },
    }


def _extract_chunk_text(chunk: Any) -> str:
    """Extract text content from an OpenAI streaming chunk."""
    try:
        choices = chunk.choices
        if not choices:
            return ""
        delta = choices[0].delta
        if delta is None:
            return ""
        if isinstance(delta, dict):
            return delta.get("content") or ""
        return getattr(delta, "content", None) or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Router — uses ProviderProfile from harness.providers.base
# ---------------------------------------------------------------------------


class LLMRouter:
    """Holds provider profiles, resolves by model name, dispatches by api_mode."""

    def __init__(self):
        self._profiles: dict[str, ProviderProfile] = {}       # provider name → profile
        self._profiles_by_model: dict[str, ProviderProfile] = {}  # model → profile
        self._roles: dict[str, str] = {}
        # Provider failover: ring buffer per provider + circuit breaker state
        self._event_rings: dict[str, deque] = {}
        self._circuit_breakers: dict[str, dict[str, Any]] = {}
        self._db_provider: Any = None
        # Wire of harness.pricing_cache (C00-C-3, F15/CC6):
        # per-model quality tracking. The router consults
        # ``get_provider_quality`` from ``get_model_for_role`` so a
        # model that is silently degrading doesn't keep getting
        # picked. Greptile's caveat: "don't assume model-agnosticism
        # is free" — measure recall and precision per provider.
        self._provider_health: dict[str, dict[str, Any]] = {}
        # Global concurrency limiter: OpenCode Go / Console Go API
        # cannot handle parallel requests from subagents spawned
        # simultaneously. Serialize all LLM calls to prevent
        # "Upstream request failed" errors.
        self._api_semaphore = asyncio.Semaphore(1)

    def _record_usage(self, model: str, usage: Any) -> None:
        """Record token usage from an API response."""
        db = self._db_provider
        if not db:
            return
        if isinstance(usage, dict):
            inp = usage.get("prompt_tokens", 0)
            out = usage.get("completion_tokens", 0)
        else:
            inp = getattr(usage, "prompt_tokens", 0)
            out = getattr(usage, "completion_tokens", 0)
        if not inp and not out:
            return
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self._save_usage(inp, out, model))
        except RuntimeError:
            pass

    async def _save_usage(self, inp: int, out: int, model: str) -> None:
        db = self._db_provider
        if not db:
            return
        cost = 0.0
        try:
            from harness.pricing_cache import get_pricing_cache
            cache = get_pricing_cache()
            rates = await cache.get_rate(model)
            if rates:
                cost = (inp / 1000) * rates.get("input", 0) + (out / 1000) * rates.get("output", 0)
        except Exception:
            pass
        try:
            await db.execute(
                "INSERT INTO token_usage (session_id, model, input_tokens, output_tokens, estimated_cost_usd, timestamp) VALUES ($1,$2,$3,$4,$5,NOW())",
                "system", model, inp, out, round(cost, 6),
            )
        except Exception:
            # Fallback: if session_id FK fails, try without it
            try:
                await db.execute(
                    "INSERT INTO token_usage (model, input_tokens, output_tokens, estimated_cost_usd, timestamp) VALUES ($1,$2,$3,$4,NOW())",
                    model, inp, out, round(cost, 6),
                )
            except Exception:
                pass

    def set_db(self, db: Any) -> None:
        self._db_provider = db

    def record_provider_outcome(
        self, model: str, success: bool, latency_ms: float, error_type: str = "",
    ) -> None:
        """Track per-model call outcomes for quality scoring (F15/CC6)."""
        h = self._provider_health.setdefault(model, {
            "calls": 0, "successes": 0, "failures": 0,
            "total_latency_ms": 0.0, "max_latency_ms": 0.0,
            "last_error": "", "last_seen": 0.0,
        })
        h["calls"] += 1
        h["total_latency_ms"] += latency_ms
        if latency_ms > h["max_latency_ms"]:
            h["max_latency_ms"] = latency_ms
        h["last_seen"] = time.time()
        if success:
            h["successes"] += 1
            self.record_success(model)
        else:
            h["failures"] += 1
            h["last_error"] = error_type[:200]
            self.record_failure(model)

    def get_provider_quality(self, model: str) -> float:
        """Return a 0.0-1.0 quality score for a model.

        Pure success-rate with a latency penalty. Unknown models
        return 0.5 (neutral). Below 0.2 the model is considered
        unhealthy. Greptile: "deprioritize latency … a developer
        would rather wait a little longer and get something accurate
        than get a fast answer they can't trust" — so success-rate
        is weighted higher than latency.
        """
        h = self._provider_health.get(model)
        if not h or h["calls"] == 0:
            return 0.5
        success_rate = h["successes"] / h["calls"]
        avg_latency = h["total_latency_ms"] / h["calls"]
        # Latency penalty: 0 at 2s, 0.3 at 32s, linear in between.
        latency_penalty = min(0.3, max(0.0, (avg_latency - 2000.0) / 30000.0))
        return max(0.0, min(1.0, success_rate - latency_penalty))

    def get_provider_health(self) -> dict[str, dict[str, Any]]:
        """Read-only snapshot of per-model quality stats (for the dashboard)."""
        return {k: dict(v) for k, v in self._provider_health.items()}

    def record_event(self, provider: str, event_type: str, message: str = "") -> None:
        """Record a provider event in the ring buffer and optionally persist to DB."""
        if provider not in self._event_rings:
            self._event_rings[provider] = deque(maxlen=100)
        ev = {
            "provider": provider,
            "type": event_type,
            "message": message,
            "timestamp": time.time(),
        }
        self._event_rings[provider].append(ev)
        # Persist to DB if available
        if self._db_provider:
            import asyncio
            try:
                asyncio.create_task(self._db_provider.execute(
                    "INSERT INTO provider_events (provider, event_type, message, created_at) VALUES ($1, $2, $3, $4)",
                    provider, event_type, message, datetime.datetime.now(),
                ))
            except Exception:
                pass

    def get_events(self, provider: str = "", limit: int = 50) -> list[dict]:
        """Get failover events. If provider is empty, return all."""
        result = []
        for prov, ring in self._event_rings.items():
            if provider and prov != provider:
                continue
            result.extend(list(ring))
        result.sort(key=lambda x: x["timestamp"], reverse=True)
        return result[:limit]

    def get_circuit_breakers(self) -> dict[str, dict[str, Any]]:
        """Read-only snapshot of circuit breaker states for monitoring."""
        return {k: dict(v) for k, v in self._circuit_breakers.items()}

    def is_circuit_open(self, provider: str) -> bool:
        """Check if circuit breaker is open for a provider."""
        cb = self._circuit_breakers.get(provider)
        if not cb:
            return False
        if cb["state"] == "open":
            # Check if cooldown expired
            if time.time() - cb["opened_at"] > 30:
                cb["state"] = "half-open"
                return False
            return True
        return False

    def record_failure(self, provider: str) -> None:
        """Record a failure and potentially open the circuit."""
        if provider not in self._circuit_breakers:
            self._circuit_breakers[provider] = {"state": "closed", "failures": 0, "opened_at": 0}
        cb = self._circuit_breakers[provider]
        cb["failures"] += 1
        if cb["failures"] >= 3:
            cb["state"] = "open"
            cb["opened_at"] = time.time()
            self.record_event(provider, "circuit_open", f"Circuit opened after {cb['failures']} failures")
        self.record_event(provider, "failure", f"Request failed ({cb['failures']} consecutive)")

    def record_success(self, provider: str) -> None:
        """Record a success, resetting the circuit breaker."""
        if provider in self._circuit_breakers:
            self._circuit_breakers[provider] = {"state": "closed", "failures": 0, "opened_at": 0}
            self.record_event(provider, "recovery", "Provider recovered")

    def configure(self, settings: list[dict[str, Any]]) -> None:
        self._profiles.clear()
        self._profiles_by_model.clear()
        self._roles.clear()

        # Import provider registry to look up registered profiles
        from harness.providers import get_provider_profile

        for s in settings:
            if not s.get("enabled", True):
                continue
            model = s.get("model", "") or _DEFAULT_MODEL
            api_mode = s.get("api_mode", "openai")
            provider_name = s.get("provider", "")

            # Resolve API key from config dict (stored in DB)
            api_key = s.get("api_key") or s.get("apiKey") or ""

            # Look up registered provider profile by name or alias
            registered = get_provider_profile(provider_name)
            if registered:
                # Use registered profile as base, override with user config
                profile = ProviderProfile(
                    name=registered.name,
                    api_mode=registered.api_mode or api_mode,
                    aliases=registered.aliases,
                    display_name=registered.display_name,
                    description=registered.description,
                    signup_url=registered.signup_url,
                    env_vars=registered.env_vars,
                    base_url=s.get("base_url") or s.get("baseUrl") or registered.base_url,
                    models_url=registered.models_url,
                    auth_type=registered.auth_type,
                    supports_health_check=registered.supports_health_check,
                    fallback_models=registered.fallback_models,
                    hostname=registered.hostname,
                    default_headers=registered.default_headers,
                    fixed_temperature=registered.fixed_temperature,
                    default_max_tokens=registered.default_max_tokens,
                    default_aux_model=registered.default_aux_model,
                    api_key=api_key,
                    model=model,
                    options=s.get("options", {}) or {},
                )
            else:
                # No registered profile — create a generic one
                profile = ProviderProfile(
                    name=provider_name,
                    model=model,
                    api_key=api_key,
                    base_url=s.get("base_url") or s.get("baseUrl") or "",
                    api_mode=api_mode,
                    options=s.get("options", {}) or {},
                )
            self._profiles[provider_name] = profile
            self._profiles_by_model[model] = profile
            self._roles[provider_name] = s.get("role", "default") or "default"

    def get_status(self) -> list[dict[str, Any]]:
        return [
            {
                "provider": name,
                "configured": True,
                "model": p.model,
                "has_key": bool(p.api_key),
                "base_url": p.base_url,
                "api_mode": p.api_mode,
            }
            for name, p in self._profiles.items()
        ]

    def get_model_for_role(self, role: str = "default") -> str | None:
        role = role.lower()
        for provider, r in self._roles.items():
            if r.lower() == role:
                p = self._profiles.get(provider)
                if p:
                    return p.model
        for p in self._profiles.values():
            return p.model
        return None

    # ── Q8 per-tier model selection ──────────────────────────────────
    #
    # The Q8 design calls for per-role + per-tier model selection.
    # The per-role path is the existing ``get_model_for_role``
    # above. Per-tier is layered on top: a ``_tier`` override
    # forces the router to pick a model from the named tier's
    # allow-list (configured at startup). Used by the budget
    # tracker's step-3 throttle to drop to a cheaper model mid-run.
    #
    # Tier semantics (matches the autonomy roadmap Q8):
    #   - "big"    — best model, used by orchestrator / planner
    #   - "medium" — used by fixer
    #   - "small"  — used by leaf workers; the throttle-ladder step 3
    #                target when a run is over budget
    _tier: str | None = None
    _tier_to_role: dict[str, str] = {
        "big": "orchestrator",
        "medium": "fixer",
        "small": "leaf",
    }

    def set_tier(self, tier: str | None) -> None:
        """Override the router's model selection by tier name.

        ``tier`` is one of "big" | "medium" | "small" | None.
        ``None`` clears the override and reverts to the per-role
        default. The override is process-global (not per-call);
        in the budget-tracker's step-3 hook this is fine because
        the throttle applies for the remainder of the run.
        """
        if tier is not None and tier not in self._tier_to_role:
            raise ValueError(
                f"unknown tier {tier!r}; expected one of "
                f"{sorted(self._tier_to_role)} or None"
            )
        self._tier = tier

    def get_tier(self) -> str | None:
        return self._tier

    def _resolve(self, model: str | None = None) -> ProviderProfile:
        if model and model in self._profiles_by_model:
            profile = self._profiles_by_model[model]
            if not self.is_circuit_open(profile.name):
                return profile
            # Fall through to next provider
        # Q8 per-tier: if a tier override is set, look up the role
        # mapped to that tier and prefer that profile.
        if self._tier and self._tier in self._tier_to_role:
            target_role = self._tier_to_role[self._tier]
            for provider, r in self._roles.items():
                if r.lower() == target_role:
                    profile = self._profiles.get(provider)
                    if profile and not self.is_circuit_open(profile.name):
                        return profile
        for p in self._profiles.values():
            if not self.is_circuit_open(p.name):
                return p
        # All circuits open — try the first one anyway (fail open)
        for p in self._profiles.values():
            return p
        raise RuntimeError(
            "No LLM provider configured. "
            "Go to Settings → Backend Providers to add API keys."
        )

    def _resolve_max_tokens(self, profile: ProviderProfile, max_tokens: int) -> int:
        profile_max = profile.get_max_tokens(profile.model)
        if profile_max is not None:
            return profile_max
        if profile.default_max_tokens is not None:
            return profile.default_max_tokens
        return max_tokens

    def _resolve_temperature(self, profile: ProviderProfile, temperature: float) -> float | None:
        ft = profile.fixed_temperature
        if ft is None:
            return temperature
        if ft is OMIT_TEMPERATURE:
            return None
        return ft

    def _build_headers(self, profile: ProviderProfile) -> dict[str, str]:
        headers: dict[str, str] = {}
        if profile.api_key:
            headers["Authorization"] = f"Bearer {profile.api_key}"
        # OpenCode Go/Zen requires User-Agent to avoid Cloudflare 403
        if "opencode" in profile.name.lower():
            headers["User-Agent"] = "TestAI/1.0"
        headers.update(profile.default_headers)
        return headers

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 393216,
        model: str | None = None,
        top_p: float = 0.9,
    ) -> CompletionResponse:
        async with self._api_semaphore:
            profile = self._resolve(model)
            dict_messages = messages_to_dicts(messages)
            max_tokens = self._resolve_max_tokens(profile, max_tokens)
            temperature = self._resolve_temperature(profile, temperature)

            import openai as _openai
            last_exc = None
            for attempt in range(3):
                try:
                    _start = time.monotonic()
                    _error_type = ""
                    try:
                        if profile.api_mode == "anthropic":
                            result = await self._chat_anthropic(profile, dict_messages, tools, tool_choice, temperature, max_tokens, top_p)
                        else:
                            result = await self._chat_openai(profile, dict_messages, tools, tool_choice, temperature, max_tokens, top_p)
                    except Exception as exc:
                        _error_type = type(exc).__name__
                        raise
                    finally:
                        self.record_provider_outcome(
                            profile.model,
                            success=not _error_type,
                            latency_ms=(time.monotonic() - _start) * 1000.0,
                            error_type=_error_type,
                        )
                    return result
                except _openai.APIStatusError as e:
                    last_exc = e
                    if e.status_code in (400, 502, 503, 504) and attempt < 2:
                        retry_delay = (2 ** attempt) * (0.5 + 0.5)
                        await asyncio.sleep(retry_delay)
                    else:
                        raise
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    last_exc = e
                    if attempt < 2:
                        retry_delay = (2 ** attempt) * (0.5 + 0.5)
                        await asyncio.sleep(retry_delay)
                    else:
                        raise
            if last_exc:
                raise last_exc

    async def _chat_openai(
        self, profile: ProviderProfile,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> CompletionResponse:
        import openai
        headers = self._build_headers(profile)
        client = openai.AsyncOpenAI(
            api_key=profile.api_key,
            base_url=profile.base_url,
            default_headers=headers if headers else None,
            timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
        )
        messages = profile.prepare_messages(messages)
        kwargs: dict[str, Any] = {
            "model": profile.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "top_p": top_p,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        try:
            eb_extra = profile.build_extra_body(session_id=None)
            rc = profile.options.get("reasoning") if profile.options else None
            eb, tl = profile.build_api_kwargs_extras(model=profile.model, reasoning_config=rc)
            merged_eb: dict[str, Any] = {}
            if eb_extra:
                merged_eb.update(eb_extra)
            if eb:
                merged_eb.update(eb)
            if merged_eb:
                kwargs["extra_body"] = merged_eb
            if tl:
                kwargs.update(tl)
        except Exception:
            if profile.options:
                kwargs["extra_body"] = dict(profile.options)

        response = await client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [_to_tool_call_dict(tc) for tc in msg.tool_calls]
        reasoning_content = getattr(msg, "reasoning_content", None) or ""
        content = msg.content or reasoning_content or ""
        usage = getattr(response, "usage", None) or {}
        self._record_usage(profile.model, usage)
        return CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
            model=response.model,
            reasoning_content=reasoning_content,
        )

    async def _chat_anthropic(
        self, profile: ProviderProfile,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> CompletionResponse:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )
        headers = self._build_headers(profile)
        client = anthropic.AsyncAnthropic(
            api_key=profile.api_key,
            base_url=profile.base_url,
            default_headers=headers if headers else None,
        )
        messages = profile.prepare_messages(messages)
        kwargs: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        system, body = self._split_anthropic_messages(messages)
        if system:
            kwargs["system"] = system
        kwargs["messages"] = body
        if tools:
            kwargs["tools"] = self._convert_anthropic_tools(tools)
        if profile.options:
            kwargs["extra_body"] = profile.options

        response = await client.messages.create(**kwargs)
        content_parts = []
        tool_calls = None
        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": str(block.input),
                    },
                })
        usage = getattr(response, "usage", None) or {}
        return CompletionResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": usage.input_tokens if usage else 0,
                "completion_tokens": usage.output_tokens if usage else 0,
                "total_tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0),
            },
            model=response.model,
        )

    @staticmethod
    def _split_anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
        system = None
        body = []
        for m in messages:
            if m.get("role") == "system":
                system = (system or "") + (m.get("content") or "")
            else:
                body.append(m)
        return system, body

    @staticmethod
    def _convert_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for t in tools:
            func = t.get("function", {})
            result.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return result

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 393216,
        model: str | None = None,
        top_p: float = 0.9,
    ) -> AsyncGenerator[Any, None]:
        async with self._api_semaphore:
            profile = self._resolve(model)
            dict_messages = messages_to_dicts(messages)
            max_tokens = self._resolve_max_tokens(profile, max_tokens)
            temperature = self._resolve_temperature(profile, temperature)

            if profile.api_mode == "anthropic":
                async for chunk in self._stream_anthropic(profile, dict_messages, tools, temperature, max_tokens, top_p):
                    yield chunk
                return

            # Retry loop for transient upstream failures
            import openai as _openai
            last_exc = None
            for attempt in range(3):
                try:
                    async for chunk in self._stream_openai(profile, dict_messages, tools, tool_choice, temperature, max_tokens, top_p):
                        yield chunk
                    return
                except _openai.APIStatusError as e:
                    last_exc = e
                    if e.status_code in (400, 502, 503, 504) and attempt < 2:
                        retry_delay = (2 ** attempt) * (0.5 + 0.5)
                        logger.warning(
                            "LLM stream attempt %d/3 failed (status=%d), retrying in %.1fs: %s",
                            attempt + 1, e.status_code, retry_delay, e.message[:200],
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        raise
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    if e.response.status_code in (502, 503, 504) and attempt < 2:
                        retry_delay = (2 ** attempt) * (0.5 + 0.5)
                        await asyncio.sleep(retry_delay)
                    else:
                        raise
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    last_exc = e
                    if attempt < 2:
                        retry_delay = (2 ** attempt) * (0.5 + 0.5)
                        await asyncio.sleep(retry_delay)
                    else:
                        raise
            if last_exc:
                raise last_exc

    async def _stream_openai(
        self, profile: ProviderProfile,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> AsyncGenerator[Any, None]:
        import openai
        headers = self._build_headers(profile)
        client = openai.AsyncOpenAI(
            api_key=profile.api_key,
            base_url=profile.base_url,
            default_headers=headers if headers else None,
            timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
        )
        messages = profile.prepare_messages(messages)
        kwargs: dict[str, Any] = {
            "model": profile.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": True,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        try:
            eb_extra = profile.build_extra_body(session_id=None)
            rc = profile.options.get("reasoning") if profile.options else None
            eb, tl = profile.build_api_kwargs_extras(model=profile.model, reasoning_config=rc)
            merged_eb: dict[str, Any] = {}
            if eb_extra:
                merged_eb.update(eb_extra)
            if eb:
                merged_eb.update(eb)
            if merged_eb:
                kwargs["extra_body"] = merged_eb
            if tl:
                kwargs.update(tl)
        except Exception:
            if profile.options:
                kwargs["extra_body"] = dict(profile.options)

        stream = await client.chat.completions.create(**kwargs)
        full_text = ""
        async for chunk in stream:
            full_text += _extract_chunk_text(chunk)
            yield chunk
        if full_text and max_tokens > 0:
            inp_tok = len(str(messages)) // 4
            out_tok = len(full_text) // 4
            if inp_tok or out_tok:
                try:
                    import asyncio
                    asyncio.get_running_loop().create_task(self._save_usage(inp_tok, out_tok, profile.model))
                except RuntimeError:
                    pass

    async def _stream_anthropic(
        self, profile: ProviderProfile,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
        top_p: float,
    ) -> AsyncGenerator[Any, None]:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("Anthropic SDK not installed. Run: pip install anthropic")
        headers = self._build_headers(profile)
        client = anthropic.AsyncAnthropic(
            api_key=profile.api_key,
            base_url=profile.base_url,
            default_headers=headers if headers else None,
        )
        messages = profile.prepare_messages(messages)
        kwargs: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        system, body = self._split_anthropic_messages(messages)
        if system:
            kwargs["system"] = system
        kwargs["messages"] = body
        if tools:
            kwargs["tools"] = self._convert_anthropic_tools(tools)
        if profile.options:
            kwargs["extra_body"] = profile.options
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield {"type": "token", "content": text}
