"""
fiofilter.profiles.base — BaseProfile ABC.

Profiles are policy overlays. They may restrict compression eligibility.
They may never override invariants I1–I16 (I12).

The profile's get_policy() returns a Policy object indicating:
  - allowed_dispositions: which dispositions are permitted
  - transform_whitelist: which transforms may be applied
  - notes: human-readable rationale

The engine then runs invariant checks on top of the profile policy.
If invariants conflict with profile policy, invariants win.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import FrozenSet

from fiofilter.types import Disposition, EvidenceClass, Mode


@dataclass(frozen=True)
class Policy:
    """
    Policy returned by a profile for a given evidence class and mode.

    The engine uses this to determine which transforms are permitted.
    Invariants are checked after this — they may override.
    """

    allowed_dispositions: FrozenSet[Disposition]
    """Which dispositions the profile permits. Invariants may restrict further."""

    transform_whitelist: FrozenSet[str]
    """Transform IDs permitted by this profile for this class+mode."""

    notes: str = ""
    """Human-readable notes for audit. Never shown to the model."""


# Convenience constants
_RAW_ONLY = Policy(
    allowed_dispositions=frozenset([Disposition.RAW]),
    transform_whitelist=frozenset(),
    notes="RAW only",
)

_TRANSFORM_T01 = Policy(
    allowed_dispositions=frozenset([Disposition.TRANSFORM, Disposition.RAW]),
    transform_whitelist=frozenset(["T01"]),
    notes="T01 (duplicate fold) allowed",
)


class BaseProfile(abc.ABC):
    """Abstract base class for FioFilter profiles."""

    @property
    @abc.abstractmethod
    def profile_id(self) -> str:
        """Unique profile identifier, e.g. 'default'."""
        ...

    @abc.abstractmethod
    def get_policy(self, evidence_class: EvidenceClass, mode: Mode) -> Policy:
        """
        Return the policy for the given evidence class and mode.

        The engine calls this AFTER normalizing metadata and BEFORE
        checking invariants. Invariants may further restrict the policy.

        Implementations must NEVER:
          - Return TRANSFORM for AUTHORITY, SECURITY, UNKNOWN, FAILURE,
            CANONICAL_STATE, or BENCHMARK in any mode (I12).
          - Expand allowed_dispositions beyond what the core taxonomy permits.
          - Override invariants I1–I16.

        Implementations may:
          - Restrict allowed_dispositions (e.g., force RAW for DISCOVERY in BUILD)
          - Restrict transform_whitelist
          - Add notes for auditing
        """
        ...
