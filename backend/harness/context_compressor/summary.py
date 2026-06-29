"""Summary generation, serialization, and tail-cut utilities for context compression.

What lives here:
  * Token-budget computation for the summary (`compute_summary_budget`)
  * Conversation-to-text serialisation for the summariser LLM
    (`serialize_for_summary`)
  * The structured LLM summary prompt with iterative-update support
    (`generate_summary`)
  * Auxiliary-model fallback when the dedicated summary model fails
    (`fallback_to_main_for_compression`)
  * Summary handoff prefix management (`strip_summary_prefix`,
    `with_summary_prefix`, `is_context_summary_content`,
    `find_latest_context_summary`)
  * Tail-cut by token budget (`find_tail_cut_by_tokens`) — keeps the
    last ~20K tokens of context safe across re-compactions.

These helpers are stateful in that they reach into the
`ContextCompressor` instance for `self._llm`, `self.model`,
`self.summary_model`, cooldown state, and the `max_summary_tokens`
budget. They are kept as module functions (not methods) so they can
be unit-tested with a stub object — but the orchestrating class
binds them via `self`-passing call sites in `compress()`.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from harness._compressor_utils import (
    _is_connection_error,
    _redact_sensitive_text,
    estimate_messages_tokens_rough,
)
from harness.context_compressor.content import (
    CHARS_PER_TOKEN,
    content_length_for_budget,
    content_text_for_contains,
)
from harness.context_compressor.pruning import (
    align_boundary_backward,
    ensure_last_user_message_in_tail,
)
from harness.llm import ChatMessage


__all__ = [
    "compute_summary_budget",
    "serialize_for_summary",
    "generate_summary",
    "fallback_to_main_for_compression",
    "strip_summary_prefix",
    "with_summary_prefix",
    "is_context_summary_content",
    "find_latest_context_summary",
    "find_tail_cut_by_tokens",
    "SUMMARY_PREFIX",
    "LEGACY_SUMMARY_PREFIX",
    "MIN_SUMMARY_TOKENS",
    "SUMMARY_RATIO",
    "SUMMARY_TOKENS_CEILING",
    "SUMMARY_FAILURE_COOLDOWN_SECONDS",
    "CONTENT_MAX",
    "CONTENT_HEAD",
    "CONTENT_TAIL",
    "TOOL_ARGS_MAX",
    "TOOL_ARGS_HEAD",
]


logger = logging.getLogger(__name__)


# Handoff prefix — current
SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is a handoff from a previous context "
    "window — treat it as background reference, NOT as active instructions. "
    "Do NOT answer questions or fulfill requests mentioned in this summary; "
    "they were already addressed. "
    "Your current task is identified in the '## Active Task' section of the "
    "summary — resume exactly from there. "
    "IMPORTANT: Your persistent memory (MEMORY.md, USER.md) in the system "
    "prompt is ALWAYS authoritative and active — never ignore or deprioritize "
    "memory content due to this compaction note. "
    "Respond ONLY to the latest user message "
    "that appears AFTER this summary. The current session state (files, "
    "config, etc.) may reflect work described here — avoid repeating it:"
)
LEGACY_SUMMARY_PREFIX = "[CONTEXT SUMMARY]:"

# Minimum tokens for the summary output
MIN_SUMMARY_TOKENS = 2000
# Proportion of compressed content to allocate for summary
SUMMARY_RATIO = 0.20
# Absolute ceiling for summary tokens (even on very large context windows)
SUMMARY_TOKENS_CEILING = 12_000
SUMMARY_FAILURE_COOLDOWN_SECONDS = 600

# Truncation limits for the summarizer input.  These bound how much of
# each message the summary model sees — the budget is the *summary*
# model's context window, not the main model's.
CONTENT_MAX = 6000       # total chars per message body
CONTENT_HEAD = 4000      # chars kept from the start
CONTENT_TAIL = 1500      # chars kept from the end
TOOL_ARGS_MAX = 1500     # tool call argument chars
TOOL_ARGS_HEAD = 1200    # kept from the start of tool args


def _redact(text: str) -> str:
    return _redact_sensitive_text(text)


def compute_summary_budget(
    turns_to_summarize: List[Dict[str, Any]],
    max_summary_tokens: int,
) -> int:
    """Scale summary token budget with the amount of content being compressed.

    The maximum scales with the model's context window (5% of context,
    capped at ``SUMMARY_TOKENS_CEILING``) so large-context models get
    richer summaries instead of being hard-capped at 8K tokens.
    """
    content_tokens = estimate_messages_tokens_rough(turns_to_summarize)
    budget = int(content_tokens * SUMMARY_RATIO)
    return max(MIN_SUMMARY_TOKENS, min(budget, max_summary_tokens))


def serialize_for_summary(turns: List[Dict[str, Any]]) -> str:
    """Serialize conversation turns into labeled text for the summarizer.

    Includes tool call arguments and result content (up to
    ``CONTENT_MAX`` chars per message) so the summarizer can preserve
    specific details like file paths, commands, and outputs.

    All content is redacted before serialization to prevent secrets
    (API keys, tokens, passwords) from leaking into the summary that
    gets sent to the auxiliary model and persisted across compactions.
    """
    parts = []
    for msg in turns:
        role = msg.get("role", "unknown")
        content = _redact(msg.get("content") or "")

        # Tool results: keep enough content for the summarizer
        if role == "tool":
            tool_id = msg.get("tool_call_id", "")
            if len(content) > CONTENT_MAX:
                content = content[:CONTENT_HEAD] + "\n...[truncated]...\n" + content[-CONTENT_TAIL:]
            parts.append(f"[TOOL RESULT {tool_id}]: {content}")
            continue

        # Assistant messages: include tool call names AND arguments
        if role == "assistant":
            if len(content) > CONTENT_MAX:
                content = content[:CONTENT_HEAD] + "\n...[truncated]...\n" + content[-CONTENT_TAIL:]
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                tc_parts = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        fn = tc.get("function", {})
                        name = fn.get("name", "?")
                        args = _redact(fn.get("arguments", ""))
                        # Truncate long arguments but keep enough for context
                        if len(args) > TOOL_ARGS_MAX:
                            args = args[:TOOL_ARGS_HEAD] + "..."
                        tc_parts.append(f"  {name}({args})")
                    else:
                        fn = getattr(tc, "function", None)
                        name = getattr(fn, "name", "?") if fn else "?"
                        tc_parts.append(f"  {name}(...)")
                content += "\n[Tool calls:\n" + "\n".join(tc_parts) + "\n]"
            parts.append(f"[ASSISTANT]: {content}")
            continue

        # User and other roles
        if len(content) > CONTENT_MAX:
            content = content[:CONTENT_HEAD] + "\n...[truncated]...\n" + content[-CONTENT_TAIL:]
        parts.append(f"[{role.upper()}]: {content}")

    return "\n\n".join(parts)


def fallback_to_main_for_compression(
    compressor: Any,  # ContextCompressor instance — typed Any to avoid circular import
    e: Exception,
    reason: str,
) -> None:
    """Switch from a separate ``summary_model`` back to the main model.

    Centralises the bookkeeping shared by every fallback branch in
    :func:`generate_summary` (model-not-found, timeout, JSON decode,
    unknown error): record the aux-model failure for ``/usage``-style
    callers, clear the summary model so the next call uses the main one,
    and clear the cooldown so the immediate retry can run.

    ``reason`` is a short human-readable phrase ("unavailable",
    "timed out", "returned invalid JSON", "failed") that is interpolated
    into the warning log.
    """
    compressor._summary_model_fallen_back = True
    logger.warning(
        "Summary model '%s' %s (%s). "
        "Falling back to main model '%s' for compression.",
        compressor.summary_model, reason, e, compressor.model,
    )
    err_text = str(e).strip() or e.__class__.__name__
    if len(err_text) > 220:
        err_text = err_text[:217].rstrip() + "..."
    compressor._last_aux_model_failure_error = err_text
    compressor._last_aux_model_failure_model = compressor.summary_model
    compressor.summary_model = ""  # empty = use main model
    compressor._summary_failure_cooldown_until = 0.0  # no cooldown — retry immediately


def _is_model_not_found_error(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    err_str = str(e).lower()
    return (
        status in {404, 503}
        or "model_not_found" in err_str
        or "does not exist" in err_str
        or "no available channel" in err_str
    )


def _is_timeout_error(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    err_str = str(e).lower()
    return (
        status in {408, 429, 502, 504}
        or "timeout" in err_str
    )


def _is_json_decode_error(e: Exception) -> bool:
    # Non-JSON / malformed-body responses from misconfigured providers
    # or proxies (e.g. an HTML 502 page returned with
    # ``Content-Type: application/json``) bubble up as
    # ``json.JSONDecodeError`` from the OpenAI SDK's ``response.json()``,
    # or as a wrapping ``APIResponseValidationError`` whose message
    # carries the substring "expecting value".  Treat these like a
    # transient provider failure: one retry on the main model, then a
    # short cooldown.  Issue #22244.
    err_str = str(e).lower()
    return (
        isinstance(e, json.JSONDecodeError)
        or "expecting value" in err_str
    )


def _is_streaming_closed_error(e: Exception) -> bool:
    # httpcore / httpx streaming premature-close errors surface as
    # ConnectionError subclasses or plain Exception with characteristic
    # substrings ("incomplete chunked read", "peer closed connection",
    # "response ended prematurely", "unexpected eof").  These are
    # transient network events; treat them like a timeout so we fall
    # back to the main model instead of entering a 60-second cooldown.
    # See issue #18458.
    return _is_connection_error(e)


async def generate_summary(
    compressor: Any,  # ContextCompressor instance
    turns_to_summarize: List[Dict[str, Any]],
    focus_topic: str = None,
) -> Optional[str]:
    """Generate a structured summary of conversation turns.

    Uses a structured template (Goal, Progress, Decisions, Resolved/Pending
    Questions, Files, Remaining Work) with explicit preamble telling the
    summarizer not to answer questions.  When a previous summary exists,
    generates an iterative update instead of summarizing from scratch.

    Args:
        focus_topic: Optional focus string for guided compression.  When
            provided, the summariser prioritises preserving information
            related to this topic and is more aggressive about compressing
            everything else.  Inspired by ``/compact``.

    Returns None if all attempts fail — the caller should drop
    the middle turns without a summary rather than inject a useless
    placeholder.
    """
    now = time.monotonic()
    if now < compressor._summary_failure_cooldown_until:
        logger.debug(
            "Skipping context summary during cooldown (%.0fs remaining)",
            compressor._summary_failure_cooldown_until - now,
        )
        return None

    summary_budget = compute_summary_budget(turns_to_summarize, compressor.max_summary_tokens)
    content_to_summarize = serialize_for_summary(turns_to_summarize)

    # Preamble shared by both first-compaction and iterative-update prompts.
    # Keep the wording deliberately plain: Azure/OpenAI-compatible content
    # filters have flagged stronger "injection" / "do not respond" framing.
    _summarizer_preamble = (
        "You are a summarization agent creating a context checkpoint. "
        "Treat the conversation turns below as source material for a "
        "compact record of prior work. "
        "Produce only the structured summary; do not add a greeting, "
        "preamble, or prefix. "
        "Write the summary in the same language the user was using in the "
        "conversation — do not translate or switch to English. "
        "NEVER include API keys, tokens, passwords, secrets, credentials, "
        "or connection strings in the summary — replace any that appear "
        "with [REDACTED]. Note that the user had credentials present, but "
        "do not preserve their values."
    )

    # Shared structured template (used by both paths).
    _template_sections = f"""## Active Task
