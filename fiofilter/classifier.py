"""
fiofilter.classifier — Deterministic evidence classifier.

No LLM. No external calls. All classification is rule-based (I11).

Classification pipeline:
  1. Exit-code check (non-zero → FAILURE candidate)
  2. Binary content check → MACHINE_DATA
  3. JSON parseability → MACHINE_DATA
  4. Security/authority patterns → SECURITY or AUTHORITY
  5. Git/hash/canonical patterns → CANONICAL_STATE
  6. Benchmark patterns → BENCHMARK
  7. Repetitive/duplicate line detection → NOISE or PROGRESS
  8. Directory listing patterns → DISCOVERY
  9. Test output patterns → SUCCESS_SUMMARY or FAILURE
 10. Default → UNKNOWN

Confidence below MIN_CONFIDENCE → UNKNOWN (I5).

Returns ClassifyResult with:
  evidence_class: EvidenceClass
  confidence: float (0.0–1.0)
  inline_required_facts: List[str]  — facts that must appear inline (I4)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from fiofilter.types import EvidenceClass

# Minimum confidence required to use a non-UNKNOWN classification.
# Below this threshold, the classifier defaults to UNKNOWN → RAW (I5).
MIN_CONFIDENCE: float = 0.6

# Maximum bytes to inspect for classification (avoids O(n) on huge outputs).
# Content is still stored fully in RAW; only classification is bounded.
INSPECT_LIMIT: int = 16_384


@dataclass
class ClassifyResult:
    """Output of the classifier."""

    evidence_class: EvidenceClass
    """Assigned evidence class."""

    confidence: float
    """Classifier confidence (0.0–1.0). Below MIN_CONFIDENCE → UNKNOWN."""

    inline_required_facts: List[str] = field(default_factory=list)
    """Facts that must appear inline in the visible output (I4).
    The engine checks these after any transform."""

    classifier_notes: str = ""
    """Human-readable notes for audit/debugging. Never shown to the model."""


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Patterns suggesting SECURITY content
_SECURITY_PATTERNS = [
    re.compile(r"\bBEGIN\s+(RSA|EC|DSA|PRIVATE|PUBLIC|CERTIFICATE)\b", re.IGNORECASE),
    re.compile(r"\bAWS_SECRET_ACCESS_KEY\b"),
    re.compile(r"\bGH[PO]_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),        # OpenAI-style keys
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b"),
]

# Patterns suggesting AUTHORITY content
_AUTHORITY_PATTERNS = [
    re.compile(r"\bIAM\b.*\bpolicy\b", re.IGNORECASE),
    re.compile(r"\bPermission(s)?\s+(denied|granted)\b", re.IGNORECASE),
    re.compile(r"\bsigned\s+by\b", re.IGNORECASE),
    re.compile(r"\baudit\s+log\b", re.IGNORECASE),
]

# Patterns suggesting CANONICAL_STATE
_CANONICAL_PATTERNS = [
    re.compile(r"^commit [0-9a-f]{7,40}", re.MULTILINE),
    re.compile(r"^On branch \w+", re.MULTILINE),
    re.compile(r"\bSHA-?256\s*[:=]\s*[0-9a-f]{64}\b", re.IGNORECASE),
    re.compile(r"\bSHA-?1\s*[:=]\s*[0-9a-f]{40}\b", re.IGNORECASE),
    re.compile(r"^HEAD detached", re.MULTILINE),
    re.compile(r"^nothing to commit", re.MULTILINE),
]

# Patterns suggesting BENCHMARK
_BENCHMARK_PATTERNS = [
    re.compile(r"\bbenchmark\b.*\bns/op\b", re.IGNORECASE),
    re.compile(r"\b\d+\.\d+\s*ms\b.*\b(mean|median|p50|p95|p99)\b", re.IGNORECASE),
    re.compile(r"Benchmark\w+\s+-\s+\d+", re.MULTILINE),
]

# Patterns suggesting FAILURE
_FAILURE_PATTERNS = [
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bFAIL\b"),
    re.compile(r"\bERROR\b.*\bTraceback\b", re.DOTALL),
    re.compile(r"^Traceback \(most recent call last\)", re.MULTILINE),
    re.compile(r"\bAssertionError\b"),
    re.compile(r"\bException\b.*\bError\b"),
    re.compile(r"\bfatal error\b", re.IGNORECASE),
]

# Patterns suggesting SUCCESS_SUMMARY
_SUCCESS_PATTERNS = [
    re.compile(r"\b\d+\s+passed\b", re.IGNORECASE),
    re.compile(r"\b(all\s+tests?\s+pass(ed)?)\b", re.IGNORECASE),
    re.compile(r"\bOK\s*\(\s*\d+\s+test", re.IGNORECASE),
    re.compile(r"^\d+ tests?, 0 failures?$", re.MULTILINE | re.IGNORECASE),
]

# Patterns suggesting DISCOVERY (directory/file listings)
_DISCOVERY_PATTERNS = [
    re.compile(r"^(total\s+\d+|drwx|lrwx|-rw)", re.MULTILINE),
    re.compile(r"^\s*(├──|└──|│)", re.MULTILINE),  # tree output
    re.compile(r"\bDirectory of\b", re.IGNORECASE),
]

# Progress bar / spinner patterns → PROGRESS
_PROGRESS_PATTERNS = [
    re.compile(r"\[#+\s*\]"),           # [######   ]
    re.compile(r"\d+%\|"),              # tqdm-style
    re.compile(r"downloading.*\d+%", re.IGNORECASE),
    re.compile(r"\.\.\.\s*$", re.MULTILINE),
]


def _is_binary(data: bytes) -> bool:
    """Heuristic: content with null bytes is likely binary.
    High-byte UTF-8 sequences (box-drawing chars, emoji, etc.) are NOT binary.
    We only flag content that cannot be decoded as UTF-8 at all, or contains
    a significant fraction of null bytes.
    """
    # Null bytes are the clearest binary indicator
    if b"\x00" in data[:1024]:
        return True
    # Try UTF-8 decode — if it succeeds, it's text (not binary)
    try:
        data[:INSPECT_LIMIT].decode("utf-8")
        return False
    except UnicodeDecodeError:
        pass
    # Fallback: high ratio of control chars (excluding common text controls)
    sample = data[:512]
    if not sample:
        return False
    non_text = sum(1 for b in sample if b < 32 and b not in (9, 10, 13))
    return non_text / len(sample) > 0.20


def _has_json(text: str) -> bool:
    """True if text is valid JSON (object or array at root)."""
    stripped = text.strip()
    if not (stripped.startswith(("{", "["))):
        return False
    try:
        json.loads(stripped)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _duplicate_line_ratio(text: str) -> float:
    """Fraction of lines that are exact duplicates of a preceding line."""
    lines = text.splitlines()
    if len(lines) < 4:
        return 0.0
    seen: dict = {}
    dups = 0
    for line in lines:
        if line in seen:
            dups += 1
        seen[line] = True
    return dups / len(lines)


def classify(tool_result_content: bytes, exit_code: Optional[int] = None) -> ClassifyResult:
    """
    Classify a tool result's content deterministically.

    Args:
        tool_result_content: Raw bytes of the tool result.
        exit_code: Exit code if known. Non-zero is a FAILURE signal.

    Returns:
        ClassifyResult with evidence_class, confidence, inline_required_facts.
    """
    # Immediate failure signal from exit code (I6)
    if exit_code is not None and exit_code != 0:
        return ClassifyResult(
            evidence_class=EvidenceClass.FAILURE,
            confidence=0.95,
            classifier_notes=f"Non-zero exit code: {exit_code}",
        )

    # Empty content
    if not tool_result_content:
        return ClassifyResult(
            evidence_class=EvidenceClass.UNKNOWN,
            confidence=1.0,
            classifier_notes="Empty content",
        )

    # Binary content → MACHINE_DATA (may not be text-transformable)
    if _is_binary(tool_result_content):
        return ClassifyResult(
            evidence_class=EvidenceClass.MACHINE_DATA,
            confidence=0.9,
            classifier_notes="Binary content detected",
        )

    # Decode for text analysis (best-effort)
    try:
        text = tool_result_content[:INSPECT_LIMIT].decode("utf-8", errors="replace")
    except Exception:
        return ClassifyResult(
            evidence_class=EvidenceClass.UNKNOWN,
            confidence=1.0,
            classifier_notes="Decode failed",
        )

    # Security patterns (highest priority — I7)
    for pattern in _SECURITY_PATTERNS:
        if pattern.search(text):
            return ClassifyResult(
                evidence_class=EvidenceClass.SECURITY,
                confidence=0.95,
                inline_required_facts=[],
                classifier_notes=f"Security pattern: {pattern.pattern[:40]}",
            )

    # Authority patterns (high priority — I7)
    for pattern in _AUTHORITY_PATTERNS:
        if pattern.search(text):
            return ClassifyResult(
                evidence_class=EvidenceClass.AUTHORITY,
                confidence=0.85,
                inline_required_facts=[],
                classifier_notes=f"Authority pattern: {pattern.pattern[:40]}",
            )

    # Canonical state patterns
    canonical_hits = sum(1 for p in _CANONICAL_PATTERNS if p.search(text))
    if canonical_hits >= 1:
        # Extract canonical facts for inline preservation (I4)
        facts = []
        for m in re.finditer(r"^commit ([0-9a-f]{7,40})", text, re.MULTILINE):
            facts.append(m.group(0))
        for m in re.finditer(r"^On branch (\S+)", text, re.MULTILINE):
            facts.append(m.group(0))
        return ClassifyResult(
            evidence_class=EvidenceClass.CANONICAL_STATE,
            confidence=min(0.75 + 0.05 * canonical_hits, 0.95),
            inline_required_facts=facts[:10],  # cap at 10
            classifier_notes=f"Canonical hits: {canonical_hits}",
        )

    # JSON → MACHINE_DATA (lossless-only transforms permitted)
    if _has_json(text):
        return ClassifyResult(
            evidence_class=EvidenceClass.MACHINE_DATA,
            confidence=0.9,
            classifier_notes="JSON content",
        )

    # Benchmark patterns
    for pattern in _BENCHMARK_PATTERNS:
        if pattern.search(text):
            return ClassifyResult(
                evidence_class=EvidenceClass.BENCHMARK,
                confidence=0.85,
                classifier_notes=f"Benchmark pattern: {pattern.pattern[:40]}",
            )

    # Failure patterns (text-level, exit_code already handled above)
    failure_hits = sum(1 for p in _FAILURE_PATTERNS if p.search(text))
    if failure_hits >= 1:
        return ClassifyResult(
            evidence_class=EvidenceClass.FAILURE,
            confidence=min(0.7 + 0.08 * failure_hits, 0.95),
            classifier_notes=f"Failure pattern hits: {failure_hits}",
        )

    # Success summary (all PASS, no FAIL)
    success_hits = sum(1 for p in _SUCCESS_PATTERNS if p.search(text))
    if success_hits >= 1 and failure_hits == 0:
        return ClassifyResult(
            evidence_class=EvidenceClass.SUCCESS_SUMMARY,
            confidence=min(0.7 + 0.08 * success_hits, 0.92),
            classifier_notes=f"Success pattern hits: {success_hits}",
        )

    # Discovery (directory listings, tree output)
    discovery_hits = sum(1 for p in _DISCOVERY_PATTERNS if p.search(text))
    if discovery_hits >= 1:
        return ClassifyResult(
            evidence_class=EvidenceClass.DISCOVERY,
            confidence=min(0.7 + 0.08 * discovery_hits, 0.90),
            classifier_notes=f"Discovery pattern hits: {discovery_hits}",
        )

    # Progress bars / spinners
    progress_hits = sum(1 for p in _PROGRESS_PATTERNS if p.search(text))
    if progress_hits >= 1:
        return ClassifyResult(
            evidence_class=EvidenceClass.PROGRESS,
            confidence=min(0.65 + 0.08 * progress_hits, 0.88),
            classifier_notes=f"Progress pattern hits: {progress_hits}",
        )

    # High duplicate-line ratio → NOISE
    dup_ratio = _duplicate_line_ratio(text)
    if dup_ratio >= 0.5:
        return ClassifyResult(
            evidence_class=EvidenceClass.NOISE,
            confidence=min(0.6 + dup_ratio * 0.3, 0.90),
            classifier_notes=f"Duplicate line ratio: {dup_ratio:.2f}",
        )

    # Default: UNKNOWN → RAW (I5)
    return ClassifyResult(
        evidence_class=EvidenceClass.UNKNOWN,
        confidence=1.0,
        classifier_notes="No rule matched; defaulting to UNKNOWN",
    )
