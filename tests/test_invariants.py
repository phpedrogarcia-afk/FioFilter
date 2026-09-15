"""
tests/test_invariants.py — Invariant enforcement tests.

Tests: I5, I6, I7, I9, I12
Quality gate: UNEXPECTED_PROTECTED_TRANSFORMATIONS = 0
              SECURITY_OR_AUTHORITY_FACT_LOSS = 0
"""

import pytest

from fiofilter.invariants import (
    check_all,
    check_i5,
    check_i6,
    check_i7,
    check_i9,
    check_i12_profile_cannot_weaken,
    first_forced,
)
from fiofilter.types import Disposition, EvidenceClass, Mode


class TestI5UnknownDefaultsToRAW:
    def test_unknown_forces_raw(self):
        result = check_i5(EvidenceClass.UNKNOWN)
        assert not result.ok
        assert result.forced_disposition == Disposition.RAW
        assert result.invariant_id == "I5"

    def test_known_class_passes(self):
        for cls in [EvidenceClass.NOISE, EvidenceClass.DISCOVERY, EvidenceClass.SUCCESS_SUMMARY]:
            result = check_i5(cls)
            assert result.ok, f"Expected OK for {cls}"


class TestI6FailureEscalation:
    def test_failure_class_forces_raw(self):
        result = check_i6(EvidenceClass.FAILURE, exit_code=None)
        assert not result.ok
        assert result.forced_disposition == Disposition.RAW
        assert result.invariant_id == "I6"

    def test_nonzero_exit_forces_raw(self):
        result = check_i6(EvidenceClass.NOISE, exit_code=1)
        assert not result.ok
        assert result.forced_disposition == Disposition.RAW

    def test_nonzero_exit_noise_still_escalates(self):
        """Non-zero exit + NOISE → RAW (exit code overrides noise classification)."""
        result = check_i6(EvidenceClass.NOISE, exit_code=127)
        assert not result.ok

    def test_zero_exit_noise_passes(self):
        result = check_i6(EvidenceClass.NOISE, exit_code=0)
        assert result.ok

    def test_no_exit_code_known_class_passes(self):
        result = check_i6(EvidenceClass.DISCOVERY, exit_code=None)
        assert result.ok


class TestI7AuthoritySecurityProtection:
    def test_authority_forces_raw(self):
        result = check_i7(EvidenceClass.AUTHORITY)
        assert not result.ok
        assert result.forced_disposition == Disposition.RAW
        assert result.invariant_id == "I7"

    def test_security_forces_raw(self):
        result = check_i7(EvidenceClass.SECURITY)
        assert not result.ok
        assert result.forced_disposition == Disposition.RAW

    def test_noise_passes(self):
        result = check_i7(EvidenceClass.NOISE)
        assert result.ok

    def test_discovery_passes(self):
        result = check_i7(EvidenceClass.DISCOVERY)
        assert result.ok


class TestI9NoExpansion:
    def test_expansion_forces_raw(self):
        result = check_i9(raw_byte_length=100, transformed_byte_length=101)
        assert not result.ok
        assert result.invariant_id == "I9"

    def test_same_size_forces_raw(self):
        result = check_i9(raw_byte_length=100, transformed_byte_length=100)
        assert not result.ok

    def test_smaller_passes(self):
        result = check_i9(raw_byte_length=100, transformed_byte_length=50)
        assert result.ok

    def test_one_byte_smaller_passes(self):
        result = check_i9(raw_byte_length=100, transformed_byte_length=99)
        assert result.ok


class TestI12ProfileNonWeakening:
    def test_profile_cannot_weaken_unknown(self):
        result = check_i12_profile_cannot_weaken(
            EvidenceClass.UNKNOWN, Disposition.TRANSFORM
        )
        assert not result.ok
        assert result.invariant_id == "I12"

    def test_profile_cannot_weaken_authority(self):
        result = check_i12_profile_cannot_weaken(
            EvidenceClass.AUTHORITY, Disposition.TRANSFORM
        )
        assert not result.ok

    def test_profile_cannot_weaken_security(self):
        result = check_i12_profile_cannot_weaken(
            EvidenceClass.SECURITY, Disposition.TRANSFORM
        )
        assert not result.ok

    def test_profile_can_restrict_noise_to_raw(self):
        """Profile restricting NOISE to RAW is allowed."""
        result = check_i12_profile_cannot_weaken(
            EvidenceClass.NOISE, Disposition.RAW
        )
        assert result.ok  # Restricting is fine

    def test_profile_can_allow_transform_for_noise(self):
        """Profile allowing TRANSFORM for NOISE is fine (NOISE is not protected)."""
        result = check_i12_profile_cannot_weaken(
            EvidenceClass.NOISE, Disposition.TRANSFORM
        )
        assert result.ok


class TestCheckAll:
    def test_authority_any_mode_forces_raw(self):
        for mode in Mode:
            ok, results = check_all(EvidenceClass.AUTHORITY, mode)
            assert not ok
            forced = first_forced(results)
            assert forced is not None
            assert forced.forced_disposition == Disposition.RAW

    def test_security_any_mode_forces_raw(self):
        for mode in Mode:
            ok, results = check_all(EvidenceClass.SECURITY, mode)
            assert not ok

    def test_unknown_any_mode_forces_raw(self):
        for mode in Mode:
            ok, results = check_all(EvidenceClass.UNKNOWN, mode)
            assert not ok

    def test_failure_any_mode_forces_raw(self):
        for mode in Mode:
            ok, results = check_all(EvidenceClass.FAILURE, mode)
            assert not ok

    def test_noise_explore_passes_basic_checks(self):
        """NOISE in EXPLORE with no exit code — basic invariants pass."""
        ok, results = check_all(EvidenceClass.NOISE, Mode.EXPLORE, exit_code=0)
        forced = first_forced(results)
        # No invariant should fire for clean NOISE in EXPLORE
        assert forced is None

    def test_prove_mode_locks_discovery(self):
        """DISCOVERY in PROVE mode forces RAW."""
        ok, results = check_all(EvidenceClass.DISCOVERY, Mode.PROVE)
        assert not ok
        forced = first_forced(results)
        assert forced is not None
