"""Deterministic M15-S1 mission-prompt shadow accounting."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

import pytest

from fiofilter.mission_context_shadow import (
    CanonicalArtifactProof,
    DuplicateProof,
    EvidenceQuality,
    MissionByteClass,
    MissionContextShadowAnalyzer,
    MissionSpan,
    ShadowManifest,
    aggregate_shadow_results,
    load_manifest,
)
from fiofilter.mission_context import SafetyAssessment


def _tracked_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def _manifest(raw: bytes, spans=()) -> ShadowManifest:
    return ShadowManifest(
        mission_id="FIOFILTER-M15-S1-TEST",
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes=len(raw),
        evidence_quality=EvidenceQuality.SYNTHETIC,
        spans=tuple(spans),
        sensitivity_assessment=SafetyAssessment.NON_SENSITIVE,
    )


def _canonical_proof(repo: pathlib.Path, segment: bytes) -> CanonicalArtifactProof:
    artifact = b"prefix\n" + segment + b"suffix\n"
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


def test_accounting_conservation_exact_delivery_and_critical_inline(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    critical = b"CRITICAL: keep this exact fact inline.\n"
    delta = b"DELTA: perform the current task.\n"
    canonical = b"canonical foundation rule remains unchanged\n" * 8
    duplicate = b"EXACT DUPLICATE BLOCK\n" * 5
    unknown = b"ambiguous prose remains visible\n"
    raw = critical + delta + canonical + duplicate + duplicate + unknown
    bounds = []
    cursor = 0
    for part in (critical, delta, canonical, duplicate, duplicate):
        bounds.append((cursor, cursor + len(part)))
        cursor += len(part)
    proof = _canonical_proof(repo, canonical)
    spans = (
        MissionSpan(*bounds[0], MissionByteClass.INLINE_CRITICAL),
        MissionSpan(*bounds[1], MissionByteClass.DELTA),
        MissionSpan(*bounds[2], MissionByteClass.REFERENCE_CANONICAL, canonical=proof),
        MissionSpan(
            *bounds[4], MissionByteClass.DROP_DUPLICATE,
            duplicate=DuplicateProof(*bounds[3]),
        ),
    )

    result = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw, spans))

    assert result.delivered_mission_bytes == raw
    assert result.raw_mission_bytes == len(raw)
    assert result.inline_critical_bytes == len(critical)
    assert result.delta_bytes == len(delta)
    assert result.reference_canonical_bytes == len(canonical)
    assert result.drop_duplicate_candidate_bytes == len(duplicate)
    assert result.unknown_conservative_bytes == len(duplicate) + len(unknown)
    assert sum((
        result.inline_critical_bytes, result.delta_bytes,
        result.reference_canonical_bytes, result.drop_duplicate_candidate_bytes,
        result.unknown_conservative_bytes,
    )) == result.raw_mission_bytes
    assert result.minimum_sufficient_candidate_bytes == len(result.candidate_bytes)
    assert result.hypothetical_visible_bytes_reduction == len(raw) - len(result.candidate_bytes)
    assert critical in result.candidate_bytes
    assert result.active_delivery_authorized is False
    assert result.behavioral_equivalence == "UNKNOWN"
    assert result.semantic_inference_used is False


def test_exact_byte_reproducibility_and_deterministic_record(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"foundation bytes\n" * 40
    proof = _canonical_proof(repo, raw)
    manifest = _manifest(raw, (
        MissionSpan(0, len(raw), MissionByteClass.REFERENCE_CANONICAL, canonical=proof),
    ))
    analyzer = MissionContextShadowAnalyzer(repo)

    first = analyzer.analyze(raw, manifest)
    second = analyzer.analyze(raw, manifest)

    assert first == second
    assert first.delivered_mission_sha256 == hashlib.sha256(raw).hexdigest()
    assert first.candidate_sha256 == hashlib.sha256(first.candidate_bytes).hexdigest()
    assert first.to_record() == second.to_record()
    assert json.dumps(first.to_record(), sort_keys=True) == json.dumps(second.to_record(), sort_keys=True)


def test_unknown_is_conservative_and_no_semantic_inference_exists(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = (
        b"docs/canonical.txt contains the same same same words.\n"
        b"CRITICAL-looking text is not automatically classified.\n"
    )

    result = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw))

    assert result.unknown_conservative_bytes == len(raw)
    assert result.minimum_sufficient_candidate_bytes == len(raw)
    assert result.hypothetical_visible_bytes_reduction == 0
    assert result.candidate_bytes == raw
    assert result.delivered_mission_bytes == raw
    assert result.proof_failures == ()


@pytest.mark.parametrize("defect", ["missing", "untracked", "hash", "range", "content", "escape"])
def test_missing_or_invalid_canonical_reference_stays_unknown(
    tmp_path: pathlib.Path, defect: str
) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"canonical exact text\n" * 20
    proof = _canonical_proof(repo, raw)
    if defect == "missing":
        proof = CanonicalArtifactProof("docs/missing.txt", proof.artifact_sha256,
                                       proof.artifact_start, proof.artifact_end)
    elif defect == "untracked":
        untracked = repo / "untracked.txt"
        untracked.write_bytes(raw)
        proof = CanonicalArtifactProof("untracked.txt", hashlib.sha256(raw).hexdigest(), 0, len(raw))
    elif defect == "hash":
        proof = CanonicalArtifactProof(proof.repository_path, "0" * 64,
                                       proof.artifact_start, proof.artifact_end)
    elif defect == "range":
        proof = CanonicalArtifactProof(proof.repository_path, proof.artifact_sha256, 9999, 10000)
    elif defect == "content":
        proof = CanonicalArtifactProof(proof.repository_path, proof.artifact_sha256, 0, len(raw))
    elif defect == "escape":
        proof = CanonicalArtifactProof("../outside.txt", proof.artifact_sha256,
                                       proof.artifact_start, proof.artifact_end)
    span = MissionSpan(0, len(raw), MissionByteClass.REFERENCE_CANONICAL, canonical=proof)

    result = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw, (span,)))

    assert result.reference_canonical_bytes == 0
    assert result.unknown_conservative_bytes == len(raw)
    assert result.candidate_bytes == raw
    assert result.proof_failures == ("REFERENCE_CANONICAL_PROOF_FAILED",)


def test_exact_duplicate_proof_required_and_source_must_remain_inline(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    first = b"repeat exactly\n" * 8
    changed = b"repeat changed\n" * 8
    raw = first + first + changed
    target = MissionSpan(
        len(first), len(first) * 2, MissionByteClass.DROP_DUPLICATE,
        duplicate=DuplicateProof(0, len(first)),
    )
    wrong = MissionSpan(
        len(first) * 2, len(raw), MissionByteClass.DROP_DUPLICATE,
        duplicate=DuplicateProof(0, len(changed)),
    )

    result = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw, (target, wrong)))

    assert result.drop_duplicate_candidate_bytes == len(first)
    assert result.unknown_conservative_bytes == len(first) + len(changed)
    assert result.proof_failures == ("DROP_DUPLICATE_PROOF_FAILED",)
    assert result.candidate_bytes == first + changed

    hidden_source = MissionSpan(
        0, len(first), MissionByteClass.DROP_DUPLICATE,
        duplicate=DuplicateProof(len(first), len(first) * 2),
    )
    hidden = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw, (hidden_source, target)))
    assert hidden.drop_duplicate_candidate_bytes == 0
    assert hidden.unknown_conservative_bytes == len(raw)


def test_overlapping_spans_and_wrong_raw_binding_are_rejected(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"0123456789"
    overlap = _manifest(raw, (
        MissionSpan(0, 6, MissionByteClass.DELTA),
        MissionSpan(5, 9, MissionByteClass.INLINE_CRITICAL),
    ))
    with pytest.raises(ValueError, match="overlap"):
        MissionContextShadowAnalyzer(repo).analyze(raw, overlap)

    wrong = ShadowManifest(
        mission_id="FIOFILTER-M15-S1-TEST", raw_sha256="0" * 64,
        raw_bytes=len(raw), evidence_quality=EvidenceQuality.SYNTHETIC, spans=(),
    )
    with pytest.raises(ValueError, match="SHA-256"):
        MissionContextShadowAnalyzer(repo).analyze(raw, wrong)


def test_manifest_has_no_raw_or_semantic_inference_fields(tmp_path: pathlib.Path) -> None:
    raw = b"opaque bytes\n"
    path = tmp_path / "manifest.json"
    base = {
        "schema_version": "FIO_MISSION_CONTEXT_SHADOW_MANIFEST_V1",
        "mission_id": "FIOFILTER-M15-S1-TEST",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "evidence_quality": "SYNTHETIC",
        "sensitivity_assessment": "NON_SENSITIVE",
        "spans": [],
    }
    path.write_text(json.dumps(base), encoding="utf-8")
    assert load_manifest(path) == _manifest(raw)

    for forbidden in ("raw_prompt", "prompt", "semantic_equivalence", "model_judgment"):
        invalid = dict(base)
        invalid[forbidden] = "private or inferred content"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises(ValueError, match="manifest fields"):
            load_manifest(path)


def test_record_contains_counts_and_hashes_but_not_prompt_content(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"INERT_PRIVATE_MISSION_SENTINEL\n"
    result = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw))
    serialized = json.dumps(result.to_record(), sort_keys=True)

    assert "INERT_PRIVATE_MISSION_SENTINEL" not in serialized
    assert str(tmp_path) not in serialized
    assert result.to_record()["RAW_MISSION_BYTES"] == len(raw)
    assert result.to_record()["EVIDENCE_QUALITY"] == "SYNTHETIC"


def test_unknown_assessment_blocks_even_exact_reduction_proofs(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"exact foundation bytes\n" * 30
    proof = _canonical_proof(repo, raw)
    manifest = ShadowManifest(
        mission_id="FIOFILTER-M15-S1-TEST",
        raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
        evidence_quality=EvidenceQuality.SYNTHETIC,
        sensitivity_assessment=SafetyAssessment.UNKNOWN,
        spans=(MissionSpan(
            0, len(raw), MissionByteClass.REFERENCE_CANONICAL, canonical=proof,
        ),),
    )

    result = MissionContextShadowAnalyzer(repo).analyze(raw, manifest)

    assert result.reference_canonical_bytes == 0
    assert result.unknown_conservative_bytes == len(raw)
    assert result.candidate_bytes == raw
    assert result.proof_failures == ("ASSESSMENT_OR_SENSITIVITY_REQUIRES_INLINE",)


def test_aggregate_requires_two_real_byte_bound_samples(tmp_path: pathlib.Path) -> None:
    repo = _tracked_repo(tmp_path)
    raw = b"real opaque mission\n"
    synthetic = MissionContextShadowAnalyzer(repo).analyze(raw, _manifest(raw))
    current_manifest = ShadowManifest(
        mission_id="FIOFILTER-M15-S1-CURRENT",
        raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
        evidence_quality=EvidenceQuality.CURRENT_MISSION_VISIBLE_TEXT_UTF8_LF,
        sensitivity_assessment=SafetyAssessment.NON_SENSITIVE, spans=(),
    )
    current = MissionContextShadowAnalyzer(repo).analyze(raw, current_manifest)

    insufficient = aggregate_shadow_results((synthetic, current))
    assert insufficient == {
        "AGGREGATE_STATUS": "NOT_COMPUTED_INSUFFICIENT_TRUSTWORTHY_SAMPLES",
        "TRUSTWORTHY_SAMPLES": 1,
        "MEDIAN_HYPOTHETICAL_REDUCTION_PERCENT": None,
        "TOTAL_PROVEN_REEXPOSURE_BYTES": None,
        "TOTAL_UNKNOWN_BYTES": None,
    }

    preserved_manifest = ShadowManifest(
        mission_id="FIOFILTER-M15-S1-PRESERVED",
        raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
        evidence_quality=EvidenceQuality.REPOSITORY_PRESERVED_ORIGINAL,
        sensitivity_assessment=SafetyAssessment.NON_SENSITIVE, spans=(),
    )
    preserved = MissionContextShadowAnalyzer(repo).analyze(raw, preserved_manifest)
    aggregate = aggregate_shadow_results((synthetic, current, preserved))
    assert aggregate["AGGREGATE_STATUS"] == "COMPUTED"
    assert aggregate["TRUSTWORTHY_SAMPLES"] == 2
    assert aggregate["MEDIAN_HYPOTHETICAL_REDUCTION_PERCENT"] == 0.0
    assert aggregate["TOTAL_PROVEN_REEXPOSURE_BYTES"] == 0
    assert aggregate["TOTAL_UNKNOWN_BYTES"] == len(raw) * 2
