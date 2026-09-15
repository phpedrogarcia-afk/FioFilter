"""
tests/test_mode_escalation.py — Mode and failure escalation tests (I6).

Tests: EXPLORE/BUILD/PROVE disposition behavior; failure escalation.
"""

import pytest

from fiofilter.engine import process
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult


class TestFailureEscalationInAllModes:
    def test_failure_in_explore_is_raw(self, failure_tool_result, tmp_raw_store, tmp_metrics_log):
        """I6: FAILURE in EXPLORE mode → RAW (escalates from EXPLORE behavior)."""
        result = process(failure_tool_result, mode=Mode.EXPLORE,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    def test_failure_in_build_is_raw(self, failure_tool_result, tmp_raw_store, tmp_metrics_log):
        result = process(failure_tool_result, mode=Mode.BUILD,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    def test_failure_in_prove_is_raw(self, failure_tool_result, tmp_raw_store, tmp_metrics_log):
        result = process(failure_tool_result, mode=Mode.PROVE,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)


class TestProveModeLockdown:
    def test_noise_in_prove_is_transformed(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        result = process(noise_tool_result, mode=Mode.PROVE,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.disposition == Disposition.TRANSFORM
        assert len(result.content) < len(noise_tool_result.content)

    def test_discovery_in_prove_is_raw(self, tmp_raw_store, tmp_metrics_log):
        """DISCOVERY in PROVE mode → RAW."""
        content = b"total 12\ndrwxr-xr-x  2 user staff  64 Sep 15 12:00 .\n" * 2
        tr = ToolResult(content=content, source="shell")
        result = process(tr, mode=Mode.PROVE, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        # In PROVE mode, DISCOVERY should be RAW
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)


class TestModePresentInResult:
    def test_mode_recorded_in_result(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        for mode in Mode:
            result = process(noise_tool_result, mode=mode, raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
            assert result.mode == mode
            assert result.metrics.mode == mode
