"""Context compression package.

Splits the original 1741-line ``harness/context_compressor.py`` god module
into four focused modules by concern:

  * :mod:`harness.context_compressor.content` — pure data-shape helpers
    (multimodal length, text view, JSON-safe argument shrinking,
    image-part stripping). No state, no I/O.
  * :mod:`harness.context_compressor.pruning` — cheap pre-pass helpers
    (tool-result summaries, dedupe, tool-call argument shrinking,
    boundary alignment, tail protection by token budget, tool-pair
    sanitisation).
  * :mod:`harness.context_compressor.summary` — LLM-backed helpers
    (summary budget, serialisation, structured-prompt generation,
    model fallback, summary-prefix management, tail cut by tokens).
  * :mod:`harness.context_compressor.compressor` — the
    :class:`ContextCompressor` state machine that glues the three
    modules together.

Backward-compat: this package re-exports :class:`ContextCompressor` and
the two ``SUMMARY_PREFIX`` constants so existing imports
(``from harness.context_compressor import ContextCompressor``) keep
working unchanged.
"""
from harness.context_compressor.compressor import (
    ContextCompressor,
    LEGACY_SUMMARY_PREFIX,
    SUMMARY_PREFIX,
)


__all__ = ["ContextCompressor", "SUMMARY_PREFIX", "LEGACY_SUMMARY_PREFIX"]
