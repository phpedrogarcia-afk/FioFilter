"""Compact, payload-free provenance for Mission Context shadow measurement.

The manifest records byte offsets and mechanical repository proofs.  It never
changes the mission delivered to an agent.  Invalid manifests and failed
proofs are measured conservatively as UNKNOWN/inline.
"""

from __future__ import annotations

import enum
import hashlib
import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from fiofilter.mission_context import SafetyAssessment
from fiofilter.mission_context_shadow import (
    CanonicalArtifactProof,
    EvidenceQuality,
    MissionByteClass,
    MissionContextShadowAnalyzer,
    MissionSpan,
    ShadowManifest,
)


MANIFEST_SCHEMA_VERSION = "FIO_MISSION_CONTEXT_MANIFEST_V1"
RESULT_SCHEMA_VERSION = "FIO_MISSION_CONTEXT_MANIFEST_SHADOW_RESULT_V1"
MAX_MANIFEST_BYTES = 65_536
MAX_ENTRIES = 4_096
_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ManifestDisposition(str, enum.Enum):
    """Author-declared intent; all but a proven reference remain inline."""

    CANONICAL_REFERENCE = "R"
    INLINE_CRITICAL = "I"
    DELTA = "D"


@dataclass(frozen=True)
class ManifestEntry:
    start: int
    end: int
    disposition: ManifestDisposition
    canonical: Optional[CanonicalArtifactProof] = None

    def __post_init__(self) -> None:
        if not _is_int(self.start) or not _is_int(self.end) or self.start < 0 or self.end <= self.start:
            raise ValueError("manifest entry requires non-negative increasing integer offsets")
        if not isinstance(self.disposition, ManifestDisposition):
            raise ValueError("manifest entry requires an exact disposition")
        if self.disposition is ManifestDisposition.CANONICAL_REFERENCE:
            if not isinstance(self.canonical, CanonicalArtifactProof):
                raise ValueError("canonical reference requires a mechanical artifact proof")
        elif self.canonical is not None:
            raise ValueError("inline critical and delta entries cannot carry a canonical proof")


@dataclass(frozen=True)
class MissionContextManifest:
    mission_id: str
    mission_sha256: str
    raw_bytes: int
    entries: Tuple[ManifestEntry, ...]
    sensitivity_assessment: SafetyAssessment = SafetyAssessment.NON_SENSITIVE
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported mission context manifest schema")
        if not isinstance(self.mission_id, str) or _MISSION_ID.fullmatch(self.mission_id) is None:
            raise ValueError("invalid mission id")
        if not isinstance(self.mission_sha256, str) or _SHA256.fullmatch(self.mission_sha256) is None:
            raise ValueError("invalid mission SHA-256")
        if not _is_int(self.raw_bytes) or self.raw_bytes < 0:
            raise ValueError("raw_bytes must be a non-negative integer")
        if not isinstance(self.entries, tuple) or not all(
            isinstance(item, ManifestEntry) for item in self.entries
        ):
            raise ValueError("entries must be a tuple of ManifestEntry values")
        if len(self.entries) > MAX_ENTRIES:
            raise ValueError("manifest has too many entries")
        if not isinstance(self.sensitivity_assessment, SafetyAssessment):
            raise ValueError("invalid sensitivity assessment")


