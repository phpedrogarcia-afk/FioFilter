"""M15-S2 compact Mission Context manifest regressions."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

import pytest

from fiofilter.mission_context import SafetyAssessment
from fiofilter.mission_context_manifest import (
    MANIFEST_SCHEMA_VERSION,
    CanonicalArtifactProof,
    ManifestDisposition,
    ManifestEntry,
    MissionContextManifest,
    encode_manifest,
    measure_manifest_shadow,
    parse_manifest,
)
from fiofilter.mission_context_shadow import EvidenceQuality


def _tracked_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def _manifest(raw: bytes, entries=()) -> MissionContextManifest:
    return MissionContextManifest(
        mission_id="FIOFILTER-M15-S2-TEST",
        mission_sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes=len(raw),
        entries=tuple(entries),
        sensitivity_assessment=SafetyAssessment.NON_SENSITIVE,
    )


def _canonical_proof(repo: pathlib.Path, segment: bytes) -> CanonicalArtifactProof:
    artifact = b"artifact-prefix\n" + segment + b"artifact-suffix\n"
    path = repo / "docs" / "canonical.txt"
    path.parent.mkdir()
    path.write_bytes(artifact)
    subprocess.run(["git", "-C", str(repo), "add", "docs/canonical.txt"], check=True)
    start = artifact.index(segment)
    return CanonicalArtifactProof(
        repository_path="docs/canonical.txt",
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        artifact_start=start,
        artifact_end=start + len(segment),
    )


def _measure(repo: pathlib.Path, raw: bytes, manifest_bytes: bytes):
    return measure_manifest_shadow(
        raw, manifest_bytes, repo, evidence_quality=EvidenceQuality.SYNTHETIC,
    )


def test_schema_is_compact_deterministic_and_roundtrips() -> None:
    raw = b"critical\ndelta\n"
    manifest = _manifest(raw, (
        ManifestEntry(0, 9, ManifestDisposition.INLINE_CRITICAL),
        ManifestEntry(9, len(raw), ManifestDisposition.DELTA),
    ))

    first = encode_manifest(manifest)
    second = encode_manifest(manifest)

    assert first == second
    assert first.endswith(b"\n")
    assert b'"v":"FIO_MISSION_CONTEXT_MANIFEST_V1"' in first
    assert parse_manifest(first) == manifest
    assert encode_manifest(parse_manifest(first)) == first


@pytest.mark.parametrize("manifest_bytes", [
    b"not json\n",
    b"{}\n",
    b'{"e":[],"e":[],"h":"' + b"0" * 64 + b'","m":"X","n":0,"s":"NON_SENSITIVE","v":"FIO_MISSION_CONTEXT_MANIFEST_V1"}\n',
    b'{"e":[],"h":"' + b"0" * 64 + b'","m":"X","n":0,"s":"NON_SENSITIVE","v":"WRONG"}\n',
    b'{"e":[],"h":"' + b"0" * 64 + b'","m":"X","n":0,"prompt":"secret","s":"NON_SENSITIVE","v":"FIO_MISSION_CONTEXT_MANIFEST_V1"}\n',
])
def test_malformed_manifest_fails_conservative(
    tmp_path: pathlib.Path, manifest_bytes: bytes
) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"opaque mission bytes\n"

    result = _measure(repo, raw, manifest_bytes)

    assert result.delivered_mission_bytes == raw
    assert result.unknown_bytes == len(raw)
    assert result.verified_canonical_reference_bytes == 0
    assert result.proven_reexposure_bytes == 0
    assert result.net_candidate_reduction_bytes == -len(manifest_bytes)
    assert result.proof_outcome == "MALFORMED_MANIFEST_CONSERVATIVE"


def test_mission_binding_failure_is_unknown_and_inline(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"exact mission\n"
    manifest = _manifest(b"different mission\n")

    result = _measure(repo, raw, encode_manifest(manifest))

    assert result.delivered_mission_bytes == raw
    assert result.unknown_bytes == len(raw)
    assert result.proof_outcome == "MISSION_BINDING_FAILED_CONSERVATIVE"
    assert result.proof_failures == ("MISSION_LENGTH_OR_SHA256_MISMATCH",)


@pytest.mark.parametrize("defect", ["missing", "hash"])
def test_missing_or_wrong_canonical_artifact_is_unknown(
    tmp_path: pathlib.Path, defect: str
) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"canonical instructions\n" * 40
    proof = _canonical_proof(repo, raw)
    if defect == "missing":
        proof = CanonicalArtifactProof(
            "docs/missing.txt", proof.artifact_sha256,
            proof.artifact_start, proof.artifact_end,
        )
    else:
        proof = CanonicalArtifactProof(
            proof.repository_path, "0" * 64,
            proof.artifact_start, proof.artifact_end,
        )
    manifest = _manifest(raw, (
        ManifestEntry(0, len(raw), ManifestDisposition.CANONICAL_REFERENCE, proof),
    ))

    result = _measure(repo, raw, encode_manifest(manifest))

    assert result.delivered_mission_bytes == raw
    assert result.verified_canonical_reference_bytes == 0
    assert result.unknown_bytes == len(raw)
    assert result.proof_outcome == "PROOFS_PARTIAL_CONSERVATIVE"
    assert result.proof_failures == ("REFERENCE_CANONICAL_PROOF_FAILED",)


def test_valid_canonical_proof_and_manifest_overhead_accounting(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"canonical foundation content\n" * 100
    proof = _canonical_proof(repo, raw)
    manifest_bytes = encode_manifest(_manifest(raw, (
        ManifestEntry(0, len(raw), ManifestDisposition.CANONICAL_REFERENCE, proof),
    )))

    result = _measure(repo, raw, manifest_bytes)

    assert result.delivered_mission_bytes == raw
    assert result.verified_canonical_reference_bytes == len(raw)
    assert result.proven_reexposure_bytes == len(raw)
    assert result.manifest_bytes == len(manifest_bytes)
    assert result.net_candidate_reduction_bytes == len(raw) - len(manifest_bytes)
    assert result.manifest_economic_win is True
    assert result.proof_outcome == "PASS"


def test_critical_delta_unknown_and_accounting_conservation(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    critical = b"CRITICAL remains inline\n"
    delta = b"current mission delta\n"
    unknown = b"undeclared remains unknown\n"
    raw = critical + delta + unknown
    manifest = _manifest(raw, (
        ManifestEntry(0, len(critical), ManifestDisposition.INLINE_CRITICAL),
        ManifestEntry(
            len(critical), len(critical) + len(delta), ManifestDisposition.DELTA,
        ),
    ))

    result = _measure(repo, raw, encode_manifest(manifest))

    assert result.delivered_mission_bytes == raw
    assert result.inline_critical_bytes == len(critical)
    assert result.delta_bytes == len(delta)
    assert result.unknown_bytes == len(unknown)
    assert sum((
        result.inline_critical_bytes,
        result.delta_bytes,
        result.verified_canonical_reference_bytes,
        result.unknown_bytes,
    )) == result.raw_mission_bytes
    assert result.proven_reexposure_bytes == 0
    assert result.net_candidate_reduction_bytes == -result.manifest_bytes
    assert result.manifest_economic_win is False


def test_overlapping_entries_fail_conservative(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"0123456789"
    manifest = _manifest(raw, (
        ManifestEntry(0, 6, ManifestDisposition.INLINE_CRITICAL),
        ManifestEntry(5, 9, ManifestDisposition.DELTA),
    ))

    result = _measure(repo, raw, encode_manifest(manifest))

    assert result.delivered_mission_bytes == raw
    assert result.unknown_bytes == len(raw)
    assert result.proof_outcome == "MANIFEST_LAYOUT_FAILED_CONSERVATIVE"


def test_record_has_hashes_and_counts_but_no_prompt_body_or_absolute_path(
    tmp_path: pathlib.Path,
) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"INERT_PRIVATE_PROMPT_SENTINEL\n"
    manifest_bytes = encode_manifest(_manifest(raw))

    result = _measure(repo, raw, manifest_bytes)
    serialized = json.dumps(result.to_record(), sort_keys=True)

    assert "INERT_PRIVATE_PROMPT_SENTINEL" not in serialized
    assert str(tmp_path) not in serialized
    assert result.to_record()["PROMPT_BODY_PERSISTED"] is False
    assert result.to_record()["DELIVERED_MISSION_MUTATED"] is False
    assert result.to_record()["SHADOW_ONLY"] is True
    assert result.to_record()["SEMANTIC_INFERENCE_USED"] is False


def test_repeated_measurement_is_deterministic_and_delivery_cannot_change(
    tmp_path: pathlib.Path,
) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"critical exact bytes\r\nunknown exact bytes"
    manifest_bytes = encode_manifest(_manifest(raw, (
        ManifestEntry(0, 22, ManifestDisposition.INLINE_CRITICAL),
    )))

    first = _measure(repo, raw, manifest_bytes)
    second = _measure(repo, raw, manifest_bytes)

    assert first == second
    assert first.delivered_mission_bytes == raw
    assert first.to_record() == second.to_record()
    assert json.dumps(first.to_record(), sort_keys=True) == json.dumps(
        second.to_record(), sort_keys=True
    )
    assert first.active_delivery_authorized is False


def test_schema_has_no_duplicate_or_semantic_removal_class() -> None:
    assert MANIFEST_SCHEMA_VERSION == "FIO_MISSION_CONTEXT_MANIFEST_V1"
    assert {item.name for item in ManifestDisposition} == {
        "CANONICAL_REFERENCE", "INLINE_CRITICAL", "DELTA",
    }
    with pytest.raises(ValueError, match="disposition"):
        ManifestEntry(0, 1, "SEMANTICALLY_REDUNDANT")  # type: ignore[arg-type]


def test_committed_dogfood_manifest_is_compact_and_payload_free() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    repository_path = "docs/M15-S2-DOGFOOD-MANIFEST.json"
    manifest_bytes = (root / repository_path).read_bytes()
    manifest = parse_manifest(manifest_bytes)

    attributes = subprocess.run(
        ["git", "-C", str(root), "check-attr", "text", "eol", "--", repository_path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert len(manifest_bytes) == 223
    assert manifest_bytes.endswith(b"\n")
    assert not manifest_bytes.endswith(b"\r\n")
    assert b"\r\n" not in manifest_bytes
    assert attributes == [
        f"{repository_path}: text: set",
        f"{repository_path}: eol: lf",
    ]
    assert manifest.mission_id == "FIOFILTER-M15-S2-MISSION-CONTEXT-MANIFEST"
    assert manifest.raw_bytes == 3639
    assert encode_manifest(manifest) == manifest_bytes
    assert b"OBJECTIVE" not in manifest_bytes
    assert b"CRITICAL:" not in manifest_bytes
    assert b"prompt" not in manifest_bytes.lower()


def test_m16_dogfood_manifest_is_canonical_and_payload_free() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    repository_path = "docs/M16-PD1-DOGFOOD-MANIFEST.json"
    manifest_bytes = (root / repository_path).read_bytes()
    manifest = parse_manifest(manifest_bytes)

    attributes = subprocess.run(
        ["git", "-C", str(root), "check-attr", "text", "eol", "--", repository_path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert len(manifest_bytes) == 234
    assert manifest_bytes.endswith(b"\n")
    assert b"\r\n" not in manifest_bytes
    assert attributes == [
        f"{repository_path}: text: set",
        f"{repository_path}: eol: lf",
    ]
    assert manifest.mission_id == "FIOFILTER-M16-PD1-PROGRESSIVE-DISCLOSURE-BOOTSTRAP"
    assert manifest.raw_bytes == 8454
    assert encode_manifest(manifest) == manifest_bytes
    assert b"INLINE_CRITICAL" not in manifest_bytes
    assert b"DELTA / OBJECTIVE" not in manifest_bytes


def test_m16_pd2_dogfood_manifest_is_canonical_and_payload_free() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    repository_path = "docs/M16-PD2-DOGFOOD-MANIFEST.json"
    manifest_bytes = (root / repository_path).read_bytes()
    manifest = parse_manifest(manifest_bytes)

    attributes = subprocess.run(
        ["git", "-C", str(root), "check-attr", "text", "eol", "--", repository_path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert len(manifest_bytes) == 227
    assert manifest_bytes.endswith(b"\n")
    assert b"\r\n" not in manifest_bytes
    assert attributes == [
        f"{repository_path}: text: set",
        f"{repository_path}: eol: lf",
    ]
    assert manifest.mission_id == "FIOFILTER-M16-PD2-SECTION-LEVEL-WORKING-SET"
    assert manifest.raw_bytes == 8551
    assert encode_manifest(manifest) == manifest_bytes
    assert b"WHOLE_DOCUMENT_ROUTE_WASTE" not in manifest_bytes
    assert b"INLINE_CRITICAL" not in manifest_bytes
    assert b"OBJECTIVE" not in manifest_bytes
