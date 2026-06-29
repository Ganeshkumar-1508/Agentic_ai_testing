"""Failure classification — typed verdict for every tool call.

Consumes the ``rca_verdict`` dict that ``ToolRegistry.execute()``
already attaches to every ``ToolResult`` and promotes it to a typed,
composable module with real consumers.

Three adapters at one seam (``FailureClassifier`` Protocol):
  1. PatternClassifier   — regex-based (flaky/defect patterns from rca.py)
  2. HistoricalFlaky     — per-test pass/fail history (wraps flaky_detector)
  3. LLMClassifier       — LLM-based for ambiguous cases (future)

Two design additions from production-harness research:
  - retryable flag (CrewAI guardrails pattern): transient failures
    auto-retry instead of surfacing to the agent
  - severity score (TestSprite pattern): 0.0-1.0 so the success
    detector can weight verdicts (DEFECT*5 + FLAKY*1 vs clean)
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FailureVerdict(str, Enum):
    """The five-class verdict taxonomy."""
    OK = "ok"
    FLAKY = "flaky"
    DEFECT = "defect"
    UNKNOWN = "unknown"


class FailureCategory(str, Enum):
    """Why the verdict was assigned."""
    NO_SIGNAL = "no_signal"
    TRANSIENT = "transient"
    REAL_FAILURE = "real_failure"
    EMPTY = "empty"
    UNCLASSIFIED = "unclassified"
    RCA_UNAVAILABLE = "rca_unavailable"
    RECOVERED = "recovered"


# ---------------------------------------------------------------------------
# Typed classification — replaces the raw dict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureClassification:
    """Structured outcome of failure classification.

    ``verdict`` — the high-level category (ok / flaky / defect / unknown).
    ``category`` — why that verdict was assigned (transient / real_failure / ...).
    ``matched_pattern`` — the regex pattern that matched (for observability).
    ``tool_name`` — the tool that produced this output.
    ``severity`` — 0.0 (harmless) to 1.0 (critical). A ``defect`` verdict
        always gets >=0.7. A ``flaky`` gets 0.3-0.6. ``ok`` gets 0.0.
    ``retryable`` — if True, the caller should auto-retry the tool call
        instead of surfacing the error to the agent. Transient flaky
        failures are retryable; real defects are not.
    ``evidence`` — short excerpt of what triggered the match (first 200 chars).
    ``recovery_hint`` — optional suggestion for how to resolve (e.g.
        "retry with backoff", "check credentials", "increase timeout").
    """
    verdict: FailureVerdict = FailureVerdict.OK
    category: FailureCategory = FailureCategory.NO_SIGNAL
    matched_pattern: str | None = None
    tool_name: str = ""
    severity: float = 0.0
    retryable: bool = False
    evidence: str = ""
    recovery_hint: str = ""
    n_retries: int = 0


# ---------------------------------------------------------------------------
# Protocol — every adapter implements this
# ---------------------------------------------------------------------------


class FailureClassifier(Protocol):
    """Classify a single tool-call result.

    Pure function shape: ``(tool_name, output, success) → FailureClassification``.
    """
    name: str

    def classify(
        self, tool_name: str, output: str, success: bool,
    ) -> FailureClassification: ...


# ---------------------------------------------------------------------------
# PatternClassifier — regex-based, uses FLAKY_PATTERNS / DEFECT_PATTERNS
# ---------------------------------------------------------------------------

# Common flaky patterns in error messages
_FLAKY_PATTERNS: list[tuple[str, str, bool]] = [
    (r"(?i)timeout", "timeout", True),
    (r"(?i)network|connection refused|reset", "network", True),
    (r"(?i)element[^ ]* not (found|interactable|visible|clickable)", "element_not_found", True),
    (r"(?i)stale element", "stale_element", True),
    (r"(?i)no such element", "no_such_element", True),
    (r"(?i)session.*not (created|found)", "session_error", True),
    (r"(?i)unexpected alert", "unexpected_alert", True),
    (r"(?i)port.*in use", "port_in_use", True),
    (r"(?i)resource.*(exhausted|busy|unavailable)", "resource_exhausted", True),
    (r"(?i)retry|retryable", "retry_signal", True),
    (r"(?i)intermittent", "intermittent", True),
    (r"(?i)flaky", "flaky_signal", True),
    (r"(?i)animation|transition.*not (finished|complete)", "animation_incomplete", True),
    (r"(?i)async.*timeout", "async_timeout", True),
    (r"(?i)rate limit|429|too many requests", "rate_limited", True),
    (r"(?i)service unavailable|503", "service_unavailable", True),
    (r"(?i)gateway timeout|504", "gateway_timeout", True),
]

# Patterns suggesting real defects (NOT retryable)
_DEFECT_PATTERNS: list[tuple[str, str, bool]] = [
    (r"(?i)assertion.*failed|assert.*error", "assertion_failed", False),
    (r"(?i)expected.*but.*got|expected.*actual", "assertion_mismatch", False),
    (r"(?i)nullpointer|null reference|undefined", "null_reference", False),
    (r"(?i)typeerror|cannot read property", "type_error", False),
    (r"(?i)keyerror|indexerror|valueerror", "key_error", False),
    (r"(?i)divide by zero|division by zero", "math_error", False),
    (r"(?i)attributeerror|nameerror", "attribute_error", False),
    (r"(?i)syntaxerror", "syntax_error", False),
    (r"(?i)exception.*not handled", "unhandled_exception", False),
    (r"(?i)500|502|503|504", "http_server_error", False),
    (r"(?i)unauthorized|forbidden|403|401", "auth_error", False),
    (r"(?i)not found.*404|404.*not found", "not_found", False),
    (r"(?i)validation.*failed|invalid.*input", "validation_error", False),
    (r"(?i)circular import|import error|modulenotfound", "import_error", False),
    (r"(?i)permission denied|eaccès", "permission_denied", False),
    (r"(?i)disk full|no space left", "disk_full", False),
    (r"(?i)out of memory|memoryerror|oom", "out_of_memory", False),
]


class PatternClassifier:
    """Classify tool output by pattern-matching known error strings.

    Two pattern groups with different severity and retryability:
      - Flaky patterns (transient, retryable, severity ~0.3-0.6)
      - Defect patterns (real failure, NOT retryable, severity >=0.8)

    Usage::

        classifier = PatternClassifier()
        result = classifier.classify("bash", "Error: timeout", False)
        # FailureClassification(verdict=FLAKY, severity=0.5, retryable=True)
    """

    name = "pattern_classifier"

    def __init__(
        self,
        flaky_patterns: list[tuple[str, str, bool]] | None = None,
        defect_patterns: list[tuple[str, str, bool]] | None = None,
    ) -> None:
        self._flaky_patterns = flaky_patterns if flaky_patterns is not None else _FLAKY_PATTERNS
        self._defect_patterns = defect_patterns if defect_patterns is not None else _DEFECT_PATTERNS

    def classify(
        self, tool_name: str, output: str, success: bool,
    ) -> FailureClassification:
        text = str(output or "")
        if not text:
            return FailureClassification(
                verdict=FailureVerdict.UNKNOWN,
                category=FailureCategory.EMPTY,
                tool_name=tool_name,
            )

        for pat, label, retryable in self._flaky_patterns:
            if re.search(pat, text):
                excerpt = text[:200]
                return FailureClassification(
                    verdict=FailureVerdict.FLAKY,
                    category=FailureCategory.TRANSIENT,
                    matched_pattern=label,
                    tool_name=tool_name,
                    severity=0.5,
                    retryable=retryable,
                    evidence=excerpt,
                    recovery_hint=self._recovery_hint(label),
                )

        for pat, label, retryable in self._defect_patterns:
            if re.search(pat, text):
                excerpt = text[:200]
                return FailureClassification(
                    verdict=FailureVerdict.DEFECT,
                    category=FailureCategory.REAL_FAILURE,
                    matched_pattern=label,
                    tool_name=tool_name,
                    severity=0.8,
                    retryable=retryable,
                    evidence=excerpt,
                    recovery_hint=self._recovery_hint(label),
                )

        return FailureClassification(
            verdict=FailureVerdict.UNKNOWN,
            category=FailureCategory.UNCLASSIFIED,
            tool_name=tool_name,
            severity=0.2,
        )

    @staticmethod
    def _recovery_hint(pattern_label: str) -> str:
        hints = {
            "timeout": "retry with longer timeout or reduce workload",
            "network": "check connectivity and retry",
            "rate_limited": "wait and retry with backoff",
            "resource_exhausted": "reduce concurrency or increase resources",
            "service_unavailable": "retry after service recovers",
            "gateway_timeout": "retry with longer timeout",
            "auth_error": "check credentials and permissions",
            "permission_denied": "verify file permissions and user rights",
            "disk_full": "free disk space and retry",
            "out_of_memory": "reduce input size or increase memory limit",
            "import_error": "install missing dependencies",
            "assertion_failed": "fix the failing assertion in code",
            "validation_error": "correct the input format",
            "not_found": "verify the path or resource exists",
            "null_reference": "add null check before access",
        }
        return hints.get(pattern_label, "")


# ---------------------------------------------------------------------------
# HistoricalFlakyClassifier — per-test pass/fail history
# ---------------------------------------------------------------------------


class HistoricalFlakyClassifier:
    """Classify based on per-test historical pass/fail ratio.

    Wraps the existing ``flaky_detector`` module. A test that has
    flaky_score >= 0.4 gets ``FLAKY`` verdict even if the current
    call's output looks clean — the history is the signal.

    Usage::

        classifier = HistoricalFlakyClassifier()
        result = await classifier.classify(db, "test_login", "passed", "main")
        # FailureClassification(verdict=OK) if stable
        # FailureClassification(verdict=FLAKY, severity=0.6) if flaky
    """

    name = "historical_flaky"

    def __init__(self, flaky_threshold: float = 0.4) -> None:
        self.flaky_threshold = flaky_threshold

    async def classify(
        self,
        db: Any,
        test_name: str,
        branch: str = "",
    ) -> FailureClassification:
        try:
            from harness.flaky_detector import update_flaky_score
            result = await update_flaky_score(db, test_name, branch)
        except Exception as exc:
            logger.debug("HistoricalFlakyClassifier failed: %s", exc)
            return FailureClassification(
                verdict=FailureVerdict.UNKNOWN,
                category=FailureCategory.RCA_UNAVAILABLE,
                tool_name=test_name,
            )

        score = float(result.get("flaky_score", 0.0))
        if score >= self.flaky_threshold:
            return FailureClassification(
                verdict=FailureVerdict.FLAKY,
                category=FailureCategory.TRANSIENT,
                tool_name=test_name,
                severity=min(score, 0.9),
                retryable=True,
                evidence=f"historical flaky_score={score:.2f} over {result.get('total_runs', 0)} runs",
            )

        return FailureClassification(
            verdict=FailureVerdict.OK,
            category=FailureCategory.NO_SIGNAL,
            tool_name=test_name,
            severity=score,
        )


# ---------------------------------------------------------------------------
# ComposedClassifier — runs multiple classifiers and returns the worst verdict
# ---------------------------------------------------------------------------


class ComposedClassifier:
    """Run multiple classifiers and return the most severe verdict.

    Useful for combining pattern-based and history-based classification::

        classifier = ComposedClassifier([
            PatternClassifier(),
            historical_lambda,
        ])
        result = classifier.classify(tool_name, output, success)
    """

    name = "composed_classifier"

    def __init__(self, classifiers: list) -> None:
        self._classifiers = list(classifiers)

    def classify(
        self, tool_name: str, output: str, success: bool,
    ) -> FailureClassification:
        worst: FailureClassification | None = None
        for c in self._classifiers:
            try:
                result = c.classify(tool_name, output, success)
                if worst is None or _verdict_rank(result.verdict) > _verdict_rank(worst.verdict):
                    worst = result
                elif result.verdict == worst.verdict and result.severity > worst.severity:
                    worst = result
            except Exception as exc:
                logger.debug("classifier %s failed: %s", getattr(c, "name", c), exc)
        return worst or FailureClassification(
            verdict=FailureVerdict.UNKNOWN,
            category=FailureCategory.RCA_UNAVAILABLE,
            tool_name=tool_name,
        )


# ---------------------------------------------------------------------------
# LLMClassifier — uses an LLM to classify ambiguous failures
# ---------------------------------------------------------------------------

_LLM_CLASSIFY_PROMPT = """You are a failure classifier for an AI coding agent.
Analyze the tool output below and determine if it indicates:

