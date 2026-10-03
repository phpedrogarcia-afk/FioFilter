"""Run one finite, local FioOS -> FioFilter work-item emission pilot.

The caller supplies the already-observed canonical FioFilter HEAD. This script
does not invoke Git, a model, a network service, cloud infrastructure, or shell
effects through FioOS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import urllib.request
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Prefer this checkout over any unrelated editable FioFilter installation.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) in sys.path:
    sys.path.remove(str(_REPOSITORY_ROOT))
sys.path.insert(0, str(_REPOSITORY_ROOT))

from fiofilter.fioos_consumer import (
    CAPABILITY,
    OPERATION,
    FioFilterWorkItemConsumer,
    WORK_ITEM_CATALOG,
)


def _proposal(reason_code: str, proposal_id: str) -> dict[str, object]:
    definition = WORK_ITEM_CATALOG[reason_code]
    return {
        "proposal_id": proposal_id,
        "source_id": "fiofilter-local-pilot",
        "source_revision": "main-b740b78",
        "objective": "Review a documented FioFilter development uncertainty.",
        "requested_capabilities": [CAPABILITY],
        "requested_tools": [OPERATION],
        "metadata": {
            "target_project": "FioFilter",
            "target_scope": definition.target_scope,
            "proposal_type": definition.proposal_type,
            "reason_code": reason_code,
            "evidence_refs": list(definition.evidence_refs),
        },
    }


def _guard_external_io(stack: ExitStack) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GIT_OR_NETWORK_CALL_DURING_PILOT_EFFECT")

    stack.enter_context(patch.object(subprocess, "run", forbidden))
    stack.enter_context(patch.object(subprocess, "Popen", forbidden))
    stack.enter_context(patch.object(os, "system", forbidden))
    stack.enter_context(patch.object(socket, "create_connection", forbidden))
    stack.enter_context(patch.object(socket.socket, "connect", forbidden))
    stack.enter_context(patch.object(urllib.request, "urlopen", forbidden))


def _source_digest_map(repo_root: Path) -> dict[str, str]:
    files = sorted((repo_root / "fiofilter").rglob("*.py"))
    return {
        path.relative_to(repo_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }


def run_pilot(repo_root: Path, canonical_head: str) -> dict[str, object]:
    repo_root = repo_root.resolve(strict=True)
    outbox_base = repo_root / "fioos-outbox"
    outbox_base.mkdir(exist_ok=True)
    resolved_outbox_base = outbox_base.resolve(strict=True)
    if not resolved_outbox_base.is_relative_to(repo_root):
        raise ValueError("OUTBOX_BASE_OUTSIDE_REPOSITORY")
    if resolved_outbox_base != outbox_base:
        raise ValueError("OUTBOX_BASE_REDIRECTED")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    outbox = resolved_outbox_base / ("pilot-" + run_id)
    outbox.mkdir()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    consumer = FioFilterWorkItemConsumer(
        repo_root=repo_root,
        outbox_dir=outbox,
        canonical_head=canonical_head,
        created_at=created_at,
    )

    cases: list[tuple[str, dict[str, object]]] = [
        ("VALID", _proposal(code, "candidate-" + str(index)))
        for index, code in enumerate(WORK_ITEM_CATALOG, start=1)
    ]

    wrong_project = _proposal("M20_QUALITY_UNMEASURED", "wrong-project")
    wrong_project["metadata"]["target_project"] = "ProjetoFio"  # type: ignore[index]
    cases.append(("DENY", wrong_project))

    wrong_scope = _proposal("M20_QUALITY_UNMEASURED", "wrong-scope")
    wrong_scope["metadata"]["target_scope"] = "fiofilter/"  # type: ignore[index]
    cases.append(("DENY", wrong_scope))

    wrong_tool = _proposal("M20_QUALITY_UNMEASURED", "wrong-tool")
    wrong_tool["requested_tools"] = ["shell.execute"]
    cases.append(("DENY", wrong_tool))

    claimed_authority = _proposal("M20_QUALITY_UNMEASURED", "claimed-authority")
    claimed_authority["metadata"]["authorized"] = True  # type: ignore[index]
    claimed_authority["metadata"]["target_scope"] = "fiofilter/"  # type: ignore[index]
    cases.append(("DENY", claimed_authority))

    top_level_authority = _proposal("M20_QUALITY_UNMEASURED", "top-level-authority")
    top_level_authority["authorized"] = True
    cases.append(("DENY", top_level_authority))

    malformed = _proposal("M20_QUALITY_UNMEASURED", "malformed")
    malformed.pop("objective")
    cases.append(("DENY", malformed))

    oversized = _proposal("M20_QUALITY_UNMEASURED", "oversized")
    oversized["objective"] = "x" * 2_001
    cases.append(("DENY", oversized))

    untrusted_identity = _proposal("M20_QUALITY_UNMEASURED", "identity-no-grant")
    untrusted_identity["source_id"] = "trusted"
    untrusted_identity["requested_capabilities"] = ["admin"]
    untrusted_identity["requested_tools"] = ["shell.execute"]
    cases.append(("DENY", untrusted_identity))

    replay = _proposal("M20_QUALITY_UNMEASURED", "candidate-1")
    replay["metadata"]["authorized"] = True  # type: ignore[index]
    cases.append(("REPLAY", replay))

    conflict = _proposal("M04_PRODUCER_PROVENANCE", "candidate-1")
    cases.append(("DENY", conflict))

    source_before = _source_digest_map(repo_root)
    receipts: list[dict[str, object]] = []
    failures = 0
    with ExitStack() as stack:
        _guard_external_io(stack)
        for kind, proposal in cases:
            receipt = consumer.submit(proposal)
            receipts.append(
                {
                    "case": kind,
                    "proposal_id": receipt.proposal_id,
                    "request_id": receipt.request_id,
                    "decision": receipt.decision,
                    "status": receipt.status,
                    "effect_count": receipt.effect_count,
                    "result_id": receipt.result_id,
                    "reason": receipt.reason,
                }
            )
            if kind == "VALID" and not (
                receipt.decision == "ALLOW"
                and receipt.status == "SUCCEEDED"
                and receipt.effect_count == 1
            ):
                failures += 1
            if kind == "DENY" and not (
                receipt.decision == "DENY" and receipt.effect_count == 0
            ):
                failures += 1
            if kind == "REPLAY" and not (
                receipt.decision == "ALLOW"
                and receipt.status == "SUCCEEDED"
                and receipt.effect_count == 1
            ):
                failures += 1

    source_after = _source_digest_map(repo_root)
    artifact_path = outbox / "notes.jsonl"
    records = [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
    ] if artifact_path.exists() else []
    items = [json.loads(record["text"]) for record in records]
    item_ids = [item["work_item_id"] for item in items]
    request_ids = [record["request_id"] for record in records]
    duplicates = len(item_ids) - len(set(item_ids)) + len(request_ids) - len(set(request_ids))
    correlation_failures = sum(
        1
        for record, item in zip(records, items)
        if record["request_id"] != item["request_id"]
        or item["result_id"] != "effect:" + item["request_id"]
        or item["canonical_head_observed"] != canonical_head
    )
    if len(records) != len(WORK_ITEM_CATALOG) or duplicates or correlation_failures:
        failures += 1
    if source_before != source_after:
        failures += 1

    authorized = sum(1 for item in receipts if item["case"] == "VALID")
    denied = sum(1 for item in receipts if item["case"] == "DENY")
    replayed = sum(1 for item in receipts if item["case"] == "REPLAY")
    unknown = sum(1 for item in receipts if item["status"] == "UNKNOWN")
    return {
        "proposals": len(cases),
        "authorized": authorized,
        "denied": denied,
        "replayed": replayed,
        "artifacts": len(records),
        "duplicate_artifacts": duplicates,
        "unknown": unknown,
        "failures": failures,
        "authority_bypasses": 0 if all(
            item["case"] != "DENY" or item["effect_count"] == 0 for item in receipts
        ) else 1,
        "source_files_unchanged": source_before == source_after,
        "network_or_git_calls": 0,
        "outbox": str(artifact_path),
        "outbox_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if artifact_path.exists()
        else None,
        "receipts": receipts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-head", required=True)
    parser.add_argument(
        "--repo-root", type=Path, default=_REPOSITORY_ROOT
    )
    args = parser.parse_args()
    report = run_pilot(args.repo_root.resolve(strict=True), args.canonical_head)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["failures"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
