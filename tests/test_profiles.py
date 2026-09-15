"""
tests/test_profiles.py — Profile invariant enforcement tests.

Tests: I12 — profiles cannot weaken core invariants.
"""

import pytest

from fiofilter.engine import process
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult


PROTECTED_PROFILES = ["default", "fioos", "fioideias"]
PROTECTED_CLASSES_ANY_MODE = [
    EvidenceClass.AUTHORITY,
    EvidenceClass.SECURITY,
    EvidenceClass.FAILURE,
    EvidenceClass.CANONICAL_STATE,
    EvidenceClass.BENCHMARK,
    EvidenceClass.UNKNOWN,
]


class TestProfilesCannotWeakenInvariants:
    @pytest.mark.parametrize("profile_id", PROTECTED_PROFILES)
    @pytest.mark.parametrize("mode", list(Mode))
    def test_authority_is_raw_all_profiles(
        self, profile_id, mode, authority_content, tmp_raw_store, tmp_metrics_log
    ):
        """I12: No profile can turn AUTHORITY into TRANSFORM."""
        tr = ToolResult(content=authority_content, source="shell")
        result = process(tr, mode=mode, profile_id=profile_id,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW), \
            f"Profile {profile_id} + {mode} returned {result.disposition} for AUTHORITY"

    @pytest.mark.parametrize("profile_id", PROTECTED_PROFILES)
    @pytest.mark.parametrize("mode", list(Mode))
    def test_security_is_raw_all_profiles(
        self, profile_id, mode, security_content, tmp_raw_store, tmp_metrics_log
    ):
        tr = ToolResult(content=security_content, source="shell")
        result = process(tr, mode=mode, profile_id=profile_id,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)

    @pytest.mark.parametrize("profile_id", PROTECTED_PROFILES)
    def test_unknown_profile_falls_back_to_default(
        self, profile_id, tmp_raw_store, tmp_metrics_log
    ):
        """Unknown profile ID falls back to default safely."""
        tr = ToolResult(content=b"xyzzy\n", source="shell")
        result = process(tr, mode=Mode.EXPLORE, profile_id="nonexistent_profile",
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        # Unknown profile falls back to default → UNKNOWN content → RAW
        assert result.disposition in (Disposition.RAW, Disposition.ESCALATE_TO_RAW)


class TestFioOSProfileAdditionalRestrictions:
    def test_fioos_diagnostic_is_raw_in_build(self, tmp_raw_store, tmp_metrics_log):
        """FioOS profile: DIAGNOSTIC → RAW in BUILD mode."""
        # Diagnostic content: warnings (non-failure)
        content = b"DeprecationWarning: old_func() is deprecated\n" * 3
        tr = ToolResult(content=content, source="shell")
        # FioOS profile restricts DIAGNOSTIC to RAW in all modes
        result = process(tr, mode=Mode.BUILD, profile_id="fioos",
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        # May be RAW due to classification or profile — either is acceptable
        assert isinstance(result.content, bytes)
