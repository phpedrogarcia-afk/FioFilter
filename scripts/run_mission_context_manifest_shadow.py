"""Measure one exact mission plus FIO_MISSION_CONTEXT_MANIFEST_V1 in shadow."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Optional, Sequence

from fiofilter.mission_context_manifest import measure_manifest_shadow
from fiofilter.mission_context_shadow import EvidenceQuality


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--mission", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument(
        "--evidence-quality",
        choices=[item.value for item in EvidenceQuality],
        required=True,
    )
    args = parser.parse_args(argv)

    result = measure_manifest_shadow(
        args.mission.read_bytes(),
        args.manifest.read_bytes(),
        args.repo,
        evidence_quality=EvidenceQuality(args.evidence_quality),
    )
    print(json.dumps(result.to_record(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
