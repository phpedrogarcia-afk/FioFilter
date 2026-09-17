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
    LiveReadResult,
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
# V0 Capability Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class V0CapabilityEntry:
    """Explicit capability record in the V0 registry."""
    capability_id: str
    version: str
    name: str
    lifecycle_state: CapabilityLifecycleState
    authority: str
    activation_mode: str
    evidence_gate: str
    production_status: str
    description: str = ""


CapabilityDescriptor = V0CapabilityEntry

_t02_entry = V0CapabilityEntry(
    capability_id="T02_RG_STANDARD_GROUP_V1",
    version="1.0.0",
    name="Lossless Ripgrep Standard Path-Line Grouping",
    lifecycle_state=CapabilityLifecycleState.VALIDATED_OFFLINE,
    authority="TRANSFORM_ONLY_WHEN_PROVEN",
    activation_mode="EXPLICIT_ONLY",
    evidence_gate="ENGINE_METADATA_GATE_REMAINS",
    production_status="NOT_PRODUCTION_READY",
    description="Lossless grouping for authorized RG_STANDARD_PATH_LINE_TEXT grammar with roundtrip guarantee.",
)

_rcpt_entry = V0CapabilityEntry(
    capability_id="READ_RECEIPT_SHADOW_V1",
    version="1.0.0",
    name="Filesystem-Aware Read Receipt Shadow",
    lifecycle_state=CapabilityLifecycleState.SHADOW_READY,
    authority="OBSERVATIONAL_SHADOW_ONLY",
    activation_mode="EXPLICIT_SHADOW",
    evidence_gate="PASSIVE_OR_DIRECT_EVIDENCE_PROVEN",
    production_status="NOT_PRODUCTION_READY",
    description="Tracks read views and computes hypothetical reference replacements without modifying output.",
)

_disc_entry = V0CapabilityEntry(
    capability_id="DISCOVERY_RUNTIME_SHADOW_V1",
    version="1.0.0",
    name="BM25 Discovery Runtime Shadow",
    lifecycle_state=CapabilityLifecycleState.SHADOW_READY,
    authority="NAVIGATION_ONLY",
    activation_mode="EXPLICIT_SHADOW",
    evidence_gate="CONTENT_SENSITIVE_V2_FINGERPRINT",
    production_status="NOT_PRODUCTION_READY",
    description="Deterministic BM25 repository file ranking and compact map generation.",
)

