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

    label_scopes = {}
    for scope, scoped in summary.metrics_by_label_scope.items():
        total_missed_bytes = sum(
            bucket["raw_bytes"] for bucket in scoped["missed_by_bucket"].values()
        )
        missed_report = {}
        for bucket_name, data in scoped["missed_by_bucket"].items():
            share = (
                round(data["raw_bytes"] / total_missed_bytes * 100.0, 2)
                if total_missed_bytes > 0
                else 0.0
            )
            missed_report[bucket_name] = {
                "entry_count": data["entry_count"],
                "raw_bytes": data["raw_bytes"],
                "estimated_tokens": round(data["estimated_tokens"], 1),
                "share_of_missed_bytes_pct": share,
                "sample_entries": data["sample_entries"],
            }
        label_scopes[scope] = {
            "claim_status": (
                "INDEPENDENTLY_REVIEWED"
                if scope.startswith("ORACLE:")
                else "HEURISTIC_ONLY_NOT_SAFETY_PROOF"
            ),
            "entry_count": scoped["entry_count"],
            "safety_comparison": {
                "dangerous_false_transform_eligibility": scoped[
                    "dangerous_false_transform_eligibility"
                ],
                "dangerous_entries": scoped["dangerous_entries"],
                "safe_opportunity_missed": scoped["safe_opportunity_missed"],
                "safe_match": scoped["safe_match"],
                "unsafe_sensitivity_leak": scoped["unsafe_sensitivity_leak"],
                "label_uncertain": scoped["label_uncertain"],
            },
            "t01_unapproved_grammar_entries": scoped[
                "t01_unapproved_grammar_entries"
            ],
            "missed_opportunities": missed_report,
            "confusion_matrix": scoped["predicted_vs_label_matrix"],
        }

    out = {
        "corpus_path": str(p),
        "mode": mode.value,
        "profile_id": profile_id,
        "total_entries": summary.total_entries,
        "total_raw_bytes": summary.total_raw_bytes,
        "total_visible_bytes": summary.total_visible_bytes,
        "total_raw_token_estimate": round(summary.total_raw_token_estimate, 1),
        "total_visible_token_estimate": round(summary.total_visible_token_estimate, 1),
        "token_estimate_method": summary.token_estimate_method,
        "local_byte_reduction_pct": summary.local_byte_reduction_pct,
        "local_token_estimate_reduction_pct": summary.local_token_estimate_reduction_pct,
        "measurement_scope": {
            "raw_bytes": "exact bytes in loaded corpus entries",
            "visible_bytes": "exact bytes returned by FioFilter replay",
            "token_values": "local estimates, not actual/model/billing tokens",
            "whole_mission_savings": "UNKNOWN",
        },
        "t01_performance": {
            "eligible_entries": summary.t01_eligible_entries,
            "transformed_entries": summary.t01_transformed_entries,
            "raw_bytes": summary.t01_raw_bytes,
            "visible_bytes": summary.t01_visible_bytes,
            "marker_overhead_defeated_entries": summary.t01_marker_overhead_defeated_entries,
            "classes_affected": sorted(list(summary.t01_classes_affected)),
        },
        "label_scopes": label_scopes,
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
    print(
        f"Total Raw Bytes: {report['total_raw_bytes']} "
        f"({report['total_raw_token_estimate']} estimated tokens)"
    )
    print(
        f"Total Visible Bytes: {report['total_visible_bytes']} "
        f"({report['total_visible_token_estimate']} estimated tokens)"
    )
    print(f"Local Byte Reduction: {report['local_byte_reduction_pct']}%")
    print(
        "Local Token ESTIMATE Reduction: "
        f"{report['local_token_estimate_reduction_pct']}% "
        f"({report['token_estimate_method']})"
    )

    print("\n--- T01 PERFORMANCE ---")
    t = report["t01_performance"]
    print(f"Eligible Entries: {t['eligible_entries']}")
    print(f"Transformed Entries: {t['transformed_entries']}")
    print(f"T01 Raw Bytes: {t['raw_bytes']} -> Visible Bytes: {t['visible_bytes']}")
    print(f"Marker Overhead Defeated Entries: {t['marker_overhead_defeated_entries']}")
    print(f"Classes Affected: {t['classes_affected']}")

    for scope, scoped in report["label_scopes"].items():
        print(f"\n--- LABEL SCOPE: {scope} ---")
        print(f"Claim status: {scoped['claim_status']}")
        safety = scoped["safety_comparison"]
        for name, value in safety.items():
            print(f"{name}: {value}")
        print(
            "T01 unapproved grammar entries: "
            f"{scoped['t01_unapproved_grammar_entries']}"
        )
        print("Missed opportunities:")
        for bucket, bucket_data in scoped["missed_opportunities"].items():
            if bucket_data["entry_count"]:
                print(
                    f"  {bucket}: {bucket_data['entry_count']} entries, "
                    f"{bucket_data['raw_bytes']} bytes, "
                    f"{bucket_data['share_of_missed_bytes_pct']}% of this scope"
                )
        print("Predicted vs label matrix:")
        for label_class, predictions in scoped["confusion_matrix"].items():
            print(f"  Label [{label_class}]: {dict(predictions)}")


if __name__ == "__main__":
    main()
