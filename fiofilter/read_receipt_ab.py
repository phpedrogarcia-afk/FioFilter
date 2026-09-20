"""M14 explicit Read Receipt Behavioral A/B laboratory.

This module is deliberately outside the normal FioFilter runtime.  It offers a
small, in-memory experiment interface for comparing RAW repeat delivery with a
recoverable READREF.  It is not a hook, proxy, daemon, or automatic suppression
mechanism.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import pathlib
import re
from dataclasses import dataclass
from typing import Dict, Optional

from fiofilter.read_receipt import (
    FreshnessLevel,
    ReadReceiptDecision,
    ReadReceiptDisposition,
    ReadReceiptEvaluator,
    ReadView,
    ReadViewType,
    extract_view_bytes,
    normalize_source_identity,
)
from fiofilter.types import Sensitivity


M14_READREF_VERSION = "v1"


class ABCondition(str, enum.Enum):
    CONTROL = "CONTROL"
    TREATMENT = "TREATMENT"


class ABDelivery(str, enum.Enum):
    RAW = "RAW"
    READREF = "READREF"


class RecoveryError(ValueError):
    """Raised when a READREF cannot recover its exact session buffer."""


@dataclass(frozen=True)
class StoredReceipt:
    """Private, in-memory session buffer retained solely for M14 recovery."""

    session_id: str
    receipt_id: str
    source_identity: str
    view_id: str
    sha256: str
    content: bytes


class EphemeralReceiptStore:
    """Process-local receipt buffer with no serialization or cross-session lookup."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._records: Dict[str, StoredReceipt] = {}
        self._closed = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_empty(self) -> bool:
        return not self._records

    @property
    def closed(self) -> bool:
        return self._closed

    def put(
        self,
        receipt_id: str,
        source_identity: str,
        view_id: str,
        content: bytes,
    ) -> StoredReceipt:
        if self._closed:
            raise RecoveryError("EPHEMERAL_SESSION_CLOSED")
        sha256 = hashlib.sha256(content).hexdigest()
        record = StoredReceipt(
            session_id=self._session_id,
            receipt_id=receipt_id,
            source_identity=source_identity,
            view_id=view_id,
            sha256=sha256,
            content=bytes(content),
        )
        self._records[receipt_id] = record
        return record

    def get(self, receipt_id: str, session_id: str) -> StoredReceipt:
        if self._closed or session_id != self._session_id:
            raise RecoveryError("CROSS_SESSION_OR_CLOSED_RECEIPT")
        try:
            return self._records[receipt_id]
        except KeyError as exc:
            raise RecoveryError("MISSING_EPHEMERAL_RECEIPT") from exc

    def close(self) -> None:
        self._records.clear()
        self._closed = True


@dataclass(frozen=True)
class ABReadResult:
    condition: ABCondition
    delivery: ABDelivery
    payload: bytes
    raw_bytes: int
    decision: Optional[ReadReceiptDecision]
    reason: str
    reference_bytes: int = 0

    @property
    def reference_text(self) -> Optional[str]:
        if self.delivery is not ABDelivery.READREF:
            return None
        return self.payload.decode("utf-8")


@dataclass(frozen=True)
class NetVisibleByteEconomics:
    """Matched-pair economics; all values are bytes, never actual tokens."""

    control_repeat_raw_bytes: int
    treatment_reference_bytes: int
    treatment_recovery_bytes: int = 0
    treatment_additional_context_bytes: int = 0

    def __post_init__(self) -> None:
        if any(value < 0 for value in dataclasses.astuple(self)):
            raise ValueError("M14 byte accounting cannot be negative")

    @property
    def gross_visible_bytes_saved(self) -> int:
        return self.control_repeat_raw_bytes - self.treatment_reference_bytes

    @property
    def treatment_total_visible_bytes(self) -> int:
        return (
            self.treatment_reference_bytes
            + self.treatment_recovery_bytes
            + self.treatment_additional_context_bytes
        )

    @property
    def net_visible_bytes_saved(self) -> int:
        return self.control_repeat_raw_bytes - self.treatment_total_visible_bytes

    @property
    def estimated_context_token_equivalent_bytes_div_4(self) -> float:
        """Explicitly an estimate, not provider-reported token usage."""
        return self.net_visible_bytes_saved / 4.0


