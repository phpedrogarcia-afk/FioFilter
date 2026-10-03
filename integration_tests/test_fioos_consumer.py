"""Explicit Python 3.11+ integration tests for the pinned public FioOS core.

Run with: python -m pytest integration_tests/test_fioos_consumer.py -q
This directory is deliberately outside FioFilter's default Python 3.9 suite.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from fiofilter.fioos_consumer import (
    FioFilterWorkItemConsumer,
    WORK_ITEM_CATALOG,
    WORKSPACE_ID,
    CAPABILITY,
    OPERATION,
)


HEAD = "b740b7813c50d2a05a689041c5f4cb3b761cf394"
CREATED_AT = "2026-10-02T12:00:00Z"


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "FioFilter"
    repo.mkdir()
    for definition in WORK_ITEM_CATALOG.values():
        for reference in definition.evidence_refs:
            target = repo / Path(*reference.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture evidence\n", encoding="utf-8")
    outbox_base = repo / "fioos-outbox"
    outbox_base.mkdir()
    outbox = outbox_base / "run-001"
    outbox.mkdir()
    return repo, outbox


def make_consumer(tmp_path: Path) -> tuple[FioFilterWorkItemConsumer, Path]:
    repo, outbox = make_repo(tmp_path)
    consumer = FioFilterWorkItemConsumer(
        repo_root=repo,
        outbox_dir=outbox,
        canonical_head=HEAD,
        created_at=CREATED_AT,
    )
    return consumer, outbox


def make_proposal(
    reason_code: str,
    proposal_id: str = "proposal-001",
    **overrides: object,
) -> dict[str, object]:
    definition = WORK_ITEM_CATALOG[reason_code]
    payload: dict[str, object] = {
        "proposal_id": proposal_id,
        "source_id": "local-review-agent",
        "source_revision": "fixture-v1",
        "objective": "Review one documented FioFilter uncertainty.",
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
    payload.update(overrides)
    return payload


def read_records(outbox: Path) -> list[dict[str, object]]:
    path = outbox / "notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("reason_code", sorted(WORK_ITEM_CATALOG))
def test_each_catalogued_proposal_emits_one_correlated_human_review_item(
    tmp_path: Path, reason_code: str
) -> None:
    consumer, outbox = make_consumer(tmp_path)
    receipt = consumer.submit(make_proposal(reason_code))

    records = read_records(outbox)
    assert receipt.decision == "ALLOW"
    assert receipt.status == "SUCCEEDED"
    assert receipt.effect_count == 1
    assert receipt.evidence_ref == "notes.jsonl"
    assert len(records) == 1
    assert records[0]["request_id"] == receipt.request_id
    item = json.loads(records[0]["text"])
    assert item["result_id"] == receipt.result_id
    assert item["canonical_head_observed"] == HEAD
    assert item["reason_code"] == reason_code
    assert item["status"] == "PROPOSED_REQUIRES_HUMAN_REVIEW"
    assert item["authority_decision"] == "A0_GATEWAY_POLICY_ALLOW"
    assert "authorized" not in item


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("wrong_project", "PROJECT_OR_SCOPE_NOT_ALLOWED"),
        ("wrong_scope", "PROJECT_OR_SCOPE_NOT_ALLOWED"),
        ("wrong_tool", "TOOL_NOT_ALLOWED"),
        ("self_authorized_wrong_scope", "PROJECT_OR_SCOPE_NOT_ALLOWED"),
        ("top_level_authorized", "ADMISSION_REJECTED:UNKNOWN_FIELD"),
        ("wrong_evidence", "EVIDENCE_REFS_NOT_ALLOWED"),
    ],
)
def test_unauthorized_or_out_of_scope_proposals_have_no_file_effect(
    tmp_path: Path, mutation: str, expected_reason: str
) -> None:
    consumer, outbox = make_consumer(tmp_path)
    payload = make_proposal("M20_QUALITY_UNMEASURED")
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)

    if mutation == "wrong_project":
        metadata["target_project"] = "ProjetoFio"
    elif mutation == "wrong_scope":
        metadata["target_scope"] = "fiofilter/"
    elif mutation == "wrong_tool":
        payload["requested_tools"] = ["shell.execute"]
    elif mutation == "self_authorized_wrong_scope":
        metadata["authorized"] = True
        metadata["target_scope"] = "fiofilter/"
    elif mutation == "top_level_authorized":
        payload["authorized"] = True
    elif mutation == "wrong_evidence":
        metadata["evidence_refs"] = ["../private.txt"]

    receipt = consumer.submit(payload)
    assert receipt.decision == "DENY"
    assert receipt.effect_count == 0
    assert expected_reason in (receipt.reason or "")
    assert read_records(outbox) == []


def test_malformed_and_oversize_proposals_fail_closed(tmp_path: Path) -> None:
    consumer, outbox = make_consumer(tmp_path)
    malformed = make_proposal("M20_QUALITY_UNMEASURED", proposal_id="missing-objective")
    malformed.pop("objective")
    oversized = make_proposal("M20_QUALITY_UNMEASURED", proposal_id="oversized")
    oversized["objective"] = "x" * 2_001
    invalid_reason = make_proposal("M20_QUALITY_UNMEASURED", proposal_id="bad-reason")
    invalid_reason["metadata"]["reason_code"] = []  # type: ignore[index]
    invalid_refs = make_proposal("M20_QUALITY_UNMEASURED", proposal_id="bad-refs")
    invalid_refs["metadata"]["evidence_refs"] = "docs/DECISIONS.md"  # type: ignore[index]

    assert consumer.submit(None).effect_count == 0  # type: ignore[arg-type]
    assert consumer.submit(malformed).effect_count == 0
    assert consumer.submit(oversized).effect_count == 0
    assert consumer.submit(invalid_reason).reason == "REASON_CODE_INVALID"
    assert consumer.submit(invalid_refs).reason == "EVIDENCE_REFS_INVALID"
    assert read_records(outbox) == []


def test_same_request_replay_is_idempotent_but_not_durable(tmp_path: Path) -> None:
    consumer, outbox = make_consumer(tmp_path)
    proposal = make_proposal("M20_QUALITY_UNMEASURED", proposal_id="replay-001")
    first = consumer.submit(proposal)
    proposal["metadata"]["authorized"] = True  # type: ignore[index]
    replay = consumer.submit(proposal)

    assert first == replay
    assert len(read_records(outbox)) == 1
    assert first.effect_count == 1


def test_same_id_changed_content_is_denied_without_second_effect(tmp_path: Path) -> None:
    consumer, outbox = make_consumer(tmp_path)
    first = consumer.submit(
        make_proposal("M20_QUALITY_UNMEASURED", proposal_id="conflict-001")
    )
    conflict = consumer.submit(
        make_proposal("M04_PRODUCER_PROVENANCE", proposal_id="conflict-001")
    )

    assert first.status == "SUCCEEDED"
    assert conflict.decision == "DENY"
    assert conflict.reason == "REQUEST_ID_CONFLICT"
    assert conflict.effect_count == 0
    assert len(read_records(outbox)) == 1


def test_effect_uses_no_git_network_or_source_write(tmp_path: Path) -> None:
    consumer, outbox = make_consumer(tmp_path)
    repo = consumer.repo_root
    source_files = sorted((repo / "fiofilter").rglob("*.py"))
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external process or network call attempted by effect")

    with (
        patch.object(subprocess, "run", forbidden),
        patch.object(subprocess, "Popen", forbidden),
        patch.object(os, "system", forbidden),
        patch.object(socket, "create_connection", forbidden),
        patch.object(socket.socket, "connect", forbidden),
        patch.object(urllib.request, "urlopen", forbidden),
    ):
        receipt = consumer.submit(
            make_proposal("M04_PRODUCER_PROVENANCE", proposal_id="local-only")
        )

    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    assert receipt.status == "SUCCEEDED"
    assert before == after
    assert len(read_records(outbox)) == 1


def test_outbox_must_be_empty_and_inside_dedicated_fiofilter_directory(
    tmp_path: Path,
) -> None:
    repo, outbox = make_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    kwargs = {"repo_root": repo, "canonical_head": HEAD, "created_at": CREATED_AT}
    with pytest.raises(ValueError, match="OUTBOX_OUTSIDE_DEDICATED_DIRECTORY"):
        FioFilterWorkItemConsumer(outbox_dir=outside, **kwargs)

    (outbox / "prior.txt").write_text("do not append to an old run", encoding="utf-8")
    with pytest.raises(ValueError, match="OUTBOX_DIRECTORY_NOT_EMPTY"):
        FioFilterWorkItemConsumer(outbox_dir=outbox, **kwargs)


def test_windows_outbox_junction_cannot_redirect_pilot_outside_repository(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction behavior is platform-specific")

    from scripts.fioos_first_consumer_pilot import run_pilot

    repo, _ = make_repo(tmp_path)
    outbox_base = repo / "fioos-outbox"
    (outbox_base / "run-001").rmdir()
    outbox_base.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    command = f'mklink /J "{outbox_base}" "{outside}"'
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not outbox_base.is_symlink()
    assert outbox_base.resolve(strict=True) == outside.resolve(strict=True)

    with pytest.raises(ValueError, match="OUTBOX_BASE_OUTSIDE_REPOSITORY"):
        run_pilot(repo, HEAD)

    kwargs = {"repo_root": repo, "canonical_head": HEAD, "created_at": CREATED_AT}
    with pytest.raises(ValueError, match="OUTBOX_BASE_OUTSIDE_REPOSITORY"):
        FioFilterWorkItemConsumer(
            outbox_dir=outbox_base / "run-001",
            **kwargs,
        )
    assert list(outside.iterdir()) == []
