"""``ContextCompressor`` orchestrator class.

The actual compression algorithm lives in three sibling modules:

  * :mod:`harness.context_compressor.content` — pure data-shape helpers
    (multimodal length, text view, JSON-safe argument shrinking,
    image-part stripping).
  * :mod:`harness.context_compressor.pruning` — cheap pre-pass helpers
    (tool-result summaries, dedupe, tool-call argument shrinking,
    boundary alignment, tail protection by token budget, tool-pair
    sanitisation).
  * :mod:`harness.context_compressor.summary` — LLM-backed helpers
    (summary budget, serialisation, structured-prompt generation,
    model fallback, summary-prefix management, tail cut by tokens).

What lives here:
  * The :class:`ContextCompressor` state machine (per-session reset,
    anti-thrashing counters, summary-failure cooldowns).
  * The :meth:`ContextCompressor.compress` orchestrator that glues the
    three modules together.

External surface (the only thing callers should depend on):
  * :class:`ContextCompressor` (imported from
    ``harness.context_compressor``)
  * :meth:`name`
  * :meth:`on_session_reset`
  * :meth:`update_model`
  * :meth:`update_from_response`
  * :meth:`should_compress`
  * :meth:`has_content_to_compress`
  * :meth:`compress`

Everything else is implementation detail and may change without notice.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

COMPRESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS compressions (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    before_tokens INTEGER NOT NULL DEFAULT 0,
    after_tokens  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compressions_session_id ON compressions (session_id);
"""

from harness._compressor_utils import (
    MINIMUM_CONTEXT_LENGTH,
    ContextEngine,
    estimate_messages_tokens_rough,
    get_model_context_length,
)
from harness.context_compressor.content import (
    append_text_to_content,
    content_text_for_contains,
    strip_historical_media,
)
from harness.context_compressor.pruning import (
    align_boundary_forward,
    protect_head_size,
    prune_old_tool_results,
    sanitize_tool_pairs,
)
from harness.context_compressor.summary import (
    LEGACY_SUMMARY_PREFIX,
    SUMMARY_PREFIX,
    SUMMARY_TOKENS_CEILING,
    find_latest_context_summary,
    find_tail_cut_by_tokens,
    generate_summary,
)
from harness.llm import LLMRouter


__all__ = ["ContextCompressor", "SUMMARY_PREFIX", "LEGACY_SUMMARY_PREFIX"]


logger = logging.getLogger(__name__)


# System-prompt note appended when the protected head is carried through
# compression.  Tells the model that earlier turns were summarised and
# that its persistent memory (MEMORY.md, USER.md) remains authoritative.
SYSTEM_COMPACTION_NOTE = (
    "[Note: Some earlier conversation turns have been compacted into a "
    "handoff summary to preserve context space. The current session "
    "state may still reflect earlier work, so build on that summary and "
    "state rather than re-doing work. Your persistent memory (MEMORY.md, "
    "USER.md) remains fully authoritative regardless of compaction.]"
)

# Explicit end marker appended to standalone summary messages (and
# prepended to merged-into-tail summaries).  Weak models otherwise read
# the verbatim "## Active Task" quote of a past user request as fresh
# input (#11475, #14521) and try to answer it.
SUMMARY_END_MARKER = (
    "\n\n--- END OF CONTEXT SUMMARY — "
    "respond to the message below, not the summary above ---"
)


_compaction_state: dict[str, Any] = {
    "compactions_total": 0,
    "last_before_tokens": None,
    "last_after_tokens": None,
    "last_threshold_percent": None,
    "last_context_length": None,
    "last_at": None,
}


def get_compaction_state_snapshot() -> dict[str, Any]:
    return dict(_compaction_state)


