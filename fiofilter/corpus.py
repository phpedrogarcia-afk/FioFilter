"""
fiofilter.corpus — Empirical workload evaluation harness and schema.

Separates:
  1. SOURCE DATA (provenance, command, exit_code, stream, raw bytes/reference)
  2. HUMAN/ORACLE LABELS (independent evidence class, sensitivity, eligibility, inline facts)
  3. DERIVED METRICS (predicted class, disposition, byte/token reduction, safety outcome)

Guarantees:
  - Caller-specified local paths outside the repository.
  - No raw historical tool results or secrets stored in repo code.
  - Deterministic evaluation and explicit safety gates.
"""

from __future__ import annotations

import base64
import json
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fiofilter.engine import process
from fiofilter.metrics import estimate_tokens
from fiofilter.types import Disposition, EvidenceClass, Mode, Persistence, Sensitivity, ToolResult


# Candidate buckets for missed safe reduction opportunities
MISSED_OPPORTUNITY_BUCKETS = (
    "REPETITIVE_PROGRESS",
    "DIRECTORY_OR_PATH_REDUNDANCY",
    "KNOWN_SUCCESS_RECORDS",
    "KNOWN_BOILERPLATE",
    "DUPLICATED_HEADERS",
    "STRUCTURED_BUT_CONSUMER_SPECIFIC",
    "OTHER",
)

# Safety classifications for audit
SAFETY_SAFE_MATCH = "SAFE_MATCH"
SAFETY_SAFE_OPPORTUNITY_MISSED = "SAFE_OPPORTUNITY_MISSED"
SAFETY_DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY = "DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY"
SAFETY_UNSAFE_SENSITIVITY_LEAK = "UNSAFE_SENSITIVITY_LEAK"


@dataclass
class CorpusSourceData:
    """Raw execution evidence and execution metadata."""

    provenance: str
    """Source session, call_id, or artifact provenance."""

    command: Optional[str] = None
    """Command executed, if known."""

    exit_code: Optional[int] = None
    """Exit code, if known."""

    stdout_stderr: str = "combined"
    """'stdout', 'stderr', 'combined', or 'file'."""

    content_type_hint: Optional[str] = None
    """Hint: 'json', 'text', 'binary'."""

    raw_content_b64: Optional[str] = None
    """Base64-encoded raw bytes (for synthetic fixtures or small samples)."""

    raw_ref_path: Optional[str] = None
    """Local absolute path to external raw bytes on disk (outside repository)."""

    byte_length: int = 0
    """Expected length in bytes."""

    truncated: bool = False
    """Whether tool output was already truncated upstream."""

    def get_bytes(self) -> bytes:
        """Resolve raw bytes from inline base64 or external local file."""
        if self.raw_content_b64 is not None:
            data = base64.b64decode(self.raw_content_b64.encode("ascii"))
            return data
        if self.raw_ref_path is not None:
            p = pathlib.Path(self.raw_ref_path)
            if not p.exists():
                raise FileNotFoundError(f"Corpus raw reference path not found: {self.raw_ref_path}")
            return p.read_bytes()
        raise ValueError("CorpusSourceData has neither raw_content_b64 nor raw_ref_path")


@dataclass
class CorpusOracleLabels:
    """Independent ground-truth labels established before or outside FioFilter."""

    evidence_class: str
    """Oracle evidence class (e.g. 'CANONICAL_STATE', 'NOISE', 'FAILURE')."""

    sensitivity: str = "UNKNOWN"
    """Oracle sensitivity: 'NOT_SENSITIVE', 'SENSITIVE_SECRET', 'SENSITIVE_PII', 'UNKNOWN'."""

    transform_eligibility: str = "RAW_REQUIRED"
    """'SAFE_TO_REDUCE', 'RAW_REQUIRED', or 'UNKNOWN'."""

    inline_required_facts: List[str] = field(default_factory=list)
    """Critical facts that must remain visible in transformed output."""

    oracle_rationale: str = ""
    """Human/reviewer rationale for the oracle labels."""

    missed_opportunity_category: Optional[str] = None
    """If SAFE_TO_REDUCE, candidate bucket from MISSED_OPPORTUNITY_BUCKETS."""


