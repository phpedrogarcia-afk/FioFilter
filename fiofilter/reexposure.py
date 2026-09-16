"""fiofilter.reexposure — Session-aware Reexposure Shadow evaluation engine.

Implements deterministic, session-scoped reexposure shadow analysis inspired
by LeanCTX and Headroom donor mechanisms:
- Content-hash identity (SHA-256)
- Session-scoped delivery receipts
- Shadow disposition without runtime raw delivery suppression
- Critical inline evidence and sensitivity gates
- Distance and recency metrics
- Append-only hash-chained ledger
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import math
import pathlib
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from fiofilter.classifier import classify
from fiofilter.sensitivity import contains_sensitive_material, scan_text
from fiofilter.types import EvidenceClass as EC

SCHEMA_VERSION = "M06_REEXPOSURE_SHADOW_V1"
REFERENCE_VERSION = "v1"

# Distance and Recency Buckets
RECENCY_BUCKETS = (
    "0-2",
    "3-5",
    "6-10",
    "11-25",
    "26-50",
    "51-100",
    ">100",
)

EPISODE_BUCKETS = (
    "0_same_episode",
    "1_episode",
    "2-5_episodes",
    ">5_episodes",
)


class SourceKind(str, enum.Enum):
    """Tool family / producer class."""
    FILE_READ = "FILE_READ"
    SEARCH = "SEARCH"
    DIRECTORY_LIST = "DIRECTORY_LIST"
    GIT = "GIT"
    TEST = "TEST"
    BUILD = "BUILD"
    WRITE_OR_EDIT = "WRITE_OR_EDIT"
    SCRIPT = "SCRIPT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ShadowDisposition(str, enum.Enum):
    """Hypothetical disposition for a delivery event in shadow evaluation."""
    FIRST_DELIVERY = "FIRST_DELIVERY"
    EXACT_REDELIVERY_SHADOW_REFERENCE = "EXACT_REDELIVERY_SHADOW_REFERENCE"
    SAME_SOURCE_CHANGED = "SAME_SOURCE_CHANGED"
    AMBIGUOUS_IDENTITY_RAW = "AMBIGUOUS_IDENTITY_RAW"
    SENSITIVE_RAW = "SENSITIVE_RAW"
    DO_NOT_PERSIST_RAW = "DO_NOT_PERSIST_RAW"
    UNKNOWN_RAW = "UNKNOWN_RAW"
    SHADOW_REFERENCE_NOT_ECONOMIC = "SHADOW_REFERENCE_NOT_ECONOMIC"
    CROSS_SOURCE_RAW = "CROSS_SOURCE_RAW"
    UNSAFE_EVIDENCE_RAW = "UNSAFE_EVIDENCE_RAW"


@dataclass
class DeliveryReceipt:
    """Session-scoped record of a delivery event for content-hash identity."""
    receipt_id: str
    session_id: str
    source_kind: str
    source_identity: str
    content_sha256: str
    byte_length: int
    first_seen_index: int
    last_seen_index: int
    first_seen_call_id: str
    last_seen_call_id: str
    first_seen_timestamp: Optional[str] = None
    last_seen_timestamp: Optional[str] = None
    first_seen_episode: Optional[int] = None
    last_seen_episode: Optional[int] = None
    sensitivity: str = "NOT_SENSITIVE"
    persistence_policy: str = "EPHEMERAL"
    evidence_class: str = "UNKNOWN"
    reference_count: int = 0
    invalidated: bool = False
    invalidation_reason: Optional[str] = None
    raw_bytes: Optional[bytes] = field(default=None, repr=False)


@dataclass(frozen=True)
class ShadowReference:
    """Hypothetical compact reference replacing an exact redelivery."""
    sha256: str
    byte_length: int
    receipt_id: str
    version: str = REFERENCE_VERSION

    def format_text(self) -> str:
        return (
            f"[[FIOFILTER:REF:{self.version}\n"
            f"sha256={self.sha256}\n"
            f"bytes={self.byte_length}\n"
            f"receipt={self.receipt_id}\n"
            f"]]"
        )

    def format_bytes(self) -> bytes:
        return self.format_text().encode("utf-8")

    @classmethod
    def parse(cls, text: str) -> Optional["ShadowReference"]:
        pattern = (
            r"^\[\[FIOFILTER:REF:([a-zA-Z0-9_-]+)\n"
            r"sha256=([0-9a-fA-F]{64})\n"
            r"bytes=(\d+)\n"
            r"receipt=([^\n]+)\n"
            r"\]\]$"
        )
        m = re.match(pattern, text.strip())
        if not m:
            return None
        return cls(
            version=m.group(1),
            sha256=m.group(2).lower(),
            byte_length=int(m.group(3)),
            receipt_id=m.group(4),
        )


@dataclass(frozen=True)
class ShadowDecision:
    """Hypothetical evaluation outcome for one tool output event."""
    call_id: str
    call_index: int
    session_id: str
    disposition: str
    original_bytes: int
    hypothetical_visible_bytes: int
    hypothetical_bytes_avoided: int
    reference_target: Optional[str]
    reference_bytes: int
    reason: str
    confidence: str
    source_kind: str
    source_identity: str
    same_source: bool
    evidence_class: str
    call_distance_from_first: Optional[int] = None
    call_distance_from_latest: Optional[int] = None
    time_distance_seconds: Optional[float] = None
    episode_distance: Optional[int] = None
    content_sha256: str = ""
    target_path: Optional[str] = None
    read_range: Optional[Tuple[int, int]] = None
    is_read_receipt_candidate: bool = False


class ReceiptRegistry:
    """Session-scoped registry of delivery receipts.

    CROSS_SESSION_REFERENCE is strictly forbidden.
    """

    def __init__(self, session_id: str) -> None:
        if not session_id or not isinstance(session_id, str):
            raise ValueError("ReceiptRegistry requires a non-empty session_id")
        self.session_id = session_id
        # Map sha256 -> primary DeliveryReceipt (first delivery)
        self.receipts_by_hash: Dict[str, DeliveryReceipt] = {}
        # Map (source_kind, source_identity) -> latest DeliveryReceipt
        self.receipts_by_source: Dict[Tuple[str, str], DeliveryReceipt] = {}
        self._counter = 0

    def register_first_delivery(
        self,
        source_kind: str,
        source_identity: str,
        content_sha256: str,
        raw_bytes: bytes,
        call_id: str,
        call_index: int,
        timestamp: Optional[str] = None,
        episode_id: Optional[int] = None,
        sensitivity: str = "NOT_SENSITIVE",
        persistence_policy: str = "EPHEMERAL",
        evidence_class: str = "UNKNOWN",
    ) -> DeliveryReceipt:
        self._counter += 1
        receipt_id = f"RCP-{self.session_id[:8]}-{self._counter:06d}"
        receipt = DeliveryReceipt(
            receipt_id=receipt_id,
            session_id=self.session_id,
            source_kind=source_kind,
            source_identity=source_identity,
            content_sha256=content_sha256,
            byte_length=len(raw_bytes),
            first_seen_index=call_index,
            last_seen_index=call_index,
            first_seen_call_id=call_id,
            last_seen_call_id=call_id,
            first_seen_timestamp=timestamp,
            last_seen_timestamp=timestamp,
            first_seen_episode=episode_id,
            last_seen_episode=episode_id,
            sensitivity=sensitivity,
            persistence_policy=persistence_policy,
            evidence_class=evidence_class,
            reference_count=0,
            invalidated=False,
            raw_bytes=raw_bytes,
        )
        if content_sha256 not in self.receipts_by_hash:
            self.receipts_by_hash[content_sha256] = receipt
        self.receipts_by_source[(source_kind, source_identity)] = receipt
        return receipt

    def get_by_hash(self, content_sha256: str) -> Optional[DeliveryReceipt]:
        return self.receipts_by_hash.get(content_sha256)

    def get_by_source(self, source_kind: str, source_identity: str) -> Optional[DeliveryReceipt]:
        return self.receipts_by_source.get((source_kind, source_identity))

    def record_reference(self, receipt: DeliveryReceipt, call_id: str, call_index: int, timestamp: Optional[str] = None, episode_id: Optional[int] = None) -> None:
        receipt.reference_count += 1
        receipt.last_seen_index = call_index
        receipt.last_seen_call_id = call_id
        if timestamp:
            receipt.last_seen_timestamp = timestamp
        if episode_id is not None:
            receipt.last_seen_episode = episode_id

    def invalidate(self, receipt: DeliveryReceipt, reason: str) -> None:
        receipt.invalidated = True
        receipt.invalidation_reason = reason


def _classify_recency_bucket(call_distance: int) -> str:
    if call_distance <= 2:
        return "0-2"
    if call_distance <= 5:
        return "3-5"
    if call_distance <= 10:
        return "6-10"
    if call_distance <= 25:
        return "11-25"
    if call_distance <= 50:
        return "26-50"
    if call_distance <= 100:
        return "51-100"
    return ">100"


def _classify_episode_bucket(ep_distance: Optional[int]) -> str:
    if ep_distance is None:
        return "unknown"
    if ep_distance == 0:
        return "0_same_episode"
    if ep_distance == 1:
        return "1_episode"
    if 2 <= ep_distance <= 5:
        return "2-5_episodes"
    return ">5_episodes"


class ReexposureShadowEvaluator:
    """Evaluates delivery events sequentially under shadow reference rules.

    The actual consumer still receives RAW. This evaluator only records what
    FioFilter WOULD have proposed as a compact reference under lossless,
    evidence-preserving, and non-expanding invariants.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.registry = ReceiptRegistry(session_id)
        self.decisions: List[ShadowDecision] = []
        self.seen_sources: Dict[Tuple[str, str], List[DeliveryReceipt]] = defaultdict(list)

    def evaluate(
        self,
        call_id: str,
        call_index: int,
        source_kind: str,
        source_identity: str,
        raw_bytes: bytes,
        exit_code: Optional[int] = None,
        truncated: bool = False,
        timestamp: Optional[str] = None,
        episode_id: Optional[int] = None,
        target_path: Optional[str] = None,
        read_range: Optional[Tuple[int, int]] = None,
        session_id: Optional[str] = None,
        evidence_class: Optional[str] = None,
    ) -> ShadowDecision:
        """Evaluate a single delivery event under shadow rules."""
        # Invariant: Scoped to this explicit session
        current_session = session_id or self.session_id
        if current_session != self.session_id:
            raise ValueError(
                f"CROSS_SESSION_REFERENCE=FORBIDDEN: Evaluator scoped to session "
                f"'{self.session_id}', received event for session '{current_session}'."
            )

        content_sha = hashlib.sha256(raw_bytes).hexdigest()
        raw_len = len(raw_bytes)
        source_key = (source_kind, source_identity)

        # 1. Classify evidence class and sensitivity
        cl = classify(raw_bytes, exit_code=exit_code)
        if evidence_class is not None:
            ev_class = evidence_class
        elif cl.evidence_class != EC.UNKNOWN:
            ev_class = cl.evidence_class.value
        elif source_kind in ("FILE_READ", "SEARCH", "DIRECTORY_LIST") and target_path:
            ev_class = "CONTENT_EVIDENCE"
        else:
            ev_class = EC.UNKNOWN.value

        is_sensitive = contains_sensitive_material(raw_bytes)

        # 2. Check if this is the first delivery of this exact content
        prior_receipt = self.registry.get_by_hash(content_sha)
        prior_source_receipt = self.registry.get_by_source(source_kind, source_identity)

        if prior_receipt is None:
            # First delivery is required; subsequent are reexposure candidates
            receipt = self.registry.register_first_delivery(
                source_kind=source_kind,
                source_identity=source_identity,
                content_sha256=content_sha,
                raw_bytes=raw_bytes,
                call_id=call_id,
                call_index=call_index,
                timestamp=timestamp,
                episode_id=episode_id,
                sensitivity="SENSITIVE" if is_sensitive else "NOT_SENSITIVE",
                persistence_policy="DO_NOT_PERSIST" if is_sensitive else "EPHEMERAL",
                evidence_class=ev_class,
            )
            self.seen_sources[source_key].append(receipt)

            decision = ShadowDecision(
                call_id=call_id,
                call_index=call_index,
                session_id=self.session_id,
                disposition=ShadowDisposition.FIRST_DELIVERY.value,
                original_bytes=raw_len,
                hypothetical_visible_bytes=raw_len,
                hypothetical_bytes_avoided=0,
                reference_target=None,
                reference_bytes=0,
                reason="FIRST_DELIVERY_REQUIRED_IN_RAW",
                confidence="PROVEN",
                source_kind=source_kind,
                source_identity=source_identity,
                same_source=False,
                evidence_class=ev_class,
                content_sha256=content_sha,
                target_path=target_path,
                read_range=read_range,
                is_read_receipt_candidate=False,
            )
            self.decisions.append(decision)
            return decision

        # Hash collision defense in replay/tests: where raw bytes exist on receipt, verify byte equality
        if prior_receipt.raw_bytes is not None and prior_receipt.raw_bytes != raw_bytes:
            # Hash collision or corrupted payload
            decision = ShadowDecision(
                call_id=call_id,
                call_index=call_index,
                session_id=self.session_id,
                disposition=ShadowDisposition.AMBIGUOUS_IDENTITY_RAW.value,
                original_bytes=raw_len,
                hypothetical_visible_bytes=raw_len,
                hypothetical_bytes_avoided=0,
                reference_target=None,
                reference_bytes=0,
                reason="HASH_EQUALITY_WITHOUT_BYTE_EQUALITY_DETECTED",
                confidence="PROVEN",
                source_kind=source_kind,
                source_identity=source_identity,
                same_source=False,
                evidence_class=ev_class,
                content_sha256=content_sha,
                target_path=target_path,
                read_range=read_range,
                is_read_receipt_candidate=False,
            )
            self.decisions.append(decision)
            return decision

        # Exact redelivery of previously seen content!
        call_dist_first = call_index - prior_receipt.first_seen_index
        call_dist_latest = call_index - prior_receipt.last_seen_index
        ep_dist = (
            episode_id - prior_receipt.first_seen_episode
            if (episode_id is not None and prior_receipt.first_seen_episode is not None)
            else None
        )

        is_same_source = (
            prior_source_receipt is not None
            and prior_source_receipt.content_sha256 == content_sha
            and source_identity not in ("", "UNKNOWN", None)
        )

        # File read candidate detection
        is_read_cand = (source_kind == "FILE_READ" and target_path is not None and is_same_source)

        # Critical Inline Evidence Gate:
        # Exclude when structurally known:
        # AUTHORITY, SECURITY, CANONICAL_STATE, FAILURE, DIAGNOSTIC, UNKNOWN, truncated, sensitive.
        if truncated:
            disp = ShadowDisposition.AMBIGUOUS_IDENTITY_RAW.value
            reason = "TRUNCATED_STREAM_REQUIRES_RAW"
        elif exit_code is not None and exit_code != 0:
            disp = ShadowDisposition.UNSAFE_EVIDENCE_RAW.value
            reason = "FAILURE_NONZERO_EXIT_REQUIRES_RAW"
        elif is_sensitive or ev_class == EC.SECURITY.value:
            disp = ShadowDisposition.SENSITIVE_RAW.value
            reason = "SENSITIVE_MATERIAL_DETECTED_REQUIRES_RAW"
        elif not is_same_source:
            # Content matches, but source identity differs or is unknown
            disp = ShadowDisposition.CROSS_SOURCE_RAW.value
            reason = "CROSS_SOURCE_IDENTICAL_BYTES_OBSERVATIONAL_ONLY"
        elif ev_class == EC.AUTHORITY.value:
            disp = ShadowDisposition.UNSAFE_EVIDENCE_RAW.value
            reason = "AUTHORITY_EVIDENCE_REQUIRES_RAW"
        elif ev_class == EC.CANONICAL_STATE.value:
            disp = ShadowDisposition.UNSAFE_EVIDENCE_RAW.value
            reason = "CANONICAL_STATE_REQUIRES_RAW"
        elif ev_class == EC.FAILURE.value:
            disp = ShadowDisposition.UNSAFE_EVIDENCE_RAW.value
            reason = "FAILURE_EVIDENCE_REQUIRES_RAW"
        elif ev_class == EC.DIAGNOSTIC.value:
            disp = ShadowDisposition.UNSAFE_EVIDENCE_RAW.value
            reason = "DIAGNOSTIC_EVIDENCE_REQUIRES_RAW"
        elif ev_class == EC.UNKNOWN.value:
            disp = ShadowDisposition.UNKNOWN_RAW.value
            reason = "UNKNOWN_EVIDENCE_CLASS_REQUIRES_RAW"
        else:
            # Same source, safe evidence class, non-sensitive.
            # Now apply economic gate (no expansion).
            shadow_ref = ShadowReference(
                sha256=content_sha,
                byte_length=raw_len,
                receipt_id=prior_receipt.receipt_id,
            )
            ref_bytes = len(shadow_ref.format_bytes())
            if ref_bytes >= raw_len:
                disp = ShadowDisposition.SHADOW_REFERENCE_NOT_ECONOMIC.value
                reason = "REFERENCE_BYTES_EXCEED_OR_EQUAL_RAW_BYTES"
            else:
                disp = ShadowDisposition.EXACT_REDELIVERY_SHADOW_REFERENCE.value
                reason = "SAFE_SAME_SOURCE_EXACT_REDELIVERY"

        # Calculate hypothetical savings
        if disp == ShadowDisposition.EXACT_REDELIVERY_SHADOW_REFERENCE.value:
            shadow_ref = ShadowReference(
                sha256=content_sha,
                byte_length=raw_len,
                receipt_id=prior_receipt.receipt_id,
            )
            ref_b = len(shadow_ref.format_bytes())
            vis_b = ref_b
            avoided_b = raw_len - ref_b
            ref_target = prior_receipt.receipt_id
            self.registry.record_reference(prior_receipt, call_id, call_index, timestamp, episode_id)
        else:
            ref_b = 0
            vis_b = raw_len
            avoided_b = 0
            ref_target = None

        decision = ShadowDecision(
            call_id=call_id,
            call_index=call_index,
            session_id=self.session_id,
            disposition=disp,
            original_bytes=raw_len,
            hypothetical_visible_bytes=vis_b,
            hypothetical_bytes_avoided=avoided_b,
            reference_target=ref_target,
            reference_bytes=ref_b,
            reason=reason,
            confidence="PROVEN",
            source_kind=source_kind,
            source_identity=source_identity,
            same_source=is_same_source,
            evidence_class=ev_class,
            call_distance_from_first=call_dist_first,
            call_distance_from_latest=call_dist_latest,
            episode_distance=ep_dist,
            content_sha256=content_sha,
            target_path=target_path,
            read_range=read_range,
            is_read_receipt_candidate=is_read_cand,
        )
        self.decisions.append(decision)
        return decision


