"""Versioned corpus schema and replay harness for bounded workload evaluation.

The extractor may suggest labels, but only separately reviewed labels are an
oracle. Replay never feeds either kind of label into FioFilter.
"""

from __future__ import annotations

import base64
import json
import pathlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fiofilter.engine import process
from fiofilter.metrics import estimate_tokens
from fiofilter.types import Disposition, EvidenceClass, Mode, Persistence, Sensitivity, ToolResult


CORPUS_SCHEMA_VERSION = 4
M03_V3_AS_HEURISTIC = "M03_V3_AS_HEURISTIC"

MISSED_OPPORTUNITY_BUCKETS = (
    "REPETITIVE_PROGRESS",
    "DIRECTORY_OR_PATH_REDUNDANCY",
    "KNOWN_SUCCESS_RECORDS",
    "KNOWN_BOILERPLATE",
    "DUPLICATED_HEADERS",
    "STRUCTURED_BUT_CONSUMER_SPECIFIC",
    "OTHER",
)
ORACLE_PROVENANCE_VALUES = ("INDEPENDENT_REVIEW", "HUMAN_REVIEW", "GOLD")
SENSITIVITY_SCREENING_RESULTS = (
    "DETECTOR_NO_MATCH",
    "DETECTOR_MATCH",
    "NOT_RUN",
    "UNKNOWN",
)

SAFETY_SAFE_MATCH = "SAFE_MATCH"
SAFETY_SAFE_OPPORTUNITY_MISSED = "SAFE_OPPORTUNITY_MISSED"
SAFETY_DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY = "DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY"
SAFETY_UNSAFE_SENSITIVITY_LEAK = "UNSAFE_SENSITIVITY_LEAK"
SAFETY_LABEL_UNCERTAIN = "LABEL_UNCERTAIN"


@dataclass
class CorpusSourceData:
    """Raw execution evidence and execution metadata."""

    provenance: str
    command: Optional[str] = None
    exit_code: Optional[int] = None
    stdout_stderr: str = "combined"
    content_type_hint: Optional[str] = None
    raw_content_b64: Optional[str] = None
    raw_ref_path: Optional[str] = None
    byte_length: int = 0
    truncated: bool = False

    def get_bytes(self) -> bytes:
        """Resolve exactly one inline or external source of bytes."""
        if self.raw_content_b64 is not None and self.raw_ref_path is not None:
            raise ValueError("CorpusSourceData has both raw_content_b64 and raw_ref_path")
        if self.raw_content_b64 is not None:
            try:
                return base64.b64decode(self.raw_content_b64.encode("ascii"), validate=True)
            except (UnicodeEncodeError, ValueError) as exc:
                raise ValueError("CorpusSourceData has invalid base64 content") from exc
        if self.raw_ref_path is not None:
            path = pathlib.Path(self.raw_ref_path)
            if not path.exists():
                raise FileNotFoundError(f"Corpus raw reference path not found: {self.raw_ref_path}")
            return path.read_bytes()
        raise ValueError("CorpusSourceData has neither raw_content_b64 nor raw_ref_path")


@dataclass
class CorpusSensitivityScreening:
    """Result of a screening step, not a non-sensitivity assertion."""

    result: str = "UNKNOWN"
    method: str = ""
    notes: str = ""


@dataclass
class CorpusHeuristicSuggestion:
    """Machine/extractor suggestion that must not be reported as ground truth."""

    evidence_class: str
    transform_eligibility: str = "UNKNOWN"
    inline_required_facts: List[str] = field(default_factory=list)
    rationale: str = ""
    missed_opportunity_category: Optional[str] = None
    method: str = "M03_EXTRACTOR_V1"


@dataclass
class CorpusOracleLabels:
    """Labels with explicit independent review provenance."""

    evidence_class: str
    provenance: str
    reviewer_id: str
    review_protocol: str
    sensitivity: str = "UNKNOWN"
    transform_eligibility: str = "UNKNOWN"
    inline_required_facts: List[str] = field(default_factory=list)
    oracle_rationale: str = ""
    missed_opportunity_category: Optional[str] = None