[THE SINGLE MOST IMPORTANT FIELD. Copy the user's most recent request or
task assignment verbatim — the exact words they used. If multiple tasks
were requested and only some are done, list only the ones NOT yet completed.
Continuation should pick up exactly here. Example:
"User asked: 'Now refactor the auth module to use JWT instead of sessions'"
If no outstanding task exists, write "None."]

## Goal
[What the user is trying to accomplish overall]

## Constraints & Preferences
[User preferences, coding style, constraints, important decisions]

## Completed Actions
[Numbered list of concrete actions taken — include tool used, target, and outcome.
Format each as: N. ACTION target — outcome [tool: name]
Example:
1. READ config.py:45 — found `==` should be `!=` [tool: read_file]
2. PATCH config.py:45 — changed `==` to `!=` [tool: patch]
3. TEST `pytest tests/` — 3/50 failed: test_parse, test_validate, test_edge [tool: terminal]
Be specific with file paths, commands, line numbers, and results.]

## Active State
[Current working state — include:
- Working directory and branch (if applicable)
- Modified/created files with brief note on each
- Test status (X/Y passing)
- Any running processes or servers
- Environment details that matter]

## In Progress
[Work currently underway — what was being done when compaction fired]

## Blocked
[Any blockers, errors, or issues not yet resolved. Include exact error messages.]

