"""
tests/test_decision_engine.py — Full pipeline integration tests.

Tests: all disposition paths, fail-open, protected evidence, mode effects.
Quality gate: FAILURE_DIAGNOSTIC_UNSAFE_CASES = 0
"""

import pathlib
import pytest

from fiofilter.engine import process
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult


class TestProtectedClassesAlwaysRAW:
    def test_authority_content_is_raw_all_modes(
        self, authority_content, tmp_raw_store, tmp_metrics_log
    ):
        for mode in Mode:
            tr = ToolResult(content=authority_content, source="shell")
            result = process(tr, mode=mode, raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
            assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW), \
                f"Expected RAW for AUTHORITY in {mode}, got {result.disposition}"

    def test_security_content_is_raw_all_modes(
        self, security_content, tmp_raw_store, tmp_metrics_log
    ):
        for mode in Mode:
            tr = ToolResult(content=security_content, source="shell")
            result = process(tr, mode=mode, raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
            assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    def test_failure_is_raw_all_modes(
        self, failure_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        for mode in Mode:
            result = process(failure_tool_result, mode=mode, raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
            assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    def test_unknown_is_raw_all_modes(
        self, unknown_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        for mode in Mode:
            result = process(unknown_tool_result, mode=mode, raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
            assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    def test_canonical_is_raw_all_modes(
        self, canonical_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        for mode in Mode:
            result = process(canonical_tool_result, mode=mode, raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
            assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)


class TestRAWStoreAlwaysWritten:
    def test_raw_ref_always_present(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """FilterResult always has a raw_ref, even for RAW disposition."""
        result = process(noise_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        assert result.raw_ref is not None
        assert result.raw_sha256 is not None

    def test_raw_store_recoverable_after_transform(
        self, noise_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """After transform, original bytes recoverable from RAW store."""
        original = noise_tool_result.content
        result = process(noise_tool_result, mode=Mode.BUILD, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        recovered = tmp_raw_store.read(result.raw_ref, verify=True)
        assert recovered == original


class TestMetricsAlwaysEmitted:
    def test_metrics_emitted_for_raw_disposition(
        self, canonical_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """I16: Metrics logged even for RAW disposition."""
        process(canonical_tool_result, mode=Mode.BUILD, raw_store=tmp_raw_store,
                metrics_log_path=tmp_metrics_log)
        assert tmp_metrics_log.exists()
        lines = tmp_metrics_log.read_text().strip().splitlines()
        assert len(lines) >= 1

    def test_metrics_emitted_for_transform_disposition(
        self, noise_tool_result, tmp_raw_store, tmp_metrics_log
    ):
        """I16: Metrics logged for TRANSFORM disposition."""
        process(noise_tool_result, mode=Mode.EXPLORE, raw_store=tmp_raw_store,
                metrics_log_path=tmp_metrics_log)
        lines = tmp_metrics_log.read_text().strip().splitlines()
        assert len(lines) >= 1


class TestModeEffects:
    def test_noise_transforms_in_explore(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """NOISE in EXPLORE mode → TRANSFORM disposition expected."""
        result = process(noise_tool_result, mode=Mode.EXPLORE, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        assert result.disposition == Disposition.TRANSFORM
        assert len(result.content) < len(noise_tool_result.content)

    def test_noise_in_build_mode(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """NOISE in BUILD mode → policy allows TRANSFORM."""
        result = process(noise_tool_result, mode=Mode.BUILD, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        assert result.disposition == Disposition.TRANSFORM


class TestFilterResultStructure:
    def test_result_has_required_fields(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        result = process(noise_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        assert result.content is not None
        assert result.disposition is not None
        assert result.raw_ref is not None
        assert result.raw_sha256 is not None
        assert result.evidence_class is not None
        assert result.mode is not None
        assert result.metrics is not None

    def test_raw_sha256_matches_raw_store(self, noise_tool_result, tmp_raw_store, tmp_metrics_log):
        """raw_sha256 in result matches what's in the RAW store."""
        result = process(noise_tool_result, raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
        import hashlib
        expected_sha = hashlib.sha256(noise_tool_result.content).hexdigest()
        assert result.raw_sha256 == expected_sha
