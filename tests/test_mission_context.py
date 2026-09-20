"""Objective contract tests for the narrow M15-C1 Mission Context foundation."""

import pytest

from fiofilter.mission_context import (
    CriticalFact,
    MissionContextDisposition,
    MissionContextMode,
    MissionContextSession,
    SafetyAssessment,
)


CRITICAL = b"CRITICAL: preserve this exact rule inline.\n"
FOUNDATION = (
    b"Mission foundation applies to every task.\n"
    + CRITICAL
    + b"Noncritical orientation text.\n" * 40
    + CRITICAL
)
FACTS = (CriticalFact("preserve-rule", CRITICAL),)
INLINE_CRITICAL = CRITICAL * 2


def _canonical_session():
    session = MissionContextSession("m15-c1-test")
    result = session.canonicalize(FOUNDATION, FACTS, SafetyAssessment.NON_SENSITIVE)
    assert result.disposition is MissionContextDisposition.RAW
    assert result.receipt is not None
    return session, result.receipt


def test_foundation_is_raw_once_and_reference_recovers_exact_bytes() -> None:
    session, receipt = _canonical_session()

    assert session.recover(receipt.format_reference()) == FOUNDATION


def test_inline_critical_is_a_raw_baseline_not_a_hidden_delivery() -> None:
    session, receipt = _canonical_session()

    decision = session.evaluate(
        MissionContextMode.INLINE_CRITICAL,
        receipt,
        delta_bytes=b"Task-specific instruction.\n",
        assessment=SafetyAssessment.NON_SENSITIVE,
    )

    assert decision.disposition is MissionContextDisposition.RAW
    assert decision.delivered_bytes == FOUNDATION + b"Task-specific instruction.\n"
    assert decision.candidate_bytes_avoided == 0
    assert decision.active_delivery_authorized is False
    assert decision.behavioral_equivalence == "UNKNOWN"


def test_reference_canonical_is_recoverable_but_remains_raw_only() -> None:
    session, receipt = _canonical_session()

    decision = session.evaluate(
        MissionContextMode.REFERENCE_CANONICAL,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        assessment=SafetyAssessment.NON_SENSITIVE,
    )

    assert decision.disposition is MissionContextDisposition.SHADOW_CANDIDATE_RAW_DELIVERY
    assert decision.delivered_bytes == FOUNDATION
    assert decision.reference_text is not None
    assert session.recover(decision.reference_text) == FOUNDATION
    assert decision.reference_recoverable is True
    assert decision.active_delivery_authorized is False
    assert decision.behavioral_equivalence == "UNKNOWN"
    assert decision.candidate_bytes_avoided > 0


def test_delta_keeps_all_designated_critical_occurrences_inline() -> None:
    session, receipt = _canonical_session()
    delta = b"Delta: inspect only the relevant module.\n"

    decision = session.evaluate(
        MissionContextMode.DELTA,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        delta_bytes=delta,
        assessment=SafetyAssessment.NON_SENSITIVE,
    )

    assert decision.disposition is MissionContextDisposition.SHADOW_CANDIDATE_RAW_DELIVERY
    assert decision.delivered_bytes == FOUNDATION + delta
    assert decision.candidate_bytes.endswith(INLINE_CRITICAL + delta)
    assert decision.candidate_bytes.count(CRITICAL) >= FOUNDATION.count(CRITICAL)


def test_drop_duplicate_is_limited_to_the_exact_foundation_case() -> None:
    session, receipt = _canonical_session()

    decision = session.evaluate(
        MissionContextMode.DROP_DUPLICATE,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        repeated_foundation_bytes=FOUNDATION,
        assessment=SafetyAssessment.NON_SENSITIVE,
    )
    partial = session.evaluate(
        MissionContextMode.DROP_DUPLICATE,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        delta_bytes=b"partial duplicate analysis is deferred\n",
        repeated_foundation_bytes=FOUNDATION,
        assessment=SafetyAssessment.NON_SENSITIVE,
    )
    unproven = session.evaluate(
        MissionContextMode.DROP_DUPLICATE,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        assessment=SafetyAssessment.NON_SENSITIVE,
    )
    changed = session.evaluate(
        MissionContextMode.DROP_DUPLICATE,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        repeated_foundation_bytes=FOUNDATION + b"changed",
        assessment=SafetyAssessment.NON_SENSITIVE,
    )

    assert decision.disposition is MissionContextDisposition.SHADOW_CANDIDATE_RAW_DELIVERY
    assert partial.disposition is MissionContextDisposition.RAW
    assert partial.reason == "MODE_REQUIRES_EXACT_FOUNDATION_DUPLICATE"
    assert unproven.disposition is MissionContextDisposition.RAW
    assert changed.disposition is MissionContextDisposition.RAW