def record_compaction(
    *,
    before_tokens: int | None,
    after_tokens: int | None,
    threshold_percent: float,
    context_length: int,
    session_id: str = "",
) -> None:
    import time as _time
    import datetime as _dt
    _compaction_state["compactions_total"] = int(_compaction_state.get("compactions_total", 0)) + 1
    _compaction_state["last_before_tokens"] = before_tokens
    _compaction_state["last_after_tokens"] = after_tokens
    _compaction_state["last_threshold_percent"] = threshold_percent
    _compaction_state["last_context_length"] = context_length
    _compaction_state["last_at"] = _time.time()

    # Persist compression event to DB for lineage tracking.
    # Session lineage lets the dashboard show compression history
    # and future memory queries can trace back through ancestor
    # sessions.
    if session_id and before_tokens and after_tokens:
        try:
            import asyncio
            from harness.memory.db_context import get_db
            db = get_db()
            if db is None:
                return
            asyncio.create_task(_persist_compression(
                db, session_id, before_tokens, after_tokens,
            ))
        except Exception:
            pass


async def _persist_compression(
    db: Any, session_id: str, before_tokens: int, after_tokens: int,
) -> None:
    """Insert a compression lineage record."""
    try:
        await db.execute(
            "INSERT INTO compressions (session_id, before_tokens, after_tokens) "
            "VALUES ($1, $2, $3)",
            session_id, before_tokens, after_tokens,
        )
    except Exception as exc:
        logger.debug("Failed to persist compression event: %s", exc)