@dataclass
class CorpusDerivedMetrics:
    """Runtime observations and comparisons, with label scope attached."""

    predicted_evidence_class: Optional[str] = None
    predicted_disposition: Optional[str] = None
    predicted_sensitivity: Optional[str] = None
    predicted_transform_id: Optional[str] = None
    raw_bytes: int = 0
    visible_bytes: int = 0
    raw_token_estimate: float = 0.0
    visible_token_estimate: float = 0.0
    token_estimate_method: str = "utf8_bytes_div_4_ESTIMATE"
    comparison_by_label_scope: Dict[str, str] = field(default_factory=dict)
    inline_facts_preserved_by_label_scope: Dict[str, bool] = field(default_factory=dict)
    t01_marker_overhead_defeated: bool = False
    t01_unapproved_grammar_by_label_scope: Dict[str, bool] = field(default_factory=dict)
    policy_reason: str = ""
    notes: str = ""


@dataclass
class CorpusEntry:
    """One source item plus optional heuristic and independently reviewed labels."""

    entry_id: str
    source_data: CorpusSourceData
    oracle_labels: Optional[CorpusOracleLabels] = None
    heuristic_suggestion: Optional[CorpusHeuristicSuggestion] = None
    sensitivity_screening: CorpusSensitivityScreening = field(
        default_factory=CorpusSensitivityScreening
    )
    derived_metrics: Optional[CorpusDerivedMetrics] = None
    tags: List[str] = field(default_factory=list)
    schema_version: int = CORPUS_SCHEMA_VERSION

    def to_tool_result(self) -> ToolResult:
        """Create an unbiased subject input from source data only.

        Oracle sensitivity and required facts are evaluation references. Feeding
        them into the engine would make sensitivity and preservation results
        circular.
        """
        return ToolResult(
            content=self.source_data.get_bytes(),
            source=self.source_data.provenance,
            command=self.source_data.command,
            exit_code=self.source_data.exit_code,
            stream=self.source_data.stdout_stderr,
            content_type_hint=self.source_data.content_type_hint,
            truncated=self.source_data.truncated,
            inline_required_facts=[],
            sensitivity=Sensitivity.UNKNOWN,
            persistence=Persistence.EPHEMERAL,
        )

    def to_dict(self, include_raw: bool = True) -> Dict[str, Any]:
        """Serialize the versioned schema; reports may omit raw references."""
        source: Dict[str, Any] = {
            "provenance": self.source_data.provenance,
            "command": self.source_data.command,
            "exit_code": self.source_data.exit_code,
            "stdout_stderr": self.source_data.stdout_stderr,
            "content_type_hint": self.source_data.content_type_hint,
            "byte_length": self.source_data.byte_length,
            "truncated": self.source_data.truncated,
        }
        if include_raw:
            source["raw_content_b64"] = self.source_data.raw_content_b64
            source["raw_ref_path"] = self.source_data.raw_ref_path
        data: Dict[str, Any] = {
            "schema_version": CORPUS_SCHEMA_VERSION,
            "entry_id": self.entry_id,
            "source_data": source,
            "sensitivity_screening": asdict(self.sensitivity_screening),
            "heuristic_suggestion": (
                asdict(self.heuristic_suggestion) if self.heuristic_suggestion else None
            ),
            "oracle_labels": asdict(self.oracle_labels) if self.oracle_labels else None,
            "tags": list(self.tags),
        }
        if self.derived_metrics is not None:
            data["derived_metrics"] = asdict(self.derived_metrics)
        return data

    @classmethod
    def from_dict(
        cls, d: Dict[str, Any], migration: Optional[str] = None
    ) -> "CorpusEntry":
        """Parse v4, or explicitly demote an M03 v3 oracle to a heuristic."""
        if not isinstance(d, dict):
            raise TypeError("CorpusEntry dictionary must be a dict")
        version = d.get("schema_version")
        if version != CORPUS_SCHEMA_VERSION:
            if migration != M03_V3_AS_HEURISTIC:
                raise ValueError(
                    "Corpus schema is not v4; pass migration=M03_V3_AS_HEURISTIC "
                    "to demote legacy M03 labels to heuristic suggestions"
                )
            return cls._from_m03_v3_as_heuristic(d)

        entry_id = str(d.get("entry_id") or "")
        if not entry_id:
            raise ValueError("CorpusEntry missing required 'entry_id'")
        source_data = _parse_source_data(d.get("source_data"))
        screening_raw = d.get("sensitivity_screening") or {}
        screening = CorpusSensitivityScreening(
            result=str(screening_raw.get("result", "UNKNOWN")),
            method=str(screening_raw.get("method", "")),
            notes=str(screening_raw.get("notes", "")),
        )
        heuristic_raw = d.get("heuristic_suggestion")
        heuristic = _parse_heuristic(heuristic_raw) if heuristic_raw else None
        oracle_raw = d.get("oracle_labels")
        oracle = _parse_oracle(oracle_raw) if oracle_raw else None
        derived = None
        if d.get("derived_metrics") is not None:
            derived = CorpusDerivedMetrics(**d["derived_metrics"])
        return cls(
            entry_id=entry_id,
            source_data=source_data,
            oracle_labels=oracle,
            heuristic_suggestion=heuristic,
            sensitivity_screening=screening,
            derived_metrics=derived,
            tags=list(d.get("tags") or []),
        )

    @classmethod
    def _from_m03_v3_as_heuristic(cls, d: Dict[str, Any]) -> "CorpusEntry":
        entry_id = str(d.get("entry_id") or d.get("corpus_entry_id") or "")
        if not entry_id:
            raise ValueError("CorpusEntry missing required 'entry_id'")
        source_raw = d.get("source_data") or {
            "provenance": d.get("source", "unknown"),
            "raw_content_b64": d.get("raw_content_b64"),
            "command": d.get("command"),
            "exit_code": d.get("exit_code"),
            "stdout_stderr": d.get("stdout_stderr", "combined"),
            "byte_length": d.get("byte_length", 0),
        }
        source_data = _parse_source_data(source_raw)
        old = d.get("oracle_labels") or {
            "evidence_class": d.get("classification_label", "UNKNOWN"),
            "transform_eligibility": (
                "SAFE_TO_REDUCE"
                if d.get("expected_disposition") == "TRANSFORM"
                else "RAW_REQUIRED"
            ),
            "inline_required_facts": d.get("inline_required_facts", []),
            "oracle_rationale": d.get("notes", ""),
        }
        heuristic = CorpusHeuristicSuggestion(
            evidence_class=str(old.get("evidence_class", "UNKNOWN")),
            transform_eligibility=str(old.get("transform_eligibility", "UNKNOWN")),
            inline_required_facts=list(old.get("inline_required_facts") or []),
            rationale=str(old.get("oracle_rationale", "")),
            missed_opportunity_category=old.get("missed_opportunity_category"),
            method="M03_V3_MIGRATED_HEURISTIC",
        )
        old_sensitivity = str(old.get("sensitivity", "UNKNOWN"))
        return cls(
            entry_id=entry_id,
            source_data=source_data,
            oracle_labels=None,
            heuristic_suggestion=heuristic,
            sensitivity_screening=CorpusSensitivityScreening(
                result="UNKNOWN",
                method="M03_V3_MIGRATION",
                notes=(
                    "Legacy label was %s; migration does not treat it as an assessment."
                    % old_sensitivity
                ),
            ),
            tags=list(d.get("tags") or []),
        )