## Key Decisions
[Important technical decisions and WHY they were made]

## Resolved Questions
[Questions the user asked that were ALREADY answered — include the answer so it is not repeated]

## Pending User Asks
[Questions or requests from the user that have NOT yet been answered or fulfilled. If none, write "None."]

## Relevant Files
[Files read, modified, or created — with brief note on each]

## Remaining Work
[What remains to be done — framed as context, not instructions]

## Critical Context
[Any specific values, error messages, configuration details, or data that would be lost without explicit preservation. NEVER include API keys, tokens, passwords, or credentials — write [REDACTED] instead.]

Target ~{summary_budget} tokens. Be CONCRETE — include file paths, command outputs, error messages, line numbers, and specific values. Avoid vague descriptions like "made some changes" — say exactly what changed.

Write only the summary body. Do not include any preamble or prefix."""

    if compressor._previous_summary:
        # Iterative update: preserve existing info, add new progress
        prompt = f"""{_summarizer_preamble}

You are updating a context compaction summary. A previous compaction produced the summary below. New conversation turns have occurred since then and need to be incorporated.

PREVIOUS SUMMARY:
{compressor._previous_summary}

NEW TURNS TO INCORPORATE:
{content_to_summarize}

Update the summary using this exact structure. PRESERVE all existing information that is still relevant. ADD new completed actions to the numbered list (continue numbering). Move items from "In Progress" to "Completed Actions" when done. Move answered questions to "Resolved Questions". Update "Active State" to reflect current state. Remove information only if it is clearly obsolete. CRITICAL: Update "## Active Task" to reflect the user's most recent unfulfilled request — this is the most important field for task continuity.

