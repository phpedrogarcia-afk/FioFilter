"""Separate per-result byte estimates and externally supplied mission observations.

Logging is opt-in and content-free through the engine; None means unmeasured.
The UTF-8 bytes/4 heuristic is an ESTIMATE, never actual/billing token truth.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Optional

from fiofilter.types import Disposition, EvidenceClass, FilterMetrics, Mode

# Approximation: average chars per token (rough heuristic, not exact).
# Never claim this equals a real tokenizer output (I15).
_CHARS_PER_TOKEN: float = 4.0

def estimate_tokens(content: bytes) -> float:
    """
    Approximate token count.

    Uses UTF-8 bytes/4 heuristic — a deliberate approximation.
    This is NOT equivalent to provider billing tokens (I15).
    """
    return len(content) / _CHARS_PER_TOKEN


def make_metrics(
    raw_content: bytes,
    visible_content: bytes,
    decision: Disposition,
    evidence_class: EvidenceClass,
    mode: Mode,
    transform_duration_ms: float = 0.0,
    corrective_retrieval_required: Optional[bool] = None,
    raw_recovery_count: Optional[int] = None,
    actual_model_tokens: Optional[int] = None,
    model_turns: Optional[int] = None,
    corrective_retrievals: Optional[int] = None,
) -> FilterMetrics:
    """
    Construct a FilterMetrics instance.

    These six dimensions are tracked separately and must never be conflated (I14):
      raw_bytes, visible_bytes — byte counts
      raw_token_estimate, visible_token_estimate — approximate tokens
      transform_duration_ms — latency
      corrective_retrieval_required — mission-level boolean
    """
    return FilterMetrics(
        raw_bytes=len(raw_content),
        visible_bytes=len(visible_content),
        raw_token_estimate=estimate_tokens(raw_content),
        visible_token_estimate=estimate_tokens(visible_content),
        transform_duration_ms=transform_duration_ms,
        decision=decision,
        evidence_class=evidence_class,
        mode=mode,
        corrective_retrieval_required=corrective_retrieval_required,
        raw_recovery_count=raw_recovery_count,
        actual_model_tokens=actual_model_tokens,
        model_turns=model_turns,
        corrective_retrievals=corrective_retrievals,
    )


def log_metrics(
    metrics: FilterMetrics,
    raw_sha256: str,
    transform_id: Optional[str] = None,
    session_id: Optional[str] = None,
    log_path: Optional[pathlib.Path] = None,
    audit: Optional[dict] = None,
) -> None:
    """
    Append a metrics record to the JSONL log.

    The log is append-only. Each line is a JSON object.
    With an explicit path, callers may log RAW or TRANSFORM metrics.
    The engine supplies I16 in memory and suppresses sensitive disk audit.

    Args:
        metrics: The FilterMetrics to log.
        raw_sha256: SHA-256 of the raw content (for correlation with RAW store).
        transform_id: The transform applied, if any.
        session_id: Legacy argument; never persisted (metadata minimization).
        log_path: Override log path (for testing).
    """
    if log_path is None:
        return  # Persistence must be explicitly requested.
    log_path = pathlib.Path(log_path)

    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    record = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_sha256": raw_sha256,
        "raw_bytes": metrics.raw_bytes,
        "visible_bytes": metrics.visible_bytes,
        "raw_token_estimate": round(metrics.raw_token_estimate, 1),
        "visible_token_estimate": round(metrics.visible_token_estimate, 1),
        # NOTE: token estimates are approximations (UTF-8 bytes/4), NOT billing metrics (I15)
        "transform_duration_ms": round(metrics.transform_duration_ms, 2),
        "decision": metrics.decision.value,
        "evidence_class": metrics.evidence_class.value,
        "mode": metrics.mode.value,
        "transform_id": transform_id,
        "token_estimate_method": metrics.token_estimate_method,
        "actual_model_tokens": metrics.actual_model_tokens,
        "model_turns": metrics.model_turns,
        "corrective_retrievals": metrics.corrective_retrievals,
        "raw_recovery_count": metrics.raw_recovery_count,
        "audit": audit or {},
        "corrective_retrieval_required": metrics.corrective_retrieval_required,
        "byte_reduction_pct": (
            round((1.0 - metrics.visible_bytes / metrics.raw_bytes) * 100, 2)
            if metrics.raw_bytes > 0 else 0.0
        ),
        # IMPORTANT: byte_reduction_pct is a LOCAL metric only.
        # It does NOT represent whole-mission savings (I15).
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