def _parse_source_data(raw: Any) -> CorpusSourceData:
    if not isinstance(raw, dict):
        raise ValueError("CorpusEntry missing required source_data object")
    return CorpusSourceData(
        provenance=str(raw.get("provenance", "unknown")),
        command=raw.get("command"),
        exit_code=raw.get("exit_code"),
        stdout_stderr=str(raw.get("stdout_stderr", "combined")),
        content_type_hint=raw.get("content_type_hint"),
        raw_content_b64=raw.get("raw_content_b64"),
        raw_ref_path=raw.get("raw_ref_path"),
        byte_length=int(raw.get("byte_length", 0)),
        truncated=bool(raw.get("truncated", False)),
    )


def _parse_heuristic(raw: Dict[str, Any]) -> CorpusHeuristicSuggestion:
    return CorpusHeuristicSuggestion(
        evidence_class=str(raw.get("evidence_class", "UNKNOWN")),
        transform_eligibility=str(raw.get("transform_eligibility", "UNKNOWN")),
        inline_required_facts=list(raw.get("inline_required_facts") or []),
        rationale=str(raw.get("rationale", "")),
        missed_opportunity_category=raw.get("missed_opportunity_category"),
        method=str(raw.get("method", "M03_EXTRACTOR_V1")),
    )


