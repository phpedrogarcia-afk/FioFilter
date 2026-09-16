"""CLI runner for the offline Context Waste Census (M05).

Extracts and analyzes historical coding-agent sessions to measure empirical
reexposure waste, representation waste, and discovery costs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import tempfile
from dataclasses import asdict
from typing import Any, Dict

from fiofilter.context_census import CENSUS_SCHEMA_VERSION, ContextWasteCensus


def _publish_no_clobber(source: pathlib.Path, target: pathlib.Path) -> None:
    """Safely publish output to target without overwriting existing files."""
    if target.exists():
        raise FileExistsError(f"Target file already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, target)
    source.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline Context Waste Census")
    parser.add_argument("--session", required=True, help="Path to input session JSONL")
    parser.add_argument("--events-output", required=True, help="Path to output events JSONL")
    parser.add_argument("--manifest-output", required=True, help="Path to output manifest JSON")
    parser.add_argument("--summary-output", required=True, help="Path to output summary JSON")
    parser.add_argument("--observation-date", default="2026-09-16", help="Observation date")
    args = parser.parse_args()

    session_path = pathlib.Path(args.session).resolve()
    if not session_path.exists():
        raise FileNotFoundError(f"Session not found: {session_path}")

    # Verify fingerprint
    session_bytes = session_path.read_bytes()
    session_sha256 = hashlib.sha256(session_bytes).hexdigest()
    session_size = len(session_bytes)

    census = ContextWasteCensus(session_path)
    summary = census.analyze()

    events_out = pathlib.Path(args.events_output).resolve()
    manifest_out = pathlib.Path(args.manifest_output).resolve()
    summary_out = pathlib.Path(args.summary_output).resolve()

    for p in (events_out, manifest_out, summary_out):
        if p.exists():
            raise FileExistsError(f"Target already exists: {p}")

    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="fio_census_"))
    temp_events = temp_dir / "events.jsonl"
    temp_manifest = temp_dir / "manifest.json"
    temp_summary = temp_dir / "summary.json"

    try:
        with open(temp_events, "w", encoding="utf-8") as f:
            for ev in census.events:
                f.write(json.dumps(asdict(ev), sort_keys=True) + "\n")

        manifest_data = {
            "schema_version": CENSUS_SCHEMA_VERSION,
            "observation_date": args.observation_date,
            "session_fingerprint": {
                "absolute_path_local_only": str(session_path),
                "filename": session_path.name,
                "size_bytes": session_size,
                "sha256": session_sha256,
            },
            "events_count": len(census.events),
            "episodes_count": len(census.episodes),
            "summary": summary,
        }

        with open(temp_manifest, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest_data, indent=2, sort_keys=True) + "\n")

        with open(temp_summary, "w", encoding="utf-8") as f:
            f.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")

        _publish_no_clobber(temp_events, events_out)
        _publish_no_clobber(temp_manifest, manifest_out)
        _publish_no_clobber(temp_summary, summary_out)

        print(json.dumps(summary, indent=2, sort_keys=True))

    finally:
        for tmp_f in (temp_events, temp_manifest, temp_summary):
            if tmp_f.exists():
                tmp_f.unlink()
        if temp_dir.exists():
            temp_dir.rmdir()


if __name__ == "__main__":
    main()