@dataclass
class CorpusDerivedMetrics:
    """Metrics and findings computed by replaying FioFilter against the entry."""

    predicted_evidence_class: Optional[str] = None
    predicted_disposition: Optional[str] = None
    predicted_sensitivity: Optional[str] = None
    predicted_transform_id: Optional[str] = None
    raw_bytes: int = 0
    visible_bytes: int = 0
    raw_token_estimate: float = 0.0
    visible_token_estimate: float = 0.0
    inline_facts_preserved: bool = True
    safety_classification: str = SAFETY_SAFE_MATCH
    t01_marker_overhead_defeated: bool = False
    t01_unapproved_grammar_repetition: bool = False
    policy_reason: str = ""
    notes: str = ""


@dataclass
class CorpusEntry:
    """A single evaluated workload item."""

    entry_id: str
    source_data: CorpusSourceData
    oracle_labels: CorpusOracleLabels
    derived_metrics: Optional[CorpusDerivedMetrics] = None
    tags: List[str] = field(default_factory=list)

    def to_tool_result(self) -> ToolResult:
        """Convert entry source data into a FioFilter ToolResult."""
        content = self.source_data.get_bytes()
        sens = Sensitivity.UNKNOWN
        if self.oracle_labels.sensitivity in ("SENSITIVE_SECRET", "SENSITIVE_PII", "SENSITIVE"):
            sens = Sensitivity.SENSITIVE
        elif self.oracle_labels.sensitivity in ("NOT_SENSITIVE", "NON_SENSITIVE"):
            sens = Sensitivity.NON_SENSITIVE

        return ToolResult(
            content=content,
            source=self.source_data.provenance,
            command=self.source_data.command,
            exit_code=self.source_data.exit_code,
            stream=self.source_data.stdout_stderr,
            content_type_hint=self.source_data.content_type_hint,
            truncated=self.source_data.truncated,
            inline_required_facts=list(self.oracle_labels.inline_required_facts),
            sensitivity=sens,
            persistence=Persistence.EPHEMERAL,
        )

    def to_dict(self, include_raw: bool = True) -> Dict[str, Any]:
        """Serialize to dictionary. Set include_raw=False for clean reports."""
        d: Dict[str, Any] = {
            "entry_id": self.entry_id,
            "source_data": {
                "provenance": self.source_data.provenance,
                "command": self.source_data.command,
                "exit_code": self.source_data.exit_code,
                "stdout_stderr": self.source_data.stdout_stderr,
                "content_type_hint": self.source_data.content_type_hint,
                "byte_length": self.source_data.byte_length,
                "truncated": self.source_data.truncated,
            },
            "oracle_labels": {
                "evidence_class": self.oracle_labels.evidence_class,
                "sensitivity": self.oracle_labels.sensitivity,
                "transform_eligibility": self.oracle_labels.transform_eligibility,
                "inline_required_facts": list(self.oracle_labels.inline_required_facts),
                "oracle_rationale": self.oracle_labels.oracle_rationale,
                "missed_opportunity_category": self.oracle_labels.missed_opportunity_category,
            },
            "tags": list(self.tags),
        }
        if include_raw:
            d["source_data"]["raw_content_b64"] = self.source_data.raw_content_b64
            d["source_data"]["raw_ref_path"] = self.source_data.raw_ref_path

        if self.derived_metrics is not None:
            d["derived_metrics"] = asdict(self.derived_metrics)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CorpusEntry:
        """Parse entry from dictionary with backward-compatible schema checking."""
        if not isinstance(d, dict):
            raise TypeError("CorpusEntry dictionary must be a dict")
        entry_id = str(d.get("entry_id") or d.get("corpus_entry_id") or "")
        if not entry_id:
            raise ValueError("CorpusEntry missing required 'entry_id'")

        # Parse source data
        src_raw = d.get("source_data", {})
        if not src_raw:
            # legacy M01 flat schema fallback
            src_raw = {
                "provenance": d.get("source", "unknown"),
                "raw_content_b64": d.get("raw_content_b64"),
                "command": d.get("command"),
                "exit_code": d.get("exit_code"),
                "stdout_stderr": d.get("stdout_stderr", "combined"),
            }

        source_data = CorpusSourceData(
            provenance=str(src_raw.get("provenance", "unknown")),
            command=src_raw.get("command"),
            exit_code=src_raw.get("exit_code"),
            stdout_stderr=str(src_raw.get("stdout_stderr", "combined")),
            content_type_hint=src_raw.get("content_type_hint"),
            raw_content_b64=src_raw.get("raw_content_b64"),
            raw_ref_path=src_raw.get("raw_ref_path"),
            byte_length=int(src_raw.get("byte_length", 0)),
            truncated=bool(src_raw.get("truncated", False)),
        )

        # Parse oracle labels
        orc_raw = d.get("oracle_labels", {})
        if not orc_raw:
            orc_raw = {
                "evidence_class": d.get("classification_label", "UNKNOWN"),
                "sensitivity": d.get("sensitivity", "UNKNOWN"),
                "transform_eligibility": (
                    "SAFE_TO_REDUCE" if d.get("expected_disposition") == "TRANSFORM" else "RAW_REQUIRED"
                ),
                "inline_required_facts": d.get("inline_required_facts", []),
                "oracle_rationale": d.get("notes", ""),
            }

        oracle_labels = CorpusOracleLabels(
            evidence_class=str(orc_raw.get("evidence_class", "UNKNOWN")),
            sensitivity=str(orc_raw.get("sensitivity", "UNKNOWN")),
            transform_eligibility=str(orc_raw.get("transform_eligibility", "RAW_REQUIRED")),
            inline_required_facts=list(orc_raw.get("inline_required_facts") or []),
            oracle_rationale=str(orc_raw.get("oracle_rationale", "")),
            missed_opportunity_category=orc_raw.get("missed_opportunity_category"),
        )

        derived_metrics = None
        if "derived_metrics" in d and d["derived_metrics"] is not None:
            derived_metrics = CorpusDerivedMetrics(**d["derived_metrics"])

        tags = list(d.get("tags") or [])

        return cls(
            entry_id=entry_id,
            source_data=source_data,
            oracle_labels=oracle_labels,
            derived_metrics=derived_metrics,
            tags=tags,
        )