def _parse_oracle(raw: Dict[str, Any]) -> CorpusOracleLabels:
    return CorpusOracleLabels(
        evidence_class=str(raw.get("evidence_class", "UNKNOWN")),
        provenance=str(raw.get("provenance", "")),
        reviewer_id=str(raw.get("reviewer_id", "")),
        review_protocol=str(raw.get("review_protocol", "")),
        sensitivity=str(raw.get("sensitivity", "UNKNOWN")),
        transform_eligibility=str(raw.get("transform_eligibility", "UNKNOWN")),
        inline_required_facts=list(raw.get("inline_required_facts") or []),
        oracle_rationale=str(raw.get("oracle_rationale", "")),
        missed_opportunity_category=raw.get("missed_opportunity_category"),
    )


def _validate_label(
    entry_id: str, label: Any, label_name: str, raw: Optional[bytes]
) -> List[str]:
    errors: List[str] = []
    valid_classes = {item.value for item in EvidenceClass}
    if label.evidence_class not in valid_classes:
        errors.append(f"Entry {entry_id} has invalid {label_name} evidence_class: {label.evidence_class}")
    if label.transform_eligibility not in ("SAFE_TO_REDUCE", "RAW_REQUIRED", "UNKNOWN"):
        errors.append(
            f"Entry {entry_id} has invalid {label_name} transform_eligibility: "
            f"{label.transform_eligibility}"
        )
    bucket = label.missed_opportunity_category
    if bucket is not None and bucket not in MISSED_OPPORTUNITY_BUCKETS:
        errors.append(f"Entry {entry_id} has invalid missed_opportunity_category: {bucket}")
    if label.transform_eligibility != "SAFE_TO_REDUCE" and bucket is not None:
        errors.append(f"Entry {entry_id} has a missed-opportunity bucket without SAFE_TO_REDUCE")
    if label.transform_eligibility == "SAFE_TO_REDUCE" and label.evidence_class in {
        EvidenceClass.AUTHORITY.value,
        EvidenceClass.SECURITY.value,
        EvidenceClass.FAILURE.value,
        EvidenceClass.CANONICAL_STATE.value,
    }:
        errors.append(f"Entry {entry_id} marks protected evidence SAFE_TO_REDUCE")
    if not all(isinstance(fact, str) and fact for fact in label.inline_required_facts):
        errors.append(f"Entry {entry_id} has invalid inline_required_facts")
    elif raw is not None:
        for fact, count in Counter(label.inline_required_facts).items():
            if raw.count(fact.encode("utf-8")) < count:
                errors.append(
                    f"Entry {entry_id} requires {count} occurrence(s) of absent inline fact: {fact}"
                )
    return errors


