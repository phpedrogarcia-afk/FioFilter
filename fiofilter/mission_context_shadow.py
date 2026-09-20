"""Payload-free, deterministic Mission Context measurement surface.

The caller supplies exact byte spans and mechanical proofs.  This module never
infers semantic equivalence or changes the mission delivered to an agent.  Its
candidate is shadow-only and exists solely to measure a conservative lower bound
under the M15 Mission Context contract.
"""

from __future__ import annotations

import enum
import hashlib
import json
import pathlib
import re
import subprocess
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

from fiofilter.mission_context import SCHEMA_VERSION as FOUNDATION_CONTRACT_VERSION
from fiofilter.mission_context import SafetyAssessment, WASTE_CLASS
from fiofilter.sensitivity import contains_sensitive_material


SHADOW_SCHEMA_VERSION = "FIO_MISSION_CONTEXT_SHADOW_V1"
MANIFEST_SCHEMA_VERSION = "FIO_MISSION_CONTEXT_SHADOW_MANIFEST_V1"
REFERENCE_VERSION = "v1"
_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MissionByteClass(str, enum.Enum):
    INLINE_CRITICAL = "INLINE_CRITICAL"
    DELTA = "DELTA"
    REFERENCE_CANONICAL = "REFERENCE_CANONICAL"
    DROP_DUPLICATE = "DROP_DUPLICATE"


class EvidenceQuality(str, enum.Enum):
    CURRENT_MISSION_VISIBLE_TEXT_UTF8_LF = "CURRENT_MISSION_VISIBLE_TEXT_UTF8_LF"
    REPOSITORY_PRESERVED_ORIGINAL = "REPOSITORY_PRESERVED_ORIGINAL"
    SYNTHETIC = "SYNTHETIC"


@dataclass(frozen=True)
class CanonicalArtifactProof:
    repository_path: str
    artifact_sha256: str
    artifact_start: int
    artifact_end: int


@dataclass(frozen=True)
class DuplicateProof:
    source_start: int
    source_end: int


@dataclass(frozen=True)
class MissionSpan:
    start: int
    end: int
    byte_class: MissionByteClass
    canonical: Optional[CanonicalArtifactProof] = None
    duplicate: Optional[DuplicateProof] = None

    def __post_init__(self) -> None:
        if not _is_int(self.start) or not _is_int(self.end) or self.start < 0 or self.end <= self.start:
            raise ValueError("mission span requires non-negative increasing integer offsets")
        if not isinstance(self.byte_class, MissionByteClass):
            raise ValueError("mission span requires an exact MissionByteClass")
        if self.byte_class is MissionByteClass.REFERENCE_CANONICAL:
            if not isinstance(self.canonical, CanonicalArtifactProof) or self.duplicate is not None:
                raise ValueError("canonical span requires only CanonicalArtifactProof")
        elif self.byte_class is MissionByteClass.DROP_DUPLICATE:
            if not isinstance(self.duplicate, DuplicateProof) or self.canonical is not None:
                raise ValueError("duplicate span requires only DuplicateProof")
        elif self.canonical is not None or self.duplicate is not None:
            raise ValueError("inline and delta spans cannot carry reduction proofs")


@dataclass(frozen=True)
class ShadowManifest:
    mission_id: str
    raw_sha256: str
    raw_bytes: int
    evidence_quality: EvidenceQuality
    spans: Tuple[MissionSpan, ...]
    sensitivity_assessment: SafetyAssessment = SafetyAssessment.NON_SENSITIVE
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported shadow manifest schema")
        if not isinstance(self.mission_id, str) or _MISSION_ID.fullmatch(self.mission_id) is None:
            raise ValueError("invalid mission id")
        if not isinstance(self.raw_sha256, str) or _SHA256.fullmatch(self.raw_sha256) is None:
            raise ValueError("invalid raw SHA-256")
        if not _is_int(self.raw_bytes) or self.raw_bytes < 0:
            raise ValueError("raw_bytes must be a non-negative integer")
        if not isinstance(self.evidence_quality, EvidenceQuality):
            raise ValueError("invalid evidence quality")
        if not isinstance(self.sensitivity_assessment, SafetyAssessment):
            raise ValueError("invalid sensitivity assessment")
        if not isinstance(self.spans, tuple) or not all(isinstance(item, MissionSpan) for item in self.spans):
            raise ValueError("spans must be a tuple of MissionSpan values")