1. A REAL DEFECT — the tool output contains a genuine bug in the code being built.
2. A FLAKY/TRANSIENT failure — the tool output shows an environmental issue
   (timeout, network, rate limit, resource exhaustion) that would resolve on retry.
3. OK / NO SIGNAL — the tool output is normal or doesn't indicate any issue.
4. UNKNOWN — can't determine from the available information.

Tool: {tool_name}
Output: {output}

Respond with exactly one word: DEFECT, FLAKY, OK, or UNKNOWN."""


class LLMClassifier:
    """Use an LLM to classify ambiguous tool outputs.

    Wired into ``ComposedClassifier`` after ``PatternClassifier`` so
    it only runs on outputs no pattern matched. The LLM catches
    patterns the regexes miss — novel error formats, domain-specific
    failures, or edge cases.

    Usage::

        classifier = ComposedClassifier([
            PatternClassifier(),
            LLMClassifier(llm=lambda prompt: ...),
        ])
        result = classifier.classify("bash", "some ambiguous error", False)
    """

    name = "llm_classifier"

    def __init__(
        self,
        llm: Callable[[str], Awaitable[str]] | None = None,
        *,
        classify_only_unknown: bool = True,
    ) -> None:
        self._llm = llm or self._default_llm
        self._classify_only_unknown = classify_only_unknown

    async def classify(
        self, tool_name: str, output: str, success: bool,
    ) -> FailureClassification:
        text = str(output or "")
        if not text:
            return FailureClassification(
                verdict=FailureVerdict.UNKNOWN,
                category=FailureCategory.EMPTY,
                tool_name=tool_name,
            )

        prompt = _LLM_CLASSIFY_PROMPT.format(tool_name=tool_name, output=text[:1500])
        try:
            response = await self._llm(prompt)
        except Exception as exc:
            logger.debug("LLMClassifier llm call failed: %s", exc)
            return FailureClassification(
                verdict=FailureVerdict.UNKNOWN,
                category=FailureCategory.RCA_UNAVAILABLE,
                tool_name=tool_name,
            )

        verdict_str = response.strip().upper().split("\n")[0].split(".")[0].strip()
        if verdict_str == "DEFECT":
            return FailureClassification(
                verdict=FailureVerdict.DEFECT,
                category=FailureCategory.REAL_FAILURE,
                tool_name=tool_name,
                severity=0.8,
                evidence=text[:200],
                recovery_hint="LLM classified as defect — investigate the code",
            )
        if verdict_str == "FLAKY":
            return FailureClassification(
                verdict=FailureVerdict.FLAKY,
                category=FailureCategory.TRANSIENT,
                tool_name=tool_name,
                severity=0.4,
                retryable=True,
                evidence=text[:200],
                recovery_hint="LLM classified as transient — retry may succeed",
            )
        if verdict_str == "OK":
            return FailureClassification(
                verdict=FailureVerdict.OK,
                category=FailureCategory.NO_SIGNAL,
                tool_name=tool_name,
            )

        return FailureClassification(
            verdict=FailureVerdict.UNKNOWN,
            category=FailureCategory.UNCLASSIFIED,
            tool_name=tool_name,
            evidence=text[:200],
        )

    @staticmethod
    async def _default_llm(prompt: str) -> str:
        """Fallback: return UNKNOWN when no LLM is configured."""
        return "UNKNOWN"


def _verdict_rank(v: FailureVerdict) -> int:
    """Higher = more severe."""
    return {"ok": 0, "unknown": 1, "flaky": 2, "defect": 3}.get(v, 0)