{_template_sections}"""
    else:
        # First compaction: summarize from scratch
        prompt = f"""{_summarizer_preamble}

Create a structured checkpoint summary for the conversation after earlier turns are compacted. The summary should preserve enough detail for continuity without re-reading the original turns.

TURNS TO SUMMARIZE:
{content_to_summarize}

Use this exact structure:

{_template_sections}"""

    # Inject focus topic guidance when the user provides one via /compress <focus>.
    # This goes at the end of the prompt so it takes precedence.
    if focus_topic:
        prompt += f"""

FOCUS TOPIC: "{focus_topic}"
The user has requested that this compaction PRIORITISE preserving all information related to the focus topic above. For content related to "{focus_topic}", include full detail — exact values, file paths, command outputs, error messages, and decisions. For content NOT related to the focus topic, summarise more aggressively (brief one-liners or omit if truly irrelevant). The focus topic sections should receive roughly 60-70% of the summary token budget. Even for the focus topic, NEVER preserve API keys, tokens, passwords, or credentials — use [REDACTED]."""

    try:
        if not compressor._llm:
            raise RuntimeError("No LLM router configured for context compression")
        model = compressor.summary_model if compressor.summary_model else compressor.model
        response = await compressor._llm.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            model=model,
            max_tokens=int(summary_budget * 1.3),
            temperature=0.3,
        )
        content = response.content
        if not isinstance(content, str):
            content = str(content) if content else ""
        summary = _redact(content.strip())
        compressor._previous_summary = summary
        compressor._summary_failure_cooldown_until = 0.0
        compressor._summary_model_fallen_back = False
        compressor._last_summary_error = None
        return with_summary_prefix(summary)
    except RuntimeError:
        # No provider configured — long cooldown, unlikely to self-resolve
        compressor._summary_failure_cooldown_until = time.monotonic() + SUMMARY_FAILURE_COOLDOWN_SECONDS
        compressor._last_summary_error = "no auxiliary LLM provider configured"
        logger.warning("Context compression: no provider available for "
                        "summary. Middle turns will be dropped without summary "
                        "for %d seconds.",
                        SUMMARY_FAILURE_COOLDOWN_SECONDS)
        return None
    except Exception as e:
        is_model_not_found = _is_model_not_found_error(e)
        is_timeout = _is_timeout_error(e)
        is_json_decode = _is_json_decode_error(e)
        is_streaming_closed = _is_streaming_closed_error(e)
        if is_json_decode and not is_model_not_found and not is_timeout:
            logger.error(
                "Context compression failed: auxiliary LLM returned a "
                "non-JSON response. provider=%s summary_model=%s "
                "main_model=%s base_url=%s err=%s",
                compressor.provider or "auto",
                compressor.summary_model or "(main)",
                compressor.model,
                compressor.base_url or "default",
                e,
            )
        if (
            (is_model_not_found or is_timeout or is_json_decode or is_streaming_closed)
            and compressor.summary_model
            and compressor.summary_model != compressor.model
            and not getattr(compressor, "_summary_model_fallen_back", False)
        ):
            if is_json_decode:
                _reason = "returned invalid JSON"
            elif is_model_not_found:
                _reason = "unavailable"
            elif is_streaming_closed:
                _reason = "closed stream prematurely"
            else:
                _reason = "timed out"
            fallback_to_main_for_compression(compressor, e, _reason)
            return await generate_summary(compressor, turns_to_summarize, focus_topic=focus_topic)  # retry immediately

        # Unknown-error best-effort retry on main model.  Losing N turns of
        # context is almost always worse than one extra summary attempt, so
        # if we haven't already fallen back and the summary model differs
        # from the main model, try once more on main before entering
        # cooldown.  Errors that DID match _is_model_not_found above are
        # already handled by the fast-path retry; this branch catches
        # everything else (400s, provider-specific "no route" strings,
        # aggregator rejections, etc.) where auto-retry is still safer
        # than dropping the turns.
        if (
            compressor.summary_model
            and compressor.summary_model != compressor.model
            and not getattr(compressor, "_summary_model_fallen_back", False)
        ):
            fallback_to_main_for_compression(compressor, e, "failed")
            return await generate_summary(compressor, turns_to_summarize, focus_topic=focus_topic)

        # Transient errors (timeout, rate limit, network, JSON decode,
        # streaming premature-close) — shorter cooldown for JSON decode and
        # streaming-closed since those conditions can self-resolve quickly.
        _transient_cooldown = 30 if (is_json_decode or is_streaming_closed) else 60
        compressor._summary_failure_cooldown_until = time.monotonic() + _transient_cooldown
        err_text = str(e).strip() or e.__class__.__name__
        if len(err_text) > 220:
            err_text = err_text[:217].rstrip() + "..."
        compressor._last_summary_error = err_text
        logger.warning(
            "Failed to generate context summary: %s. "
            "Further summary attempts paused for %d seconds.",
            e,
            _transient_cooldown,
        )
        return None


# ----------------------------------------------------------------------
# Summary handoff prefix management
# ----------------------------------------------------------------------


def strip_summary_prefix(summary: str) -> str:
    """Return summary body without the current or legacy handoff prefix."""
    text = (summary or "").strip()
    for prefix in (SUMMARY_PREFIX, LEGACY_SUMMARY_PREFIX):
        if text.startswith(prefix):
            return text[len(prefix):].lstrip()
    return text


def with_summary_prefix(summary: str) -> str:
    """Normalize summary text to the current compaction handoff format."""
    text = strip_summary_prefix(summary)
    return f"{SUMMARY_PREFIX}\n{text}" if text else SUMMARY_PREFIX


def is_context_summary_content(content: Any) -> bool:
    text = content_text_for_contains(content).lstrip()
    return text.startswith(SUMMARY_PREFIX) or text.startswith(LEGACY_SUMMARY_PREFIX)


def find_latest_context_summary(
    messages: List[Dict[str, Any]],
    start: int,
    end: int,
) -> Tuple[Optional[int], str]:
    """Find the newest handoff summary inside a compression window."""
    for idx in range(end - 1, start - 1, -1):
        content = messages[idx].get("content")
        if is_context_summary_content(content):
            return idx, strip_summary_prefix(content_text_for_contains(content))
    return None, ""


# ----------------------------------------------------------------------
# Tail cut by token budget
# ----------------------------------------------------------------------


def find_tail_cut_by_tokens(
    messages: List[Dict[str, Any]],
    head_end: int,
    token_budget: int,
    quiet_mode: bool = False,
) -> int:
    """Walk backward from the end of messages, accumulating tokens until
    the budget is reached. Returns the index where the tail starts.

    ``token_budget`` defaults to ``self.tail_token_budget`` which is
    derived from ``summary_target_ratio * context_length``, so it
    scales automatically with the model's context window.

    Token budget is the primary criterion.  A hard minimum of 3 messages
    is always protected, but the budget is allowed to exceed by up to
    1.5x to avoid cutting inside an oversized message (tool output, file
    read, etc.).  If even the minimum 3 messages exceed 1.5x the budget
    the cut is placed right after the head so compression still runs.

    Never cuts inside a tool_call/result group.  Always ensures the most
    recent user message is in the tail (see
    ``ensure_last_user_message_in_tail``).
    """
    n = len(messages)
    # Hard minimum: always keep at least 3 messages in the tail
    min_tail = min(3, n - head_end - 1) if n - head_end > 1 else 0
    soft_ceiling = int(token_budget * 1.5)
    accumulated = 0
    cut_idx = n  # start from beyond the end

    for i in range(n - 1, head_end - 1, -1):
        msg = messages[i]
        raw_content = msg.get("content") or ""
        content_len = content_length_for_budget(raw_content)
        msg_tokens = content_len // CHARS_PER_TOKEN + 10  # +10 for role/metadata
        # Include tool call arguments in estimate
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                args = tc.get("function", {}).get("arguments", "")
                msg_tokens += len(args) // CHARS_PER_TOKEN
        # Stop once we exceed the soft ceiling (unless we haven't hit min_tail yet)
        if accumulated + msg_tokens > soft_ceiling and (n - i) >= min_tail:
            break
        accumulated += msg_tokens
        cut_idx = i

    # Ensure we protect at least min_tail messages
    fallback_cut = n - min_tail
    cut_idx = min(cut_idx, fallback_cut)

    # If the token budget would protect everything (small conversations),
    # force a cut after the head so compression can still remove middle turns.
    if cut_idx <= head_end:
        cut_idx = max(fallback_cut, head_end + 1)

    # Align to avoid splitting tool groups
    cut_idx = align_boundary_backward(messages, cut_idx)

    # Ensure the most recent user message is always in the tail so the
    # active task is never lost to compression (fixes #10896).
    cut_idx = ensure_last_user_message_in_tail(messages, cut_idx, head_end, quiet_mode=quiet_mode)

    return max(cut_idx, head_end + 1)
