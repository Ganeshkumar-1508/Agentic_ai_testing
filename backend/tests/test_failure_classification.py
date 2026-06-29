"""Tests for the FailureClassifier module (C5).

Each adapter gets unit tests for:
  - Normal pass-through (no pattern matched → OK)
  - Flaky pattern match
  - Defect pattern match
  - Empty/edge-case output
  - The severity and retryable fields

Also tests:
  - ComposedClassifier combines multiple adapters
  - Dict serialization round-trip
  - HistoricalFlakyClassifier (with mocked DB)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from harness.services.failure_classification import (
    ComposedClassifier,
    FailureCategory,
    FailureClassification,
    FailureVerdict,
    HistoricalFlakyClassifier,
    LLMClassifier,
    PatternClassifier,
)


# ---------------------------------------------------------------------------
# FailureClassification
# ---------------------------------------------------------------------------


class TestFailureClassification:
    def test_default_is_ok(self) -> None:
        fc = FailureClassification()
        assert fc.verdict == FailureVerdict.OK
        assert fc.category == FailureCategory.NO_SIGNAL
        assert fc.severity == 0.0
        assert fc.retryable is False

    def test_frozen(self) -> None:
        fc = FailureClassification(verdict=FailureVerdict.DEFECT)
        with pytest.raises(AttributeError):
            fc.verdict = FailureVerdict.OK  # type: ignore[misc]

    def test_verdict_rank_order(self) -> None:
        """Verify severity ranking: OK < UNKNOWN < FLAKY < DEFECT."""
        from harness.services.failure_classification import _verdict_rank
        assert _verdict_rank(FailureVerdict.OK) == 0
        assert _verdict_rank(FailureVerdict.UNKNOWN) == 1
        assert _verdict_rank(FailureVerdict.FLAKY) == 2
        assert _verdict_rank(FailureVerdict.DEFECT) == 3


# ---------------------------------------------------------------------------
# PatternClassifier
# ---------------------------------------------------------------------------


class TestPatternClassifier:
    def test_normal_output_returns_ok(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "All tests passed successfully", True)
        assert result.verdict == FailureVerdict.UNKNOWN
        assert result.category == FailureCategory.UNCLASSIFIED
        assert result.severity == 0.2

    def test_empty_output_returns_unknown(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "", True)
        assert result.verdict == FailureVerdict.UNKNOWN
        assert result.category == FailureCategory.EMPTY
        assert result.severity == 0.0

    def test_timeout_is_flaky_and_retryable(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "Error: timeout after 30s", False)
        assert result.verdict == FailureVerdict.FLAKY
        assert result.category == FailureCategory.TRANSIENT
        assert result.severity == 0.5
        assert result.retryable is True
        assert result.matched_pattern == "timeout"

    def test_network_error_is_flaky(self) -> None:
        c = PatternClassifier()
        result = c.classify("web_fetch", "connection refused: github.com:443", False)
        assert result.verdict == FailureVerdict.FLAKY
        assert result.retryable is True

    def test_rate_limit_is_flaky(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "429 Too Many Requests", False)
        assert result.verdict == FailureVerdict.FLAKY
        assert result.matched_pattern == "rate_limited"

    def test_assertion_error_is_defect(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "AssertionError: expected 5 but got 3", False)
        assert result.verdict == FailureVerdict.DEFECT
        assert result.category == FailureCategory.REAL_FAILURE
        assert result.severity == 0.8
        assert result.retryable is False

    def test_null_reference_is_defect(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "TypeError: Cannot read property 'x' of undefined", False)
        assert result.verdict == FailureVerdict.DEFECT
        assert result.retryable is False

    def test_auth_error_is_defect(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "Error 403: Forbidden", False)
        assert result.verdict == FailureVerdict.DEFECT
        assert result.matched_pattern == "auth_error"

    def test_import_error_is_defect(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "ModuleNotFoundError: No module named 'requests'", False)
        assert result.verdict == FailureVerdict.DEFECT
        assert result.matched_pattern == "import_error"

    def test_service_unavailable_is_flaky(self) -> None:
        c = PatternClassifier()
        result = c.classify("web_fetch", "503 Service Unavailable", False)
        assert result.verdict == FailureVerdict.FLAKY
        assert result.retryable is True

    def test_success_with_error_keyword_still_classifies(self) -> None:
        """Even if success=True, an error-looking output should classify."""
        c = PatternClassifier()
        result = c.classify("bash", "Error: timeout in retry loop", True)
        assert result.verdict == FailureVerdict.FLAKY

    def test_long_output_is_truncated_in_evidence(self) -> None:
        c = PatternClassifier()
        long_out = "Error: timeout " + "x" * 1000
        result = c.classify("bash", long_out, False)
        assert len(result.evidence) <= 200

    def test_recovery_hint_present(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "Error: timeout after 30s", False)
        assert result.recovery_hint == "retry with longer timeout or reduce workload"

    def test_no_hint_for_unknown(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "some random message", True)
        assert result.recovery_hint == ""

    def test_service_unavailable_hint(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "503 Service Unavailable", False)
        assert "retry" in result.recovery_hint

    def test_auth_error_hint(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "403 Forbidden", False)
        assert "credentials" in result.recovery_hint

    def test_custom_patterns_override_defaults(self) -> None:
        c = PatternClassifier(
            flaky_patterns=[(r"(?i)custom_flaky", "custom_flaky", True)],
            defect_patterns=[(r"(?i)custom_defect", "custom_defect", False)],
        )
        flaky = c.classify("bash", "CUSTOM_FLAKY error", False)
        assert flaky.verdict == FailureVerdict.FLAKY
        assert flaky.matched_pattern == "custom_flaky"

        defect = c.classify("bash", "CUSTOM_DEFECT error", False)
        assert defect.verdict == FailureVerdict.DEFECT
        assert defect.matched_pattern == "custom_defect"

    def test_tool_name_is_preserved(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", "Error: timeout", False)
        assert result.tool_name == "bash"

    def test_output_none_is_empty(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", None, False)  # type: ignore[arg-type]
        assert result.verdict == FailureVerdict.UNKNOWN
        assert result.category == FailureCategory.EMPTY

    def test_output_not_string_is_coerced(self) -> None:
        c = PatternClassifier()
        result = c.classify("bash", 123, False)  # type: ignore[arg-type]
        assert result.verdict == FailureVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# HistoricalFlakyClassifier
# ---------------------------------------------------------------------------


class TestHistoricalFlakyClassifier:
    @pytest.mark.asyncio
    async def test_stable_test_returns_ok(self) -> None:
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[
            {"status": "passed", "duration_ms": 100, "created_at": "2026-01-01"},
        ])
        c = HistoricalFlakyClassifier()
        result = await c.classify(db, "test_login", "main")
        assert result.verdict == FailureVerdict.OK

    @pytest.mark.asyncio
    async def test_flaky_test_returns_flaky(self) -> None:
        db = MagicMock()
        # 5 runs, 3 failures → flaky_score >= 0.4
        rows = []
        for i in range(5):
            rows.append({
                "status": "passed" if i % 2 == 0 else "failed",
                "duration_ms": 100,
                "created_at": f"2026-01-0{i+1}",
            })
        db.fetch = AsyncMock(return_value=rows)
        # Also mock execute for the flaky_tests upsert
        db.execute = AsyncMock(return_value=None)
        # Mock fetchval for the flaky score
        db.fetchval = AsyncMock(return_value=0.6)

        c = HistoricalFlakyClassifier(flaky_threshold=0.4)
        result = await c.classify(db, "test_flaky_alt", "main")
        assert result.verdict == FailureVerdict.FLAKY
        assert result.retryable is True

    @pytest.mark.asyncio
    async def test_tool_name_is_set(self) -> None:
        db = MagicMock()
        db.fetch = AsyncMock(return_value=[])
        c = HistoricalFlakyClassifier()
        result = await c.classify(db, "test_specific", "main")
        assert result.tool_name == "test_specific"


# ---------------------------------------------------------------------------
# ComposedClassifier
# ---------------------------------------------------------------------------


class TestComposedClassifier:
    def test_first_classifier_wins_when_more_severe(self) -> None:
        class _AlwaysOk:
            name = "always_ok"
            def classify(self, tool_name, output, success):
                return FailureClassification()

        class _AlwaysDefect:
            name = "always_defect"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.DEFECT,
                    category=FailureCategory.REAL_FAILURE,
                    severity=0.8,
                )

        c = ComposedClassifier([_AlwaysOk(), _AlwaysDefect()])
        result = c.classify("bash", "anything", False)
        assert result.verdict == FailureVerdict.DEFECT

    def test_worst_verdict_wins(self) -> None:
        class _Flaky:
            name = "flaky"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.FLAKY, severity=0.5,
                )

        class _Defect:
            name = "defect"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.DEFECT, severity=0.8,
                )

        c = ComposedClassifier([_Flaky(), _Defect()])
        result = c.classify("bash", "anything", False)
        assert result.verdict == FailureVerdict.DEFECT

    def test_all_ok_returns_ok(self) -> None:
        class _Ok1:
            name = "ok1"
            def classify(self, tool_name, output, success):
                return FailureClassification()

        class _Ok2:
            name = "ok2"
            def classify(self, tool_name, output, success):
                return FailureClassification()

        c = ComposedClassifier([_Ok1(), _Ok2()])
        result = c.classify("bash", "anything", True)
        assert result.verdict == FailureVerdict.OK

    def test_classifier_exception_does_not_crash(self) -> None:
        class _Crashy:
            name = "crashy"
            def classify(self, tool_name, output, success):
                raise RuntimeError("boom")

        class _Defect:
            name = "defect"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.DEFECT, severity=0.8,
                )

        c = ComposedClassifier([_Crashy(), _Defect()])
        result = c.classify("bash", "anything", False)
        assert result.verdict == FailureVerdict.DEFECT

    def test_more_severe_verdict_with_lower_severity(self) -> None:
        """DEFECT always beats FLAKY regardless of severity value."""
        class _HighFlaky:
            name = "high_flaky"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.FLAKY, severity=0.9,
                )

        class _LowDefect:
            name = "low_defect"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.DEFECT, severity=0.3,
                )

        c = ComposedClassifier([_HighFlaky(), _LowDefect()])
        result = c.classify("bash", "anything", False)
        assert result.verdict == FailureVerdict.DEFECT


# ---------------------------------------------------------------------------
# LLMClassifier
# ---------------------------------------------------------------------------


class TestLLMClassifier:
    @pytest.mark.asyncio
    async def test_default_llm_returns_unknown(self) -> None:
        c = LLMClassifier()
        result = await c.classify("bash", "some weird error", False)
        assert result.verdict == FailureVerdict.UNKNOWN
        assert result.category == FailureCategory.UNCLASSIFIED

    @pytest.mark.asyncio
    async def test_llm_says_defect(self) -> None:
        async def _fake_llm(prompt: str) -> str:
            return "DEFECT"
        c = LLMClassifier(llm=_fake_llm)
        result = await c.classify("bash", "Segmentation fault", False)
        assert result.verdict == FailureVerdict.DEFECT
        assert result.category == FailureCategory.REAL_FAILURE

    @pytest.mark.asyncio
    async def test_llm_says_flaky(self) -> None:
        async def _fake_llm(prompt: str) -> str:
            return "FLAKY"
        c = LLMClassifier(llm=_fake_llm)
        result = await c.classify("bash", "connection reset by peer", False)
        assert result.verdict == FailureVerdict.FLAKY
        assert result.retryable is True

    @pytest.mark.asyncio
    async def test_llm_says_ok(self) -> None:
        async def _fake_llm(prompt: str) -> str:
            return "OK"
        c = LLMClassifier(llm=_fake_llm)
        result = await c.classify("bash", "All good", True)
        assert result.verdict == FailureVerdict.OK

    @pytest.mark.asyncio
    async def test_llm_returns_gibberish(self) -> None:
        async def _fake_llm(prompt: str) -> str:
            return "I think this might be a bug but I'm not sure"
        c = LLMClassifier(llm=_fake_llm)
        result = await c.classify("bash", "something strange", False)
        assert result.verdict == FailureVerdict.UNKNOWN

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back(self) -> None:
        async def _fake_llm(prompt: str) -> str:
            raise RuntimeError("LLM is down")
        c = LLMClassifier(llm=_fake_llm)
        result = await c.classify("bash", "something", False)
        assert result.verdict == FailureVerdict.UNKNOWN
        assert result.category == FailureCategory.RCA_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_empty_output(self) -> None:
        async def _fake_llm(prompt: str) -> str:
            return "OK"
        c = LLMClassifier(llm=_fake_llm)
        result = await c.classify("bash", "", True)
        assert result.verdict == FailureVerdict.UNKNOWN
        assert result.category == FailureCategory.EMPTY
        """DEFECT always beats FLAKY regardless of severity value."""
        class _HighFlaky:
            name = "high_flaky"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.FLAKY, severity=0.9,
                )

        class _LowDefect:
            name = "low_defect"
            def classify(self, tool_name, output, success):
                return FailureClassification(
                    verdict=FailureVerdict.DEFECT, severity=0.3,
                )

        c = ComposedClassifier([_HighFlaky(), _LowDefect()])
        result = c.classify("bash", "anything", False)
        assert result.verdict == FailureVerdict.DEFECT