class ShadowLedger:
    """Append-only local shadow ledger with SHA-256 hash chaining."""

    def __init__(self, output_dir: pathlib.Path) -> None:
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.output_dir / "m06_reexposure_shadow_events_v1.jsonl"
        self.manifest_path = self.output_dir / "m06_reexposure_shadow_manifest_v1.json"
        self.summary_path = self.output_dir / "m06_reexposure_shadow_summary_v1.json"
        self.last_hash = "0" * 64
        self.record_count = 0

    def write_events(self, decisions: List[ShadowDecision]) -> None:
        """Write decisions to jsonl with cryptographic hash chaining."""
        if self.events_path.exists():
            raise FileExistsError(f"Refusing to clobber existing ledger: {self.events_path}")

        current_hash = self.last_hash
        with open(self.events_path, "w", encoding="utf-8") as f:
            for d in decisions:
                self.record_count += 1
                rec = asdict(d)
                rec["record_index"] = self.record_count
                rec["previous_event_hash"] = current_hash
                
                # Canonical hash computation
                serialized = json.dumps(rec, sort_keys=True).encode("utf-8")
                current_hash = hashlib.sha256(serialized).hexdigest()
                rec["event_hash"] = current_hash
                f.write(json.dumps(rec) + "\n")
        self.last_hash = current_hash

    def write_manifest_and_summary(self, manifest: Dict[str, Any], summary: Dict[str, Any]) -> None:
        if self.manifest_path.exists():
            raise FileExistsError(f"Refusing to clobber existing manifest: {self.manifest_path}")
        if self.summary_path.exists():
            raise FileExistsError(f"Refusing to clobber existing summary: {self.summary_path}")

        manifest["final_ledger_hash"] = self.last_hash
        manifest["total_ledger_records"] = self.record_count

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        with open(self.summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
