"""Versioned, payload-free longitudinal efficiency evidence.

FIO_EFFICIENCY_FEED_V1 stores operational counts, hashes and scoped hypotheses.
It deliberately has no field for prompts, messages, tool arguments, command text,
file contents, authorization data or absolute local paths.
"""

from __future__ import annotations

import enum
import hashlib
import json
import pathlib
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


EFFICIENCY_FEED_SCHEMA_VERSION = "FIO_EFFICIENCY_FEED_V1"
EFFICIENCY_FEED_AGGREGATE_VERSION = "FIO_EFFICIENCY_FEED_V1_AGGREGATE"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?Z$"
)
_MODEL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OTHER_TOKEN_METRIC = re.compile(r"^other_provider_[a-z0-9_]{1,64}_tokens$")
_TOKEN_METRICS = {
    "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens",
}
_TOOL_FAMILIES = {"FILE_READ", "SEARCH", "TEST", "SCRIPT", "GIT", "BUILD", "OTHER"}


class TokenMeasurementQuality(str, enum.Enum):
    PROVIDER_REPORTED_EXACT = "PROVIDER_REPORTED_EXACT"
    RUNTIME_REPORTED_EXACT = "RUNTIME_REPORTED_EXACT"
    DERIVED_FROM_EXACT_ACCOUNTING = "DERIVED_FROM_EXACT_ACCOUNTING"
    ESTIMATED_BYTES_DIV_4 = "ESTIMATED_BYTES_DIV_4"
    UNAVAILABLE = "UNAVAILABLE"


class LiveEvidenceClass(str, enum.Enum):
    REAL_CODEX_FULL_SESSION = "REAL_CODEX_FULL_SESSION"
    REAL_CODEX_PARTIAL_SESSION = "REAL_CODEX_PARTIAL_SESSION"
    CONTROLLED_LIVE_LAB = "CONTROLLED_LIVE_LAB"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    SYNTHETIC = "SYNTHETIC"


class MissionOutcomeClass(str, enum.Enum):
    VERIFIED_COMPLETED = "VERIFIED_COMPLETED"
    VERIFIED_FAILED = "VERIFIED_FAILED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class WasteCandidateClass(str, enum.Enum):
    DISCOVERY_WASTE_CANDIDATE = "DISCOVERY_WASTE_CANDIDATE"
    REEXPOSURE_WASTE_CANDIDATE = "REEXPOSURE_WASTE_CANDIDATE"
    REPRESENTATION_WASTE_CANDIDATE = "REPRESENTATION_WASTE_CANDIDATE"
    HANDOFF_REDUNDANCY_CANDIDATE = "HANDOFF_REDUNDANCY_CANDIDATE"


def hash_private_identifier(value: str) -> str:
    """Return a portable identifier without exporting the underlying value."""
    if not isinstance(value, str) or not value:
        raise ValueError("identifier must be non-empty text")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_hash(value: Optional[str], field_name: str, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _require_nonnegative(value: Optional[int], field_name: str, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True)
class TokenMeasurement:
    value: Optional[int]
    quality: TokenMeasurementQuality
    basis_bytes: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.quality, TokenMeasurementQuality):
            raise ValueError("token measurement quality is required")
        if self.quality is TokenMeasurementQuality.UNAVAILABLE:
            if self.value is not None or self.basis_bytes is not None:
                raise ValueError("UNAVAILABLE token measurements cannot carry values")
            return
        _require_nonnegative(self.value, "token value")
        if self.quality is TokenMeasurementQuality.ESTIMATED_BYTES_DIV_4:
            _require_nonnegative(self.basis_bytes, "token estimate basis_bytes")
        elif self.basis_bytes is not None:
            raise ValueError("exact token measurements cannot carry estimate basis bytes")

    @classmethod
    def unavailable(cls) -> "TokenMeasurement":
        return cls(value=None, quality=TokenMeasurementQuality.UNAVAILABLE)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "token_measurement_quality": self.quality.value,
            "basis_bytes": self.basis_bytes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TokenMeasurement":
        expected = {"value", "token_measurement_quality", "basis_bytes"}
        if set(value) != expected:
            raise ValueError("invalid token measurement fields")
        return cls(
            value=value["value"],
            quality=TokenMeasurementQuality(value["token_measurement_quality"]),
            basis_bytes=value["basis_bytes"],
        )


