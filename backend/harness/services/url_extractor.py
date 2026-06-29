"""URLAutoExtractor &mdash; regex-based GitHub URL detection from text.

Wire of C03 (orchestrator decomposition), Phase 4. The original
``harness.orchestrator.OrchestratorEngine.run_single`` had a
30-line block that:

1. ran a regex over the ``goal`` string looking for a GitHub URL,
2. if that missed, ran the same regex over the ``spec.prompt``
   string,
3. stripped trailing punctuation (``.strip('/.,;:')``),
4. logged the auto-extraction.

The logic has zero dependencies and zero state &mdash; it
is a pure function of two input strings. The extraction is
the obvious first collaborator to pull out of ``run_single``
because it has no coupling to the sandbox, the DB, the
delegate_task tool, or any other local.

Per :mod:`CONTEXT.md` glossary:
- **URLAutoExtractor** &mdash; this module
- **extract_from_goal** &mdash; pure: regex on the goal string
- **extract_from_prompt** &mdash; pure: regex on the spec prompt
- **extract** &mdash; orchestrator: try goal first, then prompt,
  return the first match or ``None``
- **GITHUB_URL_PATTERN** &mdash; the shared regex
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

logger = logging.getLogger(__name__)


class URLAutoExtractor:
    """Regex-based GitHub URL detection from free-form text.

    The LLM (or the user, in a chat submission) often embeds
    the repo URL in the prompt text instead of using the
    ``repo_url`` parameter. This module finds it.
    """

    #: The shared regex for GitHub URLs. Matches
    #: ``https://github.com/<org>/<repo>`` and
    #: ``http://github.com/<org>/<repo>`` with optional
    #: trailing path (``/issues/123``, ``/blob/main/README.md``,
    #: ``/tree/v1.0``). Stops at whitespace and the common
    #: punctuation that ends a sentence (``), ``]`` ``"`` ``'``
    #: ``<`` ``>``).
    GITHUB_URL_PATTERN: ClassVar[str] = (
        r'https?://github\.com/[^\s,)\]"\'<>]+'
    )

    #: Compiled regex &mdash; one instance reused across calls.
    #: ``re.search`` against this is the hot path; the engine
    #: calls it at most twice per ``run_single``.
    _COMPILED: ClassVar[re.Pattern[str] | None] = None

    #: Trailing characters to strip after the regex match.
    #: These appear when the URL is at the end of a sentence
    #: in the prompt ("see https://github.com/foo/bar.").
    TRAILING_CHARS: ClassVar[str] = "/.,;:"

    # ------------------------------------------------------------------
    # Pure: regex on a single string. No DB, no I/O.
    # ------------------------------------------------------------------

    @staticmethod
    def _match(text: str) -> str | None:
        """Run the regex on ``text`` and return the cleaned URL, or ``None``.

        "Cleaned" means trailing ``/.,;:`` stripped &mdash; the
        original function used ``.rstrip('/.,;:')`` to handle
        the case where the URL is followed by a sentence-ending
        period or a trailing slash. We keep the same
        behaviour.
        """
        if not text:
            return None
        regex = URLAutoExtractor._get_compiled()
        match = regex.search(text)
        if not match:
            return None
        return match.group(0).rstrip(URLAutoExtractor.TRAILING_CHARS)

    @staticmethod
    def _get_compiled() -> re.Pattern[str]:
        """Lazily compile the regex; cache in a class var.

        ``re.compile`` is cheap but called once per
        ``run_single``; the cache is the obvious micro-opt.
        """
        if URLAutoExtractor._COMPILED is None:
            URLAutoExtractor._COMPILED = re.compile(URLAutoExtractor.GITHUB_URL_PATTERN)
        return URLAutoExtractor._COMPILED

    # ------------------------------------------------------------------
    # Orchestrators: combine the two sources with the right
    # precedence.
    # ------------------------------------------------------------------

    @staticmethod
    def extract_from_goal(goal: str) -> str | None:
        """Run the regex on the engine's ``goal`` string.

        This is the first place the LLM (or the chat Role's
        ``submit_job`` wrapper) usually embeds the URL.
        """
        url = URLAutoExtractor._match(goal)
        if url:
            logger.info("Auto-extracted repo_url from goal: %s", url)
        return url

    @staticmethod
    def extract_from_prompt(spec_prompt: str) -> str | None:
        """Run the regex on the ``JobSpec.prompt`` string.

        This is the fallback when the goal doesn't have a URL
        &mdash; the spec's original prompt often does.
        """
        url = URLAutoExtractor._match(spec_prompt)
        if url:
            logger.info("Auto-extracted repo_url from prompt: %s", url)
        return url

    @staticmethod
    def extract(goal: str, spec_prompt: str = "") -> str | None:
        """Try the goal first, then the spec prompt. Return the first match.

        Matches the original ``run_single`` behaviour:
        1. If ``goal`` contains a URL, return it.
        2. Else, if ``spec_prompt`` contains a URL, return it.
        3. Else, return ``None``.

        The ``spec_prompt`` argument is optional so callers that
        only have a goal (e.g. a chat submission that hasn't been
        wrapped in a ``JobSpec`` yet) can still use this method.
        """
        url = URLAutoExtractor.extract_from_goal(goal)
        if url:
            return url
        return URLAutoExtractor.extract_from_prompt(spec_prompt)