@dataclass(frozen=True)
class MissionContextManifestResult:
    mission_id: str
    mission_sha256: str
    manifest_sha256: str
    delivered_mission_bytes: bytes = field(repr=False)
    raw_mission_bytes: int
    manifest_bytes: int
    inline_critical_bytes: int
    delta_bytes: int
    verified_canonical_reference_bytes: int
    unknown_bytes: int
    proof_outcome: str
    proof_failures: Tuple[str, ...]
    evidence_quality: EvidenceQuality
    schema_version: str = RESULT_SCHEMA_VERSION
    shadow_only: bool = True
    active_delivery_authorized: bool = False
    semantic_inference_used: bool = False

    @property
    def proven_reexposure_bytes(self) -> int:
        return self.verified_canonical_reference_bytes

    @property
    def net_candidate_reduction_bytes(self) -> int:
        return self.proven_reexposure_bytes - self.manifest_bytes

    @property
    def manifest_economic_win(self) -> bool:
        return self.net_candidate_reduction_bytes > 0

    def to_record(self) -> Dict[str, Any]:
        """Return deterministic sanitized evidence without mission content."""

        return {
            "schema_version": self.schema_version,
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "MISSION_ID": self.mission_id,
            "MISSION_SHA256": self.mission_sha256,
            "MANIFEST_SHA256": self.manifest_sha256,
            "RAW_MISSION_BYTES": self.raw_mission_bytes,
            "MANIFEST_BYTES": self.manifest_bytes,
            "INLINE_CRITICAL_BYTES": self.inline_critical_bytes,
            "DELTA_BYTES": self.delta_bytes,
            "VERIFIED_CANONICAL_REFERENCE_BYTES": self.verified_canonical_reference_bytes,
            "UNKNOWN_BYTES": self.unknown_bytes,
            "PROVEN_REEXPOSURE_BYTES": self.proven_reexposure_bytes,
            "NET_CANDIDATE_REDUCTION_BYTES": self.net_candidate_reduction_bytes,
            "MANIFEST_ECONOMIC_WIN": self.manifest_economic_win,
            "PROOF_OUTCOME": self.proof_outcome,
            "PROOF_FAILURES": list(self.proof_failures),
            "EVIDENCE_QUALITY": self.evidence_quality.value,
            "DELIVERED_MISSION_MUTATED": False,
            "SHADOW_ONLY": self.shadow_only,
            "ACTIVE_DELIVERY_AUTHORIZED": self.active_delivery_authorized,
            "SEMANTIC_INFERENCE_USED": self.semantic_inference_used,
            "PROMPT_BODY_PERSISTED": False,
        }


def encode_manifest(manifest: MissionContextManifest) -> bytes:
    """Return the single canonical compact UTF-8 representation, including LF."""

    if not isinstance(manifest, MissionContextManifest):
        raise ValueError("manifest must be MissionContextManifest")
    value = {
        "e": [_encode_entry(item) for item in manifest.entries],
        "h": manifest.mission_sha256,
        "m": manifest.mission_id,
        "n": manifest.raw_bytes,
        "s": manifest.sensitivity_assessment.value,
        "v": manifest.schema_version,
    }
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("canonical manifest exceeds size limit")
    return encoded