@dataclass(frozen=True)
class PathReadObservation:
    path_hash: str
    repository_relative_path: Optional[str]
    read_events: int
    bytes_delivered: int

    def __post_init__(self) -> None:
        _require_hash(self.path_hash, "path_hash")
        _require_nonnegative(self.read_events, "read_events")
        _require_nonnegative(self.bytes_delivered, "bytes_delivered")
        path = self.repository_relative_path
        if path is not None:
            if (
                not isinstance(path, str)
                or not path
                or len(path) > 1024
                or any(character in path for character in ("\x00", "\r", "\n"))
            ):
                raise ValueError("repository_relative_path must be clean text")
            normalized = path.replace("\\", "/")
            pure = pathlib.PurePosixPath(normalized)
            if pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:", normalized):
                raise ValueError("absolute and parent-traversal paths are forbidden")
            object.__setattr__(self, "repository_relative_path", normalized)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PathReadObservation":
        expected = {"path_hash", "repository_relative_path", "read_events", "bytes_delivered"}
        if set(value) != expected:
            raise ValueError("invalid path observation fields")
        return cls(**dict(value))


@dataclass(frozen=True)
class EfficiencyFeedRecord:
    session_id_hash: str
    run_id_hash: Optional[str]
    repository_id: str
    git_head: str
    worktree_fingerprint: str
    model: Optional[str]
    start_time: str
    end_time: str
    task_hash: Optional[str]
    live_evidence_class: LiveEvidenceClass
    token_measurements: Mapping[str, TokenMeasurement]
    tool_output_bytes: int
    tool_calls: int
    turns_if_known: Optional[int]
    tool_output_bytes_by_family: Mapping[str, int]
    file_read_events: int
    file_read_bytes: int
    first_reads: int
    repeated_source_view_reads: int
    identical_reread_events: int
    identical_reread_bytes: int
    f4_proven_events: int
    read_reference_candidates: int
    read_reference_hypothetical_bytes_avoided: int
    discovery_queries: int
    first_target_read_position: Optional[int]
    t02_applicable_events: int
    t02_no_economic_gain: int
    t02_rejected: int
    t02_hypothetical_bytes_avoided: int
    corrective_rereads: int
    mission_outcome_class: MissionOutcomeClass
    search_output_events: int = 0
    structurally_proven_rg_events: int = 0
    automatic_t02_applied: int = 0
    raw_codex_behavior_changed: bool = False
    active_suppression: bool = False
    auto_context_selection: bool = False
    path_read_observations: Tuple[PathReadObservation, ...] = ()
    waste_candidate_counts: Mapping[str, int] = field(default_factory=dict)
    schema_version: str = field(default=EFFICIENCY_FEED_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_hash(self.session_id_hash, "session_id_hash")
        _require_hash(self.run_id_hash, "run_id_hash", allow_none=True)
        _require_hash(self.worktree_fingerprint, "worktree_fingerprint")
        _require_hash(self.task_hash, "task_hash", allow_none=True)
        if not isinstance(self.git_head, str) or _HEX_40.fullmatch(self.git_head) is None:
            raise ValueError("git_head must be a lowercase Git SHA-1")
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", self.repository_id):
            raise ValueError("repository_id must be owner/name")
        if self.model is not None and (
            not isinstance(self.model, str) or _MODEL_IDENTIFIER.fullmatch(self.model) is None
        ):
            raise ValueError("model must be a bounded identifier")
        if (
            not isinstance(self.start_time, str)
            or _TIMESTAMP.fullmatch(self.start_time) is None
            or not isinstance(self.end_time, str)
            or _TIMESTAMP.fullmatch(self.end_time) is None
        ):
            raise ValueError("start_time and end_time must be UTC timestamps")
        if not isinstance(self.live_evidence_class, LiveEvidenceClass):
            raise ValueError("live_evidence_class is required")
        if not isinstance(self.mission_outcome_class, MissionOutcomeClass):
            raise ValueError("mission_outcome_class is required")
        required_token_metrics = {
            "input_tokens", "output_tokens", "cached_input_tokens",
        }
        if not required_token_metrics.issubset(self.token_measurements):
            raise ValueError("input/output/cached token provenance must be explicit")
        for name, measurement in self.token_measurements.items():
            if (
                not isinstance(name, str)
                or (name not in _TOKEN_METRICS and _OTHER_TOKEN_METRIC.fullmatch(name) is None)
                or not isinstance(measurement, TokenMeasurement)
            ):
                raise ValueError("every token metric requires an explicit measurement")
        count_fields = (
            "tool_output_bytes", "tool_calls", "file_read_events", "file_read_bytes",
            "first_reads", "repeated_source_view_reads", "identical_reread_events",
            "identical_reread_bytes", "f4_proven_events", "read_reference_candidates",
            "read_reference_hypothetical_bytes_avoided", "discovery_queries",
            "t02_applicable_events", "t02_no_economic_gain", "t02_rejected",
            "t02_hypothetical_bytes_avoided", "corrective_rereads",
            "search_output_events", "structurally_proven_rg_events",
            "automatic_t02_applied",
        )
        for name in count_fields:
            _require_nonnegative(getattr(self, name), name)
        _require_nonnegative(self.turns_if_known, "turns_if_known", allow_none=True)
        _require_nonnegative(
            self.first_target_read_position,
            "first_target_read_position",
            allow_none=True,
        )
        for family, value in self.tool_output_bytes_by_family.items():
            if family not in _TOOL_FAMILIES:
                raise ValueError("unknown tool family")
            _require_nonnegative(value, f"tool family {family}")
        if sum(self.tool_output_bytes_by_family.values()) != self.tool_output_bytes:
            raise ValueError("tool family bytes must equal tool_output_bytes")
        if self.file_read_bytes > self.tool_output_bytes:
            raise ValueError("file_read_bytes cannot exceed tool_output_bytes")
        if self.file_read_events > self.tool_calls:
            raise ValueError("file_read_events cannot exceed tool_calls")
        if self.first_reads + self.repeated_source_view_reads > self.file_read_events:
            raise ValueError("classified reads cannot exceed file_read_events")
        if self.identical_reread_events > self.repeated_source_view_reads:
            raise ValueError("identical rereads require repeated source/view reads")
        if self.identical_reread_bytes > self.file_read_bytes:
            raise ValueError("identical reread bytes cannot exceed file_read_bytes")
        if self.f4_proven_events > self.identical_reread_events:
            raise ValueError("F4 events require byte-identical rereads")
        if self.read_reference_candidates > self.identical_reread_events:
            raise ValueError("reference candidates require byte-identical rereads")
        if self.read_reference_hypothetical_bytes_avoided > self.identical_reread_bytes:
            raise ValueError("reference savings cannot exceed identical reread bytes")
        if self.search_output_events > self.tool_calls:
            raise ValueError("search_output_events cannot exceed tool_calls")
        if self.structurally_proven_rg_events > self.search_output_events:
            raise ValueError("proven rg events require search events")
        if (
            self.t02_applicable_events + self.t02_no_economic_gain + self.t02_rejected
            > self.search_output_events
        ):
            raise ValueError("T02 classifications cannot exceed search events")
        if self.t02_hypothetical_bytes_avoided > self.tool_output_bytes:
            raise ValueError("T02 hypothetical savings cannot exceed observed bytes")
        if (
            self.raw_codex_behavior_changed
            or self.active_suppression
            or self.auto_context_selection
            or self.automatic_t02_applied != 0
        ):
            raise ValueError("Efficiency Feed v1 is shadow-only")
        allowed_waste = {item.value for item in WasteCandidateClass}
        for name, value in self.waste_candidate_counts.items():
            if name not in allowed_waste:
                raise ValueError("unknown waste candidate class")
            _require_nonnegative(value, name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id_hash": self.session_id_hash,
            "run_id_hash": self.run_id_hash,
            "repository_id": self.repository_id,
            "git_head": self.git_head,
            "worktree_fingerprint": self.worktree_fingerprint,
            "model": self.model,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "task_hash": self.task_hash,
            "live_evidence_class": self.live_evidence_class.value,
            "token_measurements": {
                name: self.token_measurements[name].to_dict()
                for name in sorted(self.token_measurements)
            },
            "tool_output_bytes": self.tool_output_bytes,
            "tool_calls": self.tool_calls,
            "turns_if_known": self.turns_if_known,
            "tool_output_bytes_by_family": dict(sorted(self.tool_output_bytes_by_family.items())),
            "file_read_events": self.file_read_events,
            "file_read_bytes": self.file_read_bytes,
            "first_reads": self.first_reads,
            "repeated_source_view_reads": self.repeated_source_view_reads,
            "identical_reread_events": self.identical_reread_events,
            "identical_reread_bytes": self.identical_reread_bytes,
            "f4_proven_events": self.f4_proven_events,
            "read_reference_candidates": self.read_reference_candidates,
            "read_reference_hypothetical_bytes_avoided": self.read_reference_hypothetical_bytes_avoided,
            "discovery_queries": self.discovery_queries,
            "first_target_read_position": self.first_target_read_position,
            "t02_applicable_events": self.t02_applicable_events,
            "t02_no_economic_gain": self.t02_no_economic_gain,
            "t02_rejected": self.t02_rejected,
            "t02_hypothetical_bytes_avoided": self.t02_hypothetical_bytes_avoided,
            "corrective_rereads": self.corrective_rereads,
            "mission_outcome_class": self.mission_outcome_class.value,
            "search_output_events": self.search_output_events,
            "structurally_proven_rg_events": self.structurally_proven_rg_events,
            "automatic_t02_applied": self.automatic_t02_applied,
            "raw_codex_behavior_changed": self.raw_codex_behavior_changed,
            "active_suppression": self.active_suppression,
            "auto_context_selection": self.auto_context_selection,
            "path_read_observations": [item.to_dict() for item in self.path_read_observations],
            "waste_candidate_counts": dict(sorted(self.waste_candidate_counts.items())),
        }

    def to_json(self) -> str:
        return serialize_feed_record(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EfficiencyFeedRecord":
        expected = {
            "schema_version", "session_id_hash", "run_id_hash", "repository_id",
            "git_head", "worktree_fingerprint", "model", "start_time", "end_time",
            "task_hash", "live_evidence_class", "token_measurements",
            "tool_output_bytes", "tool_calls", "turns_if_known",
            "tool_output_bytes_by_family", "file_read_events", "file_read_bytes",
            "first_reads", "repeated_source_view_reads", "identical_reread_events",
            "identical_reread_bytes", "f4_proven_events", "read_reference_candidates",
            "read_reference_hypothetical_bytes_avoided", "discovery_queries",
            "first_target_read_position", "t02_applicable_events",
            "t02_no_economic_gain", "t02_rejected",
            "t02_hypothetical_bytes_avoided", "corrective_rereads",
            "mission_outcome_class", "path_read_observations", "waste_candidate_counts",
            "search_output_events", "structurally_proven_rg_events",
            "automatic_t02_applied", "raw_codex_behavior_changed",
            "active_suppression", "auto_context_selection",
        }
        if set(value) != expected:
            raise ValueError("invalid or forbidden Efficiency Feed fields")
        if value["schema_version"] != EFFICIENCY_FEED_SCHEMA_VERSION:
            raise ValueError("unsupported Efficiency Feed schema")
        kwargs = dict(value)
        kwargs.pop("schema_version")
        kwargs["live_evidence_class"] = LiveEvidenceClass(kwargs["live_evidence_class"])
        kwargs["mission_outcome_class"] = MissionOutcomeClass(kwargs["mission_outcome_class"])
        kwargs["token_measurements"] = {
            name: TokenMeasurement.from_dict(item)
            for name, item in kwargs["token_measurements"].items()
        }
        kwargs["path_read_observations"] = tuple(
            PathReadObservation.from_dict(item) for item in kwargs["path_read_observations"]
        )
        return cls(**kwargs)


def serialize_feed_record(record: EfficiencyFeedRecord) -> str:
    return json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"


def deserialize_feed_record(encoded: str) -> EfficiencyFeedRecord:
    if not isinstance(encoded, str) or not encoded.strip():
        raise ValueError("feed record must be non-empty JSON text")
    return EfficiencyFeedRecord.from_dict(json.loads(encoded))


def aggregate_efficiency_feed(records: Iterable[EfficiencyFeedRecord]) -> Dict[str, Any]:
    """Aggregate without collapsing exact and estimated token classes."""
    items = list(records)
    token_totals: Dict[str, Counter] = defaultdict(Counter)
    token_unavailable: Counter = Counter()
    family_bytes: Counter = Counter()
    evidence_counts: Counter = Counter()
    outcome_counts: Counter = Counter()
    waste_counts: Counter = Counter()
    paths: Dict[Tuple[str, Optional[str]], Counter] = defaultdict(Counter)

    additive = Counter()
    additive_names = (
        "tool_output_bytes", "tool_calls", "file_read_events", "file_read_bytes",
        "first_reads", "repeated_source_view_reads",
        "identical_reread_events", "identical_reread_bytes", "read_reference_candidates",
        "read_reference_hypothetical_bytes_avoided", "discovery_queries",
        "f4_proven_events", "t02_applicable_events", "t02_no_economic_gain",
        "t02_rejected", "t02_hypothetical_bytes_avoided", "corrective_rereads",
        "search_output_events", "structurally_proven_rg_events", "automatic_t02_applied",
    )
    for record in items:
        for name, measurement in record.token_measurements.items():
            if measurement.quality is TokenMeasurementQuality.UNAVAILABLE:
                token_unavailable[name] += 1
            else:
                token_totals[name][measurement.quality.value] += int(measurement.value or 0)
        family_bytes.update(record.tool_output_bytes_by_family)
        evidence_counts[record.live_evidence_class.value] += 1
        outcome_counts[record.mission_outcome_class.value] += 1
        waste_counts.update(record.waste_candidate_counts)
        for name in additive_names:
            additive[name] += getattr(record, name)
        for observation in record.path_read_observations:
            key = (observation.path_hash, observation.repository_relative_path)
            paths[key]["read_events"] += observation.read_events
            paths[key]["bytes_delivered"] += observation.bytes_delivered

    dominant = [
        {"family": family, "output_bytes": value}
        for family, value in sorted(family_bytes.items(), key=lambda item: (-item[1], item[0]))
    ]
    top_paths = [
        {
            "path_hash": path_hash,
            "repository_relative_path": rel,
            "read_events": counts["read_events"],
            "bytes_delivered": counts["bytes_delivered"],
        }
        for (path_hash, rel), counts in sorted(
            paths.items(),
            key=lambda item: (-item[1]["read_events"], item[0][0], item[0][1] or ""),
        )
        if counts["read_events"] > 1
    ]
    return {
        "schema_version": EFFICIENCY_FEED_AGGREGATE_VERSION,
        "records_analyzed": len(items),
        "sessions_analyzed": len({record.session_id_hash for record in items}),
        "token_totals_by_quality": {
            name: dict(sorted(counter.items())) for name, counter in sorted(token_totals.items())
        },
        "token_unavailable_record_counts": dict(sorted(token_unavailable.items())),
        "tool_output_bytes": additive["tool_output_bytes"],
        "tool_calls": additive["tool_calls"],
        "dominant_tool_families": dominant,
        "file_read_events": additive["file_read_events"],
        "file_read_bytes": additive["file_read_bytes"],
        "first_reads": additive["first_reads"],
        "repeated_source_view_reads": additive["repeated_source_view_reads"],
        "identical_reread_events": additive["identical_reread_events"],
        "identical_reread_bytes": additive["identical_reread_bytes"],
        "f4_proven_events": additive["f4_proven_events"],
        "read_reference_candidates": additive["read_reference_candidates"],
        "read_reference_hypothetical_bytes_avoided": additive["read_reference_hypothetical_bytes_avoided"],
        "discovery_queries": additive["discovery_queries"],
        "t02_applicable_events": additive["t02_applicable_events"],
        "t02_no_economic_gain": additive["t02_no_economic_gain"],
        "t02_rejected": additive["t02_rejected"],
        "t02_hypothetical_bytes_avoided": additive["t02_hypothetical_bytes_avoided"],
        "search_output_events": additive["search_output_events"],
        "structurally_proven_rg_events": additive["structurally_proven_rg_events"],
        "automatic_t02_applied": additive["automatic_t02_applied"],
        "corrective_rereads": additive["corrective_rereads"],
        "top_repeated_repository_files": top_paths,
        "mission_outcome_counts": dict(sorted(outcome_counts.items())),
        "live_evidence_class_counts": dict(sorted(evidence_counts.items())),
        "waste_candidate_counts": dict(sorted(waste_counts.items())),
        "automatic_architectural_recommendation": None,
        "handoff_redundancy_analyzer": "DEFERRED_TO_HANDOFF_BRIDGE_MISSION",
    }