V0_CAPABILITY_REGISTRY: Dict[str, V0CapabilityEntry] = {
    "T02_LOSSLESS_RG": _t02_entry,
    "T02_RG_STANDARD_GROUP": _t02_entry,
    "READ_RECEIPT_SHADOW": _rcpt_entry,
    "DISCOVERY_BM25_SHADOW": _disc_entry,
    "DISCOVERY_RUNTIME_SHADOW": _disc_entry,
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

    def __post_init__(self) -> None:
        if self.mode != "EXPLICIT_LAB":
            raise ValueError(f"Unsupported mode: '{self.mode}'. V0 only supports 'EXPLICIT_LAB'.")
        if self.active_suppression:
            raise ValueError("active_suppression=True is rejected in V0. Offline V0 must not suppress content.")
        if self.auto_context_selection:
            raise ValueError("auto_context_selection=True is rejected in V0.")
        if self.network:
            raise ValueError("network=True is rejected in V0.")
        if self.persistence != "EPHEMERAL":
            raise ValueError(f"persistence='{self.persistence}' is rejected in V0. V0 only supports 'EPHEMERAL'.")


# ---------------------------------------------------------------------------
# Decision Trace and Metrics Accounting
# ---------------------------------------------------------------------------

@dataclass
class V0DecisionTrace:
    """
    Auditable in-memory trace for an individual evaluated event.
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
    delivered_disposition: str = "RAW"  # Explicit final delivery disposition (always RAW in shadow)
    shadow_decision: Optional[str] = None
    actual_visible_bytes_reduced: int = 0
    actual_t02_bytes_reduced: int = 0
    shadow_hypothetical_bytes_avoided: int = 0
    shadow_read_reference_bytes_avoided: int = 0
    shadow_t02_bytes_avoided: int = 0
    timestamp_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class V0MetricsSummary:
    """
    Aggregate metrics summary strictly separating actual from hypothetical savings.
    INVARIANT: actual and hypothetical savings must NEVER be summed together.
    """
    events_seen: int = 0
    discovery_shadow_queries: int = 0
    discovery_orientations_produced: int = 0
    discovery_failures: int = 0
    t02_candidate_evaluated: int = 0
    t02_eligible: int = 0
    t02_no_economic_gain: int = 0
    t02_rejected: int = 0
    t02_transformed: int = 0
    t02_raw: int = 0
    read_receipt_evaluations: int = 0
    reference_candidates: int = 0
    raw_read_decisions: int = 0
    fail_to_raw_counts: int = 0
    actual_visible_bytes_reduced: int = 0
    actual_t02_bytes_reduced: int = 0
    shadow_hypothetical_bytes_avoided: int = 0
    shadow_read_reference_bytes_avoided: int = 0
    shadow_t02_bytes_avoided: int = 0

    @property
    def read_receipt_candidates(self) -> int:
        """Backwards-compatibility property matching historical read_receipt_evaluations."""
        return self.read_receipt_evaluations

    def to_dict(self) -> dict:
        d = asdict(self)
        d["read_receipt_candidates"] = self.read_receipt_evaluations
        return d


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
        self.read_evaluator = ReadReceiptEvaluator(session_id="v0-lab-session")
        self._t02 = RgStandardLosslessGrouping()
        self.traces: List[V0DecisionTrace] = []
        self.metrics = V0MetricsSummary()
        self._event_counter: int = 0
        self._read_call_counter: int = 0

    def _next_event_id(self, prefix: str) -> str:
        """Deterministic per-lab monotonic event counter."""
        self._event_counter += 1
        return f"evt-{prefix}-{self._event_counter:04d}"

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
            if ev is not None:
                self.metrics.discovery_orientations_produced += 1
                decision = "SHADOW_ORIENTATION_PRODUCED"
                reason = "BM25 ranking computed"
                disposition = "SHADOW"
                delivered_disp = "SHADOW"
            else:
                self.metrics.discovery_failures += 1
                self.metrics.fail_to_raw_counts += 1
                decision = "DISCOVERY_FAILED_FAIL_OPEN"
                reason = "Discovery evaluation returned None"
                disposition = "RAW"
                delivered_disp = "RAW"

            trace = V0DecisionTrace(
                event_id=self._next_event_id("disc"),
                event_type="DISCOVERY_QUERY",
                capabilities_considered=["DISCOVERY_BM25_SHADOW"],
                preconditions={"worktree_valid": ev is not None},
                decision=decision,
                reason=reason,
                raw_bytes=len(task_query.encode("utf-8")),
                visible_bytes=len(task_query.encode("utf-8")),
                authority_class="NAVIGATION_ONLY",
                disposition=disposition,
                delivered_disposition=delivered_disp,
                shadow_decision=decision,
            )
            self.traces.append(trace)
            return ev
        except Exception as e:
            self.metrics.fail_to_raw_counts += 1
            self.metrics.discovery_failures += 1
            trace = V0DecisionTrace(
                event_id=self._next_event_id("disc-err"),
                event_type="DISCOVERY_QUERY",
                capabilities_considered=["DISCOVERY_BM25_SHADOW"],
                preconditions={"worktree_valid": False},
                decision="FAIL_TO_RAW",
                reason=f"Exception in discovery: {e}",
                raw_bytes=len(task_query.encode("utf-8")),
                visible_bytes=len(task_query.encode("utf-8")),
                authority_class="NAVIGATION_ONLY",
                disposition="RAW",
                delivered_disposition="RAW",
                shadow_decision="FAIL_TO_RAW",
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
        call_index: Optional[int] = None,
        episode_id: Optional[int] = None,
    ) -> Tuple[bytes, ReadReceiptDecision]:
        """
        Evaluate a file read through the Read Receipt shadow harness.
        
        INVARIANTS:
        - Single physical read: the exact bytes used for freshness proof are delivered to caller.
        - PROOF_BYTES_EQUAL_DELIVERED_BYTES=PASS.
        - Delivered disposition is 100% RAW.
        - Monotonic call_index increments if omitted.
        """
        self.metrics.events_seen += 1
        self.metrics.read_receipt_evaluations += 1
        path_obj = pathlib.Path(file_path).resolve()

        if call_index is None:
            actual_call_index = self._read_call_counter
            self._read_call_counter += 1
        else:
            if call_index < 0:
                raise ValueError("call_index must be non-negative")
            actual_call_index = call_index
            if call_index >= self._read_call_counter:
                self._read_call_counter = call_index + 1

        cid = call_id or f"call-{actual_call_index}"

        try:
            # SINGLE PHYSICAL READ: evaluation and delivery use the exact same buffer
            result = self.read_evaluator.evaluate_live_read_result(
                call_id=cid,
                file_path=path_obj,
                call_index=actual_call_index,
                episode_id=episode_id,
            )
            raw_bytes = result.raw_bytes
            decision = result.decision
            raw_len = len(raw_bytes)

            # Core Single-Buffer Invariant verification
            if decision.delivered_sha256 and raw_bytes:
                assert hashlib.sha256(raw_bytes).hexdigest() == decision.delivered_sha256, (
                    "PROOF_BYTES_EQUAL_DELIVERED_BYTES invariant violated"
                )
                assert raw_len == decision.raw_bytes, "Raw length invariant violated"

            hypothetical_saved = decision.hypothetical_bytes_avoided
            is_reference_candidate = decision.disposition in (
                ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE,
                ReadReceiptDisposition.HISTORICAL_IDENTICAL_READ_CANDIDATE,
            )
            if is_reference_candidate:
                self.metrics.reference_candidates += 1
                self.metrics.shadow_hypothetical_bytes_avoided += hypothetical_saved
                self.metrics.shadow_read_reference_bytes_avoided += hypothetical_saved
            else:
                self.metrics.raw_read_decisions += 1

            trace = V0DecisionTrace(
                event_id=self._next_event_id("read"),
                event_type="FILE_READ",
                capabilities_considered=["READ_RECEIPT_SHADOW"],
                preconditions={"plane_a_freshness_proven": decision.plane_a_freshness_proven},
                decision=str(decision.disposition.value),
                reason=decision.reason,
                raw_bytes=raw_len,
                visible_bytes=raw_len,  # ALWAYS raw delivered in shadow mode
                authority_class="OBSERVATIONAL_SHADOW_ONLY",
                disposition="RAW",  # 100% RAW delivered to caller
                delivered_disposition="RAW",  # Explicit delivery disposition
                shadow_decision=str(decision.disposition.value),
                shadow_hypothetical_bytes_avoided=hypothetical_saved if is_reference_candidate else 0,
                shadow_read_reference_bytes_avoided=hypothetical_saved if is_reference_candidate else 0,
            )
            self.traces.append(trace)
            return raw_bytes, decision

        except Exception as e:
            self.metrics.fail_to_raw_counts += 1
            self.metrics.raw_read_decisions += 1
            raw_bytes = b""
            try:
                if path_obj.exists():
                    raw_bytes = path_obj.read_bytes()
            except Exception:
                pass
            raw_len = len(raw_bytes)
            trace = V0DecisionTrace(
                event_id=self._next_event_id("read-err"),
                event_type="FILE_READ",
                capabilities_considered=["READ_RECEIPT_SHADOW"],
                preconditions={"plane_a_freshness_proven": False},
                decision="FAIL_TO_RAW",
                reason=f"Read receipt evaluator error: {e}",
                raw_bytes=raw_len,
                visible_bytes=raw_len,
                authority_class="OBSERVATIONAL_SHADOW_ONLY",
                disposition="RAW",
                delivered_disposition="RAW",
                shadow_decision="FAIL_TO_RAW",
            )
            self.traces.append(trace)
            decision = ReadReceiptDecision(
                call_id=cid,
                receipt_id=None,
                disposition=ReadReceiptDisposition.READ_ERROR_RAW,
                freshness_level=FreshnessLevel.F0_UNKNOWN,
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
        - T02_ELIGIBLE iff outcome.applied == True before authorization is checked.
        - If unknown: fails open to RAW bytes.
        """
        self.metrics.events_seen += 1
        raw_len = len(raw_output_bytes)

        if evidence is None:
            # Missing producer evidence -> Gate fails open to RAW
            self.metrics.t02_raw += 1
            trace = V0DecisionTrace(
                event_id=self._next_event_id("rep"),
                event_type="SEARCH_OUTPUT",
                capabilities_considered=["T02_LOSSLESS_RG"],
                preconditions={"producer_evidence_present": False},
                decision="EMIT_RAW",
                reason="ENGINE_METADATA_GATE_REMAINS: no caller-supplied RgStandardEvidence",
                raw_bytes=raw_len,
                visible_bytes=raw_len,
                authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                disposition="RAW",
                delivered_disposition="RAW",
                shadow_decision="EMIT_RAW",
            )
            self.traces.append(trace)
            return raw_output_bytes, None

        try:
            self.metrics.t02_candidate_evaluated += 1
            outcome = self._t02.evaluate(raw_output_bytes, evidence)
            meta = outcome.metadata

            # CANONICAL ELIGIBILITY RULE:
            # T02_ELIGIBLE iff outcome.applied == True before authorization is considered
            if outcome.applied:
                self.metrics.t02_eligible += 1
            elif outcome.reason == "VALID_GRAMMAR_NO_ECONOMIC_GAIN":
                self.metrics.t02_no_economic_gain += 1
            else:
                self.metrics.t02_rejected += 1

            if outcome.applied and explicit_transform_authorized:
                # Explicit transform authorized
                bytes_saved = meta.bytes_saved if meta else 0
                self.metrics.t02_transformed += 1
                self.metrics.actual_visible_bytes_reduced += bytes_saved
                self.metrics.actual_t02_bytes_reduced += bytes_saved
                trace = V0DecisionTrace(
                    event_id=self._next_event_id("rep"),
                    event_type="SEARCH_OUTPUT",
                    capabilities_considered=["T02_LOSSLESS_RG"],
                    preconditions={
                        "producer_evidence_present": True,
                        "roundtrip_verified": meta.roundtrip_verified if meta else False,
                        "no_expansion": not meta.no_expansion_fallback if meta else False,
                    },
                    decision="APPLY_TRANSFORM",
                    reason=outcome.reason,
                    raw_bytes=raw_len,
                    visible_bytes=len(outcome.visible_content),
                    authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                    disposition="TRANSFORM",
                    delivered_disposition="TRANSFORM",
                    shadow_decision="APPLY_TRANSFORM",
                    actual_visible_bytes_reduced=bytes_saved,
                    actual_t02_bytes_reduced=bytes_saved,
                )
                self.traces.append(trace)
                return outcome.visible_content, outcome
            else:
                # Shadow/Candidate evaluation without active transformation
                self.metrics.t02_raw += 1
                potential_savings = meta.bytes_saved if (outcome.applied and meta) else 0
                if potential_savings > 0:
                    self.metrics.shadow_hypothetical_bytes_avoided += potential_savings
                    self.metrics.shadow_t02_bytes_avoided += potential_savings

                trace = V0DecisionTrace(
                    event_id=self._next_event_id("rep"),
                    event_type="SEARCH_OUTPUT",
                    capabilities_considered=["T02_LOSSLESS_RG"],
                    preconditions={"producer_evidence_present": True},
                    decision="EMIT_RAW_CANDIDATE_OBSERVED",
                    reason=f"Transform applied={outcome.applied}; explicit authorization={explicit_transform_authorized}",
                    raw_bytes=raw_len,
                    visible_bytes=raw_len,
                    authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                    disposition="RAW",
                    delivered_disposition="RAW",
                    shadow_decision="EMIT_RAW_CANDIDATE_OBSERVED" if outcome.applied else outcome.reason,
                    shadow_hypothetical_bytes_avoided=potential_savings,
                    shadow_t02_bytes_avoided=potential_savings,
                )
                self.traces.append(trace)
                return raw_output_bytes, outcome

        except Exception as e:
            self.metrics.fail_to_raw_counts += 1
            self.metrics.t02_raw += 1
            trace = V0DecisionTrace(
                event_id=self._next_event_id("rep-err"),
                event_type="SEARCH_OUTPUT",
                capabilities_considered=["T02_LOSSLESS_RG"],
                preconditions={"producer_evidence_present": True},
                decision="FAIL_TO_RAW",
                reason=f"T02 evaluation error: {e}",
                raw_bytes=raw_len,
                visible_bytes=raw_len,
                authority_class="TRANSFORM_ONLY_WHEN_PROVEN",
                disposition="RAW",
                delivered_disposition="RAW",
                shadow_decision="FAIL_TO_RAW",
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
        3. Repeated file read -> Read receipt shadow reference evaluation (emits RAW via single-buffer)
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
        assert hashlib.sha256(out_2).hexdigest() == dec_2.delivered_sha256, "Single-buffer SHA256 must match"
        results["step_3_repeated_read"] = {
            "delivered_bytes": len(out_2),
            "disposition": dec_2.disposition.value,
            "reference_eligible": dec_2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE,
            "hypothetical_reference": dec_2.hypothetical_reference,
            "hypothetical_bytes_avoided": dec_2.hypothetical_bytes_avoided,
            "duration_ms": round(t_r2_ms, 2),
        }

        # 4. Search output evaluation (T02) - Repetitive inert synthetic RG fixture
        nested_path = "src/subsystem/core/components/service_runner_handler.py"
        lines = [
            f"{nested_path}:{i}:def run_worker_task_{i}(payload: dict) -> None:"
            for i in range(1, 25)
        ]
        sample_rg = ("\n".join(lines) + "\n").encode("utf-8")
        evidence = RgStandardEvidence(
            command=f"rg run_worker_task {nested_path}",
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
        assert outcome is not None and outcome.applied is True, "Scenario fixture must be technically applicable"
        assert outcome.metadata.bytes_saved > 0, "Scenario fixture must have positive economic gain"

        results["step_4_search_representation"] = {
            "delivered_bytes": len(out_search),
            "t02_applicable": outcome.applied,
            "t02_authorized": False,
            "delivered_raw": out_search == sample_rg,
            "t02_candidate_eligible": outcome.applied,
            "bytes_saved_if_applied": outcome.metadata.bytes_saved if outcome and outcome.metadata else 0,
            "duration_ms": round(t_search_ms, 2),
        }

        # 5. Metrics & Accounting
        results["step_5_metrics"] = self.metrics.to_dict()
        results["total_scenario_ms"] = round((time.monotonic() - t0) * 1000, 2)
        return results