def validate_corpus_entry(entry: CorpusEntry) -> List[str]:
    """Validate a corpus entry against invariants and schema rules."""
    errors: List[str] = []
    if not entry.entry_id:
        errors.append("Missing entry_id")

    # Source data validation
    if not entry.source_data.raw_content_b64 and not entry.source_data.raw_ref_path:
        errors.append(f"Entry {entry.entry_id} has neither raw_content_b64 nor raw_ref_path")

    # Oracle validation
    valid_classes = {c.value for c in EvidenceClass}
    if entry.oracle_labels.evidence_class not in valid_classes:
        errors.append(
            f"Entry {entry.entry_id} has invalid oracle evidence_class: {entry.oracle_labels.evidence_class}"
        )

    if entry.oracle_labels.transform_eligibility not in ("SAFE_TO_REDUCE", "RAW_REQUIRED", "UNKNOWN"):
        errors.append(
            f"Entry {entry.entry_id} has invalid transform_eligibility: {entry.oracle_labels.transform_eligibility}"
        )

    if entry.oracle_labels.missed_opportunity_category is not None:
        if entry.oracle_labels.missed_opportunity_category not in MISSED_OPPORTUNITY_BUCKETS:
            errors.append(
                f"Entry {entry.entry_id} has invalid missed_opportunity_category: {entry.oracle_labels.missed_opportunity_category}"
            )

    return errors