def validate_corpus_entry(entry: CorpusEntry) -> List[str]:
    """Validate source identity, label provenance, and contradictions."""
    errors: List[str] = []
    if entry.schema_version != CORPUS_SCHEMA_VERSION:
        errors.append(f"Entry {entry.entry_id} is not schema v{CORPUS_SCHEMA_VERSION}")
    if not entry.entry_id:
        errors.append("Missing entry_id")
    if (entry.source_data.raw_content_b64 is None) == (entry.source_data.raw_ref_path is None):
        errors.append(
            f"Entry {entry.entry_id} must have exactly one of raw_content_b64 or raw_ref_path"
        )
    raw: Optional[bytes] = None
    try:
        raw = entry.source_data.get_bytes()
        if entry.source_data.byte_length != len(raw):
            errors.append(
                f"Entry {entry.entry_id} byte_length={entry.source_data.byte_length} "
                f"does not match {len(raw)} source bytes"
            )
    except (OSError, ValueError) as exc:
        errors.append(f"Entry {entry.entry_id} source bytes are unavailable or invalid: {exc}")

    screening = entry.sensitivity_screening
    if screening.result not in SENSITIVITY_SCREENING_RESULTS:
        errors.append(
            f"Entry {entry.entry_id} has invalid sensitivity screening result: {screening.result}"
        )
    if screening.result.startswith("DETECTOR_") and not screening.method:
        errors.append(f"Entry {entry.entry_id} detector screening is missing method provenance")

    if entry.heuristic_suggestion is None and entry.oracle_labels is None:
        errors.append(f"Entry {entry.entry_id} has no heuristic suggestion or oracle labels")
    if entry.heuristic_suggestion is not None:
        errors.extend(_validate_label(entry.entry_id, entry.heuristic_suggestion, "heuristic", raw))
        if not entry.heuristic_suggestion.method:
            errors.append(f"Entry {entry.entry_id} heuristic suggestion is missing method")
    if entry.oracle_labels is not None:
        oracle = entry.oracle_labels
        errors.extend(_validate_label(entry.entry_id, oracle, "oracle", raw))
        if oracle.provenance not in ORACLE_PROVENANCE_VALUES:
            errors.append(f"Entry {entry.entry_id} has invalid oracle provenance: {oracle.provenance}")
        if not oracle.reviewer_id:
            errors.append(f"Entry {entry.entry_id} oracle is missing reviewer_id")
        if not oracle.review_protocol:
            errors.append(f"Entry {entry.entry_id} oracle is missing review_protocol")
        if oracle.sensitivity not in (
            "NOT_SENSITIVE", "SENSITIVE_SECRET", "SENSITIVE_PII", "UNKNOWN"
        ):
            errors.append(f"Entry {entry.entry_id} has invalid oracle sensitivity: {oracle.sensitivity}")
        if (
            oracle.sensitivity in ("SENSITIVE_SECRET", "SENSITIVE_PII")
            and oracle.transform_eligibility == "SAFE_TO_REDUCE"
        ):
            errors.append(f"Entry {entry.entry_id} marks sensitive material SAFE_TO_REDUCE")
    return errors


def load_corpus(
    path: pathlib.Path | str, migration: Optional[str] = None
) -> List[CorpusEntry]:
    """Load a JSONL corpus; legacy demotion must be explicitly requested."""
    corpus_path = pathlib.Path(path)
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")
    entries: List[CorpusEntry] = []
    with open(corpus_path, "r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSON on line {line_num} of {corpus_path}: {exc}"
                ) from exc
            entry = CorpusEntry.from_dict(data, migration=migration)
            validation_errors = validate_corpus_entry(entry)
            if validation_errors:
                raise ValueError(
                    f"Invalid entry on line {line_num} of {corpus_path}: "
                    f"{'; '.join(validation_errors)}"
                )
            entries.append(entry)
    return entries


def _empty_buckets() -> Dict[str, Dict[str, Any]]:
    return {
        bucket: {
            "entry_count": 0,
            "raw_bytes": 0,
            "estimated_tokens": 0.0,
            "sample_entries": [],
        }
        for bucket in MISSED_OPPORTUNITY_BUCKETS
    }


def _empty_scope_metrics() -> Dict[str, Any]:
    return {
        "entry_count": 0,
        "dangerous_false_transform_eligibility": 0,
        "dangerous_entries": [],
        "safe_opportunity_missed": 0,
        "safe_match": 0,
        "unsafe_sensitivity_leak": 0,
        "label_uncertain": 0,
        "t01_unapproved_grammar_entries": 0,
        "missed_by_bucket": _empty_buckets(),
        "predicted_vs_label_matrix": {},
    }


