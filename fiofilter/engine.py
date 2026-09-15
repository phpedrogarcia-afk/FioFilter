"""
fiofilter.engine — Decision pipeline.

Single entry point: process()

Pipeline steps (per ARCHITECTURE.md):
  1. Normalize metadata
  2. Classify evidence
  3. Load profile
  4. Check protected invariants
  5. Select disposition
  6. Write RAW store (BEFORE any transform attempt — D011)
  7. Run candidate transform
  8. Validate output
  9. Compare economic local cost (I9)
  10. Verify inline facts present (I4 — belt and suspenders)
  11. Emit metrics (I16 — every decision logged)
  12. Return FilterResult

Fail-open rule: Any exception in steps 7–10 → return RAW.
Hard rule: Validation uncertainty → RAW.
"""

from __future__ import annotations

import time
from typing import List, Optional

from fiofilter import classifier as _classifier
from fiofilter import invariants as _invariants
from fiofilter import metrics as _metrics
from fiofilter.profiles import get_profile
from fiofilter.profiles.base import BaseProfile
from fiofilter.raw_store import RawStore, get_default_store
from fiofilter.transforms import LOSSLESS_TRANSFORM_IDS, available_transform_ids, get_transform
from fiofilter.types import (
    Disposition,
    EvidenceClass,
    FilterMetrics,
    FilterResult,
    Mode,
    RawRef,
    ToolResult,
)


def _select_transform_id(
    evidence_class: EvidenceClass,
    transform_whitelist: frozenset,
) -> Optional[str]:
    """
    Select a transform to attempt from the whitelist.

    V0: Only T01 exists. Returns first available whitelisted transform.
    Returns None if no transform is available.
    """
    available = available_transform_ids()
    for tid in sorted(transform_whitelist):  # sorted for determinism
        if tid in available:
            return tid
    return None


def _inline_facts_present(content: bytes, facts: List[str]) -> bool:
    """
    Verify all inline-required facts appear in the visible content (I4).

    Returns True if all facts are present, False if any are missing.
    """
    if not facts:
        return True
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return False
    return all(fact in text for fact in facts)


