"""Bounded FioOS v0.1 consumer for FioFilter work-item proposals.

This module is an explicit local development pilot, not a service or an
authorization source. The public FioOS source is pinned as a Git submodule.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping


FIOOS_CORE_PIN = "04ea806b80995ff95b50fb0c8d232baa2148c20a"
MAX_PROPOSALS_PER_INSTANCE = 25
WORKSPACE_ID = "fiofilter-dev-outbox-v1"
CAPABILITY = "fiofilter.work_item.emit"
OPERATION = "note.append"


@dataclass(frozen=True)
class WorkItemDefinition:
    proposal_type: str
    target_scope: str
    reason: str
    evidence_refs: tuple[str, ...]


WORK_ITEM_CATALOG = MappingProxyType(
    {
        "M20_QUALITY_UNMEASURED": WorkItemDefinition(
            proposal_type="VALIDATION",
            target_scope="tests/",
            reason=(
                "M20 records later FioOS behavioral quality as UNKNOWN; "
                "measure a bounded natural FioFilter task before widening "
                "context delivery."
            ),
            evidence_refs=("docs/DECISIONS.md", "AI-START-HERE.md"),
        ),
        "M04_PRODUCER_PROVENANCE": WorkItemDefinition(
            proposal_type="DESIGN",
            target_scope="fiofilter/",
            reason=(
                "M04 automatic routing remains disabled until trusted "
                "producer metadata can establish the required single-purpose "
                "ripgrep provenance."
            ),
            evidence_refs=(
                "docs/ARCHITECTURE.md",
                "docs/M04-RG-STANDARD-LOSSLESS-GROUPING.md",
            ),
        ),
        "M03_REAL_CORPUS_REPLAY": WorkItemDefinition(
            proposal_type="INVESTIGATION",
            target_scope="tests/",
            reason=(
                "The test strategy says the original real search corpus is "
                "not bundled or replayed and historical percentages were not "
                "reproduced; determine whether a permitted reproducible replay "
                "can close that evidence gap."
            ),
            evidence_refs=("docs/TEST-STRATEGY.md", "docs/M03-CORPUS-REPORT.md"),
        ),
        "M06_QUALITY_IMPACT_UNKNOWN": WorkItemDefinition(
            proposal_type="INVESTIGATION",
            target_scope="docs/",
            reason=(
                "M06 keeps task-quality impact UNKNOWN; define a bounded "
                "natural-task evaluation before considering any activation."
            ),
            evidence_refs=("docs/M06-REEXPOSURE-SHADOW.md",),
        ),
        "WHOLE_MISSION_ECONOMICS": WorkItemDefinition(
            proposal_type="MEASUREMENT",
            target_scope="tests/",
            reason=(
                "FioFilter distinguishes local byte reduction from whole-"
                "mission quality and economics; measure a mission-level A/B "
                "before making efficiency claims."
            ),
            evidence_refs=("docs/EVIDENCE-CONTRACT.md", "docs/TEST-STRATEGY.md"),
        ),
    }
)

_REQUIRED_METADATA = frozenset(
    {"target_project", "target_scope", "proposal_type", "reason_code", "evidence_refs"}
)
_ALLOWED_METADATA = _REQUIRED_METADATA | {"authorized"}
_HEAD_RE = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class WorkItemReceipt:
    proposal_id: str | None
    request_id: str | None
    decision: str
    status: str
    effect_count: int | None
    result_id: str | None
    evidence_ref: str | None
    reason: str | None


def _load_pinned_fioos_api() -> tuple[Any, Any, Any, Any, Any, Any]:
    if sys.version_info < (3, 11):
        raise RuntimeError("FIOOS_V0_1_REQUIRES_PYTHON_3_11_OR_NEWER")

    source_root = Path(__file__).resolve().parents[1] / "vendor" / "fioos-core"
    package_init = source_root / "fioos_core" / "__init__.py"
    if not package_init.is_file():
        raise RuntimeError("FIOOS_PUBLIC_SUBMODULE_NOT_INITIALIZED")

    source_text = str(source_root)
    loaded = sys.modules.get("fioos_core")
    if loaded is not None:
        loaded_file = getattr(loaded, "__file__", None)
        if not loaded_file or not Path(loaded_file).resolve().is_relative_to(source_root):
            raise RuntimeError("FIOOS_CORE_ALREADY_LOADED_FROM_UNPINNED_SOURCE")
    if source_text in sys.path:
        sys.path.remove(source_text)
    sys.path.insert(0, source_text)

    try:
        from fioos_core import (  # type: ignore[import-not-found]
            EffectGrant,
            LocalNoteAdapter,
            ProjectPolicy,
            RuntimeGateway,
            ToolRequest,
            admit_external_proposal,
        )
    except ImportError as error:
        raise RuntimeError("FIOOS_PUBLIC_CORE_IMPORT_FAILED") from error
    return (
        EffectGrant,
        LocalNoteAdapter,
        ProjectPolicy,
        RuntimeGateway,
        ToolRequest,
        admit_external_proposal,
    )


def _valid_evidence_ref(repo_root: Path, value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return False
    candidate = (repo_root / Path(*relative.parts)).resolve(strict=False)
    return candidate.is_relative_to(repo_root) and candidate.is_file()


class FioFilterWorkItemConsumer:
    """Emit one safe, human-reviewed work-item proposal through FioOS A0."""

    def __init__(
        self,
        *,
        repo_root: Path | str,
        outbox_dir: Path | str,
        canonical_head: str,
        created_at: str | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve(strict=True)
        if not self.repo_root.is_dir():
            raise ValueError("REPOSITORY_ROOT_NOT_DIRECTORY")
        if not isinstance(canonical_head, str) or not _HEAD_RE.fullmatch(canonical_head):
            raise ValueError("CANONICAL_HEAD_INVALID")
        self.canonical_head = canonical_head

        outbox_base = self.repo_root / "fioos-outbox"
        if outbox_base.is_symlink() or not outbox_base.is_dir():
            raise ValueError("OUTBOX_BASE_MISSING_OR_SYMLINK")
        self.outbox_base = outbox_base.resolve(strict=True)
        if not self.outbox_base.is_relative_to(self.repo_root):
            raise ValueError("OUTBOX_BASE_OUTSIDE_REPOSITORY")
        if self.outbox_base != outbox_base:
            raise ValueError("OUTBOX_BASE_REDIRECTED")
        candidate_outbox = Path(outbox_dir)
        if candidate_outbox.is_symlink():
            raise ValueError("OUTBOX_DIRECTORY_SYMLINK")
        self.outbox_dir = candidate_outbox.resolve(strict=True)
        if not self.outbox_dir.is_dir() or not self.outbox_dir.is_relative_to(
            self.outbox_base
        ):
            raise ValueError("OUTBOX_OUTSIDE_DEDICATED_DIRECTORY")
        if next(self.outbox_dir.iterdir(), None) is not None:
            raise ValueError("OUTBOX_DIRECTORY_NOT_EMPTY")

        if created_at is None:
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            )
        if not isinstance(created_at, str) or not created_at.endswith("Z"):
            raise ValueError("CREATED_AT_MUST_BE_UTC_ISO8601")
        try:
            datetime.fromisoformat(created_at[:-1] + "+00:00")
        except ValueError as error:
            raise ValueError("CREATED_AT_INVALID") from error
        self.created_at = created_at

        (
            effect_grant,
            local_note_adapter,
            project_policy,
            runtime_gateway,
            tool_request,
            admit_external_proposal,
        ) = _load_pinned_fioos_api()

        # This controller-owned policy is fixed and independent of proposal data.
        policy = project_policy(
            workspace_id=WORKSPACE_ID,
            grants=frozenset({effect_grant(CAPABILITY, OPERATION)}),
            autonomy_level="A0",
        )
        adapter = local_note_adapter(workspace_id=WORKSPACE_ID, root=self.outbox_dir)
        self._gateway = runtime_gateway(policy=policy, adapter=adapter)
        self._tool_request = tool_request
        self._admit = admit_external_proposal
        self._calls = 0
        self._lock = threading.Lock()

    @staticmethod
    def _denied(proposal_id: str | None, reason: str) -> WorkItemReceipt:
        return WorkItemReceipt(
            proposal_id=proposal_id,
            request_id=None,
            decision="DENY",
            status="DENIED",
            effect_count=0,
            result_id=None,
            evidence_ref=None,
            reason=reason,
        )

    def submit(self, payload: Mapping[str, Any]) -> WorkItemReceipt:
        with self._lock:
            if self._calls >= MAX_PROPOSALS_PER_INSTANCE:
                return self._denied(None, "PROPOSAL_LIMIT_REACHED")
            self._calls += 1

            admission = self._admit(payload)
            if not admission.accepted or admission.proposal is None:
                return self._denied(
                    None, "ADMISSION_REJECTED:" + ",".join(admission.rejection_reasons)
                )
            proposal = admission.proposal
            metadata = dict(proposal.metadata)
            if set(metadata) - _ALLOWED_METADATA:
                return self._denied(proposal.proposal_id, "UNKNOWN_METADATA_FIELD")
            if not _REQUIRED_METADATA.issubset(metadata):
                return self._denied(proposal.proposal_id, "REQUIRED_METADATA_MISSING")

            reason_code = metadata.get("reason_code")
            if type(reason_code) is not str:
                return self._denied(proposal.proposal_id, "REASON_CODE_INVALID")
            definition = WORK_ITEM_CATALOG.get(reason_code)
            if definition is None:
                return self._denied(proposal.proposal_id, "REASON_CODE_NOT_ALLOWED")
            if (
                metadata.get("target_project") != "FioFilter"
                or metadata.get("target_scope") != definition.target_scope
                or metadata.get("proposal_type") != definition.proposal_type
            ):
                return self._denied(proposal.proposal_id, "PROJECT_OR_SCOPE_NOT_ALLOWED")
            evidence_refs = metadata.get("evidence_refs")
            if type(evidence_refs) not in (list, tuple):
                return self._denied(proposal.proposal_id, "EVIDENCE_REFS_INVALID")
            if tuple(evidence_refs) != definition.evidence_refs:
                return self._denied(proposal.proposal_id, "EVIDENCE_REFS_NOT_ALLOWED")
            if not all(
                _valid_evidence_ref(self.repo_root, ref)
                for ref in definition.evidence_refs
            ):
                return self._denied(proposal.proposal_id, "EVIDENCE_REF_UNAVAILABLE")
            if proposal.requested_capabilities != (CAPABILITY,):
                return self._denied(proposal.proposal_id, "CAPABILITY_NOT_ALLOWED")
            if proposal.requested_tools != (OPERATION,):
                return self._denied(proposal.proposal_id, "TOOL_NOT_ALLOWED")

            request_id = "ffwi-" + hashlib.sha256(
                proposal.proposal_id.encode("utf-8")
            ).hexdigest()[:32]
            result_id = "effect:" + request_id
            work_item_id = "fwi-" + hashlib.sha256(
                (proposal.proposal_id + "\0" + reason_code).encode("utf-8")
            ).hexdigest()[:24]
            artifact = {
                "work_item_id": work_item_id,
                "proposal_id": proposal.proposal_id,
                "source_project": "FioFilter",
                "proposal_type": definition.proposal_type,
                "target_scope": definition.target_scope,
                "reason": definition.reason,
                "reason_code": reason_code,
                "evidence_refs": list(definition.evidence_refs),
                "canonical_head_observed": self.canonical_head,
                "created_at": self.created_at,
                "status": "PROPOSED_REQUIRES_HUMAN_REVIEW",
                "authority_decision": "A0_GATEWAY_POLICY_ALLOW",
                "request_id": request_id,
                "result_id": result_id,
            }
            text = json.dumps(
                artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )

            # Requested identity is retained only as an untrusted claim. The
            # operation and grant are selected by this controller, never by it.
            result = self._gateway.execute(
                self._tool_request(
                    request_id=request_id,
                    workspace_id=WORKSPACE_ID,
                    operation=OPERATION,
                    capability=CAPABILITY,
                    payload={"text": text},
                    identity_claim=proposal.source_id,
                )
            )
            if (
                result.decision != "ALLOW"
                or result.status != "SUCCEEDED"
                or result.effect_count != 1
                or result.effect_id != result_id
                or result.evidence_ref != "notes.jsonl"
            ):
                status = result.status
                reason = result.reason
                if result.decision == "ALLOW" and result.status == "SUCCEEDED":
                    status = "UNKNOWN"
                    reason = "RESULT_CORRELATION_MISMATCH"
                return WorkItemReceipt(
                    proposal_id=proposal.proposal_id,
                    request_id=result.request_id,
                    decision=result.decision,
                    status=status,
                    effect_count=result.effect_count,
                    result_id=result.effect_id,
                    evidence_ref=result.evidence_ref,
                    reason=reason,
                )
            return WorkItemReceipt(
                proposal_id=proposal.proposal_id,
                request_id=result.request_id,
                decision=result.decision,
                status=result.status,
                effect_count=result.effect_count,
                result_id=result.effect_id,
                evidence_ref=result.evidence_ref,
                reason=result.reason,
            )
