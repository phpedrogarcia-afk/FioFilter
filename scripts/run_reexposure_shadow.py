"""Run session-aware Reexposure Shadow evaluation on real coding-agent workloads.

Produces deterministic shadow reference decisions, eligibility funnels,
recency/distance distributions, tool-family breakdowns, and an append-only
hash-chained ledger.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import pathlib
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List

from fiofilter.context_census import ContextWasteCensus
from fiofilter.reexposure import (
    EPISODE_BUCKETS,
    RECENCY_BUCKETS,
    ReexposureShadowEvaluator,
    ShadowDisposition,
    ShadowLedger,
    SourceKind,
    _classify_episode_bucket,
    _classify_recency_bucket,
)

SOURCE_A_DEFAULT = pathlib.Path(
    r"C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl"
)
EXPECTED_SHA256 = (
    "bc4561d4588a73a6889ca38d8c180ae467e51eea5f023aaba7a222425cf350a0"
)
EXPECTED_BYTES = 206427325
SHADOW_DIR_DEFAULT = pathlib.Path(r"C:\Users\phped\.fiofilter\shadow")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run M06 Reexposure Shadow Evaluator.")
    parser.add_argument(
        "--session-path",
        type=pathlib.Path,
        default=SOURCE_A_DEFAULT,
        help="Path to historical session JSONL",
    )
    parser.add_argument(
        "--shadow-dir",
        type=pathlib.Path,
        default=SHADOW_DIR_DEFAULT,
        help="Path to output shadow ledger directory",
    )
    args = parser.parse_args()

    session_path = args.session_path.resolve()
    if not session_path.exists():
        print(f"ERROR: Session file not found: {session_path}", file=sys.stderr)
        return 1

    # Verify input file
    print(f"Verifying session input: {session_path}")
    hasher = hashlib.sha256()
    size = 0
    with open(session_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    observed_sha256 = hasher.hexdigest()

    print(f"  Observed size:   {size:,} bytes")
    print(f"  Observed SHA256: {observed_sha256}")

    if session_path == SOURCE_A_DEFAULT.resolve():
        if observed_sha256 != EXPECTED_SHA256 or size != EXPECTED_BYTES:
            print("ERROR: Source A fingerprint verification failed!", file=sys.stderr)
            return 1
        print("  Source A physical fingerprint: VERIFIED")

    # Load session via ContextWasteCensus
    print("Loading and parsing session events...")
    census = ContextWasteCensus(session_path)
    census.load_session()
    events = census.events
    total_calls = len(events)
    total_bytes = sum(e.output_bytes for e in events)
    print(f"  Loaded {total_calls:,} tool calls ({total_bytes:,} total output bytes)")

    # 1. Recompute M05 baseline
    m05_content_deliveries = defaultdict(list)
    for e in events:
        target_key = e.target_path or e.command or "UNKNOWN"
        m05_content_deliveries[(target_key, e.output_sha256)].append(e)

    m05_exact_redelivery_events = 0
    m05_exact_redelivery_bytes_gross = 0
    m05_proven_reexposure_bytes = 0
    for (target_key, sha), ev_list in m05_content_deliveries.items():
        if len(ev_list) > 1 and target_key != "UNKNOWN":
            m05_exact_redelivery_events += len(ev_list)
            b_size = ev_list[0].output_bytes
            m05_exact_redelivery_bytes_gross += b_size * len(ev_list)
            m05_proven_reexposure_bytes += b_size * (len(ev_list) - 1)

    print("\n--- M05 EXACT REDELIVERY BASELINE ---")
    print(f"  M05 Exact Redelivery Events (group total): {m05_exact_redelivery_events}")
    print(f"  M05 Exact Redelivery Gross Bytes:          {m05_exact_redelivery_bytes_gross:,} B")
    print(f"  M05 Exact Redelivered Repeated Bytes:      {m05_proven_reexposure_bytes:,} B")

    # 2. Run M06 Sequential Shadow Evaluation
    session_id = session_path.stem
    evaluator = ReexposureShadowEvaluator(session_id)

    print("\nExecuting M06 Reexposure Shadow Evaluation...")
    for idx, e in enumerate(events):
        raw = base64.b64decode(e.raw_content_b64)
        target_id = e.target_path or e.command or "UNKNOWN"
        evaluator.evaluate(
            call_id=e.call_id,
            call_index=idx + 1,
            source_kind=e.tool_family,
            source_identity=target_id,
            raw_bytes=raw,
            exit_code=e.exit_code,
            truncated=e.truncated,
            timestamp=e.timestamp,
            episode_id=e.episode_id,
            target_path=e.target_path,
            read_range=e.line_range,
            session_id=session_id,
        )

    decisions = evaluator.decisions

    # 3. Analyze Funnel
    funnel_all_calls = len(decisions)
    funnel_all_bytes = total_bytes

    # Exact content redeliveries: all calls where content was seen before (excluding first deliveries)
    content_redeliveries = [d for d in decisions if d.disposition != ShadowDisposition.FIRST_DELIVERY.value]
    funnel_content_calls = len(content_redeliveries)
    funnel_content_bytes = sum(d.original_bytes for d in content_redeliveries)

    # Same source exact redeliveries: content matches AND same source
    same_source_redeliveries = [d for d in content_redeliveries if d.same_source]
    funnel_same_src_calls = len(same_source_redeliveries)
    funnel_same_src_bytes = sum(d.original_bytes for d in same_source_redeliveries)

    # Evidence class safe: not unsafe, not unknown, not sensitive
    safe_evidence_calls = [
        d for d in same_source_redeliveries
        if d.disposition not in (
            ShadowDisposition.UNSAFE_EVIDENCE_RAW.value,
            ShadowDisposition.UNKNOWN_RAW.value,
            ShadowDisposition.AMBIGUOUS_IDENTITY_RAW.value,
            ShadowDisposition.SENSITIVE_RAW.value,
            ShadowDisposition.DO_NOT_PERSIST_RAW.value,
        )
    ]
    funnel_safe_ev_calls = len(safe_evidence_calls)
    funnel_safe_ev_bytes = sum(d.original_bytes for d in safe_evidence_calls)

    # Sensitivity allowed: (already separated above or equal)
    sens_allowed_calls = [d for d in safe_evidence_calls if d.disposition != ShadowDisposition.SENSITIVE_RAW.value]
    funnel_sens_calls = len(sens_allowed_calls)
    funnel_sens_bytes = sum(d.original_bytes for d in sens_allowed_calls)

    # Economic references (Final Shadow Reference Candidates)
    final_candidates = [
        d for d in sens_allowed_calls
        if d.disposition == ShadowDisposition.EXACT_REDELIVERY_SHADOW_REFERENCE.value
    ]
    funnel_final_calls = len(final_candidates)
    funnel_final_raw_bytes = sum(d.original_bytes for d in final_candidates)
    funnel_final_ref_bytes = sum(d.reference_bytes for d in final_candidates)
    funnel_final_avoided_bytes = sum(d.hypothetical_bytes_avoided for d in final_candidates)

    print("\n--- M06 SHADOW ELIGIBILITY FUNNEL ---")
    print(f"  1. ALL_TOOL_OUTPUTS:               {funnel_all_calls:5d} calls, {funnel_all_bytes:10,d} B (100.0%)")
    print(f"  2. EXACT_CONTENT_REDELIVERIES:     {funnel_content_calls:5d} calls, {funnel_content_bytes:10,d} B")
    print(f"  3. SAME_SOURCE_EXACT_REDELIVERIES: {funnel_same_src_calls:5d} calls, {funnel_same_src_bytes:10,d} B")
    print(f"  4. EVIDENCE_CLASS_PROVEN_SAFE:     {funnel_safe_ev_calls:5d} calls, {funnel_safe_ev_bytes:10,d} B")
    print(f"  5. SENSITIVITY_POLICY_ALLOWED:     {funnel_sens_calls:5d} calls, {funnel_sens_bytes:10,d} B")
    print(f"  6. REFERENCE_ECONOMIC (FINAL):     {funnel_final_calls:5d} calls, {funnel_final_raw_bytes:10,d} B")
    print(f"     Hypothetical Reference Bytes:                     {funnel_final_ref_bytes:10,d} B")
    print(f"     Hypothetical Local Avoided Bytes:                 {funnel_final_avoided_bytes:10,d} B")

    # Ineligibility breakdown
    ineligible_counter = Counter(d.disposition for d in content_redeliveries if d.disposition != ShadowDisposition.EXACT_REDELIVERY_SHADOW_REFERENCE.value)
    print("\n--- INELIGIBILITY REASONS (Repeated Deliveries) ---")
    for disp, cnt in ineligible_counter.most_common():
        b = sum(d.original_bytes for d in content_redeliveries if d.disposition == disp)
        print(f"  {disp:35s}: {cnt:4d} calls, {b:8,d} B")

    # 4. Tool Family Breakdown
    family_breakdown = {}
    print("\n--- BREAKDOWN BY TOOL FAMILY (All Repeated Content) ---")
    for fam in SourceKind:
        fam_name = fam.value
        fam_reps = [d for d in content_redeliveries if d.source_kind == fam_name]
        fam_same = [d for d in fam_reps if d.same_source]
        fam_elig = [d for d in fam_same if d.disposition == ShadowDisposition.EXACT_REDELIVERY_SHADOW_REFERENCE.value]
        
        rep_calls = len(fam_reps)
        rep_bytes = sum(d.original_bytes for d in fam_reps)
        same_calls = len(fam_same)
        same_bytes = sum(d.original_bytes for d in fam_same)
        elig_calls = len(fam_elig)
        elig_raw_b = sum(d.original_bytes for d in fam_elig)
        elig_ref_b = sum(d.reference_bytes for d in fam_elig)
        elig_avoid_b = sum(d.hypothetical_bytes_avoided for d in fam_elig)

        family_breakdown[fam_name] = {
            "repeated_calls": rep_calls,
            "repeated_bytes": rep_bytes,
            "same_source_calls": same_calls,
            "same_source_bytes": same_bytes,
            "eligible_calls": elig_calls,
            "eligible_raw_bytes": elig_raw_b,
            "hypothetical_reference_bytes": elig_ref_b,
            "hypothetical_bytes_avoided": elig_avoid_b,
        }
        print(f"  {fam_name:15s}: {rep_calls:4d} reps ({rep_bytes:7,d} B) | Same-Src: {same_calls:4d} ({same_bytes:7,d} B) | Eligible: {elig_calls:3d} ({elig_avoid_b:6,d} B avoided)")

    # 5. Same-File Read Specialization
    file_reads = [e for e in events if e.tool_family == "FILE_READ" and e.target_path]
    reads_by_path = defaultdict(list)
    for e in file_reads:
        reads_by_path[e.target_path].append(e)

    same_path_same_bytes_events = 0
    same_path_same_bytes_vol = 0
    same_path_changed_bytes_events = 0
    same_path_overlapping_range_events = 0

    for path, r_list in reads_by_path.items():
        if len(r_list) < 2:
            continue
        for i in range(1, len(r_list)):
            prev = r_list[i - 1]
            curr = r_list[i]
            if curr.output_sha256 == prev.output_sha256:
                same_path_same_bytes_events += 1
                same_path_same_bytes_vol += curr.output_bytes
            else:
                same_path_changed_bytes_events += 1
            if prev.line_range and curr.line_range:
                p_start, p_end = prev.line_range
                c_start, c_end = curr.line_range
                if max(p_start, c_start) < min(p_end, c_end):
                    same_path_overlapping_range_events += 1

    print("\n--- FILE_READ SPECIALIZATION (READ_RECEIPT Analysis) ---")
    print(f"  Same-path total reads:                 {len(file_reads):5d} calls")
    print(f"  Same-path same-bytes events:           {same_path_same_bytes_events:5d} calls ({same_path_same_bytes_vol:,} B)")
    print(f"  Same-path changed-bytes events:        {same_path_changed_bytes_events:5d} calls")
    print(f"  Same-path overlapping-range events:    {same_path_overlapping_range_events:5d} calls")

    # 6. Distance and Recency Distribution
    recency_dist = Counter()
    recency_bytes = defaultdict(int)
    episode_dist = Counter()
    episode_bytes = defaultdict(int)

    for d in same_source_redeliveries:
        if d.call_distance_from_first is not None:
            bucket = _classify_recency_bucket(d.call_distance_from_first)
            recency_dist[bucket] += 1
            recency_bytes[bucket] += d.original_bytes
        if d.episode_distance is not None:
            ep_bucket = _classify_episode_bucket(d.episode_distance)
            episode_dist[ep_bucket] += 1
            episode_bytes[ep_bucket] += d.original_bytes

    print("\n--- DISTANCE & RECENCY DISTRIBUTION (Same-Source Redeliveries) ---")
    print("  Call Distance Buckets:")
    for b in RECENCY_BUCKETS:
        print(f"    {b:10s}: {recency_dist[b]:4d} calls, {recency_bytes[b]:8,d} B")
    print("  Episode Distance Buckets:")
    for b in EPISODE_BUCKETS:
        print(f"    {b:15s}: {episode_dist[b]:4d} calls, {episode_bytes[b]:8,d} B")

    # 7. Comparison to M05 Baseline
    m05_repeated_bytes = m05_proven_reexposure_bytes  # 260,775 B
    m06_final_raw_bytes = funnel_final_raw_bytes
    retention_pct = (m06_final_raw_bytes / m05_repeated_bytes * 100.0) if m05_repeated_bytes > 0 else 0.0

    print("\n--- M05 VS M06 CRITICAL COMPARISON ---")
    print(f"  M05 Exact Repeated Bytes:                  {m05_repeated_bytes:8,d} B")
    print(f"  M06 Final Shadow-Eligible Raw Bytes:       {m06_final_raw_bytes:8,d} B")
    print(f"  M05 to M06 Eligibility Retention Percent:  {retention_pct:8.2f}%")
    print(f"  Hypothetical Local Bytes Avoided:          {funnel_final_avoided_bytes:8,d} B")
    print(f"  Hypothetical Local Reduction Percent:      {(funnel_final_avoided_bytes / total_bytes * 100.0):8.4f}%")

    # 8. Write Shadow Ledger
    print(f"\nWriting local shadow ledger to: {args.shadow_dir}...")
    ledger = ShadowLedger(args.shadow_dir)
    ledger.write_events(decisions)

    manifest = {
        "schema_version": "M06_REEXPOSURE_SHADOW_V1",
        "session_path": str(session_path),
        "session_sha256": observed_sha256,
        "session_bytes": size,
        "total_calls": total_calls,
        "total_output_bytes": total_bytes,
        "m05_baseline_repeated_bytes": m05_repeated_bytes,
        "m06_shadow_eligible_raw_bytes": m06_final_raw_bytes,
        "m06_hypothetical_bytes_avoided": funnel_final_avoided_bytes,
    }

    summary = {
        "funnel": {
            "all_tool_outputs_calls": funnel_all_calls,
            "all_tool_outputs_bytes": funnel_all_bytes,
            "exact_content_redelivery_calls": funnel_content_calls,
            "exact_content_redelivery_bytes": funnel_content_bytes,
            "same_source_exact_redelivery_calls": funnel_same_src_calls,
            "same_source_exact_redelivery_bytes": funnel_same_src_bytes,
            "evidence_class_safe_calls": funnel_safe_ev_calls,
            "evidence_class_safe_bytes": funnel_safe_ev_bytes,
            "sensitivity_allowed_calls": funnel_sens_calls,
            "sensitivity_allowed_bytes": funnel_sens_bytes,
            "final_shadow_reference_calls": funnel_final_calls,
            "final_shadow_raw_bytes": funnel_final_raw_bytes,
            "final_shadow_reference_bytes": funnel_final_ref_bytes,
            "hypothetical_local_bytes_avoided": funnel_final_avoided_bytes,
            "hypothetical_local_reduction_pct": round(funnel_final_avoided_bytes / total_bytes * 100.0, 4),
        },
        "retention_comparison": {
            "m05_exact_repeated_bytes": m05_repeated_bytes,
            "m06_shadow_eligible_raw_bytes": m06_final_raw_bytes,
            "m05_to_m06_eligibility_retention_pct": round(retention_pct, 2),
        },
        "tool_family_breakdown": family_breakdown,
        "file_read_specialization": {
            "same_path_same_bytes_events": same_path_same_bytes_events,
            "same_path_same_bytes_bytes": same_path_same_bytes_vol,
            "same_path_changed_bytes_events": same_path_changed_bytes_events,
            "same_path_overlapping_range_events": same_path_overlapping_range_events,
        },
        "recency_distribution": {
            "by_call_distance": {b: {"calls": recency_dist[b], "bytes": recency_bytes[b]} for b in RECENCY_BUCKETS},
            "by_episode_distance": {b: {"calls": episode_dist[b], "bytes": episode_bytes[b]} for b in EPISODE_BUCKETS},
        },
        "ineligibility_counts": dict(ineligible_counter),
        "epistemic_declarations": {
            "who_mission_savings": "UNKNOWN",
            "task_quality_impact": "UNKNOWN",
            "corrective_retrieval_rate": "UNKNOWN",
            "provider_cache_impact": "UNKNOWN",
        },
    }

    ledger.write_manifest_and_summary(manifest, summary)
    print("  Ledger, manifest, and summary written successfully.")
    print("M06 Shadow Evaluation Complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