@dataclass(frozen=True)
class MissionContextShadowResult:
    mission_id: str
    evidence_quality: EvidenceQuality
    sensitivity_assessment: SafetyAssessment
    delivered_mission_bytes: bytes = field(repr=False)
    candidate_bytes: bytes = field(repr=False)
    raw_mission_bytes: int
    inline_critical_bytes: int
    delta_bytes: int
    reference_canonical_bytes: int
    drop_duplicate_candidate_bytes: int
    unknown_conservative_bytes: int
    reference_candidate_visible_bytes: int
    proof_failures: Tuple[str, ...]
    schema_version: str = SHADOW_SCHEMA_VERSION
    active_delivery_authorized: bool = False
    behavioral_equivalence: str = "UNKNOWN"
    semantic_inference_used: bool = False

    @property
    def delivered_mission_sha256(self) -> str:
        return hashlib.sha256(self.delivered_mission_bytes).hexdigest()

    @property
    def candidate_sha256(self) -> str:
        return hashlib.sha256(self.candidate_bytes).hexdigest()

    @property
    def minimum_sufficient_candidate_bytes(self) -> int:
        return len(self.candidate_bytes)

    @property
    def hypothetical_visible_bytes_reduction(self) -> int:
        return self.raw_mission_bytes - self.minimum_sufficient_candidate_bytes

    @property
    def hypothetical_reduction_percent(self) -> float:
        if not self.raw_mission_bytes:
            return 0.0
        return round(100.0 * self.hypothetical_visible_bytes_reduction / self.raw_mission_bytes, 2)

    def to_record(self) -> Dict[str, Any]:
        """Return deterministic metadata only; no mission or candidate payload."""

        return {
            "schema_version": self.schema_version,
            "foundation_contract_version": FOUNDATION_CONTRACT_VERSION,
            "waste_class": WASTE_CLASS,
            "MISSION_ID": self.mission_id,
            "MISSION_SHA256": self.delivered_mission_sha256,
            "CANDIDATE_SHA256": self.candidate_sha256,
            "RAW_MISSION_BYTES": self.raw_mission_bytes,
            "INLINE_CRITICAL_BYTES": self.inline_critical_bytes,
            "DELTA_BYTES": self.delta_bytes,
            "REFERENCE_CANONICAL_BYTES": self.reference_canonical_bytes,
            "DROP_DUPLICATE_CANDIDATE_BYTES": self.drop_duplicate_candidate_bytes,
            "DROP_DUPLICATE_BYTES": self.drop_duplicate_candidate_bytes,
            "UNKNOWN_CONSERVATIVE_BYTES": self.unknown_conservative_bytes,
            "UNKNOWN_BYTES": self.unknown_conservative_bytes,
            "REFERENCE_CANDIDATE_VISIBLE_BYTES": self.reference_candidate_visible_bytes,
            "MINIMUM_SUFFICIENT_CANDIDATE_BYTES": self.minimum_sufficient_candidate_bytes,
            "CANDIDATE_BYTES": self.minimum_sufficient_candidate_bytes,
            "HYPOTHETICAL_VISIBLE_BYTES_REDUCTION": self.hypothetical_visible_bytes_reduction,
            "HYPOTHETICAL_REDUCTION_BYTES": self.hypothetical_visible_bytes_reduction,
            "HYPOTHETICAL_REDUCTION_PERCENT": self.hypothetical_reduction_percent,
            "EVIDENCE_QUALITY": self.evidence_quality.value,
            "SENSITIVITY_ASSESSMENT": self.sensitivity_assessment.value,
            "PROOF_FAILURES": list(self.proof_failures),
            "DELIVERED_MISSION_MUTATED": False,
            "ACTIVE_DELIVERY_AUTHORIZED": self.active_delivery_authorized,
            "AUTOMATIC_SUPPRESSION": False,
            "SEMANTIC_INFERENCE_USED": self.semantic_inference_used,
            "BEHAVIORAL_EQUIVALENCE": self.behavioral_equivalence,
        }


