"""Narrow M15-C1 Mission Context contract.

This module recognizes ``INSTRUCTION_REEXPOSURE_WASTE`` without intercepting
or changing any prompt delivery.  It keeps one explicitly assessed foundation
in an ephemeral session, proves its byte identity, and can construct a
*shadow-only* candidate containing a reference, inline critical facts, and a
delta.  Every returned delivery remains RAW.

Recoverability is deliberately not treated as authority to hide instructions:
the contract exposes candidate bytes for deterministic evaluation only and
labels behavioural equivalence as UNKNOWN.
"""

from __future__ import annotations

import enum
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

from fiofilter.sensitivity import contains_sensitive_material


SCHEMA_VERSION = "M15_MISSION_CONTEXT_CONTRACT_V1"
REFERENCE_VERSION = "v1"
WASTE_CLASS = "INSTRUCTION_REEXPOSURE_WASTE"


class MissionContextMode(str, enum.Enum):
    """The four intentionally narrow Mission Context evaluations."""

    INLINE_CRITICAL = "INLINE_CRITICAL"
    REFERENCE_CANONICAL = "REFERENCE_CANONICAL"
    DELTA = "DELTA"
    DROP_DUPLICATE = "DROP_DUPLICATE"


class SafetyAssessment(str, enum.Enum):
    """Caller assessment required before a reference can be evaluated."""

    NON_SENSITIVE = "NON_SENSITIVE"
    UNKNOWN = "UNKNOWN"
    SENSITIVE = "SENSITIVE"


class MissionContextDisposition(str, enum.Enum):
    """Delivery state; no value in this enum authorizes active suppression."""

    RAW = "RAW"
    SHADOW_CANDIDATE_RAW_DELIVERY = "SHADOW_CANDIDATE_RAW_DELIVERY"


@dataclass(frozen=True)
class CriticalFact:
    """A caller-designated fact that must retain all foundation occurrences."""

    fact_id: str
    value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not self.fact_id or not isinstance(self.fact_id, str):
            raise ValueError("critical fact requires a non-empty fact_id")
        _require_utf8_nonempty(self.value, "critical fact")


@dataclass(frozen=True)
class CriticalFactRequirement:
    """A non-secret receipt of one fact's original byte-occurrence requirement."""

    fact_id: str
    value_sha256: str
    required_occurrences: int


@dataclass(frozen=True)
class FoundationReceipt:
    """Same-session canonical identity for one delivered instruction foundation."""

    session_id: str
    foundation_sha256: str
    foundation_bytes: int
    critical_requirements: Tuple[CriticalFactRequirement, ...]

    def format_reference(self) -> str:
        return (
            f"[[FIOFILTER:MISSIONREF:{REFERENCE_VERSION}\n"
            f"session={self.session_id}\n"
            f"foundation_sha256={self.foundation_sha256}\n"
            f"foundation_bytes={self.foundation_bytes}\n"
            f"]]"
        )


@dataclass(frozen=True)
class CanonicalizationResult:
    """The first delivery is always RAW, even when a receipt is established."""

    disposition: MissionContextDisposition
    delivered_bytes: bytes = field(repr=False)
    receipt: Optional[FoundationReceipt]
    reason: str
    waste_class: str = WASTE_CLASS


@dataclass(frozen=True)
class MissionContextDecision:
    """One deterministic mode evaluation with RAW as the actual delivery."""

    requested_mode: MissionContextMode
    disposition: MissionContextDisposition
    delivered_bytes: bytes = field(repr=False)
    candidate_bytes: bytes = field(repr=False)
    reference_text: Optional[str]
    candidate_bytes_avoided: int
    reference_recoverable: bool
    active_delivery_authorized: bool
    behavioral_equivalence: str
    reason: str
    waste_class: str = WASTE_CLASS


@dataclass(frozen=True)
class _StoredFoundation:
    receipt: FoundationReceipt
    raw_bytes: bytes = field(repr=False)
    critical_facts: Tuple[CriticalFact, ...] = field(repr=False)


@dataclass(frozen=True)
class _ParsedReference:
    session_id: str
    foundation_sha256: str
    foundation_bytes: int