def parse_manifest(manifest_bytes: bytes) -> MissionContextManifest:
    """Parse a strict compact manifest; no prompt payload fields are accepted."""

    if not isinstance(manifest_bytes, bytes) or not manifest_bytes or len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError("invalid manifest byte length")
    try:
        value = json.loads(
            manifest_bytes.decode("utf-8"), object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid manifest JSON") from exc
    if not isinstance(value, dict) or set(value) != {"e", "h", "m", "n", "s", "v"}:
        raise ValueError("invalid manifest fields")
    if not isinstance(value["e"], list) or len(value["e"]) > MAX_ENTRIES:
        raise ValueError("invalid manifest entries")
    try:
        assessment = SafetyAssessment(value["s"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid sensitivity assessment") from exc
    return MissionContextManifest(
        schema_version=value["v"],
        mission_id=value["m"],
        mission_sha256=value["h"],
        raw_bytes=value["n"],
        sensitivity_assessment=assessment,
        entries=tuple(_parse_entry(item) for item in value["e"]),
    )


def measure_manifest_shadow(
    mission_bytes: bytes,
    manifest_bytes: bytes,
    repository_root: pathlib.Path,
    *,
    evidence_quality: EvidenceQuality,
) -> MissionContextManifestResult:
    """Measure a supplied manifest while preserving exact mission delivery.

    Malformed manifests, mission-binding failures, overlapping ranges, and
    failed repository proofs all fail conservative.  The caller always receives
    the original mission buffer unchanged.
    """

    if not isinstance(mission_bytes, bytes):
        raise ValueError("mission must be bytes")
    if not isinstance(manifest_bytes, bytes):
        raise ValueError("manifest must be bytes")
    if not isinstance(evidence_quality, EvidenceQuality):
        raise ValueError("invalid evidence quality")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    mission_hash = hashlib.sha256(mission_bytes).hexdigest()
    try:
        manifest = parse_manifest(manifest_bytes)
    except ValueError:
        return _conservative_result(
            mission_bytes, manifest_bytes, manifest_hash, mission_hash,
            mission_id="UNBOUND-MANIFEST", evidence_quality=evidence_quality,
            outcome="MALFORMED_MANIFEST_CONSERVATIVE",
            failure="MANIFEST_PARSE_FAILED",
        )
    if manifest.raw_bytes != len(mission_bytes) or manifest.mission_sha256 != mission_hash:
        return _conservative_result(
            mission_bytes, manifest_bytes, manifest_hash, mission_hash,
            mission_id=manifest.mission_id, evidence_quality=evidence_quality,
            outcome="MISSION_BINDING_FAILED_CONSERVATIVE",
            failure="MISSION_LENGTH_OR_SHA256_MISMATCH",
        )
    spans = tuple(_to_shadow_span(item) for item in manifest.entries)
    shadow_manifest = ShadowManifest(
        mission_id=manifest.mission_id,
        raw_sha256=manifest.mission_sha256,
        raw_bytes=manifest.raw_bytes,
        evidence_quality=evidence_quality,
        sensitivity_assessment=manifest.sensitivity_assessment,
        spans=spans,
    )
    try:
        shadow = MissionContextShadowAnalyzer(repository_root).analyze(mission_bytes, shadow_manifest)
    except ValueError:
        return _conservative_result(
            mission_bytes, manifest_bytes, manifest_hash, mission_hash,
            mission_id=manifest.mission_id, evidence_quality=evidence_quality,
            outcome="MANIFEST_LAYOUT_FAILED_CONSERVATIVE",
            failure="ENTRY_LAYOUT_INVALID",
        )
    outcome = "PASS" if not shadow.proof_failures else "PROOFS_PARTIAL_CONSERVATIVE"
    return MissionContextManifestResult(
        mission_id=manifest.mission_id,
        mission_sha256=mission_hash,
        manifest_sha256=manifest_hash,
        delivered_mission_bytes=shadow.delivered_mission_bytes,
        raw_mission_bytes=len(mission_bytes),
        manifest_bytes=len(manifest_bytes),
        inline_critical_bytes=shadow.inline_critical_bytes,
        delta_bytes=shadow.delta_bytes,
        verified_canonical_reference_bytes=shadow.reference_canonical_bytes,
        unknown_bytes=shadow.unknown_conservative_bytes,
        proof_outcome=outcome,
        proof_failures=shadow.proof_failures,
        evidence_quality=evidence_quality,
    )


def _encode_entry(entry: ManifestEntry) -> list[Any]:
    value: list[Any] = [entry.disposition.value, entry.start, entry.end]
    if entry.disposition is ManifestDisposition.CANONICAL_REFERENCE:
        assert entry.canonical is not None
        value.extend((
            entry.canonical.repository_path,
            entry.canonical.artifact_sha256,
            entry.canonical.artifact_start,
            entry.canonical.artifact_end,
        ))
    return value


def _parse_entry(value: Any) -> ManifestEntry:
    if not isinstance(value, list) or len(value) not in (3, 7):
        raise ValueError("invalid manifest entry")
    try:
        disposition = ManifestDisposition(value[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid manifest disposition") from exc
    if disposition is ManifestDisposition.CANONICAL_REFERENCE:
        if len(value) != 7:
            raise ValueError("canonical entry requires artifact proof")
        return ManifestEntry(
            start=value[1], end=value[2], disposition=disposition,
            canonical=CanonicalArtifactProof(
                repository_path=value[3], artifact_sha256=value[4],
                artifact_start=value[5], artifact_end=value[6],
            ),
        )
    if len(value) != 3:
        raise ValueError("inline entries cannot carry artifact proof")
    return ManifestEntry(start=value[1], end=value[2], disposition=disposition)


def _to_shadow_span(entry: ManifestEntry) -> MissionSpan:
    if entry.disposition is ManifestDisposition.CANONICAL_REFERENCE:
        return MissionSpan(
            entry.start, entry.end, MissionByteClass.REFERENCE_CANONICAL,
            canonical=entry.canonical,
        )
    byte_class = (
        MissionByteClass.INLINE_CRITICAL
        if entry.disposition is ManifestDisposition.INLINE_CRITICAL
        else MissionByteClass.DELTA
    )
    return MissionSpan(entry.start, entry.end, byte_class)


def _conservative_result(
    mission_bytes: bytes,
    manifest_bytes: bytes,
    manifest_hash: str,
    mission_hash: str,
    *,
    mission_id: str,
    evidence_quality: EvidenceQuality,
    outcome: str,
    failure: str,
) -> MissionContextManifestResult:
    return MissionContextManifestResult(
        mission_id=mission_id,
        mission_sha256=mission_hash,
        manifest_sha256=manifest_hash,
        delivered_mission_bytes=mission_bytes,
        raw_mission_bytes=len(mission_bytes),
        manifest_bytes=len(manifest_bytes),
        inline_critical_bytes=0,
        delta_bytes=0,
        verified_canonical_reference_bytes=0,
        unknown_bytes=len(mission_bytes),
        proof_outcome=outcome,
        proof_failures=(failure,),
        evidence_quality=evidence_quality,
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _unique_object(pairs: list[tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate manifest field")
        value[key] = item
    return value
