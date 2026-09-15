"""
tests/test_economics.py — Metrics unit separation tests (I14, I15).

Tests: metric dimensions are distinct, not conflated.
No local byte ratio may be reported as whole-mission savings (I15).
"""

import json
import pytest

from fiofilter.engine import process
from fiofilter.metrics import estimate_tokens, make_metrics
from fiofilter.types import Disposition, EvidenceClass, FilterMetrics, Mode, ToolResult


class TestTokenEstimation:
    def test_estimate_tokens_not_bytes(self):
        """raw_token_estimate ≠ raw_bytes (different units, I14)."""
        content = b"a" * 400  # 400 bytes → ~100 tokens
        tokens = estimate_tokens(content)
        assert tokens != len(content)
        assert abs(tokens - 100.0) < 1.0  # ~100 tokens

    def test_empty_is_zero_tokens(self):
        assert estimate_tokens(b"") == 0.0

    def test_estimate_is_approximation_comment(self):
        """Token estimate uses chars/4 — it's an approximation, not exact."""
        content = b"Hello"  # 5 chars → 1.25 tokens
        assert estimate_tokens(content) == 5 / 4


class TestMetricsSeparation:
    def test_raw_bytes_ne_raw_token_estimate(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """I14: raw_bytes and raw_token_estimate are different values."""
        result = process(noise_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        m = result.metrics
        assert m.raw_bytes != m.raw_token_estimate
        assert m.visible_bytes != m.visible_token_estimate

    def test_all_metrics_fields_present(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """I14: All six metric dimensions are present."""
        result = process(noise_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        m = result.metrics
        assert m.raw_bytes >= 0
        assert m.visible_bytes >= 0
        assert m.raw_token_estimate >= 0
        assert m.visible_token_estimate >= 0
        assert m.transform_duration_ms >= 0
        assert m.decision is not None
        assert m.evidence_class is not None
        assert m.mode is not None

    def test_metrics_logged_for_raw_path(
        self, canonical_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """I16: Metrics logged even when disposition is RAW."""
        process(canonical_tool_result, raw_store=tmp_raw_store,
                metrics_log_path=tmp_metrics_log)
        lines = tmp_metrics_log.read_text().strip().splitlines()
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert "raw_bytes" in record
        assert "visible_bytes" in record
        assert "raw_token_estimate" in record
        assert "visible_token_estimate" in record
        assert "decision" in record
        assert "evidence_class" in record
        assert "mode" in record

    def test_byte_reduction_pct_is_local_only(
        self, noise_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """I15: byte_reduction_pct in log is labeled as LOCAL metric.
        The log record must not claim whole-mission equivalence.
        """
        process(noise_tool_result, mode=Mode.EXPLORE, raw_store=tmp_raw_store,
                metrics_log_path=tmp_metrics_log)
        lines = tmp_metrics_log.read_text().strip().splitlines()
        record = json.loads(lines[0])
        # Field exists and is a number
        assert isinstance(record.get("byte_reduction_pct"), (int, float))
        # The field name makes no claim about whole-mission savings.
        # (I15: no log field named "mission_savings" or "token_savings")
        assert "mission_savings" not in record
        assert "whole_mission" not in record


class TestNoExpansionInMetrics:
    def test_transform_visible_lte_raw(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """I9: visible_bytes ≤ raw_bytes always (transform cannot expand)."""
        result = process(noise_tool_result, mode=Mode.EXPLORE, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        assert result.metrics.visible_bytes <= result.metrics.raw_bytes