_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REFERENCE_PATTERN = re.compile(
    r"^\[\[FIOFILTER:MISSIONREF:" + re.escape(REFERENCE_VERSION) + r"\n"
    r"session=([A-Za-z0-9][A-Za-z0-9_.-]{0,127})\n"
    r"foundation_sha256=([0-9a-f]{64})\n"
    r"foundation_bytes=(\d+)\n"
    r"\]\]$"
)


def _require_utf8_nonempty(value: bytes, label: str) -> None:
    if not isinstance(value, bytes) or not value:
        raise ValueError(f"{label} must be non-empty UTF-8 bytes")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8 bytes") from exc


def _require_utf8(value: bytes, label: str) -> None:
    if not isinstance(value, bytes):
        raise ValueError(f"{label} must be bytes")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8 bytes") from exc


def _parse_reference(reference_text: str) -> Optional[_ParsedReference]:
    if not isinstance(reference_text, str):
        return None
    match = _REFERENCE_PATTERN.fullmatch(reference_text)
    if match is None:
        return None
    return _ParsedReference(
        session_id=match.group(1),
        foundation_sha256=match.group(2),
        foundation_bytes=int(match.group(3)),
    )


class MissionContextSession:
    """Ephemeral, explicit scope for deterministic Mission Context evaluation.

    The session has no file, network, hook, CLI, or normal-runtime integration.
    It retains canonical bytes only in memory so that exact recovery can be an
    objective oracle; callers still receive RAW bytes from ``evaluate``.
    """

    def __init__(self, session_id: str) -> None:
        if not isinstance(session_id, str) or not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("session_id must match [A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
        self.session_id = session_id
        self._foundations: Dict[str, _StoredFoundation] = {}

    def canonicalize(
        self,
        foundation_bytes: bytes,
        critical_facts: Sequence[CriticalFact],
        assessment: SafetyAssessment = SafetyAssessment.UNKNOWN,
    ) -> CanonicalizationResult:
        """Deliver a foundation RAW and, only when eligible, retain its receipt."""

        if not isinstance(foundation_bytes, bytes):
            raise ValueError("foundation must be bytes")
        try:
            _require_utf8_nonempty(foundation_bytes, "foundation")
        except ValueError:
            return CanonicalizationResult(
                disposition=MissionContextDisposition.RAW,
                delivered_bytes=foundation_bytes,
                receipt=None,
                reason="INVALID_FOUNDATION_UTF8_REQUIRES_RAW",
            )
        try:
            facts = tuple(critical_facts)
            _validate_facts(facts)
        except (TypeError, ValueError):
            return CanonicalizationResult(
                disposition=MissionContextDisposition.RAW,
                delivered_bytes=foundation_bytes,
                receipt=None,
                reason="INVALID_CRITICAL_FACT_CONTRACT_REQUIRES_RAW",
            )

        if assessment is not SafetyAssessment.NON_SENSITIVE:
            return CanonicalizationResult(
                disposition=MissionContextDisposition.RAW,
                delivered_bytes=foundation_bytes,
                receipt=None,
                reason="ASSESSMENT_UNKNOWN_OR_SENSITIVE_REQUIRES_RAW",
            )
        if contains_sensitive_material(foundation_bytes):
            return CanonicalizationResult(
                disposition=MissionContextDisposition.RAW,
                delivered_bytes=foundation_bytes,
                receipt=None,
                reason="DETECTED_SENSITIVE_FOUNDATION_REQUIRES_RAW",
            )

        requirements = []
        for fact in facts:
            occurrences = foundation_bytes.count(fact.value)
            if occurrences == 0:
                return CanonicalizationResult(
                    disposition=MissionContextDisposition.RAW,
                    delivered_bytes=foundation_bytes,
                    receipt=None,
                    reason=f"CRITICAL_FACT_MISSING_FROM_FOUNDATION:{fact.fact_id}",
                )
            requirements.append(
                CriticalFactRequirement(
                    fact_id=fact.fact_id,
                    value_sha256=hashlib.sha256(fact.value).hexdigest(),
                    required_occurrences=occurrences,
                )
            )

        foundation_sha256 = hashlib.sha256(foundation_bytes).hexdigest()
        receipt = FoundationReceipt(
            session_id=self.session_id,
            foundation_sha256=foundation_sha256,
            foundation_bytes=len(foundation_bytes),
            critical_requirements=tuple(requirements),
        )
        stored = self._foundations.get(foundation_sha256)
        if stored is not None:
            if stored.receipt != receipt or stored.critical_facts != facts:
                return CanonicalizationResult(
                    disposition=MissionContextDisposition.RAW,
                    delivered_bytes=foundation_bytes,
                    receipt=None,
                    reason="FOUNDATION_FACT_CONTRACT_CHANGED_REQUIRES_RAW",
                )
        else:
            self._foundations[foundation_sha256] = _StoredFoundation(
                receipt=receipt,
                raw_bytes=foundation_bytes,
                critical_facts=facts,
            )

        return CanonicalizationResult(
            disposition=MissionContextDisposition.RAW,
            delivered_bytes=foundation_bytes,
            receipt=receipt,
            reason="FOUNDATION_DELIVERED_RAW_CANONICAL_RECEIPT_EPHEMERAL",
        )

    def recover(self, reference_text: str) -> bytes:
        """Recover exactly one issued same-session foundation or fail closed."""

        parsed = _parse_reference(reference_text)
        if parsed is None:
            raise ValueError("MALFORMED_MISSION_REFERENCE")
        if parsed.session_id != self.session_id:
            raise ValueError("CROSS_SESSION_MISSION_REFERENCE_FORBIDDEN")
        stored = self._foundations.get(parsed.foundation_sha256)
        if stored is None:
            raise ValueError("UNISSUED_MISSION_REFERENCE")
        if parsed.foundation_bytes != len(stored.raw_bytes):
            raise ValueError("MISSION_REFERENCE_LENGTH_MISMATCH")
        if hashlib.sha256(stored.raw_bytes).hexdigest() != parsed.foundation_sha256:
            raise ValueError("MISSION_REFERENCE_INTEGRITY_ERROR")
        return stored.raw_bytes

    def evaluate(
        self,
        mode: MissionContextMode,
        receipt: FoundationReceipt,
        inline_critical_bytes: bytes = b"",
        delta_bytes: bytes = b"",
        assessment: SafetyAssessment = SafetyAssessment.UNKNOWN,
        repeated_foundation_bytes: Optional[bytes] = None,
    ) -> MissionContextDecision:
        """Evaluate one mode and return RAW plus an optional shadow candidate.

        ``REFERENCE_CANONICAL`` and ``DROP_DUPLICATE`` require no delta.
        ``DELTA`` requires a non-empty delta.  ``INLINE_CRITICAL`` is the raw
        baseline that proves the foundation remains fully visible.
        """

        if not isinstance(mode, MissionContextMode):
            raise ValueError("mode must be a MissionContextMode")
        stored = self._stored_for(receipt)
        if not isinstance(inline_critical_bytes, bytes) or not isinstance(delta_bytes, bytes):
            raise ValueError("inline critical facts and delta must be bytes")
        if repeated_foundation_bytes is not None and not isinstance(repeated_foundation_bytes, bytes):
            raise ValueError("repeated foundation must be bytes")
        current_foundation = (
            repeated_foundation_bytes
            if mode is MissionContextMode.DROP_DUPLICATE and repeated_foundation_bytes is not None
            else stored.raw_bytes
        )
        raw_delivery = current_foundation + delta_bytes
        try:
            _require_utf8(inline_critical_bytes, "inline_critical_bytes")
            _require_utf8(delta_bytes, "delta_bytes")
        except ValueError:
            return self._raw_decision(mode, raw_delivery, "INVALID_CONTEXT_UTF8_REQUIRES_RAW")

        if assessment is not SafetyAssessment.NON_SENSITIVE:
            return self._raw_decision(mode, raw_delivery, "ASSESSMENT_UNKNOWN_OR_SENSITIVE_REQUIRES_RAW")
        if contains_sensitive_material(inline_critical_bytes) or contains_sensitive_material(delta_bytes):
            return self._raw_decision(mode, raw_delivery, "DETECTED_SENSITIVE_CONTEXT_REQUIRES_RAW")

        if mode is MissionContextMode.INLINE_CRITICAL:
            return self._raw_decision(mode, raw_delivery, "INLINE_CRITICAL_BASELINE_RAW")
        if mode in (MissionContextMode.REFERENCE_CANONICAL, MissionContextMode.DROP_DUPLICATE) and delta_bytes:
            return self._raw_decision(mode, raw_delivery, "MODE_REQUIRES_EXACT_FOUNDATION_DUPLICATE")
        if mode is MissionContextMode.DELTA and not delta_bytes:
            return self._raw_decision(mode, raw_delivery, "DELTA_MODE_REQUIRES_NONEMPTY_DELTA")
        if mode is MissionContextMode.DROP_DUPLICATE and repeated_foundation_bytes != stored.raw_bytes:
            return self._raw_decision(mode, raw_delivery, "EXACT_FOUNDATION_REPEAT_NOT_PROVEN")
        if mode is not MissionContextMode.DROP_DUPLICATE and repeated_foundation_bytes is not None:
            return self._raw_decision(mode, raw_delivery, "REPEATED_FOUNDATION_ONLY_FOR_DROP_DUPLICATE")
        if not self._critical_requirements_are_inline(stored, inline_critical_bytes):
            return self._raw_decision(mode, raw_delivery, "CRITICAL_FACT_OCCURRENCE_REQUIREMENT_NOT_INLINE")

        reference_text = receipt.format_reference()
        try:
            recovered = self.recover(reference_text)
        except ValueError:
            return self._raw_decision(mode, raw_delivery, "REFERENCE_RECOVERY_FAILED_REQUIRES_RAW")
        if recovered != stored.raw_bytes:
            return self._raw_decision(mode, raw_delivery, "REFERENCE_RECOVERY_INTEGRITY_FAILED_REQUIRES_RAW")

        candidate = reference_text.encode("utf-8") + b"\n" + inline_critical_bytes + delta_bytes
        if len(candidate) >= len(raw_delivery):
            return self._raw_decision(mode, raw_delivery, "CANDIDATE_NOT_ECONOMIC_NO_EXPANSION")

        return MissionContextDecision(
            requested_mode=mode,
            disposition=MissionContextDisposition.SHADOW_CANDIDATE_RAW_DELIVERY,
            delivered_bytes=raw_delivery,
            candidate_bytes=candidate,
            reference_text=reference_text,
            candidate_bytes_avoided=len(raw_delivery) - len(candidate),
            reference_recoverable=True,
            active_delivery_authorized=False,
            behavioral_equivalence="UNKNOWN",
            reason="EXACT_RECOVERABLE_REFERENCE_WITH_INLINE_CRITICAL_SHADOW_ONLY",
        )

    def _stored_for(self, receipt: FoundationReceipt) -> _StoredFoundation:
        if not isinstance(receipt, FoundationReceipt):
            raise ValueError("receipt must be a FoundationReceipt")
        if receipt.session_id != self.session_id:
            raise ValueError("CROSS_SESSION_MISSION_REFERENCE_FORBIDDEN")
        stored = self._foundations.get(receipt.foundation_sha256)
        if stored is None or stored.receipt != receipt:
            raise ValueError("UNISSUED_MISSION_FOUNDATION_RECEIPT")
        return stored

    @staticmethod
    def _critical_requirements_are_inline(
        stored: _StoredFoundation,
        inline_critical_bytes: bytes,
    ) -> bool:
        return all(
            inline_critical_bytes.count(fact.value) >= requirement.required_occurrences
            for fact, requirement in zip(stored.critical_facts, stored.receipt.critical_requirements)
        )

    @staticmethod
    def _raw_decision(
        mode: MissionContextMode,
        raw_delivery: bytes,
        reason: str,
    ) -> MissionContextDecision:
        return MissionContextDecision(
            requested_mode=mode,
            disposition=MissionContextDisposition.RAW,
            delivered_bytes=raw_delivery,
            candidate_bytes=raw_delivery,
            reference_text=None,
            candidate_bytes_avoided=0,
            reference_recoverable=False,
            active_delivery_authorized=False,
            behavioral_equivalence="UNKNOWN",
            reason=reason,
        )


def _validate_facts(facts: Tuple[CriticalFact, ...]) -> None:
    if not facts:
        raise ValueError("at least one designated critical fact is required")
    if not all(isinstance(fact, CriticalFact) for fact in facts):
        raise ValueError("critical facts must be CriticalFact values")
    fact_ids = [fact.fact_id for fact in facts]
    if len(set(fact_ids)) != len(fact_ids):
        raise ValueError("critical fact ids must be unique")