@dataclass
class CorpusReplaySummary:
    """Replay observations; label-derived claims are partitioned by provenance."""

    total_entries: int = 0
    total_raw_bytes: int = 0
    total_visible_bytes: int = 0
    total_raw_token_estimate: float = 0.0
    total_visible_token_estimate: float = 0.0
    token_estimate_method: str = "utf8_bytes_div_4_ESTIMATE"
    t01_eligible_entries: int = 0
    t01_transformed_entries: int = 0
    t01_raw_bytes: int = 0
    t01_visible_bytes: int = 0
    t01_marker_overhead_defeated_entries: int = 0
    t01_classes_affected: Set[str] = field(default_factory=set)
    metrics_by_label_scope: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def local_byte_reduction_pct(self) -> float:
        if self.total_raw_bytes <= 0:
            return 0.0
        return round((1.0 - self.total_visible_bytes / self.total_raw_bytes) * 100.0, 2)

    @property
    def local_token_estimate_reduction_pct(self) -> float:
        if self.total_raw_token_estimate <= 0:
            return 0.0
        return round(
            (1.0 - self.total_visible_token_estimate / self.total_raw_token_estimate) * 100.0,
            2,
        )


def _label_views(entry: CorpusEntry) -> List[Tuple[str, Any]]:
    views: List[Tuple[str, Any]] = []
    if entry.oracle_labels is not None:
        views.append((f"ORACLE:{entry.oracle_labels.provenance}", entry.oracle_labels))
    if entry.heuristic_suggestion is not None:
        views.append((f"HEURISTIC:{entry.heuristic_suggestion.method}", entry.heuristic_suggestion))
    return views


def _facts_preserved(content: bytes, facts: List[str]) -> bool:
    try:
        return all(
            content.count(fact.encode("utf-8")) >= required
            for fact, required in Counter(facts).items()
        )
    except (AttributeError, UnicodeError):
        return False


