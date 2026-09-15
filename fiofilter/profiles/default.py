"""Canonical runtime V0 policy: NOISE/T01 in every mode; PROGRESS/T01
in EXPLORE/BUILD. Other classes await an approved consumer contract.
This Python module is the sole core policy source (M02-D002).
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

        # T01 has no approved diagnostic/discovery/success consumer contract.
        if evidence_class == EvidenceClass.NOISE:
            return _TRANSFORM_T01  # Includes PROVE; modes never imply global RAW.
        if evidence_class == EvidenceClass.PROGRESS and mode != Mode.PROVE:
            return _TRANSFORM_T01
        return _RAW_ONLY