class MissionContextShadowAnalyzer:
    """Measure explicit proofs while returning the original mission byte buffer."""

    def __init__(self, repository_root: pathlib.Path) -> None:
        self.repository_root = repository_root.resolve()
        if not self.repository_root.is_dir():
            raise ValueError("repository root must be an existing directory")

    def analyze(self, mission_bytes: bytes, manifest: ShadowManifest) -> MissionContextShadowResult:
        if not isinstance(mission_bytes, bytes):
            raise ValueError("mission must be bytes")
        if not isinstance(manifest, ShadowManifest):
            raise ValueError("manifest must be a ShadowManifest")
        if len(mission_bytes) != manifest.raw_bytes:
            raise ValueError("mission byte length does not match manifest")
        if hashlib.sha256(mission_bytes).hexdigest() != manifest.raw_sha256:
            raise ValueError("mission SHA-256 does not match manifest")
        spans = tuple(sorted(manifest.spans, key=lambda item: (item.start, item.end)))
        self._validate_span_layout(spans, len(mission_bytes))

        # Conservative veto: detector no-match never creates NON_SENSITIVE, but
        # a detector match or absent explicit assessment forbids reductions.
        reductions_allowed = (
            manifest.sensitivity_assessment is SafetyAssessment.NON_SENSITIVE
            and not contains_sensitive_material(mission_bytes)
        )
        non_inline_spans = tuple(
            span for span in spans
            if span.byte_class in (MissionByteClass.REFERENCE_CANONICAL, MissionByteClass.DROP_DUPLICATE)
        )
        counts = {item: 0 for item in MissionByteClass}
        unknown = 0
        reference_visible = 0
        failures = []
        candidate_parts = []
        cursor = 0

        for span in spans:
            if cursor < span.start:
                gap = mission_bytes[cursor:span.start]
                candidate_parts.append(gap)
                unknown += len(gap)
            segment = mission_bytes[span.start:span.end]
            if span.byte_class in (MissionByteClass.INLINE_CRITICAL, MissionByteClass.DELTA):
                counts[span.byte_class] += len(segment)
                candidate_parts.append(segment)
            elif not reductions_allowed:
                unknown += len(segment)
                candidate_parts.append(segment)
                failures.append("ASSESSMENT_OR_SENSITIVITY_REQUIRES_INLINE")
            elif span.byte_class is MissionByteClass.REFERENCE_CANONICAL:
                assert span.canonical is not None
                marker = self._canonical_marker_if_proven(segment, span.canonical)
                if marker is None:
                    unknown += len(segment)
                    candidate_parts.append(segment)
                    failures.append("REFERENCE_CANONICAL_PROOF_FAILED")
                else:
                    counts[span.byte_class] += len(segment)
                    visible = marker if len(marker) < len(segment) else segment
                    candidate_parts.append(visible)
                    reference_visible += len(visible)
            else:
                assert span.duplicate is not None
                if self._duplicate_is_proven(
                    mission_bytes, span, span.duplicate, non_inline_spans
                ):
                    counts[span.byte_class] += len(segment)
                    # Exact earlier inline bytes remain in the candidate.
                else:
                    unknown += len(segment)
                    candidate_parts.append(segment)
                    failures.append("DROP_DUPLICATE_PROOF_FAILED")
            cursor = span.end

        if cursor < len(mission_bytes):
            tail = mission_bytes[cursor:]
            candidate_parts.append(tail)
            unknown += len(tail)
        candidate = b"".join(candidate_parts)
        categorized = sum(counts.values()) + unknown
        if categorized != len(mission_bytes):
            raise AssertionError("shadow byte accounting did not conserve input")
        if len(candidate) > len(mission_bytes):
            raise AssertionError("shadow candidate expanded input")

        return MissionContextShadowResult(
            mission_id=manifest.mission_id,
            evidence_quality=manifest.evidence_quality,
            sensitivity_assessment=manifest.sensitivity_assessment,
            delivered_mission_bytes=mission_bytes,
            candidate_bytes=candidate,
            raw_mission_bytes=len(mission_bytes),
            inline_critical_bytes=counts[MissionByteClass.INLINE_CRITICAL],
            delta_bytes=counts[MissionByteClass.DELTA],
            reference_canonical_bytes=counts[MissionByteClass.REFERENCE_CANONICAL],
            drop_duplicate_candidate_bytes=counts[MissionByteClass.DROP_DUPLICATE],
            unknown_conservative_bytes=unknown,
            reference_candidate_visible_bytes=reference_visible,
            proof_failures=tuple(failures),
        )

    @staticmethod
    def _validate_span_layout(spans: Sequence[MissionSpan], raw_bytes: int) -> None:
        previous_end = 0
        for span in spans:
            if span.end > raw_bytes:
                raise ValueError("mission span exceeds raw mission bytes")
            if span.start < previous_end:
                raise ValueError("mission spans overlap")
            previous_end = span.end

    def _canonical_marker_if_proven(
        self, segment: bytes, proof: CanonicalArtifactProof
    ) -> Optional[bytes]:
        if (
            not isinstance(proof.repository_path, str)
            or not isinstance(proof.artifact_sha256, str)
            or _SHA256.fullmatch(proof.artifact_sha256) is None
            or not _is_int(proof.artifact_start)
            or not _is_int(proof.artifact_end)
            or proof.artifact_start < 0
            or proof.artifact_end <= proof.artifact_start
        ):
            return None
        pure = pathlib.PurePosixPath(proof.repository_path)
        if (
            not proof.repository_path
            or pure.is_absolute()
            or pure.as_posix() != proof.repository_path
            or any(part in ("", ".", "..") for part in pure.parts)
        ):
            return None
        unresolved_path = self.repository_root / pathlib.Path(*pure.parts)
        if unresolved_path.is_symlink():
            return None
        artifact_path = unresolved_path.resolve()
        try:
            artifact_path.relative_to(self.repository_root)
        except ValueError:
            return None
        if not artifact_path.is_file() or not self._is_tracked(proof.repository_path):
            return None
        try:
            artifact = artifact_path.read_bytes()
        except OSError:
            return None
        if hashlib.sha256(artifact).hexdigest() != proof.artifact_sha256:
            return None
        if proof.artifact_end > len(artifact):
            return None
        if artifact[proof.artifact_start:proof.artifact_end] != segment:
            return None
        payload = {
            "artifact_sha256": proof.artifact_sha256,
            "end": proof.artifact_end,
            "path": proof.repository_path,
            "start": proof.artifact_start,
        }
        return (
            b"[[FIOFILTER:MISSION-CANONICAL:" + REFERENCE_VERSION.encode("ascii") + b":"
            + json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
            + b"]]"
        )

    def _is_tracked(self, repository_path: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.repository_root), "ls-files", "--error-unmatch", "--", repository_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0

    @staticmethod
    def _duplicate_is_proven(
        mission: bytes,
        target: MissionSpan,
        proof: DuplicateProof,
        non_inline_spans: Sequence[MissionSpan],
    ) -> bool:
        if (
            not _is_int(proof.source_start)
            or not _is_int(proof.source_end)
            or proof.source_start < 0
            or proof.source_end <= proof.source_start
            or proof.source_end > target.start
            or proof.source_end - proof.source_start != target.end - target.start
        ):
            return False
        # The proof source must itself remain inline; a chain of hidden copies is
        # not enough to call the target conservatively redundant.
        if any(
            proof.source_start < span.end and span.start < proof.source_end
            for span in non_inline_spans
        ):
            return False
        return mission[proof.source_start:proof.source_end] == mission[target.start:target.end]


