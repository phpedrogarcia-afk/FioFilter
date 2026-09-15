"""
fiofilter.invariants — I1–I16 enforcement checks.

Each invariant is callable and returns an InvariantResult.
The check() function runs all applicable invariants for a given
evidence class and policy, returning the first forced disposition
or OK if all invariants pass.

Rules:
- Invariants are additive guards — any one firing forces RAW.
- Profiles cannot override invariants (I12).
- Invariant checks are deterministic and have no side effects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import List, Optional, Tuple

from fiofilter.types import Disposition, EvidenceClass, Mode


# Evidence classes that are always RAW regardless of mode or profile (I7)
_ALWAYS_RAW: frozenset = frozenset([
    EvidenceClass.AUTHORITY,
    EvidenceClass.SECURITY,
    EvidenceClass.FAILURE,
    EvidenceClass.CANONICAL_STATE,
    EvidenceClass.BENCHMARK,
    EvidenceClass.UNKNOWN,
])

# Evidence classes that are RAW in PROVE mode (in addition to _ALWAYS_RAW)
_RAW_IN_PROVE: frozenset = frozenset([
    EvidenceClass.DISCOVERY,
    EvidenceClass.PROGRESS,
    EvidenceClass.SUCCESS_SUMMARY,
    EvidenceClass.DIAGNOSTIC,
    EvidenceClass.MACHINE_DATA,
])


@dataclass(frozen=True)
class InvariantResult:
    """Result of running invariant checks."""

    ok: bool
    """True if all checks passed and no disposition is forced."""

    forced_disposition: Optional[Disposition]
    """The disposition forced by the invariant, if any."""

    reason: str
    """Human-readable reason for the forced disposition, or 'ok'."""

    invariant_id: Optional[str]
    """The invariant that fired, e.g. 'I5', 'I7'."""


_OK = InvariantResult(ok=True, forced_disposition=None, reason="ok", invariant_id=None)


def _force_raw(invariant_id: str, reason: str) -> InvariantResult:
    return InvariantResult(
        ok=False,
        forced_disposition=Disposition.RAW,
        reason=reason,
        invariant_id=invariant_id,
    )


def check_i5(evidence_class: EvidenceClass) -> InvariantResult:
    """I5: Unknown evidence class defaults to RAW."""
    if evidence_class == EvidenceClass.UNKNOWN:
        return _force_raw("I5", "UNKNOWN evidence class defaults to RAW")
    return _OK


def check_i6(evidence_class: EvidenceClass, exit_code: Optional[int]) -> InvariantResult:
    """I6: Unexpected failures escalate toward RAW.
    Non-zero exit code + FAILURE class → force RAW.
    """
    if evidence_class == EvidenceClass.FAILURE:
        return _force_raw("I6", "FAILURE evidence class escalates to RAW")
    if exit_code is not None and exit_code != 0:
        # Non-zero exit escalates ANY class toward FAILURE treatment (I6)
        return _force_raw("I6", f"Non-zero exit code {exit_code} escalates to RAW")
    return _OK


def check_i7(evidence_class: EvidenceClass) -> InvariantResult:
    """I7: Authority and security evidence is not compressed."""
    if evidence_class in (EvidenceClass.AUTHORITY, EvidenceClass.SECURITY):
        return _force_raw(
            "I7",
            f"{evidence_class.value} evidence is never compressed (I7)"
        )
    return _OK


def check_i8_machine_data(
    evidence_class: EvidenceClass,
    proposed_transform_id: Optional[str],
    lossless_transform_ids: frozenset,
) -> InvariantResult:
    """I8: Machine-consumed data must remain machine-valid.
    Only lossless-verified transforms are permitted on MACHINE_DATA.
    """
    if evidence_class != EvidenceClass.MACHINE_DATA:
        return _OK
    if proposed_transform_id is None:
        return _OK  # RAW disposition, no transform
    if proposed_transform_id not in lossless_transform_ids:
        return _force_raw(
            "I8",
            f"Transform {proposed_transform_id} is not proven lossless for MACHINE_DATA"
        )
    return _OK


def check_i9(raw_byte_length: int, transformed_byte_length: int) -> InvariantResult:
    """I9: A transform that expands output loses to RAW."""
    if transformed_byte_length >= raw_byte_length:
        return _force_raw(
            "I9",
            f"Transform output ({transformed_byte_length}B) >= raw ({raw_byte_length}B)"
        )
    return _OK


def check_always_raw(evidence_class: EvidenceClass) -> InvariantResult:
    """Composite: classes that are always RAW (I5, I6, I7 coverage)."""
    if evidence_class in _ALWAYS_RAW:
        return _force_raw(
            "I_ALWAYS_RAW",
            f"{evidence_class.value} is always RAW"
        )
    return _OK


def check_prove_mode(evidence_class: EvidenceClass, mode: Mode) -> InvariantResult:
    """In PROVE mode, most classes are forced to RAW."""
    if mode == Mode.PROVE and evidence_class in _RAW_IN_PROVE:
        return _force_raw(
            "I_PROVE_MODE",
            f"{evidence_class.value} is RAW in PROVE mode"
        )
    return _OK


def check_i12_profile_cannot_weaken(
    evidence_class: EvidenceClass,
    profile_disposition: Disposition,
) -> InvariantResult:
    """I12: Profiles cannot weaken protected invariants.
    If the core taxonomy mandates RAW but the profile suggests TRANSFORM,
    this check fires.
    """
    if evidence_class in _ALWAYS_RAW and profile_disposition == Disposition.TRANSFORM:
        return _force_raw(
            "I12",
            f"Profile cannot weaken invariant for {evidence_class.value}"
        )
    return _OK


def check_all(
    evidence_class: EvidenceClass,
    mode: Mode,
    exit_code: Optional[int] = None,
    proposed_transform_id: Optional[str] = None,
    lossless_transform_ids: Optional[frozenset] = None,
    raw_byte_length: Optional[int] = None,
    transformed_byte_length: Optional[int] = None,
) -> Tuple[bool, List[InvariantResult]]:
    """
    Run all applicable invariant checks in order.

    Returns:
        (all_ok: bool, results: List[InvariantResult])

    If any result has ok=False, all_ok is False.
    The caller should use the first non-OK result's forced_disposition.
    """
    checks: List[InvariantResult] = []

    checks.append(check_i5(evidence_class))
    checks.append(check_i6(evidence_class, exit_code))
    checks.append(check_i7(evidence_class))
    checks.append(check_always_raw(evidence_class))
    checks.append(check_prove_mode(evidence_class, mode))

    if lossless_transform_ids is not None:
        checks.append(check_i8_machine_data(
            evidence_class, proposed_transform_id, lossless_transform_ids
        ))

    if raw_byte_length is not None and transformed_byte_length is not None:
        checks.append(check_i9(raw_byte_length, transformed_byte_length))

    all_ok = all(c.ok for c in checks)
    return all_ok, checks


def first_forced(results: List[InvariantResult]) -> Optional[InvariantResult]:
    """Return the first non-OK invariant result, or None if all passed."""
    for r in results:
        if not r.ok:
            return r
    return None
