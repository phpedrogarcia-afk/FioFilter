"""
fiofilter.profiles.default — Default profile.

Implements the core evidence taxonomy disposition table:

| Evidence Class  | EXPLORE    | BUILD      | PROVE |
|----------------|------------|------------|-------|
| NOISE          | T01        | T01        | T01   |
| DISCOVERY      | T01        | T01        | RAW   |
| PROGRESS       | T01        | T01        | RAW   |
| SUCCESS_SUMMARY| T01        | T01        | RAW   |
| DIAGNOSTIC     | T01        | RAW        | RAW   |
| FAILURE        | RAW        | RAW        | RAW   |
| CANONICAL_STATE| RAW        | RAW        | RAW   |
| MACHINE_DATA   | lossless*  | lossless*  | RAW   |
| AUTHORITY      | RAW        | RAW        | RAW   |
| SECURITY       | RAW        | RAW        | RAW   |
| BENCHMARK      | RAW        | RAW        | RAW   |
| UNKNOWN        | RAW        | RAW        | RAW   |

* lossless: only transforms in LOSSLESS_TRANSFORM_IDS (I8)
  In V0, no lossless transforms exist → MACHINE_DATA defaults to RAW.
"""

from __future__ import annotations

from fiofilter.profiles.base import BaseProfile, Policy, _RAW_ONLY, _TRANSFORM_T01
from fiofilter.types import Disposition, EvidenceClass, Mode

# V0: No lossless transforms implemented yet (T04 is a candidate, not ready)
_LOSSLESS_POLICY = _RAW_ONLY  # placeholder until T04 is implemented


class DefaultProfile(BaseProfile):
    """Default FioFilter profile — core taxonomy disposition table."""

    @property
    def profile_id(self) -> str:
        return "default"

    def get_policy(self, evidence_class: EvidenceClass, mode: Mode) -> Policy:
        # Always-RAW classes (I5, I6, I7)
        if evidence_class in (
            EvidenceClass.UNKNOWN,
            EvidenceClass.FAILURE,
            EvidenceClass.AUTHORITY,
            EvidenceClass.SECURITY,
            EvidenceClass.CANONICAL_STATE,
            EvidenceClass.BENCHMARK,
        ):
            return _RAW_ONLY

        # MACHINE_DATA: lossless-only transforms (none in V0)
        if evidence_class == EvidenceClass.MACHINE_DATA:
            if mode == Mode.PROVE:
                return _RAW_ONLY
            return _LOSSLESS_POLICY  # RAW in V0 until T04 is implemented

        # DIAGNOSTIC: transform only in EXPLORE
        if evidence_class == EvidenceClass.DIAGNOSTIC:
            if mode == Mode.EXPLORE:
                return _TRANSFORM_T01
            return _RAW_ONLY

        # DISCOVERY, PROGRESS, SUCCESS_SUMMARY, NOISE: transform in EXPLORE/BUILD
        if evidence_class in (
            EvidenceClass.NOISE,
            EvidenceClass.DISCOVERY,
            EvidenceClass.PROGRESS,
            EvidenceClass.SUCCESS_SUMMARY,
        ):
            if mode == Mode.PROVE:
                return _RAW_ONLY
            return _TRANSFORM_T01

        # Fallback (should not be reached with complete taxonomy)
        return _RAW_ONLY