def replay_corpus(
    entries: Iterable[CorpusEntry],
    mode: Mode = Mode.BUILD,
    profile_id: str = "default",
    metrics_log_path: Optional[pathlib.Path] = None,
) -> Tuple[List[CorpusEntry], CorpusReplaySummary]:
    """Replay source-only inputs and compare results within each label scope."""
    evaluated: List[CorpusEntry] = []
    summary = CorpusReplaySummary()

    for entry in entries:
        validation_errors = validate_corpus_entry(entry)
        if validation_errors:
            raise ValueError(f"Invalid entry {entry.entry_id}: {'; '.join(validation_errors)}")
        raw_bytes = entry.source_data.get_bytes()
        result = process(
            entry.to_tool_result(),
            mode=mode,
            profile_id=profile_id,
            metrics_log_path=metrics_log_path,
        )
        raw_len = len(raw_bytes)
        visible_len = len(result.content)
        raw_token_estimate = estimate_tokens(raw_bytes)
        visible_token_estimate = estimate_tokens(result.content)
        overhead_defeated = (
            result.disposition == Disposition.RAW
            and result.policy_decision
            in ("T01_NO_SAVINGS_OR_UNSAFE_FORMAT", "T01_INVALID_OR_NONREDUCING")
        )

        comparison_by_scope: Dict[str, str] = {}
        facts_by_scope: Dict[str, bool] = {}
        unapproved_by_scope: Dict[str, bool] = {}
        predicted_class = result.evidence_class.value

        for scope, label in _label_views(entry):
            scoped = summary.metrics_by_label_scope.setdefault(scope, _empty_scope_metrics())
            scoped["entry_count"] += 1
            facts_ok = _facts_preserved(result.content, label.inline_required_facts)
            facts_by_scope[scope] = facts_ok
            raw_required = (
                label.transform_eligibility == "RAW_REQUIRED"
                or label.evidence_class
                in {
                    EvidenceClass.AUTHORITY.value,
                    EvidenceClass.SECURITY.value,
                    EvidenceClass.FAILURE.value,
                    EvidenceClass.CANONICAL_STATE.value,
                }
                or getattr(label, "sensitivity", "UNKNOWN")
                in ("SENSITIVE_SECRET", "SENSITIVE_PII")
            )
            sensitivity_leak = (
                getattr(label, "sensitivity", "UNKNOWN")
                in ("SENSITIVE_SECRET", "SENSITIVE_PII")
                and result.persistence == Persistence.PERSIST
            )
            dangerous_transform = (
                result.disposition == Disposition.TRANSFORM and (raw_required or not facts_ok)
            )
            if sensitivity_leak:
                scoped["unsafe_sensitivity_leak"] += 1
                scoped["dangerous_entries"].append(entry.entry_id)
                comparison = SAFETY_UNSAFE_SENSITIVITY_LEAK
            elif dangerous_transform:
                scoped["dangerous_false_transform_eligibility"] += 1
                scoped["dangerous_entries"].append(entry.entry_id)
                comparison = SAFETY_DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY
            elif (
                label.transform_eligibility == "SAFE_TO_REDUCE"
                and result.disposition != Disposition.TRANSFORM
            ):
                scoped["safe_opportunity_missed"] += 1
                comparison = SAFETY_SAFE_OPPORTUNITY_MISSED
                bucket = label.missed_opportunity_category or "OTHER"
                if bucket not in scoped["missed_by_bucket"]:
                    bucket = "OTHER"
                bucket_metrics = scoped["missed_by_bucket"][bucket]
                bucket_metrics["entry_count"] += 1
                bucket_metrics["raw_bytes"] += raw_len
                bucket_metrics["estimated_tokens"] += raw_token_estimate
                if len(bucket_metrics["sample_entries"]) < 5:
                    bucket_metrics["sample_entries"].append(entry.entry_id)
            elif label.transform_eligibility == "UNKNOWN":
                scoped["label_uncertain"] += 1
                comparison = SAFETY_LABEL_UNCERTAIN
            else:
                scoped["safe_match"] += 1
                comparison = SAFETY_SAFE_MATCH
            comparison_by_scope[scope] = comparison

            unapproved = (
                result.disposition == Disposition.RAW
                and label.transform_eligibility == "SAFE_TO_REDUCE"
                and not overhead_defeated
            )
            unapproved_by_scope[scope] = unapproved
            if unapproved:
                scoped["t01_unapproved_grammar_entries"] += 1

            matrix = scoped["predicted_vs_label_matrix"]
            matrix.setdefault(label.evidence_class, {})
            matrix[label.evidence_class][predicted_class] = (
                matrix[label.evidence_class].get(predicted_class, 0) + 1
            )

        if result.transform_id == "T01" or result.disposition == Disposition.TRANSFORM:
            summary.t01_transformed_entries += 1
            summary.t01_raw_bytes += raw_len
            summary.t01_visible_bytes += visible_len
            summary.t01_classes_affected.add(predicted_class)
        if predicted_class in ("NOISE", "PROGRESS") and not result.truncated:
            summary.t01_eligible_entries += 1
        if overhead_defeated:
            summary.t01_marker_overhead_defeated_entries += 1

        summary.total_entries += 1
        summary.total_raw_bytes += raw_len
        summary.total_visible_bytes += visible_len
        summary.total_raw_token_estimate += raw_token_estimate
        summary.total_visible_token_estimate += visible_token_estimate

        metrics = CorpusDerivedMetrics(
            predicted_evidence_class=predicted_class,
            predicted_disposition=result.disposition.value,
            predicted_sensitivity=result.sensitivity.value,
            predicted_transform_id=result.transform_id,
            raw_bytes=raw_len,
            visible_bytes=visible_len,
            raw_token_estimate=raw_token_estimate,
            visible_token_estimate=visible_token_estimate,
            comparison_by_label_scope=comparison_by_scope,
            inline_facts_preserved_by_label_scope=facts_by_scope,
            t01_marker_overhead_defeated=overhead_defeated,
            t01_unapproved_grammar_by_label_scope=unapproved_by_scope,
            policy_reason=result.policy_decision or "",
        )
        evaluated.append(
            CorpusEntry(
                entry_id=entry.entry_id,
                source_data=entry.source_data,
                oracle_labels=entry.oracle_labels,
                heuristic_suggestion=entry.heuristic_suggestion,
                sensitivity_screening=entry.sensitivity_screening,
                derived_metrics=metrics,
                tags=list(entry.tags),
            )
        )
    return evaluated, summary
