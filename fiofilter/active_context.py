"""Explicit, opt-in FioOS context package with byte-exact recovery proofs.

The operator supplies scope; this module does not infer relevance. Failed
selection proofs deliver the complete source, while missing sources abort.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from fiofilter.sensitivity import contains_sensitive_material
from scripts.section_working_set import select_sections


SCHEMA = "FIO_ACTIVE_CONTEXT_CONTRACT_V1"
RECEIPT_SCHEMA = "FIO_ACTIVE_CONTEXT_RECEIPT_V1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ContextError(ValueError):
    """The package cannot safely be built."""


def _git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ContextError("GIT_PROOF_FAILED")
    return result.stdout.strip()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _relpath(root: pathlib.Path, name: str) -> pathlib.Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ContextError("INVALID_SOURCE_PATH")
    candidate = pathlib.PurePosixPath(name)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise ContextError("INVALID_SOURCE_PATH")
    target = (root / pathlib.Path(*candidate.parts)).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ContextError("MISSING_OR_ESCAPED_SOURCE")
    return target


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextError("INVALID_" + label)
    return value


@dataclass(frozen=True)
class ContextPackage:
    payload: bytes
    receipt: dict[str, Any]


def recover_source(root: pathlib.Path, proof: dict[str, Any]) -> bytes:
    """Open a complete omitted source only if its recorded identity still holds."""
    root = root.resolve()
    path = _relpath(root, proof["path"])
    raw = path.read_bytes()
    if len(raw) != proof["bytes"] or _digest(raw) != proof["sha256"]:
        raise ContextError("RECOVERY_IDENTITY_MISMATCH")
    return raw


def build_package(root: pathlib.Path, contract: dict[str, Any]) -> ContextPackage:
    root = root.resolve()
    if not root.is_dir() or pathlib.Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ContextError("INVALID_REPOSITORY_ROOT")
    if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
        raise ContextError("INVALID_CONTRACT")
    if contract.get("profile") != "fioos" or contract.get("assessment") != "NON_SENSITIVE":
        raise ContextError("PROFILE_OR_ASSESSMENT_NOT_AUTHORIZED")
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    if not _SHA.fullmatch(str(contract.get("expected_head", ""))) or head != contract["expected_head"]:
        raise ContextError("HEAD_IDENTITY_MISMATCH")
    if not _SHA.fullmatch(str(contract.get("expected_tree", ""))) or tree != contract["expected_tree"]:
        raise ContextError("TREE_IDENTITY_MISMATCH")
    mission_id = _require_text(contract.get("mission_id"), "MISSION_ID")
    mission = _require_text(contract.get("mission"), "MISSION")
    critical = _require_text(contract.get("inline_critical_context"), "CRITICAL_CONTEXT")
    delta = _require_text(contract.get("delta"), "DELTA")
    facts = contract.get("required_inline_facts")
    if not isinstance(facts, list) or not facts or any(not isinstance(f, str) or not f or f not in critical for f in facts):
        raise ContextError("CRITICAL_FACT_NOT_INLINE")
    if contains_sensitive_material(json.dumps(contract, ensure_ascii=False).encode("utf-8")):
        raise ContextError("SENSITIVE_CONTRACT")

    manifest_path = _relpath(root, "docs/context/context-manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        route = manifest["tasks"][contract["route"]]
        required = route["required_docs"]
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise ContextError("UNKNOWN_OR_AMBIGUOUS_ROUTE") from error
    if not isinstance(required, list) or not required or not all(isinstance(p, str) for p in required):
        raise ContextError("UNKNOWN_OR_AMBIGUOUS_ROUTE")
    sources = contract.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ContextError("NO_SOURCES")
    names = [item.get("path") for item in sources if isinstance(item, dict)]
    if len(names) != len(sources) or len(set(names)) != len(names) or not set(required).issubset(names):
        raise ContextError("INCOMPLETE_OR_AMBIGUOUS_SOURCES")
    if "AGENTS.md" not in names or "docs/context/ACTIVE-QUEUE.md" not in names:
        raise ContextError("MISSING_FIOOS_BOOTSTRAP")

    dirty = bool(_git(root, "status", "--porcelain"))
    prefix = (f"MISSION / TASK\n{mission_id}\n{mission}\n\n"
              f"INLINE CRITICAL CONTEXT\n{critical}\n\n"
              f"DELTA / CURRENT STATE\n{delta}\n\n"
              "SELECTED CANONICAL CONTEXT\n").encode("utf-8")
    baseline = bytearray(prefix)
    active = bytearray(prefix)
    proofs: list[dict[str, Any]] = []
    refs: list[str] = []
    for item in sources:
        if not isinstance(item, dict):
            raise ContextError("INVALID_SOURCE_ENTRY")
        name = item.get("path")
        path = _relpath(root, name)
        if _git(root, "ls-files", "--error-unmatch", "--", name) != name:
            raise ContextError("UNTRACKED_SOURCE")
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContextError("INVALID_UTF8_SOURCE") from error
        expected = item.get("sha256")
        if not isinstance(expected, str) or not _DIGEST.fullmatch(expected):
            raise ContextError("INVALID_SOURCE_PROOF")
        mode = item.get("mode")
        if mode not in ("FULL", "SECTIONS") or not isinstance(item.get("reason"), str) or not item["reason"]:
            raise ContextError("INVALID_SELECTION_CONTRACT")
        current = _digest(raw)
        fallback = None
        selected = raw
        headings = item.get("headings", [])
        if mode == "SECTIONS":
            if not isinstance(headings, list) or not headings or not all(isinstance(h, str) and h for h in headings):
                raise ContextError("INVALID_HEADING_CONTRACT")
            if dirty:
                fallback = "DIRTY_WORKTREE"
            elif current != expected:
                fallback = "SOURCE_IDENTITY_MISMATCH"
            else:
                result = select_sections(raw, headings)
                selected = result.content
                fallback = result.fallback_reason
        elif current != expected:
            fallback = "SOURCE_IDENTITY_MISMATCH"
        label = f"\n--- {name} ---\n".encode("utf-8")
        baseline.extend(label + raw + (b"\n" if not raw.endswith(b"\n") else b""))
        active.extend(label + selected + (b"\n" if not selected.endswith(b"\n") else b""))
        if selected != raw:
            refs.append(f"- {name} @ SHA256:{current} (full source; recover from receipt)\n")
        proofs.append({"path": name, "sha256": current, "bytes": len(raw),
                       "selected_bytes": len(selected), "headings": headings if mode == "SECTIONS" else [],
                       "reason": item["reason"], "fallback": fallback,
                       "omitted_bytes": len(raw) - len(selected)})
    ref_block = ("\nRECOVERY REFERENCES / PATHS\n" + ("".join(refs) or "- None; all sources inline.\n")).encode("utf-8")
    active.extend(ref_block)
    if contains_sensitive_material(bytes(active)):
        raise ContextError("SENSITIVE_PAYLOAD")
    baseline_bytes = len(baseline)
    active_bytes = len(active)
    receipt = {
        "schema": RECEIPT_SCHEMA, "mission_id": mission_id, "profile": "fioos", "route": contract["route"],
        "repo_head": head, "repo_tree": tree, "dirty_worktree": dirty,
        "contract_sha256": _digest(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode("utf-8")),
        "payload_sha256": _digest(bytes(active)), "baseline_context_bytes": baseline_bytes,
        "active_context_bytes": active_bytes, "packaging_overhead_bytes": len(ref_block),
        "net_avoided_context_bytes": baseline_bytes - active_bytes,
        "net_reduction_percent": round(100 * (baseline_bytes - active_bytes) / baseline_bytes, 4),
        "actual_tokens": "UNAVAILABLE", "sources": proofs,
        "critical_inline_static_check": "PASS", "recovery_contract": "FULL_SOURCE_SHA256_EXACT",
        "canary_ready": not dirty and all(proof["fallback"] is None for proof in proofs),
        "quality_proof": "PENDING_REAL_FIOOS_MISSION",
    }
    return ContextPackage(bytes(active), receipt)
