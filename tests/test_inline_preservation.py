"""
tests/test_inline_preservation.py — Critical inline fact preservation (I4).

Tests: inline-required facts survive transforms or trigger RAW fallback.
Quality gate: INLINE_REQUIRED_CRITICAL_FACT_PRESERVATION = 100%
"""

import pytest

from fiofilter.engine import _inline_facts_present
from fiofilter.engine import process
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult


class TestInlineFunctionDirectly:
    def test_all_facts_present(self):
        content = b"commit abc1234\nOn branch main\nclean"
        facts = ["commit abc1234", "On branch main"]
        assert _inline_facts_present(content, facts) is True

    def test_missing_fact_returns_false(self):
        content = b"commit abc1234\nclean"
        facts = ["commit abc1234", "On branch missing"]
        assert _inline_facts_present(content, facts) is False

    def test_empty_facts_always_true(self):
        content = b"any content"
        assert _inline_facts_present(content, []) is True

    def test_empty_content_with_facts_false(self):
        content = b""
        assert _inline_facts_present(content, ["expected fact"]) is False


class TestInlineFactsInEngine:
    def test_canonical_result_has_inline_facts(
        self, canonical_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """Canonical content returns RAW; inline facts present in content."""
        result = process(canonical_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        # Canonical → RAW → content == original → facts definitely present
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)
        original = canonical_tool_result.content.decode("utf-8", errors="replace")
        result_text = result.content.decode("utf-8", errors="replace")
        assert "commit" in result_text or "On branch" in result_text

    def test_i4_raw_content_has_all_facts(self, canonical_tool_result, tmp_raw_store, tmp_metrics_log):
        """When disposition is RAW, content == original → all facts present by definition."""
        result = process(canonical_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        # content must be the original (since it's RAW)
        assert result.content == canonical_tool_result.content


class TestInlineFactsWithTransform:
    def test_transformed_noise_does_not_remove_visible_content(
        self, noise_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """Even after T01, the fold marker preserves the line content."""
        result = process(noise_tool_result, mode=Mode.EXPLORE,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        # The original repeated line should appear in the result
        original_line = b"Building... [   OK   ]"
        assert original_line in result.content
