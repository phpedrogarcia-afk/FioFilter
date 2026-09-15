"""
fiofilter.profiles.fioos — FioOS project profile.

FioOS additional protections (beyond default):
  - DISCOVERY → RAW in BUILD mode (git trees contain canonical structure)
  - SUCCESS_SUMMARY → RAW in BUILD mode (test results may include hashes)
  - DIAGNOSTIC → RAW in all modes (FioOS diagnostics are often canonical)

Classes that remain highly protected in this profile:
  - authority
  - security
  - gateway admission (classified as AUTHORITY)
  - hashes (classified as CANONICAL_STATE)
  - mutation evidence (classified as FAILURE or CANONICAL_STATE)
  - adversarial evidence (classified as FAILURE)
  - unexpected test failures (FAILURE → RAW always)
  - canonical Git evidence (CANONICAL_STATE → RAW always)

This profile CANNOT override invariants I1–I16 (I12).
It only adds restrictions on top of the default profile.
"""

from __future__ import annotations

from fiofilter.profiles.base import BaseProfile, Policy, _RAW_ONLY, _TRANSFORM_T01
from fiofilter.types import EvidenceClass, Mode


class FioOSProfile(BaseProfile):
    """FioOS project profile — additional evidence protections."""

    @property
    def profile_id(self) -> str:
        return "fioos"

    def get_policy(self, evidence_class: EvidenceClass, mode: Mode) -> Policy:
        # Always-RAW classes (same as default — cannot be loosened)
        from fiofilter.types import (
            EvidenceClass as EC,
        )

        if evidence_class in (
            EC.UNKNOWN,
            EC.FAILURE,
            EC.AUTHORITY,
            EC.SECURITY,
            EC.CANONICAL_STATE,
            EC.BENCHMARK,
            EC.MACHINE_DATA,  # FioOS: all machine data is RAW
        ):
            return _RAW_ONLY

        # DIAGNOSTIC: RAW in all modes for FioOS
        if evidence_class == EC.DIAGNOSTIC:
            return _RAW_ONLY

        # DISCOVERY: RAW in BUILD and PROVE for FioOS
        if evidence_class == EC.DISCOVERY:
            if mode.value == "EXPLORE":
                return _TRANSFORM_T01
            return _RAW_ONLY

        # SUCCESS_SUMMARY: RAW in BUILD and PROVE for FioOS
        if evidence_class == EC.SUCCESS_SUMMARY:
            if mode.value == "EXPLORE":
                return _TRANSFORM_T01
            return _RAW_ONLY

        # NOISE, PROGRESS: transform allowed in EXPLORE/BUILD (not PROVE)
        if evidence_class in (EC.NOISE, EC.PROGRESS):
            if mode.value == "PROVE":
                return _RAW_ONLY
            return _TRANSFORM_T01

        return _RAW_ONLY
