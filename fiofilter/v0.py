"""
fiofilter.v0 — FioFilter V0 Explicit Integration Spine.

M12: Integrates existing, offline-proven FioFilter capabilities behind one explicit
local laboratory interface without activating automatic context manipulation, read
suppression, or runtime hooks.

Core Invariants:
  INDEX_AUTHORITY=NAVIGATION_ONLY
  DISCOVERY_RANKING_CANNOT_AUTHORIZE_READ_SUPPRESSION=True
  READ_RECEIPT_CANNOT_AUTHORIZE_TRANSFORM=True
  T02_CANNOT_HIDE_CRITICAL_EVIDENCE=True
  SHADOW_CANNOT_CHANGE_RAW_OUTPUT=True
  UNKNOWN_ANYWHERE_CAN_FAIL_TO_RAW=True
  CAPABILITY_DOES_NOT_GRANT_AUTHORITY=True
  ENGINE_METADATA_GATE=ENGINE_METADATA_GATE_REMAINS
  DEFAULT_DISPOSITION=RAW
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import pathlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# Proven subsystems
from fiofilter.discovery_runtime_shadow import (
    DiscoveryRuntimeShadow,
    ShadowEvaluation,
    get_worktree_state_digest_v2,
)
from fiofilter.read_receipt import (
    ReadReceiptDecision,
    ReadReceiptDisposition,
    ReadReceiptEvaluator,
    ReadViewType,
)
from fiofilter.transforms.t02_rg_standard_group import (
    RgGroupingMetadata,
    RgGroupingOutcome,
    RgStandardEvidence,
    RgStandardLosslessGrouping,
)


# ---------------------------------------------------------------------------
# Capability Lifecycle States
# ---------------------------------------------------------------------------

class CapabilityLifecycleState(str, enum.Enum):
    """
    Distinct capability status levels.
    Invariants: These states MUST NOT be collapsed or conflated.
    """
    IMPLEMENTED = "IMPLEMENTED"
    VALIDATED_OFFLINE = "VALIDATED_OFFLINE"
    SHADOW_READY = "SHADOW_READY"
    LIVE_VALIDATED = "LIVE_VALIDATED"
    ACTIVE_AUTHORIZED = "ACTIVE_AUTHORIZED"
    PRODUCTION_READY = "PRODUCTION_READY"


# ---------------------------------------------------------------------------
# Capability Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    version: str
    name: str
    lifecycle_state: CapabilityLifecycleState
    authority: str
    activation_mode: str
    evidence_gate: str
    production_status: str
    description: str


V0_CAPABILITY_REGISTRY: Dict[str, CapabilityDescriptor] = {
    "T02_LOSSLESS_RG": CapabilityDescriptor(
        capability_id="T02_RG_STANDARD_GROUP_V1",
        version="1.0.0",
        name="Lossless ripgrep path:line grouping",
        lifecycle_state=CapabilityLifecycleState.VALIDATED_OFFLINE,
        authority="TRANSFORM_ONLY_WHEN_PROVEN",
        activation_mode="EXPLICIT_ONLY",
        evidence_gate="ENGINE_METADATA_GATE_REMAINS",
        production_status="NOT_PRODUCTION_READY",
        description="Lossless grouping for authorized RG_STANDARD_PATH_LINE_TEXT grammar with roundtrip guarantee.",
    ),
    "READ_RECEIPT_SHADOW": CapabilityDescriptor(
        capability_id="READ_RECEIPT_SHADOW_V1",
        version="1.0.0",
        name="Filesystem-aware Read Receipt shadow evaluator",
        lifecycle_state=CapabilityLifecycleState.SHADOW_READY,
        authority="OBSERVATIONAL_SHADOW_ONLY",
        activation_mode="EXPLICIT_SHADOW",
        evidence_gate="PASSIVE_OR_DIRECT_EVIDENCE_PROVEN",
        production_status="NOT_PRODUCTION_READY",
        description="Tracks read views and computes hypothetical reference replacements without modifying output.",
    ),
    "DISCOVERY_BM25_SHADOW": CapabilityDescriptor(
        capability_id="DISCOVERY_RUNTIME_SHADOW_V1",
        version="1.0.0",
        name="Lexical-first discovery runtime navigation shadow",
        lifecycle_state=CapabilityLifecycleState.SHADOW_READY,
        authority="NAVIGATION_ONLY",
        activation_mode="EXPLICIT_SHADOW",
        evidence_gate="CONTENT_SENSITIVE_V2_FINGERPRINT",
        production_status="NOT_PRODUCTION_READY",
        description="Deterministic BM25 repository file ranking and compact map generation.",
    ),
}


# ---------------------------------------------------------------------------
# V0 Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class V0Config:
    mode: str = "EXPLICIT_LAB"
    active_suppression: bool = False
    auto_context_selection: bool = False
    persistence: str = "EPHEMERAL"
    network: bool = False


# ---------------------------------------------------------------------------
# Decision Trace and Metrics Accounting
# ---------------------------------------------------------------------------

@dataclass
class V0DecisionTrace:
    """
    Auditable trace for an individual evaluated event.
    No private payloads persisted.
    """
    event_id: str
    event_type: str
    capabilities_considered: List[str]
    preconditions: Dict[str, bool]
    decision: str
    reason: str
    raw_bytes: int
    visible_bytes: int
    authority_class: str
    disposition: str  # "RAW", "SHADOW", "TRANSFORM"
    actual_visible_bytes_reduced: int = 0
    shadow_hypothetical_bytes_avoided: int = 0
    timestamp_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class V0MetricsSummary:
    """
    Aggregate metrics summary strictly separating actual from hypothetical savings.
    INVARIANT: actual_visible_bytes_reduced and shadow_hypothetical_bytes_avoided
    must NEVER be summed together.
    """
    events_seen: int = 0
    discovery_shadow_queries: int = 0
    t02_eligible: int = 0
    t02_transformed: int = 0
    t02_raw: int = 0
    read_receipt_candidates: int = 0
    fail_to_raw_counts: int = 0
    actual_visible_bytes_reduced: int = 0
    shadow_hypothetical_bytes_avoided: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# V0 Integration Lab Spine
# ---------------------------------------------------------------------------

class FioFilterV0Lab:
    """
    Central controller for FioFilter V0 Explicit Integration Spine.

    Integrates:
    - BM25 Discovery Runtime Shadow
    - T02 Lossless Standard Ripgrep Transform (explicit evaluation only)
    - Read Receipt Shadow Evaluator
    - Decision Trace & Metrics Ledger
    """

    def __init__(
        self,
        config: Optional[V0Config] = None,
        ledger_dir: Optional[pathlib.Path] = None,
    ):
        self.config = config or V0Config()
        self.ledger_dir = ledger_dir
        self.discovery_shadow = DiscoveryRuntimeShadow(ledger_dir=ledger_dir)
        self.read_evaluator = ReadReceiptEvaluator(session_id='v0-lab-session')
        self._t02 = RgStandardLosslessGrouping()
        self.traces: List[V0DecisionTrace] = []
        self.metrics = V0MetricsSummary()

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------

    def get_status(self) -> Dict[str, str]:
        """Report V0 capability and system status."""
        return {
            "T02_LOSSLESS_RG": "IMPLEMENTED_EXPLICIT_ONLY",
            "READ_RECEIPT": "SHADOW_READY",
            "DISCOVERY": "SHADOW_READY",
            "ACTIVE_SUPPRESSION": "OFF",
            "AUTO_CONTEXT_SELECTION": "OFF",
            "CODEX_LIVE_VALIDATION": "PENDING",
            "ENGINE_METADATA_GATE": "ENGINE_METADATA_GATE_REMAINS",
            "DEFAULT_DISPOSITION": "RAW",
            "INDEX_AUTHORITY": "NAVIGATION_ONLY",
            "CONFIGURATION_MODE": self.config.mode,
        }

    # -----------------------------------------------------------------------
    # Discovery Shadow Evaluation
    # -----------------------------------------------------------------------

    def evaluate_discovery(
        self,
        repo_root: pathlib.Path,
        task_query: str,
        top_k: int = 10,
    ) -> Optional[ShadowEvaluation]:
        """
        Run discovery shadow navigation evaluation.
        Invariants:
        - Result is navigational only.
        - Cannot authorize read suppression.
        """
        self.metrics.events_seen += 1
        self.metrics.discovery_shadow_queries += 1
        
        try:
            ev = self.discovery_shadow.evaluate(repo_root, task_query, top_k=top_k)
            trace = V0DecisionTrace(
                event_id=f"evt-disc-{int(time.time() * 1000)}",
                event_type="DISCOVERY_QUERY",
                capabilities_considered=["DISCOVERY_BM25_SHADOW"],
                preconditions={"worktree_valid": ev is not None},
                decision="SHADOW_ORIENTATION_PRODUCED" if ev else "DISCOVERY_FAILED_FAIL_OPEN",
                reason="BM25 ranking computed" if ev else "Discovery evaluation returned None",
                raw_bytes=len(task_query.encode("utf-8")),
                visible_bytes=len(task_query.encode("utf-8")),
                authority_class="NAVIGATION_ONLY",
                disposition="SHADOW",
            )
            self.traces.append(trace)
            return ev
        except Exception as e:
            self.metrics.fail_to_raw_counts += 1
            trace = V0DecisionTrace(
                event_id=f"evt-disc-err-{int(time.time() * 1000)}",
                event_type="DISCOVERY_QUERY",
                capabilities_considered=["DISCOVERY_BM25_SHADOW"],
                preconditions={"worktree_valid": False},
                decision="FAIL_TO_RAW",
                reason=f"Exception in discovery: {e}",
                raw_bytes=len(task_query.encode("utf-8")),
                visible_bytes=len(task_query.encode("utf-8")),
                authority_class="NAVIGATION_ONLY",
                disposition="RAW",
            )
            self.traces.append(trace)
            return None

    # -----------------------------------------------------------------------
    # Read Receipt Shadow Evaluation
    # -----------------------------------------------------------------------

    def evaluate_read_shadow(
        self,
        file_path: pathlib.Path | str,
        call_id: Optional[str] = None,
        call_index: int = 0,
        episode_id: Optional[int] = None,
    ) -> Tuple[bytes, ReadReceiptDecision]:
        """
        Evaluate a file read through the Read Receipt shadow harness.
        
        INVARIANT: Returns exact raw content_bytes.
        The shadow decision computes hypothetical reference eligibility only.
        """
        self.metrics.events_seen += 1
        self.metrics.read_receipt_candidates += 1
        path_obj = pathlib.Path(file_path).resolve()
        cid = call_id or f"call-{int(time.time() * 1000)}"

        try:
            decision = self.read_evaluator.evaluate_live_read(
                call_id=cid,
                file_path=path_obj,
                call_index=call_index,
                episode_id=episode_id,
            )
            raw_bytes = path_obj.read_bytes() if path_obj.exists() else b""
            raw_len = len(raw_bytes)

            hypothetical_saved = decision.hypothetical_bytes_avoided
            if decision.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE:
                self.metrics.shadow_hypothetical_bytes_avoided += hypothetical_saved

            trace = V0DecisionTrace(
                event_id=f"evt-read-{int(time.time() * 1000)}",
                event_type="FILE_READ",
                capabilities_considered=["READ_RECEIPT_SHADOW"],
                preconditions={"plane_a_freshness_proven": decision.plane_a_freshness_proven},
                decision=str(decision.disposition.value),
                reason=decision.reason,
                raw_bytes=raw_len,
                visible_bytes=raw_len,  # ALWAYS raw delivered in shadow mode
                authority_class="OBSERVATIONAL_SHADOW_ONLY",
                disposition="SHADOW",
                shadow_hypothetical_bytes_avoided=hypothetical_saved,
            )
            self.traces.append(trace)
            return raw_bytes, decision

        except Exception as e:
            self.metrics.fail_to_raw_counts += 1
            raw_bytes = b""
            try:
                if path_obj.exists():
                    raw_bytes = path_obj.read_bytes()
            except Exception:
                pass
            raw_len = len(raw_bytes)
            trace = V0DecisionTrace(
                event_id=f"evt-read-err-{int(time.time() * 1000)}",
                event_type="FILE_READ",
                capabilities_considered=["READ_RECEIPT_SHADOW"],
                preconditions={"plane_a_freshness_proven": False},
                decision="FAIL_TO_RAW",
                reason=f"Read receipt evaluator error: {e}",
                raw_bytes=raw_len,
                visible_bytes=raw_len,
                authority_class="OBSERVATIONAL_SHADOW_ONLY",
                disposition="RAW",
            )
            self.traces.append(trace)
            decision = ReadReceiptDecision(
                call_id=cid,
                receipt_id=None,
                disposition=ReadReceiptDisposition.READ_ERROR_RAW,
                freshness_level=None,
                original_path=str(file_path),
                resolved_path_identity=None,
                requested_view=None,
                raw_bytes=raw_len,
                delivered_sha256="",
                hypothetical_reference=None,
                reference_bytes=0,
                hypothetical_bytes_avoided=0,
                call_distance=None,
                episode_distance=None,
                reason=f"Exception: {e}",
                plane_a_freshness_proven=False,
                plane_b_active_authorized=False,
            )
            return raw_bytes, decision

    # -----------------------------------------------------------------------
    # Representation Evaluation (T02)
    # -----------------------------------------------------------------------

    def evaluate_representation(
        self,
        raw_output_bytes: bytes,
        evidence: Optional[RgStandardEvidence] = None,
        explicit_transform_authorized: bool = False,
    ) -> Tuple[bytes, Optional[RgGroupingOutcome]]:
        """
        Evaluate output representation under T02.
        
        INVARIANTS:
        - If evidence is missing: emits exact RAW bytes.
        - If explicit_transform_authorized is False: evaluates candidate without applying.
        - If unknown: fails open to RAW bytes.
        """
        self.metrics.events_seen += 1
        raw_len = len(raw_output_bytes)

        if evidence is None:
            # Missing producer evidence -> Gate fails open to RAW
            self.metrics.t02_raw += 1
            trace = V0DecisionTrace(
                event_id=f"evt-rep-{int(time.time() * 1000)}",
                event_type="SEARCH_OUTPUT",
                capabilities_considered=["T02_LOSSLESS_RG"],
                preconditions={"producer_evidence_present": False},
                decision="EMIT_RAW",
                reason="ENGINE_METADATA_GATE_REMAINS: no caller-supplied RgStandardEvidence",
                raw_bytes=raw_len,
                visible_bytes=raw_len,
                authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                disposition="RAW",
            )
            self.traces.append(trace)
            return raw_output_bytes, None

        try:
            outcome = self._t02.evaluate(raw_output_bytes, evidence)
            meta = outcome.metadata
            if meta and meta.candidate_visible_byte_count is not None:
                self.metrics.t02_eligible += 1

            if outcome.applied and explicit_transform_authorized:
                # Explicit transform authorized
                self.metrics.t02_transformed += 1
                self.metrics.actual_visible_bytes_reduced += meta.bytes_saved
                trace = V0DecisionTrace(
                    event_id=f"evt-rep-{int(time.time() * 1000)}",
                    event_type="SEARCH_OUTPUT",
                    capabilities_considered=["T02_LOSSLESS_RG"],
                    preconditions={
                        "producer_evidence_present": True,
                        "roundtrip_verified": meta.roundtrip_verified,
                        "no_expansion": not meta.no_expansion_fallback,
                    },
                    decision="APPLY_TRANSFORM",
                    reason=outcome.reason,
                    raw_bytes=raw_len,
                    visible_bytes=len(outcome.visible_content),
                    authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                    disposition="TRANSFORM",
                    actual_visible_bytes_reduced=meta.bytes_saved,
                )
                self.traces.append(trace)
                return outcome.visible_content, outcome
            else:
                # Shadow/Candidate evaluation without active transformation
                self.metrics.t02_raw += 1
                trace = V0DecisionTrace(
                    event_id=f"evt-rep-{int(time.time() * 1000)}",
                    event_type="SEARCH_OUTPUT",
                    capabilities_considered=["T02_LOSSLESS_RG"],
                    preconditions={"producer_evidence_present": True},
                    decision="EMIT_RAW_CANDIDATE_OBSERVED",
                    reason=f"Transform applied={outcome.applied}; explicit authorization={explicit_transform_authorized}",
                    raw_bytes=raw_len,
                    visible_bytes=raw_len,
                    authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                    disposition="RAW",
                )
                self.traces.append(trace)
                return raw_output_bytes, outcome

        except Exception as e:
            self.metrics.fail_to_raw_counts += 1
            self.metrics.t02_raw += 1
            trace = V0DecisionTrace(
                event_id=f"evt-rep-err-{int(time.time() * 1000)}",
                event_type="SEARCH_OUTPUT",
                capabilities_considered=["T02_LOSSLESS_RG"],
                preconditions={"producer_evidence_present": True},
                decision="FAIL_TO_RAW",
                reason=f"T02 evaluation error: {e}",
                raw_bytes=raw_len,
                visible_bytes=raw_len,
                authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                disposition="RAW",
            )
            self.traces.append(trace)
            return raw_output_bytes, None

    # -----------------------------------------------------------------------
    # End-to-End Lab Scenario
    # -----------------------------------------------------------------------

    def run_lab_scenario(
        self,
        repo_root: pathlib.Path,
        task_query: str = "update read receipt freshness check",
    ) -> Dict[str, Any]:
        """
        Execute deterministic end-to-end integration scenario exercising:
        1. Task query -> Discovery shadow navigation
        2. File read -> Initial read receipt registration (emits RAW)
        3. Repeated file read -> Read receipt shadow reference evaluation (emits RAW)
        4. Search output -> T02 representation evaluation (emits RAW without explicit authorization)
        5. Metrics & accounting verification
        """
        t0 = time.monotonic()
        results: Dict[str, Any] = {}

        # 1. Discovery shadow
        t_d0 = time.monotonic()
        ev = self.evaluate_discovery(repo_root, task_query, top_k=5)
        t_discovery_ms = (time.monotonic() - t_d0) * 1000
        results["step_1_discovery"] = {
            "status": "PASS" if ev else "FAIL_OPEN",
            "top_candidates": [c.path for c in ev.candidates] if ev else [],
            "query_hash": ev.query_hash if ev else None,
            "duration_ms": round(t_discovery_ms, 2),
        }

        # 2. File read (Initial read of a real file)
        target_file = repo_root / "fiofilter" / "read_receipt.py"
        t_r1_0 = time.monotonic()
        out_1, dec_1 = self.evaluate_read_shadow(target_file, call_id="scenario-call-1", call_index=1)
        t_r1_ms = (time.monotonic() - t_r1_0) * 1000
        results["step_2_initial_read"] = {
            "delivered_bytes": len(out_1),
            "disposition": dec_1.disposition.value,
            "duration_ms": round(t_r1_ms, 2),
        }

        # 3. Repeated file read (Identical bytes in same session -> proven F4 shadow reference)
        t_r2_0 = time.monotonic()
        out_2, dec_2 = self.evaluate_read_shadow(target_file, call_id="scenario-call-2", call_index=2)
        t_r2_ms = (time.monotonic() - t_r2_0) * 1000
        assert out_2 == out_1, "Step 3 MUST deliver exact RAW bytes"
        results["step_3_repeated_read"] = {
            "delivered_bytes": len(out_2),
            "disposition": dec_2.disposition.value,
            "reference_eligible": dec_2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE,
            "hypothetical_reference": dec_2.hypothetical_reference,
            "hypothetical_bytes_avoided": dec_2.hypothetical_bytes_avoided,
            "duration_ms": round(t_r2_ms, 2),
        }

        # 4. Search output evaluation (T02)
        sample_rg = (
            b"src/main.py:10:import os\n"
            b"src/main.py:11:import sys\n"
            b"src/main.py:12:import time\n"
        )
        evidence = RgStandardEvidence(
            command="rg import src/main.py",
            command_structurally_grounded=True,
            single_search_producer=True,
            exit_code=0,
            truncated=False,
            upstream_truncation_observed=False,
            shell_failure_wrapper_observed=False,
        )
        t_s0 = time.monotonic()
        out_search, outcome = self.evaluate_representation(sample_rg, evidence, explicit_transform_authorized=False)
        t_search_ms = (time.monotonic() - t_s0) * 1000
        assert out_search == sample_rg, "Search output MUST remain RAW when explicit transform not authorized"
        results["step_4_search_representation"] = {
            "delivered_bytes": len(out_search),
            "t02_candidate_eligible": outcome is not None and outcome.metadata.candidate_visible_byte_count is not None,
            "bytes_saved_if_applied": outcome.metadata.bytes_saved if outcome else 0,
            "duration_ms": round(t_search_ms, 2),
        }

        # 5. Metrics & Accounting
        results["step_5_metrics"] = self.metrics.to_dict()
        results["total_scenario_ms"] = round((time.monotonic() - t0) * 1000, 2)
        return results
