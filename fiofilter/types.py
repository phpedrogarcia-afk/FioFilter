"""
fiofilter.types — Core type definitions for FioFilter.

All types are dataclasses or enums. No behavior lives here.
This module has zero imports from fiofilter submodules to avoid
circular dependencies.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import List, Optional


class EvidenceClass(enum.Enum):
    """
    Evidence taxonomy — 12 classes.

    These classes describe the epistemic/evidence role of a tool result.
    They are assigned by the classifier and drive disposition decisions.

    DO NOT add project-specific classes here. Use profiles for that.
    """

    NOISE = "NOISE"
    """Repetitive boilerplate, progress spinners, duplicate lines, decorative
    output with zero semantic content. Aggressive transform allowed."""

    DISCOVERY = "DISCOVERY"
    """Directory listings, broad file searches, package enumerations — large
    but low-stakes. Transform allowed in EXPLORE/BUILD."""

    PROGRESS = "PROGRESS"
    """Incremental build output, test runner dots, download progress bars —
    repetitive. Transform allowed in EXPLORE/BUILD."""

    SUCCESS_SUMMARY = "SUCCESS_SUMMARY"
    """Final pass counts, install confirmations, clean exits.
    Transform allowed in EXPLORE/BUILD."""

    DIAGNOSTIC = "DIAGNOSTIC"
    """Warnings, deprecations, stack traces (non-failure context).
    Constrained transform in EXPLORE; RAW in BUILD/PROVE."""

    FAILURE = "FAILURE"
    """Non-zero exits, test failures, crash logs, unexpected errors.
    Always RAW — all modes."""

    CANONICAL_STATE = "CANONICAL_STATE"
    """Git status/log, file hashes, version strings, authoritative registry state.
    Always RAW — all modes."""

    MACHINE_DATA = "MACHINE_DATA"
    """JSON/YAML/CSV structured outputs consumed programmatically.
    Lossless-only transforms (I8). RAW in PROVE."""

    AUTHORITY = "AUTHORITY"
    """Ownership records, permission grants, signing outputs, audit logs.
    Always RAW — all modes (I7)."""

    SECURITY = "SECURITY"
    """Key material, certificates, access tokens, auth outputs, vulnerability findings.
    Always RAW — all modes (I7)."""

    BENCHMARK = "BENCHMARK"
    """Timing data, performance measurements, regression baselines.
    Always RAW — all modes."""

    UNKNOWN = "UNKNOWN"
    """Unclassified or ambiguous. Always RAW (I5)."""


class Mode(enum.Enum):
    """
    Operational mode — influences policy, does not grant authority.

    Modes cannot override invariants I1–I16.
    Mode escalation is one-directional per result: EXPLORE → BUILD → PROVE.
    """

    EXPLORE = "EXPLORE"
    """Discovery, repetitive logs, broad searches, mechanical progress.
    Goal: aggressive context reduction."""

    BUILD = "BUILD"
    """Default development mode.
    Goal: remove known noise while preserving actionable engineering evidence."""

    PROVE = "PROVE"
    """Authority, security, unexpected failures, canonical state, benchmarks.
    Goal: evidence fidelity dominates compression."""


class Disposition(enum.Enum):
    """
    Decision outcome — what the engine decided to do with the tool result.
    """

    RAW = "RAW"
    """Return the raw content unchanged. RAW store entry still written."""

    TRANSFORM = "TRANSFORM"
    """Apply a deterministic transform. RAW store entry written first."""

    ESCALATE_TO_RAW = "ESCALATE_TO_RAW"
    """Transform was attempted or selected but a guard forced RAW return.
    Logged separately for audit purposes."""

    # Future dispositions (defined here for type safety; not routed in V0):
    # DELTA = "DELTA"
    # INDEX = "INDEX"


@dataclass(frozen=True)
class RawRef:
    """
    Reference to an entry in the immutable RAW store.

    Fields are immutable (frozen=True). Once created, a RawRef cannot change.
    """

    sha256: str
    """SHA-256 hex digest of the raw content bytes."""

    store_path: str
    """Absolute path to the content file in the RAW store."""


@dataclass
class ToolResult:
    """
    Input to the FioFilter decision engine.

    Represents a single tool result from a coding agent.
    """

    content: bytes
    """Raw content bytes — the tool output exactly as received."""

    source: str = "unknown"
    """Source identifier: 'shell', 'file_read', 'test_harness', etc."""

    command: Optional[str] = None
    """The command that produced this output, if known."""

    exit_code: Optional[int] = None
    """Exit code of the command, if applicable."""

    content_type_hint: Optional[str] = None
    """Hint about content type: 'json', 'text', 'binary'. Used by classifier."""

    session_id: Optional[str] = None
    """Session identifier for mission-level metrics."""


@dataclass
class FilterMetrics:
    """
    Per-result economics metrics (I14, I15).

    These metrics are distinct units and must never be conflated.
    Local byte reduction ≠ token reduction ≠ model turn reduction.
    """

    raw_bytes: int
    """Byte length of the raw content."""

    visible_bytes: int
    """Byte length of the content returned to the model."""

    raw_token_estimate: float
    """Estimated tokens in raw content (approximation: chars / 4).
    NOT a billing figure. Never conflate with whole-mission savings (I15)."""

    visible_token_estimate: float
    """Estimated tokens in visible output (approximation: chars / 4)."""

    transform_duration_ms: float
    """Wall-clock time for the transform step, in milliseconds."""

    decision: Disposition
    """The final disposition."""

    evidence_class: EvidenceClass
    """The assigned evidence class."""

    mode: Mode
    """The operational mode in effect."""

    corrective_retrieval_required: Optional[bool] = None
    """Whether a corrective retrieval was required. None = unknown."""

    raw_recovery_count: int = 0
    """Number of times this raw entry was retrieved (future tracking)."""


@dataclass
class FilterResult:
    """
    Output of the FioFilter decision engine.

    Always contains:
    - content: the visible output (may be identical to raw for RAW disposition)
    - raw_ref: reference to the RAW store entry (always written)
    - metrics: per-result economics

    For TRANSFORM disposition, also contains:
    - transform_id: which transform was applied
    - policy_decision: the disposition selected by the engine

    Invariant I2: all five linkage fields must be populated for TRANSFORM.
    """

    content: bytes
    """Visible content returned to the model."""

    disposition: Disposition
    """The decision outcome."""

    raw_ref: RawRef
    """Reference to the immutable RAW store entry. Always present."""

    raw_sha256: str
    """SHA-256 of the original raw content. Always present."""

    evidence_class: EvidenceClass
    """Evidence class assigned by the classifier."""

    mode: Mode
    """Mode in effect at decision time."""

    metrics: FilterMetrics
    """Per-result economics metrics."""

    transform_id: Optional[str] = None
    """Identifier of the transform applied. None for RAW disposition."""

    policy_decision: Optional[str] = None
    """Human-readable policy decision rationale."""

    inline_required_facts: List[str] = field(default_factory=list)
    """Facts that were required to be present inline. Used for auditing."""