_REFERENCE_RE = re.compile(
    r"\A\[\[FIOFILTER:READREF:v1\n"
    r"receipt=([^\n]+)\n"
    r"sha256=([0-9a-f]{64})\n"
    r"view=([^\n]+)\n"
    r"bytes=([0-9]+)\n"
    r"\]\]\Z"
)


def _parse_reference(reference: str) -> tuple[str, str, str, int]:
    match = _REFERENCE_RE.fullmatch(reference)
    if match is None:
        raise RecoveryError("MALFORMED_READREF")
    receipt_id, sha256, view_id, byte_count = match.groups()
    return receipt_id, sha256, view_id, int(byte_count)


class ReadReceiptABHarness:
    """Explicit M14 experiment surface; normal runtime never instantiates it."""

    def __init__(
        self,
        condition: ABCondition,
        session_id: str,
        base_dir: Optional[pathlib.Path] = None,
        treatment_enabled: bool = True,
    ) -> None:
        self.condition = ABCondition(condition)
        self.session_id = session_id
        self._evaluator = ReadReceiptEvaluator(session_id=session_id, base_dir=base_dir)
        self._store = EphemeralReceiptStore(session_id=session_id)
        self._treatment_enabled = treatment_enabled
        self._closed = False
        self.reference_recovery_requests = 0
        self.recovered_bytes = 0
        self.corrective_rereads = 0
        self.additional_context_bytes = 0

    @property
    def active_suppression_normal_runtime(self) -> bool:
        return False

    @property
    def automatic_activation(self) -> bool:
        return False

    @property
    def ephemeral_store(self) -> EphemeralReceiptStore:
        return self._store

    def set_kill_switch(self, enabled: bool) -> None:
        """Disable treatment substitution immediately; RAW delivery remains available."""
        self._treatment_enabled = not enabled

    def close_session(self) -> None:
        self._store.close()
        self._evaluator.reset_session()
        self._closed = True

    def _raw_without_receipt(
        self,
        file_path: pathlib.Path,
        view: Optional[ReadView],
        reason: str,
    ) -> ABReadResult:
        requested_view = view or ReadView(ReadViewType.FULL_FILE)
        try:
            with open(file_path, "rb") as source:
                raw = extract_view_bytes(source.read(), requested_view)
        except OSError:
            raw = b""
        return ABReadResult(
            condition=self.condition,
            delivery=ABDelivery.RAW,
            payload=raw,
            raw_bytes=len(raw),
            decision=None,
            reason=reason,
        )

    def _store_raw_receipt(
        self,
        result: ABReadResult,
        sensitivity: Sensitivity,
    ) -> None:
        decision = result.decision
        if (
            result.delivery is not ABDelivery.RAW
            or sensitivity is not Sensitivity.NON_SENSITIVE
            or decision is None
            or decision.receipt_id is None
            or decision.resolved_path_identity is None
            or decision.requested_view is None
            or decision.disposition is ReadReceiptDisposition.SENSITIVE_POLICY_RAW
        ):
            return
        self._store.put(
            receipt_id=decision.receipt_id,
            source_identity=decision.resolved_path_identity,
            view_id=decision.requested_view.view_id,
            content=result.payload,
        )

    def read(
        self,
        call_id: str,
        file_path: pathlib.Path,
        view: Optional[ReadView] = None,
        call_index: int = 0,
        episode_id: Optional[int] = None,
        observed_session_id: Optional[str] = None,
        sensitivity: Sensitivity = Sensitivity.UNKNOWN,
    ) -> ABReadResult:
        """Read one source view through the explicit CONTROL/TREATMENT experiment.

        A caller must explicitly assess the view NON_SENSITIVE before any M14
        receipt buffer can be retained.  Unknown assessment is fail-to-RAW.
        """
        if self._closed:
            return self._raw_without_receipt(file_path, view, "EPHEMERAL_SESSION_CLOSED_RAW")
        if observed_session_id is not None and observed_session_id != self.session_id:
            return self._raw_without_receipt(file_path, view, "CROSS_SESSION_REFERENCE_FORBIDDEN_RAW")

        evaluated = self._evaluator.evaluate_live_read_result(
            call_id=call_id,
            file_path=file_path,
            view=view,
            call_index=call_index,
            episode_id=episode_id,
        )
        raw_result = ABReadResult(
            condition=self.condition,
            delivery=ABDelivery.RAW,
            payload=evaluated.raw_bytes,
            raw_bytes=len(evaluated.raw_bytes),
            decision=evaluated.decision,
            reason=evaluated.decision.reason,
        )

        # CONTROL is absolute: retain no active substitution even when F4 is proven.
        if self.condition is ABCondition.CONTROL:
            return raw_result
        if not self._treatment_enabled:
            self._store_raw_receipt(raw_result, sensitivity)
            return dataclasses.replace(raw_result, reason="TREATMENT_KILL_SWITCH_RAW")
        if sensitivity is not Sensitivity.NON_SENSITIVE:
            return dataclasses.replace(raw_result, reason="SENSITIVITY_ASSESSMENT_NOT_NON_SENSITIVE_RAW")

        decision = evaluated.decision
        eligible = (
            decision.disposition is ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE
            and decision.freshness_level is FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL
            and decision.plane_a_freshness_proven
            and decision.receipt_id is not None
            and decision.resolved_path_identity is not None
            and decision.requested_view is not None
            and decision.hypothetical_reference is not None
            and decision.reference_bytes < len(evaluated.raw_bytes)
        )
        if not eligible:
            self._store_raw_receipt(raw_result, sensitivity)
            return raw_result

        try:
            stored = self._store.get(decision.receipt_id, self.session_id)
        except RecoveryError:
            self._store_raw_receipt(raw_result, sensitivity)
            return dataclasses.replace(raw_result, reason="MISSING_OR_INVALID_RECEIPT_RAW")

        if (
            stored.source_identity != decision.resolved_path_identity
            or stored.view_id != decision.requested_view.view_id
            or stored.sha256 != decision.delivered_sha256
            or stored.content != evaluated.raw_bytes
        ):
            self._store_raw_receipt(raw_result, sensitivity)
            return dataclasses.replace(raw_result, reason="RECEIPT_IDENTITY_MISMATCH_RAW")

        reference = decision.hypothetical_reference.encode("utf-8")
        return ABReadResult(
            condition=self.condition,
            delivery=ABDelivery.READREF,
            payload=reference,
            raw_bytes=len(evaluated.raw_bytes),
            decision=decision,
            reason="DIRECT_F4_EXACT_READREF",
            reference_bytes=len(reference),
        )

    def expand(self, reference: str) -> bytes:
        """Recover exact in-memory bytes and reject every mismatch explicitly."""
        receipt_id, expected_sha, view_id, expected_length = _parse_reference(reference)
        stored = self._store.get(receipt_id, self.session_id)
        if stored.sha256 != expected_sha or stored.view_id != view_id:
            raise RecoveryError("READREF_METADATA_MISMATCH")
        if len(stored.content) != expected_length:
            raise RecoveryError("READREF_LENGTH_MISMATCH")
        actual_sha = hashlib.sha256(stored.content).hexdigest()
        if actual_sha != expected_sha:
            raise RecoveryError("READREF_SHA256_MISMATCH")
        self.reference_recovery_requests += 1
        self.recovered_bytes += len(stored.content)
        return stored.content

    def economics_for_repeat(
        self,
        control_repeat_raw_bytes: int,
        treatment_result: ABReadResult,
        additional_context_bytes: int = 0,
    ) -> NetVisibleByteEconomics:
        if treatment_result.delivery is not ABDelivery.READREF:
            reference_bytes = treatment_result.raw_bytes
        else:
            reference_bytes = treatment_result.reference_bytes
        return NetVisibleByteEconomics(
            control_repeat_raw_bytes=control_repeat_raw_bytes,
            treatment_reference_bytes=reference_bytes,
            treatment_recovery_bytes=self.recovered_bytes,
            treatment_additional_context_bytes=additional_context_bytes,
        )
