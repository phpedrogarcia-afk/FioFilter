"""scripts/run_discovery_structural_shadow.py — M09 Discovery Structural Shadow CLI.

Implements donor mechanisms from Aider RepoMap and AgentMap:
1. Builds structural snapshot of the active repo worktree using PythonAstStructuralBackend.
2. Computes AgentMap-derived graph health (edge coverage, parse coverage, status).
3. Renders compact budgeted symbol signature maps (Aider adaptation) at 1KB, 2KB, 4KB, 8KB.
4. Executes the Commit-History Benchmark over FioFilter repository history:
   - Evaluates parent snapshot -> child changed files ground truth
   - Audits query leakage (PATH_LEAKING vs NON_LEAKING)
   - Benchmarks 4 ablation modes: LEXICAL_ONLY, STRUCTURAL_ONLY, LEXICAL_PLUS_STRUCTURAL, LEXICAL_PLUS_PPR
5. Replays Source A discovery shadow:
   - Analyzes 490 FILE_READ calls across 256 distinct targets in 151 read episodes
   - Characterizes discovery reads prior to mutation boundary
   - Enforces DISCOVERY_READ_SUPPRESSION = False, AUTO_CONTEXT_SELECTION = False
6. Emits deterministic JSON artifacts to C:\\Users\\phped\\.fiofilter\\structural-shadow\\:
   - m09_structural_snapshot_v1.json
   - m09_commit_benchmark_v1.json
   - m09_source_a_discovery_shadow_v1.json
   - m09_structural_summary_v1.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from fiofilter.context_census import ContextWasteCensus
from fiofilter.discovery_shadow import (
    CommitHistoryBenchmark,
    DiscoveryQueryExtractor,
    StructuralRanker,
)
from fiofilter.structural import (
    BUDGET_APPLIES_TO_INDEX_ONLY,
    DISCOVERY_READ_SUPPRESSION,
    EVIDENCE_OVERRIDES_BUDGET,
    INDEX_AUTHORITY,
    INDEX_CAN_AUTHORIZE_CODE_CHANGE,
    INDEX_CAN_HIDE_LOW_RANK_FILES,
    INDEX_CAN_SATISFY_CANONICAL_EVIDENCE,
    INDEX_ONLY_SHADOW,
    AUTO_CONTEXT_SELECTION,
    GraphHealthStatus,
    RankingMode,
    SourceKind,
    StructuralSnapshot,
    render_budgeted_map,
)
from fiofilter.structural_python import PythonAstStructuralBackend

DEFAULT_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_A = pathlib.Path(
    r"C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl"
)
DEFAULT_OUTPUT_DIR = pathlib.Path(r"C:\Users\phped\.fiofilter\structural-shadow")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FioFilter M09 Discovery Structural Shadow Analysis"
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=DEFAULT_REPO_ROOT,
        help=f"Path to repository root (default: {DEFAULT_REPO_ROOT})",
    )
    parser.add_argument(
        "--source-a",
        type=pathlib.Path,
        default=DEFAULT_SOURCE_A,
        help="Path to historical Source A session JSONL",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write M09 artifacts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=25,
        help="Maximum eligible commits to evaluate in history benchmark (default: 25)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    source_a = args.source_a.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("==================================================================")
    print("FIOFILTER M09 DISCOVERY STRUCTURAL SHADOW BENCHMARK")
    print("==================================================================")
    print(f"Repository root: {repo_root}")
    print(f"Source A path:   {source_a}")
    print(f"Output dir:      {output_dir}")

    # ----------------------------------------------------
    # 1. Build Worktree Structural Snapshot
    # ----------------------------------------------------
    print("\n--- 1. BUILDING WORKTREE STRUCTURAL SNAPSHOT ---")
    t0_snap = time.perf_counter()
    backend = PythonAstStructuralBackend()
    snapshot = backend.build_snapshot_from_worktree(repo_root)
    snap_wall_time = time.perf_counter() - t0_snap

    print(f"  Snapshot ID:         {snapshot.snapshot_id}")
    print(f"  Source Kind:         {snapshot.source_kind.value}")
    print(f"  Git Head:            {snapshot.git_head}")
    print(f"  Dirty State:         {snapshot.dirty_state}")
    print(f"  Files Seen:          {snapshot.health.files_seen}")
    print(f"  Files Parsed:        {snapshot.health.files_parsed}")
    print(f"  Parse Failures:      {snapshot.health.parse_failures}")
    print(f"  Parse Coverage:      {snapshot.health.parse_coverage * 100:.1f}%")
    print(f"  Local Import Edges:  {snapshot.health.resolved_local_imports} / {snapshot.health.local_import_candidates}")
    print(f"  Edge Coverage:       {snapshot.health.edge_coverage * 100:.1f}%")
    print(f"  Graph Health Status: {snapshot.health.status.value}")
    print(f"  Total Extracted Sym: {len(snapshot.symbol_index.symbols)}")
    print(f"  Snapshot Build Time: {snap_wall_time * 1000:.2f} ms")

    # ----------------------------------------------------
    # 2. Render Budgeted Signature Maps
    # ----------------------------------------------------
    print("\n--- 2. RENDERING BUDGETED SIGNATURE MAPS (AIDER ADAPTATION) ---")
    ranker = StructuralRanker(snapshot)
    dummy_query = DiscoveryQueryExtractor(snapshot).extract_query("structural discovery index shadow")
    all_cands = ranker.rank_candidates(dummy_query, mode=RankingMode.LEXICAL_PLUS_PPR, top_k=len(snapshot.files))

    budget_experiments = {}
    for budget in [1024, 2048, 4096, 8192]:
        res = render_budgeted_map(all_cands, snapshot.symbol_index, budget_bytes=budget)
        budget_experiments[f"budget_{budget}_bytes"] = res.to_dict()
        print(
            f"  Budget {budget:5d} B -> Rendered {res.rendered_bytes:5d} B "
            f"(~{res.estimated_tokens:4d} tokens), "
            f"Included {res.included_files_count:2d}/{res.total_candidate_files} files "
            f"(truncated={res.truncated})"
        )

    # ----------------------------------------------------
    # 3. Commit-History Benchmark (FioFilter Repository)
    # ----------------------------------------------------
    print(f"\n--- 3. COMMIT-HISTORY BENCHMARK ({args.max_commits} COMMITS) ---")
    t0_bm = time.perf_counter()
    bm = CommitHistoryBenchmark(repo_root)
    bm_results = bm.run_benchmark(max_commits=args.max_commits)
    bm_wall_time = time.perf_counter() - t0_bm

    print(f"  Eligible Commits:   {bm_results.get('eligible_commits_count', 0)}")
    print(f"  Snapshots Built:    {bm_results.get('snapshots_built', 0)}")
    print(f"  Benchmark Run Time: {bm_wall_time:.2f} s")

    print("\n  ALL ELIGIBLE COMMITS RECALL SUMMARY:")
    for mode_name, metrics in bm_results.get("all_eligible_metrics", {}).items():
        print(
            f"    [{mode_name:23s}] "
            f"R@1={metrics['changed_file_recall_at_1'] * 100:5.1f}% | "
            f"R@3={metrics['changed_file_recall_at_3'] * 100:5.1f}% | "
            f"R@5={metrics['changed_file_recall_at_5'] * 100:5.1f}% | "
            f"R@10={metrics['changed_file_recall_at_10'] * 100:5.1f}% | "
            f"MRR={metrics['mrr']:0.4f} | "
            f"MissTop10={metrics['no_relevant_in_top10']}"
        )

    print("\n  NON-LEAKING SUBSET (STRICT AUDIT) RECALL SUMMARY:")
    for mode_name, metrics in bm_results.get("non_leaking_subset_metrics", {}).items():
        print(
            f"    [{mode_name:23s}] "
            f"R@1={metrics['recall_at_1'] * 100:5.1f}% | "
            f"R@3={metrics['recall_at_3'] * 100:5.1f}% | "
            f"R@5={metrics['recall_at_5'] * 100:5.1f}% | "
            f"R@10={metrics['recall_at_10'] * 100:5.1f}% | "
            f"MRR={metrics['mrr']:0.4f}"
        )

    # ----------------------------------------------------
    # 4. Source A Discovery Shadow Replay
    # ----------------------------------------------------
    print("\n--- 4. SOURCE A DISCOVERY SHADOW REPLAY ---")
    source_a_replay: Dict[str, Any] = {}
    if source_a.exists():
        t0_sa = time.perf_counter()
        census = ContextWasteCensus(source_a)
        census.load_session()

        episodes: Dict[str, List[Any]] = collections.defaultdict(list)
        for ev in census.events:
            episodes[ev.episode_id].append(ev)

        read_events = [ev for ev in census.events if ev.tool_family == "FILE_READ" and ev.target_path]
        distinct_read_targets = sorted(set(ev.target_path for ev in read_events))

        # Identify exploration phase (reads before first edit in each episode)
        exploration_reads_count = 0
        rereads_after_edit_count = 0
        episode_exploration_stats = []

        for ep_id, evs in episodes.items():
            reads = [e for e in evs if e.tool_family == "FILE_READ" and e.target_path]
            if not reads:
                continue
            edits = [e for e in evs if e.tool_family in ("FILE_WRITE", "FILE_EDIT", "DIFF_APPLY")]
            first_edit_idx = edits[0].record_index if edits else float("inf")

            pre_edit_reads = [r for r in reads if r.record_index < first_edit_idx]
            post_edit_reads = [r for r in reads if r.record_index >= first_edit_idx]

            exploration_reads_count += len(pre_edit_reads)
            rereads_after_edit_count += len(post_edit_reads)

            episode_exploration_stats.append(
                {
                    "episode_id": ep_id,
                    "total_events": len(evs),
                    "total_reads": len(reads),
                    "pre_edit_exploration_reads": len(pre_edit_reads),
                    "post_edit_reads": len(post_edit_reads),
                    "first_read_path": reads[0].target_path,
                }
            )

        sa_wall_time = time.perf_counter() - t0_sa

        source_a_replay = {
            "source_path": str(source_a),
            "total_events_scanned": len(census.events),
            "total_file_read_calls": len(read_events),
            "distinct_targets_read": len(distinct_read_targets),
            "episodes_with_file_reads": len(episode_exploration_stats),
            "pre_edit_exploration_reads": exploration_reads_count,
            "post_edit_reads": rereads_after_edit_count,
            "replay_wall_time_seconds": round(sa_wall_time, 2),
            "discovery_suppression_active": DISCOVERY_READ_SUPPRESSION,
            "auto_context_selection_active": AUTO_CONTEXT_SELECTION,
            "episodes_sample": episode_exploration_stats[:10],
        }

        print(f"  Source A Total Reads:        {len(read_events)}")
        print(f"  Distinct Targets Read:       {len(distinct_read_targets)}")
        print(f"  Pre-edit Exploration Reads:  {exploration_reads_count} ({exploration_reads_count / len(read_events) * 100:.1f}%)")
        print(f"  Post-edit Reads:             {rereads_after_edit_count} ({rereads_after_edit_count / len(read_events) * 100:.1f}%)")
        print(f"  Discovery Read Suppression:  {DISCOVERY_READ_SUPPRESSION} (NEVER ACTIVE)")
        print(f"  Auto Context Selection:      {AUTO_CONTEXT_SELECTION} (NEVER ACTIVE)")
    else:
        print(f"  WARNING: Source A file not found at {source_a}; skipping session scan.")
        source_a_replay = {"error": "SOURCE_A_NOT_FOUND"}

    # ----------------------------------------------------
    # 5. Emit Deterministic Artifacts
    # ----------------------------------------------------
    print("\n--- 5. EMITTING ARTIFACTS ---")

    # Artifact 1: m09_structural_snapshot_v1.json
    snapshot_artifact = {
        "snapshot_id": snapshot.snapshot_id,
        "source_kind": snapshot.source_kind.value,
        "git_head": snapshot.git_head,
        "dirty_state": snapshot.dirty_state,
        "build_wall_time_ms": round(snap_wall_time * 1000, 2),
        "health": snapshot.health.to_dict(),
        "files_count": len(snapshot.files),
        "files": sorted(snapshot.files),
        "symbols_count": len(snapshot.symbol_index.symbols),
        "edges_count": snapshot.file_graph.edge_count,
        "edges": [e.to_dict() for e in snapshot.file_graph.edges],
        "budgeted_map_experiments": budget_experiments,
        "invariants": {
            "INDEX_AUTHORITY": INDEX_AUTHORITY,
            "INDEX_CAN_SATISFY_CANONICAL_EVIDENCE": INDEX_CAN_SATISFY_CANONICAL_EVIDENCE,
            "INDEX_CAN_AUTHORIZE_CODE_CHANGE": INDEX_CAN_AUTHORIZE_CODE_CHANGE,
            "INDEX_CAN_HIDE_LOW_RANK_FILES": INDEX_CAN_HIDE_LOW_RANK_FILES,
            "BUDGET_APPLIES_TO_INDEX_ONLY": BUDGET_APPLIES_TO_INDEX_ONLY,
            "EVIDENCE_OVERRIDES_BUDGET": EVIDENCE_OVERRIDES_BUDGET,
            "DISCOVERY_READ_SUPPRESSION": DISCOVERY_READ_SUPPRESSION,
            "AUTO_CONTEXT_SELECTION": AUTO_CONTEXT_SELECTION,
            "INDEX_ONLY_SHADOW": INDEX_ONLY_SHADOW,
        },
    }
    p1 = output_dir / "m09_structural_snapshot_v1.json"
    p1.write_text(json.dumps(snapshot_artifact, indent=2), encoding="utf-8")
    print(f"  Wrote: {p1} ({p1.stat().st_size:,} bytes)")

    # Artifact 2: m09_commit_benchmark_v1.json
    p2 = output_dir / "m09_commit_benchmark_v1.json"
    p2.write_text(json.dumps(bm_results, indent=2), encoding="utf-8")
    print(f"  Wrote: {p2} ({p2.stat().st_size:,} bytes)")

    # Artifact 3: m09_source_a_discovery_shadow_v1.json
    p3 = output_dir / "m09_source_a_discovery_shadow_v1.json"
    p3.write_text(json.dumps(source_a_replay, indent=2), encoding="utf-8")
    print(f"  Wrote: {p3} ({p3.stat().st_size:,} bytes)")

    # Artifact 4: m09_structural_summary_v1.json
    summary_artifact = {
        "mission_id": "FIOFILTER-M09-DISCOVERY-STRUCTURAL-SHADOW",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "worktree_snapshot": {
            "snapshot_id": snapshot.snapshot_id,
            "files": len(snapshot.files),
            "symbols": len(snapshot.symbol_index.symbols),
            "edges": snapshot.file_graph.edge_count,
            "health_status": snapshot.health.status.value,
            "edge_coverage": snapshot.health.edge_coverage,
            "parse_coverage": snapshot.health.parse_coverage,
        },
        "commit_benchmark": {
            "commits_evaluated": bm_results.get("eligible_commits_count", 0),
            "snapshots_built": bm_results.get("snapshots_built", 0),
            "all_eligible_metrics": bm_results.get("all_eligible_metrics", {}),
            "non_leaking_subset_metrics": bm_results.get("non_leaking_subset_metrics", {}),
        },
        "source_a_discovery_shadow": {
            "total_file_read_calls": source_a_replay.get("total_file_read_calls", 0),
            "distinct_targets": source_a_replay.get("distinct_targets_read", 0),
            "pre_edit_exploration_reads": source_a_replay.get("pre_edit_exploration_reads", 0),
            "post_edit_reads": source_a_replay.get("post_edit_reads", 0),
        },
        "invariants": {
            "INDEX_AUTHORITY": INDEX_AUTHORITY,
            "DISCOVERY_READ_SUPPRESSION": DISCOVERY_READ_SUPPRESSION,
            "AUTO_CONTEXT_SELECTION": AUTO_CONTEXT_SELECTION,
            "BUDGET_APPLIES_TO_INDEX_ONLY": BUDGET_APPLIES_TO_INDEX_ONLY,
            "EVIDENCE_OVERRIDES_BUDGET": EVIDENCE_OVERRIDES_BUDGET,
            "INDEX_ONLY_SHADOW": INDEX_ONLY_SHADOW,
        },
        "donor_mechanisms_applied": {
            "Aider_RepoMap": [
                "Personalized PageRank (PPR)",
                "Compact budgeted symbol signature summaries",
                "Task personalization seeds",
            ],
            "AgentMap": [
                "Strict separation of FILE_GRAPH from SYMBOL_INDEX",
                "Graph health accounting (parse coverage & edge coverage)",
                "Distinction of local candidate imports vs external/stdlib dependencies",
            ],
        },
    }
    p4 = output_dir / "m09_structural_summary_v1.json"
    p4.write_text(json.dumps(summary_artifact, indent=2), encoding="utf-8")
    print(f"  Wrote: {p4} ({p4.stat().st_size:,} bytes)")

    print("\n==================================================================")
    print("M09 DISCOVERY STRUCTURAL SHADOW EXECUTION COMPLETE")
    print("==================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
