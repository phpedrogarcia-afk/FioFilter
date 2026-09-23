"""Focused active-delivery proof and conservative failure matrix."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

import pytest

from fiofilter.active_context import ContextError, SCHEMA, build_package, recover_source
from fiofilter.cli import main


def _git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def fixture(tmp_path: pathlib.Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs/context").mkdir(parents=True)
    files = {
        "AGENTS.md": b"# Rules\nKeep authority.\n",
        "docs/context/ACTIVE-QUEUE.md": b"# Queue\nNo promotion.\n",
        "docs/context/guide.md": b"# A\nNeeded.\n# B\nHistorical text.\n",
        "docs/context/context-manifest.json": b'{"tasks":{"p0-02":{"required_docs":["docs/context/guide.md"]}}}',
    }
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    _git(root, "init", "-q")
    _git(root, "add", "--", *files)
    _git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base")
    contract = {
        "schema": SCHEMA, "profile": "fioos", "assessment": "NON_SENSITIVE",
        "mission_id": "TEST", "route": "p0-02", "expected_head": _git(root, "rev-parse", "HEAD"),
        "expected_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "mission": "Review this state.", "inline_critical_context": "A0; no promotion.",
        "required_inline_facts": ["A0", "no promotion"], "delta": "Current candidate only.",
        "sources": [
            {"path": name, "sha256": _sha(files[name]),
             "mode": "SECTIONS" if name.endswith("guide.md") else "FULL",
             "headings": ["A"] if name.endswith("guide.md") else [],
             "reason": "Explicit operator scope"}
            for name in ("AGENTS.md", "docs/context/ACTIVE-QUEUE.md", "docs/context/guide.md")
        ],
    }
    return root, contract


def test_active_measurement_recovery_and_determinism(fixture):
    root, contract = fixture
    first = build_package(root, contract)
    second = build_package(root, contract)
    assert first == second
    assert b"Historical text." not in first.payload
    assert b"A0; no promotion." in first.payload
    assert first.receipt["baseline_context_bytes"] - first.receipt["active_context_bytes"] == first.receipt["net_avoided_context_bytes"]
    assert first.receipt["net_avoided_context_bytes"] < 0  # Small inputs may cost more.
    assert _sha(first.payload) == first.receipt["payload_sha256"]
    assert first.receipt["canary_ready"] is True
    proof = first.receipt["sources"][-1]
    assert recover_source(root, proof) == (root / proof["path"]).read_bytes()
    (root / proof["path"]).write_text("changed", encoding="utf-8")
    with pytest.raises(ContextError, match="RECOVERY_IDENTITY_MISMATCH"):
        recover_source(root, proof)


@pytest.mark.parametrize("edit,reason", [
    (b"# Z\nMissing.\n", "DIRTY_WORKTREE"),
    (b"# A\nOne\n# A\nTwo\n", "DIRTY_WORKTREE"),
])
def test_dirty_worktree_forces_complete_source(fixture, edit, reason):
    root, contract = fixture
    source = root / "docs/context/guide.md"
    source.write_bytes(edit)
    package = build_package(root, contract)
    assert edit in package.payload
    assert package.receipt["dirty_worktree"] is True
    assert package.receipt["canary_ready"] is False
    assert package.receipt["sources"][-1]["fallback"] == reason
    assert package.receipt["sources"][-1]["omitted_bytes"] == 0


@pytest.mark.parametrize("raw,reason", [
    (b"# Z\nMissing.\n", "MISSING_HEADING:A"),
    (b"# A\nOne\n# A\nTwo\n", "AMBIGUOUS_HEADING:A"),
])
def test_heading_failures_fall_back_to_full(fixture, raw, reason):
    root, contract = fixture
    source = root / "docs/context/guide.md"
    source.write_bytes(raw)
    _git(root, "add", "--", "docs/context/guide.md")
    _git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "modified")
    contract["expected_head"] = _git(root, "rev-parse", "HEAD")
    contract["expected_tree"] = _git(root, "rev-parse", "HEAD^{tree}")
    contract["sources"][-1]["sha256"] = _sha(raw)
    package = build_package(root, contract)
    assert package.receipt["sources"][-1]["fallback"] == reason
    assert package.receipt["sources"][-1]["omitted_bytes"] == 0


def test_changed_proof_falls_back_to_full(fixture):
    root, contract = fixture
    contract["sources"][-1]["sha256"] = "0" * 64
    package = build_package(root, contract)
    assert package.receipt["sources"][-1]["fallback"] == "SOURCE_IDENTITY_MISMATCH"
    assert package.receipt["sources"][-1]["omitted_bytes"] == 0


def test_missing_invalid_unknown_and_critical_abort(fixture):
    root, contract = fixture
    contract["route"] = "unknown"
    with pytest.raises(ContextError, match="UNKNOWN_OR_AMBIGUOUS_ROUTE"):
        build_package(root, contract)
    contract["route"] = "p0-02"
    contract["required_inline_facts"].append("not inline")
    with pytest.raises(ContextError, match="CRITICAL_FACT_NOT_INLINE"):
        build_package(root, contract)
    contract["required_inline_facts"].pop()
    (root / "docs/context/guide.md").write_bytes(b"\xff")
    with pytest.raises(ContextError, match="INVALID_UTF8_SOURCE"):
        build_package(root, contract)
    (root / "docs/context/guide.md").unlink()
    with pytest.raises(ContextError, match="MISSING_OR_ESCAPED_SOURCE"):
        build_package(root, contract)


def test_failed_canonical_and_path_proofs_abort(fixture):
    root, contract = fixture
    contract["expected_head"] = "0" * 40
    with pytest.raises(ContextError, match="HEAD_IDENTITY_MISMATCH"):
        build_package(root, contract)
    contract["expected_head"] = _git(root, "rev-parse", "HEAD")
    contract["sources"][-1]["path"] = "../outside.md"
    contract["sources"].append({"path": "docs/context/guide.md", "sha256": "0" * 64,
                                "mode": "FULL", "reason": "Explicit"})
    with pytest.raises(ContextError, match="INVALID_SOURCE_PATH"):
        build_package(root, contract)


def test_cli_requires_consent_and_does_not_overwrite(fixture, tmp_path, capsys):
    root, contract = fixture
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(contract), encoding="utf-8")
    output = tmp_path / "result"
    args = ["prepare-context", "--repo-root", str(root), "--contract", str(contract_file),
            "--profile", "fioos", "--output-dir", str(output)]
    assert main(args) == 2
    assert not output.exists()
    assert main(args + ["--persist-non-sensitive"]) == 0
    original = (output / "active-context.md").read_bytes()
    assert main(args + ["--persist-non-sensitive"]) == 2
    assert (output / "active-context.md").read_bytes() == original
    assert (output / "receipt.json").is_file()
    assert "payload" in capsys.readouterr().out