def load_corpus(path: pathlib.Path | str) -> List[CorpusEntry]:
    """Load and validate all corpus entries from a JSONL file."""
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Corpus file not found: {p}")

    entries: List[CorpusEntry] = []
    with open(p, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSON on line {line_num} of {p}: {exc}") from exc

            entry = CorpusEntry.from_dict(data)
            errors = validate_corpus_entry(entry)
            if errors:
                raise ValueError(f"Invalid entry on line {line_num} of {p}: {'; '.join(errors)}")
            entries.append(entry)

    return entries


@dataclass
class CorpusReplaySummary:
    """Comprehensive summary of a corpus replay run."""

    total_entries: int = 0
    total_raw_bytes: int = 0
    total_visible_bytes: int = 0
    total_raw_tokens: float = 0.0
    total_visible_tokens: float = 0.0

    # Safety metrics
    dangerous_false_transform_eligibility: int = 0
    dangerous_entries: List[str] = field(default_factory=list)
    safe_opportunity_missed: int = 0
    safe_match: int = 0
    unsafe_sensitivity_leak: int = 0

    # T01 performance
    t01_eligible_entries: int = 0
    t01_transformed_entries: int = 0
    t01_raw_bytes: int = 0
    t01_visible_bytes: int = 0
    t01_marker_overhead_defeated_entries: int = 0
    t01_unapproved_grammar_entries: int = 0
    t01_classes_affected: Set[str] = field(default_factory=set)

    # Missed opportunity breakdowns
    missed_by_bucket: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Classifier confusion matrix against oracle
    predicted_vs_oracle_matrix: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def local_byte_reduction_pct(self) -> float:
        if self.total_raw_bytes <= 0:
            return 0.0
        return round((1.0 - self.total_visible_bytes / self.total_raw_bytes) * 100.0, 2)

    @property
    def local_token_reduction_pct(self) -> float:
        if self.total_raw_tokens <= 0:
            return 0.0
        return round((1.0 - self.total_visible_tokens / self.total_raw_tokens) * 100.0, 2)


def replay_corpus(
    entries: Iterable[CorpusEntry],
    mode: Mode = Mode.BUILD,
    profile_id: str = "default",
    metrics_log_path: Optional[pathlib.Path] = None,
) -> Tuple[List[CorpusEntry], CorpusReplaySummary]:
    """
    Replay FioFilter deterministically against all entries.

    Returns:
        (evaluated_entries, summary)
    """
    evaluated: List[CorpusEntry] = []
    summary = CorpusReplaySummary()

    # Initialize missed opportunity buckets
    for bucket in MISSED_OPPORTUNITY_BUCKETS:
        summary.missed_by_bucket[bucket] = {
            "entry_count": 0,
            "raw_bytes": 0,
            "estimated_tokens": 0.0,
            "sample_entries": [],
        }

    for entry in entries:
        raw_bytes = entry.source_data.get_bytes()
        tr = entry.to_tool_result()
        res = process(tr, mode=mode, profile_id=profile_id, metrics_log_path=metrics_log_path)

        raw_len = len(raw_bytes)
        vis_len = len(res.content)
        raw_tokens = estimate_tokens(raw_bytes)
        vis_tokens = estimate_tokens(res.content)

        # Check inline fact preservation
        facts_ok = True
        for fact in entry.oracle_labels.inline_required_facts:
            if fact.encode("utf-8") not in res.content:
                facts_ok = False
                break

        # Check T01 marker overhead defeat or repetition with unapproved grammar
        overhead_defeated = False
        unapproved_grammar = False
        if res.disposition == Disposition.RAW:
            if res.policy_decision in ("T01_NO_SAVINGS_OR_UNSAFE_FORMAT", "T01_INVALID_OR_NONREDUCING"):
                overhead_defeated = True
            elif entry.oracle_labels.transform_eligibility == "SAFE_TO_REDUCE":
                unapproved_grammar = True

        # Safety evaluation
        safety = SAFETY_SAFE_MATCH
        is_oracle_raw_required = (
            entry.oracle_labels.transform_eligibility == "RAW_REQUIRED"
            or entry.oracle_labels.evidence_class in (
                EvidenceClass.AUTHORITY.value,
                EvidenceClass.SECURITY.value,
                EvidenceClass.FAILURE.value,
                EvidenceClass.CANONICAL_STATE.value,
            )
            or entry.oracle_labels.sensitivity in ("SENSITIVE_SECRET", "SENSITIVE_PII")
        )

        if is_oracle_raw_required and res.disposition == Disposition.TRANSFORM:
            safety = SAFETY_DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY
            summary.dangerous_false_transform_eligibility += 1
            summary.dangerous_entries.append(entry.entry_id)
        elif entry.oracle_labels.sensitivity in ("SENSITIVE_SECRET", "SENSITIVE_PII") and res.persistence == Persistence.PERSIST:
            safety = SAFETY_UNSAFE_SENSITIVITY_LEAK
            summary.unsafe_sensitivity_leak += 1
            summary.dangerous_entries.append(entry.entry_id)
        elif entry.oracle_labels.transform_eligibility == "SAFE_TO_REDUCE" and res.disposition != Disposition.TRANSFORM:
            safety = SAFETY_SAFE_OPPORTUNITY_MISSED
            summary.safe_opportunity_missed += 1
            # Classify missed bucket
            b = entry.oracle_labels.missed_opportunity_category or "OTHER"
            if b not in summary.missed_by_bucket:
                b = "OTHER"
            summary.missed_by_bucket[b]["entry_count"] += 1
            summary.missed_by_bucket[b]["raw_bytes"] += raw_len
            summary.missed_by_bucket[b]["estimated_tokens"] += raw_tokens
            if len(summary.missed_by_bucket[b]["sample_entries"]) < 5:
                summary.missed_by_bucket[b]["sample_entries"].append(entry.entry_id)
        else:
            summary.safe_match += 1

        # T01 metrics
        if res.transform_id == "T01" or res.disposition == Disposition.TRANSFORM:
            summary.t01_transformed_entries += 1
            summary.t01_raw_bytes += raw_len
            summary.t01_visible_bytes += vis_len
            summary.t01_classes_affected.add(res.evidence_class.value)

        if res.evidence_class.value in ("NOISE", "PROGRESS") and not res.truncated:
            summary.t01_eligible_entries += 1

        if overhead_defeated:
            summary.t01_marker_overhead_defeated_entries += 1
        if unapproved_grammar:
            summary.t01_unapproved_grammar_entries += 1

        # Aggregates
        summary.total_entries += 1
        summary.total_raw_bytes += raw_len
        summary.total_visible_bytes += vis_len
        summary.total_raw_tokens += raw_tokens
        summary.total_visible_tokens += vis_tokens

        # Confusion matrix
        p_class = res.evidence_class.value
        o_class = entry.oracle_labels.evidence_class
        if o_class not in summary.predicted_vs_oracle_matrix:
            summary.predicted_vs_oracle_matrix[o_class] = {}
        summary.predicted_vs_oracle_matrix[o_class][p_class] = (
            summary.predicted_vs_oracle_matrix[o_class].get(p_class, 0) + 1
        )

        metrics = CorpusDerivedMetrics(
            predicted_evidence_class=p_class,
            predicted_disposition=res.disposition.value,
            predicted_sensitivity=res.sensitivity.value,
            predicted_transform_id=res.transform_id,
            raw_bytes=raw_len,
            visible_bytes=vis_len,
            raw_token_estimate=raw_tokens,
            visible_token_estimate=vis_tokens,
            inline_facts_preserved=facts_ok,
            safety_classification=safety,
            t01_marker_overhead_defeated=overhead_defeated,
            t01_unapproved_grammar_repetition=unapproved_grammar,
            policy_reason=res.policy_decision,
        )

        eval_entry = CorpusEntry(
            entry_id=entry.entry_id,
            source_data=entry.source_data,
            oracle_labels=entry.oracle_labels,
            derived_metrics=metrics,
            tags=list(entry.tags),
        )
        evaluated.append(eval_entry)

    return evaluated, summary
