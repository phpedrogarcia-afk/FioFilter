"""
fiofilter.cli — Unified explicit CLI entry point for FioFilter V0.

Commands:
  status           Report capability lifecycle states and operational invariants
  inspect-repo     Inspect repository HEAD and content-sensitive V2 digest
  discovery-shadow Run discovery shadow navigation on task query
  read-shadow      Evaluate a file read through the read-receipt shadow harness
  run-lab-scenario Run deterministic end-to-end V0 integration scenario

Note:
  T02_DIRECT_CLI = DEFERRED_UNTIL_A_CLEAN_EXPLICIT_EVIDENCE_INTERFACE_IS_JUSTIFIED
  T02 remains available through programmatic V0 API and integrated lab scenario.
  ENGINE_METADATA_GATE_REMAINS in force.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional

from fiofilter.v0 import FioFilterV0Lab, V0_CAPABILITY_REGISTRY, V0Config
from fiofilter.discovery_runtime_shadow import get_worktree_state_digest_v2


def cmd_status(lab: FioFilterV0Lab, args: argparse.Namespace) -> int:
    status = lab.get_status()
    if args.json:
        payload = {
            "status": status,
            "capabilities": {
                k: {
                    "id": c.capability_id,
                    "version": c.version,
                    "name": c.name,
                    "lifecycle_state": c.lifecycle_state.value,
                    "authority": c.authority,
                    "activation_mode": c.activation_mode,
                    "evidence_gate": c.evidence_gate,
                    "production_status": c.production_status,
                }
                for k, c in V0_CAPABILITY_REGISTRY.items()
            },
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("=" * 60)
    print("FioFilter V0 Laboratory Status")
    print("=" * 60)
    for k, v in status.items():
        print(f"  {k:<28} = {v}")
    print("\nCapabilities:")
    for k, c in V0_CAPABILITY_REGISTRY.items():
        print(f"  [{c.lifecycle_state.value}] {k} ({c.capability_id} v{c.version})")
        print(f"      Authority: {c.authority} | Activation: {c.activation_mode}")
        print(f"      Evidence Gate: {c.evidence_gate} | Prod Status: {c.production_status}")
    return 0


def cmd_inspect_repo(lab: FioFilterV0Lab, args: argparse.Namespace) -> int:
    root = pathlib.Path(args.path).resolve()
    v2_digest = get_worktree_state_digest_v2(root)
    ev = lab.discovery_shadow.evaluate(root, "test query", top_k=1)
    
    info = {
        "repo_path": str(root),
        "head_sha": ev.head_sha if ev else "UNKNOWN",
        "worktree_state_digest_v2": v2_digest,
        "dirty_digest": ev.dirty_digest if ev else "UNKNOWN",
        "files_indexed": ev.files_indexed if ev else 0,
        "file_universe_policy": "PYTHON_SOURCES_V1",
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"Repository: {info['repo_path']}")
        print(f"HEAD:       {info['head_sha']}")
        print(f"Digest V2:  {info['worktree_state_digest_v2']}")
        print(f"Files:      {info['files_indexed']}")
    return 0


def cmd_discovery_shadow(lab: FioFilterV0Lab, args: argparse.Namespace) -> int:
    root = pathlib.Path(args.path).resolve()
    ev = lab.evaluate_discovery(root, args.query, top_k=args.top_k)
    if ev is None:
        print("ERROR: Discovery shadow evaluation failed (fail open to RAW).", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(ev.to_dict(), indent=2))
    else:
        print(f"Discovery Shadow Evaluation (query: {args.query!r})")
        print(f"Snapshot ID: {ev.snapshot_id} | Evaluation Hash: {ev.evaluation_hash}")
        print(f"Total time: {ev.total_ms:.2f} ms ({ev.query_type})")
        print("\nTop Candidates:")
        for c in ev.candidates:
            print(f"  [{c.rank:02d}] {c.score:.4f} {c.path} (matched: {c.matched_tokens})")
    return 0


def cmd_read_shadow(lab: FioFilterV0Lab, args: argparse.Namespace) -> int:
    file_path = pathlib.Path(args.file).resolve()
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return 1
    raw_bytes, decision = lab.evaluate_read_shadow(file_path)
    info = {
        "file_path": str(file_path),
        "raw_bytes": len(raw_bytes),
        "disposition": decision.disposition.value,
        "freshness_level": decision.freshness_level.value if decision.freshness_level else None,
        "hypothetical_reference": decision.hypothetical_reference,
        "hypothetical_bytes_avoided": decision.hypothetical_bytes_avoided,
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"Read Shadow: {file_path}")
        print(f"Delivered: {len(raw_bytes)} RAW bytes")
        print(f"Disposition: {decision.disposition.value}")
        if decision.hypothetical_reference:
            print(f"Hypothetical Reference: {decision.hypothetical_reference}")
            print(f"Hypothetical Bytes Avoided: {decision.hypothetical_bytes_avoided}")
    return 0


def cmd_run_lab_scenario(lab: FioFilterV0Lab, args: argparse.Namespace) -> int:
    root = pathlib.Path(args.path).resolve()
    results = lab.run_lab_scenario(root, task_query=args.query)
    print(json.dumps(results, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fiofilter",
        description="FioFilter V0 Explicit Integration Spine CLI",
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    p_status = subparsers.add_parser("status", help="Report capability and system status")
    p_status.set_defaults(func=cmd_status)

    # inspect-repo
    p_inspect = subparsers.add_parser("inspect-repo", help="Inspect repository HEAD and V2 digest")
    p_inspect.add_argument("path", nargs="?", default=".", help="Repository root path")
    p_inspect.set_defaults(func=cmd_inspect_repo)

    # discovery-shadow
    p_disc = subparsers.add_parser("discovery-shadow", help="Run discovery shadow evaluation")
    p_disc.add_argument("query", help="Task query string")
    p_disc.add_argument("path", nargs="?", default=".", help="Repository root path")
    p_disc.add_argument("--top-k", type=int, default=10, help="Candidate count (default 10)")
    p_disc.set_defaults(func=cmd_discovery_shadow)

    # read-shadow
    p_read = subparsers.add_parser("read-shadow", help="Evaluate a file read through shadow harness")
    p_read.add_argument("file", help="Path to file to read")
    p_read.set_defaults(func=cmd_read_shadow)

    # run-lab-scenario
    p_lab = subparsers.add_parser("run-lab-scenario", help="Run end-to-end integration lab scenario")
    p_lab.add_argument("path", nargs="?", default=".", help="Repository root path")
    p_lab.add_argument("--query", default="update read receipt freshness check", help="Scenario task query")
    p_lab.set_defaults(func=cmd_run_lab_scenario)

    parsed = parser.parse_args(argv)
    if not parsed.command:
        parser.print_help()
        return 1

    lab = FioFilterV0Lab()
    return parsed.func(lab, parsed)


if __name__ == "__main__":
    sys.exit(main())