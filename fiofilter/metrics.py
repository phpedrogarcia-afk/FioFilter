"""
fiofilter.metrics — Per-result economics logging.

Design principles (I14, I15):
  - All six metric dimensions are tracked separately.
  - Token estimates are approximations (chars / 4). Never billing figures.
  - Local byte reduction ≠ token reduction ≠ model turn savings.
  - Metrics are emitted for every decision, including RAW pass-through.
  - Logged to JSONL for later mission-level analysis.

Log location:
  Default: ~/.fiofilter/metrics.jsonl
  Override: FIOFILTER_METRICS_LOG env var
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Optional

from fiofilter.types import Disposition, EvidenceClass, FilterMetrics, Mode

# Approximation: average chars per token (rough heuristic, not exact).
# Never claim this equals a real tokenizer output (I15).
_CHARS_PER_TOKEN: float = 4.0

_DEFAULT_METRICS_LOG = pathlib.Path.home() / ".fiofilter" / "metrics.jsonl"
_ENV_VAR = "FIOFILTER_METRICS_LOG"


def estimate_tokens(content: bytes) -> float:
    """
    Approximate token count.

    Uses chars/4 heuristic — a deliberate approximation.
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
    raw_recovery_count: int = 0,
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
    )


def _get_log_path() -> pathlib.Path:
    env_val = os.environ.get(_ENV_VAR)
    if env_val:
        return pathlib.Path(env_val)
    return _DEFAULT_METRICS_LOG


def log_metrics(
    metrics: FilterMetrics,
    raw_sha256: str,
    transform_id: Optional[str] = None,
    session_id: Optional[str] = None,
    log_path: Optional[pathlib.Path] = None,
) -> None:
    """
    Append a metrics record to the JSONL log.

    The log is append-only. Each line is a JSON object.
    Metrics are logged for every decision, including RAW (I16 requires this).

    Args:
        metrics: The FilterMetrics to log.
        raw_sha256: SHA-256 of the raw content (for correlation with RAW store).
        transform_id: The transform applied, if any.
        session_id: Optional session identifier.
        log_path: Override log path (for testing).
    """
    if log_path is None:
        log_path = _get_log_path()

    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_sha256": raw_sha256,
        "raw_bytes": metrics.raw_bytes,
        "visible_bytes": metrics.visible_bytes,
        "raw_token_estimate": round(metrics.raw_token_estimate, 1),
        "visible_token_estimate": round(metrics.visible_token_estimate, 1),
        # NOTE: token estimates are approximations (chars/4), NOT billing metrics (I15)
        "transform_duration_ms": round(metrics.transform_duration_ms, 2),
        "decision": metrics.decision.value,
        "evidence_class": metrics.evidence_class.value,
        "mode": metrics.mode.value,
        "transform_id": transform_id,
        "session_id": session_id,
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