def process(
    tool_result: ToolResult,
    mode: Mode = Mode.BUILD,
    profile_id: str = "default",
    raw_store: Optional[RawStore] = None,
    metrics_log_path=None,
) -> FilterResult:
    """
    Process a ToolResult through the FioFilter decision pipeline.

    Args:
        tool_result: The tool result to process.
        mode: Operational mode (EXPLORE, BUILD, PROVE). Default: BUILD.
        profile_id: Profile to load. Default: 'default'.
        raw_store: RAW store instance. Default: global default store.
        metrics_log_path: Override metrics log path (for testing).

    Returns:
        FilterResult with visible content, disposition, raw_ref, and metrics.

    The returned FilterResult always contains a raw_ref — even for RAW dispositions.
    """
    if raw_store is None:
        raw_store = get_default_store()

    raw_content = tool_result.content
    t_start = time.monotonic()

    # -----------------------------------------------------------------------
    # Step 1: Normalize metadata (extraction only, no classification)
    # -----------------------------------------------------------------------
    exit_code = tool_result.exit_code

    # -----------------------------------------------------------------------
    # Step 2: Classify evidence (deterministic, no LLM — I11)
    # -----------------------------------------------------------------------
    classify_result = _classifier.classify(raw_content, exit_code=exit_code)

    # Low confidence → UNKNOWN → RAW (I5)
    if classify_result.confidence < _classifier.MIN_CONFIDENCE:
        classify_result = _classifier.ClassifyResult(
            evidence_class=EvidenceClass.UNKNOWN,
            confidence=1.0,
            classifier_notes="Confidence below threshold → UNKNOWN",
        )

    evidence_class = classify_result.evidence_class
    inline_required_facts = classify_result.inline_required_facts

    # -----------------------------------------------------------------------
    # Step 3: Load profile
    # -----------------------------------------------------------------------
    profile = get_profile(profile_id)
    policy = profile.get_policy(evidence_class, mode)

    # -----------------------------------------------------------------------
    # Step 4: Check protected invariants
    # -----------------------------------------------------------------------
    all_ok, inv_results = _invariants.check_all(
        evidence_class=evidence_class,
        mode=mode,
        exit_code=exit_code,
        proposed_transform_id=None,  # checked again after transform selection
        lossless_transform_ids=LOSSLESS_TRANSFORM_IDS,
    )

    forced = _invariants.first_forced(inv_results)
    if forced is not None:
        # Invariant fired → force RAW immediately
        disposition = Disposition.RAW
        t_end = time.monotonic()
        raw_ref = raw_store.write(
            raw_content,
            source=tool_result.source,
            command=tool_result.command,
            evidence_class=evidence_class,
            mode=mode,
            session_id=tool_result.session_id,
            inline_required_facts=inline_required_facts,
        )
        m = _metrics.make_metrics(
            raw_content=raw_content,
            visible_content=raw_content,
            decision=disposition,
            evidence_class=evidence_class,
            mode=mode,
            transform_duration_ms=(t_end - t_start) * 1000,
        )
        _metrics.log_metrics(
            m, raw_sha256=raw_ref.sha256,
            log_path=metrics_log_path,
        )
        return FilterResult(
            content=raw_content,
            disposition=Disposition.RAW,
            raw_ref=raw_ref,
            raw_sha256=raw_ref.sha256,
            evidence_class=evidence_class,
            mode=mode,
            metrics=m,
            policy_decision=f"Invariant {forced.invariant_id}: {forced.reason}",
            inline_required_facts=inline_required_facts,
        )

    # -----------------------------------------------------------------------
    # Step 5: Select disposition from profile policy
    # -----------------------------------------------------------------------
    transform_id = _select_transform_id(evidence_class, policy.transform_whitelist)

    if Disposition.TRANSFORM not in policy.allowed_dispositions or transform_id is None:
        disposition = Disposition.RAW
    else:
        disposition = Disposition.TRANSFORM

    # -----------------------------------------------------------------------
    # Step 6: Write RAW store BEFORE any transform attempt (D011)
    # -----------------------------------------------------------------------
    raw_ref = raw_store.write(
        raw_content,
        source=tool_result.source,
        command=tool_result.command,
        evidence_class=evidence_class,
        mode=mode,
        session_id=tool_result.session_id,
        inline_required_facts=inline_required_facts,
    )

    if disposition == Disposition.RAW:
        t_end = time.monotonic()
        m = _metrics.make_metrics(
            raw_content=raw_content,
            visible_content=raw_content,
            decision=Disposition.RAW,
            evidence_class=evidence_class,
            mode=mode,
            transform_duration_ms=(t_end - t_start) * 1000,
        )
        _metrics.log_metrics(m, raw_sha256=raw_ref.sha256, log_path=metrics_log_path)
        return FilterResult(
            content=raw_content,
            disposition=Disposition.RAW,
            raw_ref=raw_ref,
            raw_sha256=raw_ref.sha256,
            evidence_class=evidence_class,
            mode=mode,
            metrics=m,
            policy_decision=f"Profile policy: RAW for {evidence_class.value} in {mode.value}",
            inline_required_facts=inline_required_facts,
        )

    # -----------------------------------------------------------------------
    # Step 7: Run candidate transform (fail-open — any exception → RAW)
    # -----------------------------------------------------------------------
    transform = get_transform(transform_id)
    transformed_content: Optional[bytes] = None

    if transform is not None:
        try:
            transformed_content = transform.apply(raw_content)
        except Exception as exc:
            # Fail-open (CCA principle — KEEP): exception → RAW
            t_end = time.monotonic()
            m = _metrics.make_metrics(
                raw_content=raw_content,
                visible_content=raw_content,
                decision=Disposition.ESCALATE_TO_RAW,
                evidence_class=evidence_class,
                mode=mode,
                transform_duration_ms=(t_end - t_start) * 1000,
            )
            _metrics.log_metrics(
                m, raw_sha256=raw_ref.sha256,
                transform_id=transform_id, log_path=metrics_log_path,
            )
            return FilterResult(
                content=raw_content,
                disposition=Disposition.ESCALATE_TO_RAW,
                raw_ref=raw_ref,
                raw_sha256=raw_ref.sha256,
                evidence_class=evidence_class,
                mode=mode,
                metrics=m,
                transform_id=transform_id,
                policy_decision=f"Transform {transform_id} exception: {type(exc).__name__} → RAW",
                inline_required_facts=inline_required_facts,
            )

    # Transform returned None (no improvement possible)
    if transformed_content is None:
        t_end = time.monotonic()
        m = _metrics.make_metrics(
            raw_content=raw_content,
            visible_content=raw_content,
            decision=Disposition.RAW,
            evidence_class=evidence_class,
            mode=mode,
            transform_duration_ms=(t_end - t_start) * 1000,
        )
        _metrics.log_metrics(m, raw_sha256=raw_ref.sha256, log_path=metrics_log_path)
        return FilterResult(
            content=raw_content,
            disposition=Disposition.RAW,
            raw_ref=raw_ref,
            raw_sha256=raw_ref.sha256,
            evidence_class=evidence_class,
            mode=mode,
            metrics=m,
            transform_id=transform_id,
            policy_decision=f"Transform {transform_id} produced no improvement → RAW",
            inline_required_facts=inline_required_facts,
        )

    # -----------------------------------------------------------------------
    # Step 8: Validate output (basic)
    # -----------------------------------------------------------------------
    if not isinstance(transformed_content, bytes) or len(transformed_content) == 0:
        t_end = time.monotonic()
        m = _metrics.make_metrics(
            raw_content=raw_content,
            visible_content=raw_content,
            decision=Disposition.ESCALATE_TO_RAW,
            evidence_class=evidence_class,
            mode=mode,
            transform_duration_ms=(t_end - t_start) * 1000,
        )
        _metrics.log_metrics(m, raw_sha256=raw_ref.sha256, log_path=metrics_log_path)
        return FilterResult(
            content=raw_content,
            disposition=Disposition.ESCALATE_TO_RAW,
            raw_ref=raw_ref,
            raw_sha256=raw_ref.sha256,
            evidence_class=evidence_class,
            mode=mode,
            metrics=m,
            transform_id=transform_id,
            policy_decision=f"Transform {transform_id} produced invalid output → RAW",
            inline_required_facts=inline_required_facts,
        )

    # -----------------------------------------------------------------------
    # Step 9: Economic size check (I9 — no-expansion rule)
    # -----------------------------------------------------------------------
    ok_i9, inv_i9 = _invariants.check_all(
        evidence_class=evidence_class,
        mode=mode,
        raw_byte_length=len(raw_content),
        transformed_byte_length=len(transformed_content),
    )
    forced_i9 = _invariants.first_forced(inv_i9)
    if forced_i9 is not None and forced_i9.invariant_id == "I9":
        t_end = time.monotonic()
        m = _metrics.make_metrics(
            raw_content=raw_content,
            visible_content=raw_content,
            decision=Disposition.RAW,
            evidence_class=evidence_class,
            mode=mode,
            transform_duration_ms=(t_end - t_start) * 1000,
        )
        _metrics.log_metrics(m, raw_sha256=raw_ref.sha256, log_path=metrics_log_path)
        return FilterResult(
            content=raw_content,
            disposition=Disposition.RAW,
            raw_ref=raw_ref,
            raw_sha256=raw_ref.sha256,
            evidence_class=evidence_class,
            mode=mode,
            metrics=m,
            transform_id=transform_id,
            policy_decision=f"I9: transform expanded output → RAW",
            inline_required_facts=inline_required_facts,
        )

    # -----------------------------------------------------------------------
    # Step 10: Inline-fact verification (I4 — belt and suspenders)
    # -----------------------------------------------------------------------
    if not _inline_facts_present(transformed_content, inline_required_facts):
        t_end = time.monotonic()
        m = _metrics.make_metrics(
            raw_content=raw_content,
            visible_content=raw_content,
            decision=Disposition.ESCALATE_TO_RAW,
            evidence_class=evidence_class,
            mode=mode,
            transform_duration_ms=(t_end - t_start) * 1000,
        )
        _metrics.log_metrics(m, raw_sha256=raw_ref.sha256, log_path=metrics_log_path)
        return FilterResult(
            content=raw_content,
            disposition=Disposition.ESCALATE_TO_RAW,
            raw_ref=raw_ref,
            raw_sha256=raw_ref.sha256,
            evidence_class=evidence_class,
            mode=mode,
            metrics=m,
            transform_id=transform_id,
            policy_decision=f"I4: inline-required facts missing after {transform_id} → RAW",
            inline_required_facts=inline_required_facts,
        )

    # -----------------------------------------------------------------------
    # Step 11: Emit metrics (I16 — decision logged before return)
    # -----------------------------------------------------------------------
    t_end = time.monotonic()
    m = _metrics.make_metrics(
        raw_content=raw_content,
        visible_content=transformed_content,
        decision=Disposition.TRANSFORM,
        evidence_class=evidence_class,
        mode=mode,
        transform_duration_ms=(t_end - t_start) * 1000,
    )
    _metrics.log_metrics(
        m,
        raw_sha256=raw_ref.sha256,
        transform_id=transform_id,
        session_id=tool_result.session_id,
        log_path=metrics_log_path,
    )

    # -----------------------------------------------------------------------
    # Step 12: Return FilterResult
    # -----------------------------------------------------------------------
    return FilterResult(
        content=transformed_content,
        disposition=Disposition.TRANSFORM,
        raw_ref=raw_ref,
        raw_sha256=raw_ref.sha256,
        evidence_class=evidence_class,
        mode=mode,
        metrics=m,
        transform_id=transform_id,
        policy_decision=f"{transform_id} applied",
        inline_required_facts=inline_required_facts,
    )