def load_manifest(path: pathlib.Path) -> ShadowManifest:
    """Load a strict payload-free JSON manifest."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid shadow manifest JSON") from exc
    expected = {
        "schema_version", "mission_id", "raw_sha256", "raw_bytes",
        "evidence_quality", "sensitivity_assessment", "spans",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("invalid shadow manifest fields")
    if not isinstance(value["spans"], list):
        raise ValueError("manifest spans must be a list")
    spans = tuple(_load_span(item) for item in value["spans"])
    try:
        quality = EvidenceQuality(value["evidence_quality"])
        assessment = SafetyAssessment(value["sensitivity_assessment"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid manifest enum") from exc
    return ShadowManifest(
        schema_version=value["schema_version"],
        mission_id=value["mission_id"],
        raw_sha256=value["raw_sha256"],
        raw_bytes=value["raw_bytes"],
        evidence_quality=quality,
        sensitivity_assessment=assessment,
        spans=spans,
    )


def aggregate_shadow_results(
    results: Sequence[MissionContextShadowResult],
) -> Dict[str, Any]:
    """Aggregate only real, byte-bound samples; synthetic tests are excluded."""

    if not all(isinstance(item, MissionContextShadowResult) for item in results):
        raise ValueError("aggregate requires MissionContextShadowResult values")
    trustworthy = [item for item in results if item.evidence_quality is not EvidenceQuality.SYNTHETIC]
    if len(trustworthy) < 2:
        return {
            "AGGREGATE_STATUS": "NOT_COMPUTED_INSUFFICIENT_TRUSTWORTHY_SAMPLES",
            "TRUSTWORTHY_SAMPLES": len(trustworthy),
            "MEDIAN_HYPOTHETICAL_REDUCTION_PERCENT": None,
            "TOTAL_PROVEN_REEXPOSURE_BYTES": None,
            "TOTAL_UNKNOWN_BYTES": None,
        }
    return {
        "AGGREGATE_STATUS": "COMPUTED",
        "TRUSTWORTHY_SAMPLES": len(trustworthy),
        "MEDIAN_HYPOTHETICAL_REDUCTION_PERCENT": round(
            float(statistics.median(item.hypothetical_reduction_percent for item in trustworthy)), 2
        ),
        "TOTAL_PROVEN_REEXPOSURE_BYTES": sum(
            item.reference_canonical_bytes + item.drop_duplicate_candidate_bytes
            for item in trustworthy
        ),
        "TOTAL_UNKNOWN_BYTES": sum(item.unknown_conservative_bytes for item in trustworthy),
    }


def _load_span(value: Any) -> MissionSpan:
    if not isinstance(value, dict) or not {"start", "end", "byte_class"}.issubset(value):
        raise ValueError("invalid mission span fields")
    try:
        byte_class = MissionByteClass(value["byte_class"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid mission byte class") from exc
    common = {"start", "end", "byte_class"}
    if byte_class is MissionByteClass.REFERENCE_CANONICAL:
        if set(value) != common | {"canonical"} or not isinstance(value["canonical"], dict):
            raise ValueError("invalid canonical span fields")
        proof_value = value["canonical"]
        proof_fields = {"repository_path", "artifact_sha256", "artifact_start", "artifact_end"}
        if set(proof_value) != proof_fields:
            raise ValueError("invalid canonical proof fields")
        return MissionSpan(
            value["start"], value["end"], byte_class,
            canonical=CanonicalArtifactProof(**proof_value),
        )
    if byte_class is MissionByteClass.DROP_DUPLICATE:
        if set(value) != common | {"duplicate"} or not isinstance(value["duplicate"], dict):
            raise ValueError("invalid duplicate span fields")
        proof_value = value["duplicate"]
        if set(proof_value) != {"source_start", "source_end"}:
            raise ValueError("invalid duplicate proof fields")
        return MissionSpan(
            value["start"], value["end"], byte_class,
            duplicate=DuplicateProof(**proof_value),
        )
    if set(value) != common:
        raise ValueError("invalid inline span fields")
    return MissionSpan(value["start"], value["end"], byte_class)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
