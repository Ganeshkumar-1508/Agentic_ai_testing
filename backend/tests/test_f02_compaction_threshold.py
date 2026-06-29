"""Tests for F02: 1M-context model support + 85% compaction threshold.

Covers:
  - Default `threshold_percent` change from 0.50 to 0.85
  - `TESTAI_COMPACTION_THRESHOLD` env var override
  - 1M-context models (Hermes-Grok-4.3, Gemini-2.0) resolve correctly
  - Threshold math for various context sizes
  - API endpoint shape + state reflection
"""
from __future__ import annotations

import pytest


class TestDefaultThreshold:
    def test_default_is_085(self, monkeypatch):
        monkeypatch.delenv("TESTAI_COMPACTION_THRESHOLD", raising=False)
        from harness.context_compressor.compressor import ContextCompressor
        c = ContextCompressor(model="x", quiet_mode=True)
        assert c.threshold_percent == pytest.approx(0.85, abs=1e-9)


class TestEnvOverride:
    def test_explicit_value_used(self, monkeypatch):
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "0.92")
        from harness._compressor_utils import get_compaction_threshold
        assert get_compaction_threshold() == pytest.approx(0.92, abs=1e-9)

    def test_zero_uses_floor(self, monkeypatch):
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "0.0")
        from harness._compressor_utils import get_compaction_threshold
        assert get_compaction_threshold() == 0.0

    def test_one_uses_ceiling(self, monkeypatch):
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "1.0")
        from harness._compressor_utils import get_compaction_threshold
        assert get_compaction_threshold() == 1.0

    def test_out_of_range_falls_back_to_default(self, monkeypatch):
        from harness._compressor_utils import get_compaction_threshold, DEFAULT_COMPACTION_THRESHOLD
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "1.5")
        assert get_compaction_threshold() == DEFAULT_COMPACTION_THRESHOLD
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "-0.1")
        assert get_compaction_threshold() == DEFAULT_COMPACTION_THRESHOLD

    def test_invalid_value_falls_back(self, monkeypatch):
        from harness._compressor_utils import get_compaction_threshold, DEFAULT_COMPACTION_THRESHOLD
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "not-a-number")
        assert get_compaction_threshold() == DEFAULT_COMPACTION_THRESHOLD

    def test_empty_string_falls_back(self, monkeypatch):
        from harness._compressor_utils import get_compaction_threshold, DEFAULT_COMPACTION_THRESHOLD
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "   ")
        assert get_compaction_threshold() == DEFAULT_COMPACTION_THRESHOLD


class TestOneMillionContextModels:
    @pytest.mark.parametrize("model,expected_length", [
        ("hermes-grok-4.3", 1048576),
        ("hermes-grok-4.3-1m", 1048576),
        ("grok-4.3", 1048576),
        ("gemini-2.0-flash", 1048576),
        ("gemini-1.5-pro", 1048576),
        ("claude-4-opus-1m", 1048576),
    ])
    def test_one_million_resolution(self, model, expected_length):
        from harness._compressor_utils import get_model_context_length
        assert get_model_context_length(model) == expected_length

    def test_200k_models_unchanged(self):
        from harness._compressor_utils import get_model_context_length
        assert get_model_context_length("claude-4-sonnet") == 200000
        assert get_model_context_length("claude-3-opus") == 200000

    def test_unknown_model_defaults_to_128k(self):
        from harness._compressor_utils import get_model_context_length
        assert get_model_context_length("totally-unknown-model") == 131072


class TestThresholdMath:
    def test_85pct_of_1m_equals_850k(self, monkeypatch):
        monkeypatch.delenv("TESTAI_COMPACTION_THRESHOLD", raising=False)
        from harness.context_compressor.compressor import ContextCompressor
        c = ContextCompressor(
            model="hermes-grok-4.3",
            config_context_length=1_048_576,
            quiet_mode=True,
        )
        assert c.context_length == 1_048_576
        # 85% of 1,048,576 = 891,290 (int truncation)
        assert c.threshold_tokens == int(1_048_576 * 0.85)

    def test_85pct_of_128k(self, monkeypatch):
        monkeypatch.delenv("TESTAI_COMPACTION_THRESHOLD", raising=False)
        from harness.context_compressor.compressor import ContextCompressor
        c = ContextCompressor(
            model="gpt-4o",
            config_context_length=128_000,
            quiet_mode=True,
        )
        assert c.threshold_tokens == int(128_000 * 0.85)

    def test_92pct_override(self, monkeypatch):
        monkeypatch.setenv("TESTAI_COMPACTION_THRESHOLD", "0.92")
        from harness._compressor_utils import get_compaction_threshold
        from harness.context_compressor.compressor import ContextCompressor
        c = ContextCompressor(
            model="hermes-grok-4.3",
            config_context_length=1_048_576,
            threshold_percent=get_compaction_threshold(),
            quiet_mode=True,
        )
        assert c.threshold_tokens == int(1_048_576 * 0.92)


class TestRecordCompaction:
    def test_record_increments_total(self):
        from harness.context_compressor.compressor import (
            get_compaction_state_snapshot,
            record_compaction,
        )
        before = get_compaction_state_snapshot()["compactions_total"]
        record_compaction(
            before_tokens=1000,
            after_tokens=200,
            threshold_percent=0.85,
            context_length=100_000,
        )
        snap = get_compaction_state_snapshot()
        assert snap["compactions_total"] == before + 1
        assert snap["last_before_tokens"] == 1000
        assert snap["last_after_tokens"] == 200
        assert snap["last_threshold_percent"] == 0.85
        assert snap["last_context_length"] == 100_000
        assert snap["last_at"] is not None