def test_missing_inline_occurrence_or_unknown_assessment_fails_closed_to_raw() -> None:
    session, receipt = _canonical_session()

    missing = session.evaluate(
        MissionContextMode.REFERENCE_CANONICAL,
        receipt,
        inline_critical_bytes=CRITICAL,
        assessment=SafetyAssessment.NON_SENSITIVE,
    )
    unknown = session.evaluate(
        MissionContextMode.DELTA,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        delta_bytes=b"Task delta.\n",
        assessment=SafetyAssessment.UNKNOWN,
    )

    assert missing.disposition is MissionContextDisposition.RAW
    assert missing.reason == "CRITICAL_FACT_OCCURRENCE_REQUIREMENT_NOT_INLINE"
    assert unknown.disposition is MissionContextDisposition.RAW
    assert unknown.reason == "ASSESSMENT_UNKNOWN_OR_SENSITIVE_REQUIRES_RAW"


def test_non_economic_candidate_fails_closed_to_raw() -> None:
    fact = CriticalFact("tiny", b"x")
    session = MissionContextSession("m15-c1-small")
    result = session.canonicalize(b"x", (fact,), SafetyAssessment.NON_SENSITIVE)
    assert result.receipt is not None

    decision = session.evaluate(
        MissionContextMode.REFERENCE_CANONICAL,
        result.receipt,
        inline_critical_bytes=b"x",
        assessment=SafetyAssessment.NON_SENSITIVE,
    )

    assert decision.disposition is MissionContextDisposition.RAW
    assert decision.reason == "CANDIDATE_NOT_ECONOMIC_NO_EXPANSION"


def test_cross_session_reference_cannot_recover() -> None:
    session, receipt = _canonical_session()
    other = MissionContextSession("m15-c1-other")

    with pytest.raises(ValueError, match="CROSS_SESSION_MISSION_REFERENCE_FORBIDDEN"):
        other.recover(receipt.format_reference())


def test_invalid_utf8_fails_to_raw_without_a_candidate() -> None:
    session = MissionContextSession("m15-c1-invalid")
    invalid_foundation = b"\xff" + CRITICAL

    initial = session.canonicalize(
        invalid_foundation, FACTS, SafetyAssessment.NON_SENSITIVE
    )
    assert initial.disposition is MissionContextDisposition.RAW
    assert initial.delivered_bytes == invalid_foundation
    assert initial.receipt is None

    valid_session, receipt = _canonical_session()
    decision = valid_session.evaluate(
        MissionContextMode.DELTA,
        receipt,
        inline_critical_bytes=INLINE_CRITICAL,
        delta_bytes=b"\xff",
        assessment=SafetyAssessment.NON_SENSITIVE,
    )
    assert decision.disposition is MissionContextDisposition.RAW
    assert decision.delivered_bytes == FOUNDATION + b"\xff"
    assert decision.reference_text is None


def test_duplicate_critical_fact_ids_do_not_create_a_receipt() -> None:
    session = MissionContextSession("m15-c1-duplicate-facts")
    duplicate = (FACTS[0], CriticalFact("preserve-rule", b"Mission foundation"))

    result = session.canonicalize(
        FOUNDATION, duplicate, SafetyAssessment.NON_SENSITIVE
    )

    assert result.disposition is MissionContextDisposition.RAW
    assert result.delivered_bytes == FOUNDATION
    assert result.receipt is None