class ContextCompressor(ContextEngine):
    """Default context engine — compresses conversation context via lossy summarization.

    Algorithm:
      1. Prune old tool results (cheap, no LLM call)
      2. Protect head messages (system prompt + first exchange)
      3. Protect tail messages by token budget (most recent ~20K tokens)
      4. Summarize middle turns with structured LLM prompt
      5. On subsequent compactions, iteratively update the previous summary
    """

    @property
    def name(self) -> str:
        return "compressor"

    def on_session_reset(self) -> None:
        """Reset all per-session state for /new or /reset."""
        super().on_session_reset()
        self._context_probed = False
        self._context_probe_persistable = False
        self._previous_summary: Optional[str] = None
        self._last_summary_error: Optional[str] = None
        self._last_summary_dropped_count: int = 0
        self._last_summary_fallback_used: bool = False
        self._last_aux_model_failure_error: Optional[str] = None
        self._last_aux_model_failure_model: Optional[str] = None
        self._last_compression_savings_pct: float = 100.0
        self._ineffective_compression_count: int = 0
        # Transient errors must not block a fresh session.
        self._summary_failure_cooldown_until: float = 0.0

    def update_model(
        self,
        model: str,
        context_length: int,
        base_url: str = "",
        api_key: Any = "",
        provider: str = "",
        api_mode: str = "",
    ) -> None:
        """Update model info after a model switch or fallback activation."""
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.provider = provider
        self.api_mode = api_mode
        self.context_length = context_length
        self.threshold_tokens = max(
            int(context_length * self.threshold_percent),
            MINIMUM_CONTEXT_LENGTH,
        )
        # Recalculate token budgets for the new context length so the
        # compressor stays calibrated after a model switch (e.g. 200K → 32K).
        target_tokens = int(self.threshold_tokens * self.summary_target_ratio)
        self.tail_token_budget = target_tokens
        self.max_summary_tokens = min(
            int(context_length * 0.05), SUMMARY_TOKENS_CEILING,
        )

    def __init__(
        self,
        model: str,
        threshold_percent: float = 0.85,
        protect_first_n: int = 3,
        protect_last_n: int = 20,
        summary_target_ratio: float = 0.20,
        quiet_mode: bool = False,
        summary_model_override: str = None,
        base_url: str = "",
        api_key: str = "",
        config_context_length: int | None = None,
        provider: str = "",
        api_mode: str = "",
        abort_on_summary_failure: bool = False,
        llm: LLMRouter | None = None,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.provider = provider
        self.api_mode = api_mode
        self._llm = llm
        self.threshold_percent = threshold_percent
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.summary_target_ratio = max(0.10, min(summary_target_ratio, 0.80))
        self.quiet_mode = quiet_mode
        # When True, summary-generation failure aborts compression entirely
        # (returns messages unchanged, sets _last_compress_aborted=True).
        # When False (default = historical behavior), insert a static
        # "summary unavailable" placeholder and drop the middle window.
        self.abort_on_summary_failure = abort_on_summary_failure

        self.context_length = get_model_context_length(
            model, base_url=base_url, api_key=api_key,
            config_context_length=config_context_length,
            provider=provider,
        )
        # Floor: never compress below MINIMUM_CONTEXT_LENGTH tokens even if
        # the percentage would suggest a lower value.  This prevents premature
        # compression on large-context models at 50% while keeping the % sane
        # for models right at the minimum.
        self.threshold_tokens = max(
            int(self.context_length * threshold_percent),
            MINIMUM_CONTEXT_LENGTH,
        )
        self.compression_count = 0

        # Derive token budgets: ratio is relative to the threshold, not total context
        target_tokens = int(self.threshold_tokens * self.summary_target_ratio)
        self.tail_token_budget = target_tokens
        self.max_summary_tokens = min(
            int(self.context_length * 0.05), SUMMARY_TOKENS_CEILING,
        )

        if not quiet_mode:
            logger.info(
                "Context compressor initialized: model=%s context_length=%d "
                "threshold=%d (%.0f%%) target_ratio=%.0f%% tail_budget=%d "
                "provider=%s base_url=%s",
                model, self.context_length, self.threshold_tokens,
                threshold_percent * 100, self.summary_target_ratio * 100,
                self.tail_token_budget,
                provider or "none", base_url or "none",
            )
        self._context_probed = False  # True after a step-down from context error

        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0

        self.summary_model = summary_model_override or ""

        # Stores the previous compaction summary for iterative updates
        self._previous_summary = None
        # Anti-thrashing: track whether last compression was effective
        self._last_compression_savings_pct: float = 100.0
        self._ineffective_compression_count: int = 0
        self._summary_failure_cooldown_until: float = 0.0
        self._last_summary_error: Optional[str] = None
        # When summary generation fails and a static fallback is inserted,
        # record how many turns were unrecoverably dropped so callers
        # (gateway hygiene, /compress) can surface a visible warning.
        self._last_summary_dropped_count: int = 0
        self._last_summary_fallback_used: bool = False
        # When summary generation fails we now ABORT compression entirely
        # and return the original messages unchanged instead of dropping
        # the middle window with a static placeholder.  Callers inspect
        # this flag to know "compression was attempted but aborted, freeze
        # the chat until the user manually retries via /compress".
        self._last_compress_aborted: bool = False
        # When a user-configured summary model fails and we recover by
        # retrying on the main model, record the failure so gateway /
        # CLI callers can still warn the user even though compression
        # succeeded.  Silent recovery would hide the broken config.
        self._last_aux_model_failure_error: Optional[str] = None
        self._last_aux_model_failure_model: Optional[str] = None

    def update_from_response(self, usage: Dict[str, Any]):
        """Update tracked token usage from API response."""
        self.last_prompt_tokens = usage.get("prompt_tokens", 0)
        self.last_completion_tokens = usage.get("completion_tokens", 0)
        self.last_total_tokens = usage.get("total_tokens", self.last_prompt_tokens + self.last_completion_tokens)

    def should_compress(self, prompt_tokens: int = None) -> bool:
        """Check if context exceeds the compression threshold.

        Includes anti-thrashing protection: if the last two compressions
        each saved less than 10%, skip compression to avoid infinite loops
        where each pass removes only 1-2 messages.
        """
        tokens = prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens
        if tokens < self.threshold_tokens:
            return False
        # Anti-thrashing: back off if recent compressions were ineffective
        if self._ineffective_compression_count >= 2:
            if not self.quiet_mode:
                logger.warning(
                    "Compression skipped — last %d compressions saved <10%% each. "
                    "Consider /new to start a fresh session, or /compress <topic> "
                    "for focused compression.",
                    self._ineffective_compression_count,
                )
            return False
        return True

    # ------------------------------------------------------------------
    # ContextEngine: manual /compress preflight
    # ------------------------------------------------------------------

    def has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool:
        """Return True if there is a non-empty middle region to compact.

        Overrides the ABC default so the gateway ``/compress`` guard can
        skip the LLM call when the transcript is still entirely inside
        the protected head/tail.
        """
        compress_start = align_boundary_forward(messages, protect_head_size(messages, self.protect_first_n))
        compress_end = find_tail_cut_by_tokens(messages, compress_start, self.tail_token_budget, quiet_mode=self.quiet_mode)
        return compress_start < compress_end

    # ------------------------------------------------------------------
    # Main compression entry point
    # ------------------------------------------------------------------

    async def compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: int = None,
        focus_topic: str = None,
        force: bool = False,
        session_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Compress conversation messages by summarizing middle turns.

        Algorithm:
          1. Prune old tool results (cheap pre-pass, no LLM call)
          2. Protect head messages (system prompt + first exchange)
          3. Find tail boundary by token budget (~20K tokens of recent context)
          4. Summarize middle turns with structured LLM prompt
          5. On re-compression, iteratively update the previous summary

        After compression, orphaned tool_call / tool_result pairs are cleaned
        up so the API never receives mismatched IDs.

        Args:
            focus_topic: Optional focus string for guided compression.  When
                provided, the summariser will prioritise preserving information
                related to this topic and be more aggressive about compressing
                everything else.  Inspired by ``/compact``.
            force: If True, clear any active summary-failure cooldown before
                running so a manual ``/compress`` can retry immediately after
                an auto-compression abort.  Auto-compress callers pass False.
        """
        # Reset per-call summary failure state — callers inspect these fields
        # after compress() returns to decide whether to surface a warning.
        self._last_summary_dropped_count = 0
        self._last_summary_fallback_used = False
        self._last_summary_error = None
        self._last_aux_model_failure_error = None
        self._last_aux_model_failure_model = None
        self._last_compress_aborted = False

        # Manual /compress (force=True) bypasses the failure cooldown so the
        # user can retry immediately after an auto-compress abort.  Without
        # this, /compress would silently no-op for 30-60s after a failure.
        if force and self._summary_failure_cooldown_until > 0.0:
            self._summary_failure_cooldown_until = 0.0
        n_messages = len(messages)
        # Only need head + 3 tail messages minimum (token budget decides the real tail size)
        _min_for_compress = protect_head_size(messages, self.protect_first_n) + 3 + 1
        if n_messages <= _min_for_compress:
            if not self.quiet_mode:
                logger.warning(
                    "Cannot compress: only %d messages (need > %d)",
                    n_messages, _min_for_compress,
                )
            return messages

        display_tokens = current_tokens if current_tokens else self.last_prompt_tokens or estimate_messages_tokens_rough(messages)

        # Phase 1: Prune old tool results (cheap, no LLM call)
        messages, pruned_count = prune_old_tool_results(
            messages,
            protect_tail_count=self.protect_last_n,
            protect_tail_tokens=self.tail_token_budget,
            quiet_mode=self.quiet_mode,
        )
        if pruned_count and not self.quiet_mode:
            logger.info("Pre-compression: pruned %d old tool result(s)", pruned_count)

        # Phase 2: Determine boundaries
        compress_start = protect_head_size(messages, self.protect_first_n)
        compress_start = align_boundary_forward(messages, compress_start)

        # Use token-budget tail protection instead of fixed message count
        compress_end = find_tail_cut_by_tokens(
            messages, compress_start, self.tail_token_budget, quiet_mode=self.quiet_mode,
        )

        if compress_start >= compress_end:
            return messages

        turns_to_summarize = messages[compress_start:compress_end]
        # A persisted handoff summary can sit in the protected head after a
        # resume (commonly immediately after the system prompt). Search from
        # the first non-system message through the compression window so we can
        # rehydrate iterative-summary state without serializing that handoff as
        # a new turn. Protected messages after the handoff remain live context,
        # so only summarize messages that are both after the handoff and inside
        # the current compression window.
        summary_search_start = 1 if messages and messages[0].get("role") == "system" else 0
        summary_idx, summary_body = find_latest_context_summary(
            messages,
            summary_search_start,
            compress_end,
        )
        if summary_idx is not None:
            if summary_body and not self._previous_summary:
                self._previous_summary = summary_body
            turns_to_summarize = messages[max(compress_start, summary_idx + 1):compress_end]

        if not self.quiet_mode:
            logger.info(
                "Context compression triggered (%d tokens >= %d threshold)",
                display_tokens,
                self.threshold_tokens,
            )
            logger.info(
                "Model context limit: %d tokens (%.0f%% = %d)",
                self.context_length,
                self.threshold_percent * 100,
                self.threshold_tokens,
            )
            tail_msgs = n_messages - compress_end
            logger.info(
                "Summarizing turns %d-%d (%d turns), protecting %d head + %d tail messages",
                compress_start + 1,
                compress_end,
                len(turns_to_summarize),
                compress_start,
                tail_msgs,
            )

        # Phase 3: Generate structured summary
        summary = await generate_summary(self, turns_to_summarize, focus_topic=focus_topic)

        # If summary generation failed, behavior splits on
        # ``abort_on_summary_failure`` (config: compression.abort_on_summary_failure):
        #   True  → ABORT compression entirely. Return messages unchanged
        #           and set _last_compress_aborted=True so callers can warn
        #           the user and stop the auto-compress retry loop.
        #   False → Fall through to the legacy fallback path below: insert
        #           a static "summary unavailable" placeholder and drop the
        #           middle window.  Records _last_summary_fallback_used /
        #           _last_summary_dropped_count for gateway hygiene to
        #           surface a warning.
        # Default is False (historical behavior).
        if not summary and self.abort_on_summary_failure:
            n_skipped = compress_end - compress_start
            self._last_summary_dropped_count = 0  # nothing actually dropped
            self._last_summary_fallback_used = False
            self._last_compress_aborted = True
            if not self.quiet_mode:
                logger.warning(
                    "Summary generation failed — aborting compression "
                    "(compression.abort_on_summary_failure=true). "
                    "%d message(s) preserved unchanged. Conversation is "
                    "frozen until the next /compress or /new.",
                    n_skipped,
                )
            return messages

        # Phase 4: Assemble compressed message list
        compressed = []
        for i in range(compress_start):
            msg = messages[i].copy()
            if i == 0 and msg.get("role") == "system":
                existing = msg.get("content")
                if SYSTEM_COMPACTION_NOTE not in content_text_for_contains(existing):
                    msg["content"] = append_text_to_content(
                        existing,
                        "\n\n" + SYSTEM_COMPACTION_NOTE if isinstance(existing, str) and existing else SYSTEM_COMPACTION_NOTE,
                    )
            compressed.append(msg)

        # Legacy fallback path: LLM summary failed and abort_on_summary_failure
        # is False (the default).  Insert a static placeholder so the model
        # knows context was lost rather than silently dropping everything.
        if not summary:
            if not self.quiet_mode:
                logger.warning("Summary generation failed — inserting static fallback context marker")
            n_dropped = compress_end - compress_start
            self._last_summary_dropped_count = n_dropped
            self._last_summary_fallback_used = True
            summary = (
                f"{SUMMARY_PREFIX}\n"
                f"Summary generation was unavailable. {n_dropped} message(s) were "
                f"removed to free context space but could not be summarized. The removed "
                f"messages contained earlier work in this session. Continue based on the "
                f"recent messages below and the current state of any files or resources."
            )

        _merge_summary_into_tail = False
        last_head_role = messages[compress_start - 1].get("role", "user") if compress_start > 0 else "user"
        first_tail_role = messages[compress_end].get("role", "user") if compress_end < n_messages else "user"
        # Pick a role that avoids consecutive same-role with both neighbors.
        # Priority: avoid colliding with head (already committed), then tail.
        if last_head_role in {"assistant", "tool"}:
            summary_role = "user"
        else:
            summary_role = "assistant"
        # If the chosen role collides with the tail AND flipping wouldn't
        # collide with the head, flip it.
        if summary_role == first_tail_role:
            flipped = "assistant" if summary_role == "user" else "user"
            if flipped != last_head_role:
                summary_role = flipped
            else:
                # Both roles would create consecutive same-role messages
                # (e.g. head=assistant, tail=user — neither role works).
                # Merge the summary into the first tail message instead
                # of inserting a standalone message that breaks alternation.
                _merge_summary_into_tail = True

        # When the summary lands as a standalone role="user" message,
        # weak models read the verbatim "## Active Task" quote of a past
        # user request as fresh input (#11475, #14521). Append the explicit
        # end marker — the same one used in the merge-into-tail path — so
        # the model has a clear "summary above, not new input" signal.
        if not _merge_summary_into_tail and summary_role == "user":
            summary = summary + SUMMARY_END_MARKER

        if not _merge_summary_into_tail:
            # The ``_compressed_summary`` metadata key tags this row as
            # a compression-derived placeholder. ``llm.messages_to_dicts``
            # strips any leading-underscore key before sending to the
            # provider, so this never reaches the wire. Frontends can
            # filter on the key to hide stale summaries from the user
            # without parsing role heuristics. Pattern from
            # hermes-agent `agent/context_compressor.py`.
            compressed.append({
                "role": summary_role,
                "content": summary,
                "_compressed_summary": True,
            })

        for i in range(compress_end, n_messages):
            msg = messages[i].copy()
            if _merge_summary_into_tail and i == compress_end:
                merged_prefix = summary + SUMMARY_END_MARKER + "\n\n"
                msg["content"] = append_text_to_content(
                    msg.get("content"),
                    merged_prefix,
                    prepend=True,
                )
                _merge_summary_into_tail = False
            compressed.append(msg)

        self.compression_count += 1

        compressed = sanitize_tool_pairs(compressed, quiet_mode=self.quiet_mode)

        # Replace image parts in all compressed messages before the newest
        # image-bearing user turn with a short text placeholder. Without
        # this, tail messages keep their original multi-MB base-64 image
        # payloads forever, which can push every subsequent API request
        # past the provider's body-size limit and wedge the session.
        compressed = strip_historical_media(compressed)

        new_estimate = estimate_messages_tokens_rough(compressed)
        saved_estimate = display_tokens - new_estimate

        # Anti-thrashing: track compression effectiveness
        savings_pct = (saved_estimate / display_tokens * 100) if display_tokens > 0 else 0
        self._last_compression_savings_pct = savings_pct
        if savings_pct < 10:
            self._ineffective_compression_count += 1
        else:
            self._ineffective_compression_count = 0

        try:
            record_compaction(
                before_tokens=display_tokens,
                after_tokens=new_estimate,
                threshold_percent=self.threshold_percent,
                context_length=self.context_length,
                session_id=session_id,
            )
        except Exception:
            pass

        if not self.quiet_mode:
            logger.info(
                "Compressed: %d -> %d messages (~%d tokens saved, %.0f%%)",
                n_messages,
                len(compressed),
                saved_estimate,
                savings_pct,
            )
            logger.info("Compression #%d complete", self.compression_count)

        return compressed
