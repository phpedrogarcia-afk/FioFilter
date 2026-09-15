"""
scripts/run_corpus_evaluation.py — Empirical evaluation runner.

Loads a corpus, runs FioFilter replay, evaluates safety gates, measures T01
efficiency on real workloads, analyzes missed reduction opportunities, and
generates audit statistics.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List

from fiofilter.corpus import load_corpus, replay_corpus
from fiofilter.types import Mode


def evaluate_corpus(corpus_path: str | pathlib.Path, mode_str: str = "BUILD", profile_id: str = "fioos") -> Dict[str, Any]:
    p = pathlib.Path(corpus_path)
    entries = load_corpus(p)
    mode = Mode[mode_str.upper()]

    evaluated, summary = replay_corpus(entries, mode=mode, profile_id=profile_id)

    # Calculate share of missed opportunities
    total_missed_bytes = sum(b["raw_bytes"] for b in summary.missed_by_bucket.values())
    missed_report = {}
    for bucket_name, data in summary.missed_by_bucket.items():
        share = round((data["raw_bytes"] / total_missed_bytes * 100.0), 2) if total_missed_bytes > 0 else 0.0
        missed_report[bucket_name] = {
            "entry_count": data["entry_count"],
            "raw_bytes": data["raw_bytes"],
            "estimated_tokens": round(data["estimated_tokens"], 1),
            "share_of_missed_bytes_pct": share,
            "sample_entries": data["sample_entries"],
        }

    out = {
        "corpus_path": str(p),
        "mode": mode.value,
        "profile_id": profile_id,
        "total_entries": summary.total_entries,
        "total_raw_bytes": summary.total_raw_bytes,
        "total_visible_bytes": summary.total_visible_bytes,
        "total_raw_tokens": round(summary.total_raw_tokens, 1),
        "total_visible_tokens": round(summary.total_visible_tokens, 1),
        "local_byte_reduction_pct": summary.local_byte_reduction_pct,
        "local_token_reduction_pct": summary.local_token_reduction_pct,
        "safety": {
            "dangerous_false_transform_eligibility": summary.dangerous_false_transform_eligibility,
            "dangerous_entries": summary.dangerous_entries,
            "safe_opportunity_missed": summary.safe_opportunity_missed,
            "safe_match": summary.safe_match,
            "unsafe_sensitivity_leak": summary.unsafe_sensitivity_leak,
        },
        "t01_performance": {
            "eligible_entries": summary.t01_eligible_entries,
            "transformed_entries": summary.t01_transformed_entries,
            "raw_bytes": summary.t01_raw_bytes,
            "visible_bytes": summary.t01_visible_bytes,
            "marker_overhead_defeated_entries": summary.t01_marker_overhead_defeated_entries,
            "unapproved_grammar_entries": summary.t01_unapproved_grammar_entries,
            "classes_affected": sorted(list(summary.t01_classes_affected)),
        },
        "missed_opportunities": missed_report,
        "confusion_matrix": summary.predicted_vs_oracle_matrix,
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FioFilter against a corpus JSONL file.")
    parser.add_argument("--corpus", required=True, help="Path to corpus JSONL file")
    parser.add_argument("--mode", default="BUILD", help="Operational mode (EXPLORE, BUILD, PROVE)")
    parser.add_argument("--profile", default="fioos", help="Profile ID (default, fioos, fioideias)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()
    report = evaluate_corpus(args.corpus, mode_str=args.mode, profile_id=args.profile)

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("==================================================")
    print("FIOFILTER CORPUS EVALUATION REPORT")
    print("==================================================")
    print(f"Corpus: {report['corpus_path']}")
    print(f"Mode: {report['mode']} | Profile: {report['profile_id']}")
    print(f"Total Entries: {report['total_entries']}")
    print(f"Total Raw Bytes: {report['total_raw_bytes']} ({report['total_raw_tokens']} est. tokens)")
    print(f"Total Visible Bytes: {report['total_visible_bytes']} ({report['total_visible_tokens']} est. tokens)")
    print(f"Local Byte Reduction: {report['local_byte_reduction_pct']}%")
    print(f"Local Token Reduction: {report['local_token_reduction_pct']}%")
    print("\n--- SAFETY AUDIT ---")
    s = report["safety"]
    print(f"DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY: {s['dangerous_false_transform_eligibility']}")
    print(f"UNSAFE_SENSITIVITY_LEAK: {s['unsafe_sensitivity_leak']}")
    print(f"SAFE_OPPORTUNITY_MISSED: {s['safe_opportunity_missed']}")
    print(f"SAFE_MATCH: {s['safe_match']}")
    if s["dangerous_entries"]:
        print(f"DANGEROUS ENTRIES: {s['dangerous_entries']}")

    print("\n--- T01 PERFORMANCE ---")
    t = report["t01_performance"]
    print(f"Eligible Entries: {t['eligible_entries']}")
    print(f"Transformed Entries: {t['transformed_entries']}")
    print(f"T01 Raw Bytes: {t['raw_bytes']} -> Visible Bytes: {t['visible_bytes']}")
    print(f"Marker Overhead Defeated Entries: {t['marker_overhead_defeated_entries']}")
    print(f"Unapproved Grammar Repetition Entries: {t['unapproved_grammar_entries']}")
    print(f"Classes Affected: {t['classes_affected']}")

    print("\n--- MISSED OPPORTUNITIES BY BUCKET ---")
    for bucket, bdata in report["missed_opportunities"].items():
        if bdata["entry_count"] > 0:
            print(f"  {bucket}:")
            print(f"    Entries: {bdata['entry_count']}")
            print(f"    Raw Bytes: {bdata['raw_bytes']} ({bdata['estimated_tokens']} tokens)")
            print(f"    Share of Missed Bytes: {bdata['share_of_missed_bytes_pct']}%")
            print(f"    Sample Entries: {bdata['sample_entries']}")

    print("\n--- ORACLE vs PREDICTED CLASS MATRIX ---")
    for oracle_cls, preds in report["confusion_matrix"].items():
        print(f"  Oracle [{oracle_cls}]: {dict(preds)}")


if __name__ == "__main__":
    main()
