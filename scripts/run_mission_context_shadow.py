"""Run one explicit M15-S1 mission prompt shadow measurement."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Optional, Sequence

from fiofilter.mission_context_shadow import MissionContextShadowAnalyzer, load_manifest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--mission", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    mission = args.mission.read_bytes()
    result = MissionContextShadowAnalyzer(args.repo).analyze(mission, manifest)
    print(json.dumps(result.to_record(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
