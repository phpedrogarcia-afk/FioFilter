"""
tests/test_v0_integration.py
M12: Tests for the FioFilter V0 Explicit Integration Spine.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from fiofilter.v0 import (
    FioFilterV0Lab,
    V0Config,
    V0_CAPABILITY_REGISTRY,
    CapabilityLifecycleState,
    V0DecisionTrace,
    V0MetricsSummary,
)
from fiofilter.read_receipt import ReadReceiptDisposition
from fiofilter.transforms.t02_rg_standard_group import RgStandardEvidence


REPO_ROOT = pathlib.Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Capability Registry Tests
# ---------------------------------------------------------------------------

class TestCapabilityRegistry:
    def test_registry_has_expected_capabilities(self):
        assert "T02_LOSSLESS_RG" in V0_CAPABILITY_REGISTRY
        assert "READ_RECEIPT_SHADOW" in V0_CAPABILITY_REGISTRY
        assert "DISCOVERY_BM25_SHADOW" in V0_CAPABILITY_REGISTRY

    def test_non_collapsing_status_states(self):
        t02 = V0_CAPABILITY_REGISTRY["T02_LOSSLESS_RG"]
        assert t02.lifecycle_state == CapabilityLifecycleState.VALIDATED_OFFLINE
        assert t02.production_status == "NOT_PRODUCTION_READY"
        assert t02.activation_mode == "EXPLICIT_ONLY"

        rcpt = V0_CAPABILITY_REGISTRY["READ_RECEIPT_SHADOW"]
        assert rcpt.lifecycle_state == CapabilityLifecycleState.SHADOW_READY
        assert rcpt.production_status == "NOT_PRODUCTION_READY"
        assert rcpt.activation_mode == "EXPLICIT_SHADOW"

        disc = V0_CAPABILITY_REGISTRY["DISCOVERY_BM25_SHADOW"]
        assert disc.lifecycle_state == CapabilityLifecycleState.SHADOW_READY
        assert disc.authority == "NAVIGATION_ONLY"
        assert disc.production_status == "NOT_PRODUCTION_READY"

    def test_lifecycle_states_distinct(self):
        states = set(s.value for s in CapabilityLifecycleState)
        expected = {
            "IMPLEMENTED",
            "VALIDATED_OFFLINE",
            "SHADOW_READY",
            "LIVE_VALIDATED",
            "ACTIVE_AUTHORIZED",
            "PRODUCTION_READY",
        }
        assert states == expected


# ---------------------------------------------------------------------------
# Cross-Component Invariants Tests
# ---------------------------------------------------------------------------

class TestCrossComponentInvariants:
    def test_status_reports_invariants(self):
        lab = FioFilterV0Lab()
        status = lab.get_status()
        assert status["T02_LOSSLESS_RG"] == "IMPLEMENTED_EXPLICIT_ONLY"
        assert status["READ_RECEIPT"] == "SHADOW_READY"
        assert status["DISCOVERY"] == "SHADOW_READY"
        assert status["ACTIVE_SUPPRESSION"] == "OFF"
        assert status["AUTO_CONTEXT_SELECTION"] == "OFF"
        assert status["CODEX_LIVE_VALIDATION"] == "PENDING"
        assert status["ENGINE_METADATA_GATE"] == "ENGINE_METADATA_GATE_REMAINS"
        assert status["DEFAULT_DISPOSITION"] == "RAW"
        assert status["INDEX_AUTHORITY"] == "NAVIGATION_ONLY"

    def test_discovery_cannot_authorize_read_suppression(self):
        lab = FioFilterV0Lab()
        # Discovery shadow produces orientation metadata
        ev = lab.evaluate_discovery(REPO_ROOT, "read receipt")
        assert ev is not None
        assert ev.index_authority == "NAVIGATION_ONLY"
        # Reading a candidate file through read shadow MUST deliver raw bytes
        target = REPO_ROOT / "fiofilter" / "read_receipt.py"
        raw_out, dec = lab.evaluate_read_shadow(target)
        assert raw_out == target.read_bytes()

    def test_shadow_cannot_change_raw_output(self):
        lab = FioFilterV0Lab()
        target = REPO_ROOT / "fiofilter" / "invariants.py"
        raw_bytes = target.read_bytes()
        # Call read shadow 3 times in a row
        for i in range(1, 4):
            out, dec = lab.evaluate_read_shadow(target, call_index=i)
            assert out == raw_bytes, f"Call {i} modified RAW bytes!"

    def test_unknown_anywhere_fails_to_raw(self):
        lab = FioFilterV0Lab()
        # Representation evaluation with missing evidence fails open to RAW
        raw = b"random content without evidence"
        out, outcome = lab.evaluate_representation(raw, evidence=None)
        assert out == raw
        assert outcome is None


# ---------------------------------------------------------------------------
# End-to-End Lab Scenario Tests
# ---------------------------------------------------------------------------

class TestV0EndToEndLabScenario:
    def test_run_scenario_success(self):
        lab = FioFilterV0Lab()
        results = lab.run_lab_scenario(REPO_ROOT)
        
        # Step 1: Discovery shadow
        assert results["step_1_discovery"]["status"] == "PASS"
        assert len(results["step_1_discovery"]["top_candidates"]) > 0

        # Step 2: Initial read
        assert results["step_2_initial_read"]["disposition"] == "FIRST_READ_RAW"
        assert results["step_2_initial_read"]["delivered_bytes"] > 0

        # Step 3: Repeated read
        assert results["step_3_repeated_read"]["disposition"] == "LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE"
        assert results["step_3_repeated_read"]["reference_eligible"] is True
        assert results["step_3_repeated_read"]["hypothetical_bytes_avoided"] > 0
        assert "[[FIOFILTER:READREF:v1" in results["step_3_repeated_read"]["hypothetical_reference"]

        # Step 4: Search output (T02)
        assert results["step_4_search_representation"]["delivered_bytes"] > 0
        assert results["step_4_search_representation"]["t02_applicable"] is True
        assert results["step_4_search_representation"]["t02_authorized"] is False
        assert results["step_4_search_representation"]["delivered_raw"] is True
        assert results["step_4_search_representation"]["bytes_saved_if_applied"] > 0

        # Step 5: Metrics accounting
        m = results["step_5_metrics"]
        assert m["events_seen"] == 4
        assert m["discovery_shadow_queries"] == 1
        assert m["t02_eligible"] == 1
        assert m["t02_transformed"] == 0  # Not applied without explicit authorization
        assert m["t02_raw"] == 1
        assert m["read_receipt_evaluations"] == 2
        assert m["reference_candidates"] == 1
        assert m["raw_read_decisions"] == 1
        assert m["read_receipt_candidates"] == 2
        assert m["actual_visible_bytes_reduced"] == 0
        assert m["actual_t02_bytes_reduced"] == 0
        assert m["shadow_read_reference_bytes_avoided"] > 0
        assert m["shadow_t02_bytes_avoided"] > 0
        assert m["shadow_hypothetical_bytes_avoided"] > 0

    def test_explicit_transform_authorized(self):
        lab = FioFilterV0Lab()
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
        out, outcome = lab.evaluate_representation(
            sample_rg, evidence, explicit_transform_authorized=True
        )
        assert outcome is not None and outcome.applied is True
        assert out != sample_rg
        assert b"[[FIOFILTER:T02_RG_STANDARD_GROUP:v1" in out
        assert lab.metrics.actual_visible_bytes_reduced > 0
        assert lab.metrics.actual_t02_bytes_reduced > 0
        assert lab.metrics.t02_transformed == 1


# ---------------------------------------------------------------------------
# Decision Trace and Accounting Tests
# ---------------------------------------------------------------------------

class TestDecisionTraceAndAccounting:
    def test_decision_trace_records_events(self):
        lab = FioFilterV0Lab()
        lab.run_lab_scenario(REPO_ROOT)
        assert len(lab.traces) >= 4
        for trace in lab.traces:
            assert trace.event_id
            assert trace.event_type in ("DISCOVERY_QUERY", "FILE_READ", "SEARCH_OUTPUT")
            assert trace.disposition in ("RAW", "SHADOW", "TRANSFORM")
            assert trace.authority_class in (
                "NAVIGATION_ONLY",
                "OBSERVATIONAL_SHADOW_ONLY",
                "TRANSFORM_ONLY_WHEN_PROVEN",
            )

    def test_actual_and_hypothetical_never_summed(self):
        lab = FioFilterV0Lab()
        lab.run_lab_scenario(REPO_ROOT)
        m = lab.metrics
        # In default shadow scenario: actual is 0, hypothetical is positive
        assert m.actual_visible_bytes_reduced == 0
        assert m.shadow_hypothetical_bytes_avoided > 0
        # Check dictionary has both distinct fields
        d = m.to_dict()
        assert "actual_visible_bytes_reduced" in d
        assert "shadow_hypothetical_bytes_avoided" in d


# ---------------------------------------------------------------------------
# Failure Isolation Tests
# ---------------------------------------------------------------------------

class TestFailureIsolation:
    def test_discovery_failure_returns_none(self):
        lab = FioFilterV0Lab()
        ev = lab.evaluate_discovery(pathlib.Path("C:/nonexistent/dir"), "query")
        assert ev is None

    def test_read_failure_emits_raw(self):
        lab = FioFilterV0Lab()
        out, dec = lab.evaluate_read_shadow(pathlib.Path("C:/nonexistent/file.txt"))
        assert out == b""
        assert dec.disposition == ReadReceiptDisposition.MISSING_FILE_RAW or dec.disposition == ReadReceiptDisposition.READ_ERROR_RAW


# ---------------------------------------------------------------------------
# CLI Entry Point Tests
# ---------------------------------------------------------------------------

class TestV0CLI:
    def test_cli_status(self):
        r = subprocess.run(
            [sys.executable, "-m", "fiofilter", "status"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0
        assert "T02_LOSSLESS_RG" in r.stdout
        assert "READ_RECEIPT" in r.stdout
        assert "DISCOVERY" in r.stdout

    def test_cli_status_json(self):
        r = subprocess.run(
            [sys.executable, "-m", "fiofilter", "--json", "status"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["status"]["ACTIVE_SUPPRESSION"] == "OFF"
        assert "capabilities" in data

    def test_cli_inspect_repo(self):
        r = subprocess.run(
            [sys.executable, "-m", "fiofilter", "--json", "inspect-repo", "."],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "worktree_state_digest_v2" in data
        assert len(data["worktree_state_digest_v2"]) == 16

    def test_cli_run_lab_scenario(self):
        r = subprocess.run(
            [sys.executable, "-m", "fiofilter", "run-lab-scenario", "."],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["step_1_discovery"]["status"] == "PASS"
        assert data["step_3_repeated_read"]["reference_eligible"] is True


# ---------------------------------------------------------------------------
# M12-R1 Integrity Repair Tests
# ---------------------------------------------------------------------------

class TestM12R1IntegrityRepairs:
    def test_double_read_old_architecture_divergence_reproduction(self, tmp_path):
        """Reproduce the old double-read TOCTOU danger and prove new shared-buffer immunity."""
        test_file = tmp_path / "target.txt"
        test_file.write_bytes(b"INITIAL_CONTENT_A")

        # Simulate old vulnerable architecture:
        # Step 1: Read for proof
        proof_bytes = test_file.read_bytes()
        proof_sha = hashlib.sha256(proof_bytes).hexdigest()

        # Step 2: Adversarial file mutation between reads
        test_file.write_bytes(b"MUTATED_CONTENT_B")

        # Step 3: Second read for delivery in old architecture
        delivered_bytes_old = test_file.read_bytes()
        delivered_sha_old = hashlib.sha256(delivered_bytes_old).hexdigest()

        # PROVE: Old architecture could diverge!
        assert proof_sha != delivered_sha_old, "OLD_DOUBLE_READ_DIVERGENCE_POSSIBLE must be reproduced"

        # Now test NEW FioFilter single-buffer direct read architecture:
        test_file.write_bytes(b"STABLE_CONTENT_V2")
        lab = FioFilterV0Lab()
        raw_out, dec = lab.evaluate_read_shadow(test_file, call_index=1)

        # Mutate file immediately after evaluation
        test_file.write_bytes(b"MUTATED_AFTER_READ")

        # PROVE: Buffer delivered to caller matches decision proof byte-for-byte
        assert hashlib.sha256(raw_out).hexdigest() == dec.delivered_sha256
        assert len(raw_out) == dec.raw_bytes
        assert raw_out == b"STABLE_CONTENT_V2"

    def test_single_buffer_direct_read_contract(self, tmp_path):
        """Verify single physical read contract: returned bytes equal decision proof bytes."""
        test_file = tmp_path / "sample.txt"
        content = b"Single physical read content buffer 12345"
        test_file.write_bytes(content)

        lab = FioFilterV0Lab()
        raw_bytes, dec = lab.evaluate_read_shadow(test_file, call_index=1)

        assert raw_bytes == content
        assert dec.delivered_sha256 == hashlib.sha256(content).hexdigest()
        assert dec.raw_bytes == len(content)

    def test_read_call_index_auto_increment(self, tmp_path):
        """Verify automatic incrementation of call_index when omitted by caller."""
        test_file = tmp_path / "sample.txt"
        test_file.write_bytes(b"Repeated call index test content with enough bytes to be economic: " * 10)

        lab = FioFilterV0Lab()
        # Omit call_index on both calls
        out_1, dec_1 = lab.evaluate_read_shadow(test_file)
        out_2, dec_2 = lab.evaluate_read_shadow(test_file)

        assert dec_1.call_id == "call-0"
        assert dec_2.call_id == "call-1"
        assert dec_2.call_distance == 1
        assert dec_2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE

    def test_cross_session_isolation(self, tmp_path):
        """Verify cross-session reference is strictly forbidden."""
        test_file = tmp_path / "session_test.txt"
        test_file.write_bytes(b"Cross session isolation test file content")

        lab_1 = FioFilterV0Lab()
        lab_2 = FioFilterV0Lab()

        out_1, dec_1 = lab_1.evaluate_read_shadow(test_file)
        assert dec_1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Second lab in different session reads same file
        out_2, dec_2 = lab_2.evaluate_read_shadow(test_file)
        # MUST be FIRST_READ_RAW, not a reference to lab_1's receipt
        assert dec_2.disposition == ReadReceiptDisposition.FIRST_READ_RAW

    def test_t02_eligibility_requires_applied(self):
        """Verify candidate with VALID_GRAMMAR_NO_ECONOMIC_GAIN is not counted as t02_eligible."""
        lab = FioFilterV0Lab()
        # 2 lines: valid grammar but no economic gain
        sample_no_gain = (
            b"src/a.py:1:x = 1\n"
            b"src/a.py:2:y = 2\n"
        )
        evidence = RgStandardEvidence(
            command="rg . src/a.py",
            command_structurally_grounded=True,
            single_search_producer=True,
            exit_code=0,
            truncated=False,
            upstream_truncation_observed=False,
            shell_failure_wrapper_observed=False,
        )
        out, outcome = lab.evaluate_representation(sample_no_gain, evidence, explicit_transform_authorized=False)
        assert outcome is not None
        assert outcome.applied is False
        assert outcome.reason == "VALID_GRAMMAR_NO_ECONOMIC_GAIN"
        # Must NOT be counted as t02_eligible
        assert lab.metrics.t02_eligible == 0
        assert lab.metrics.t02_no_economic_gain == 1
        assert lab.metrics.t02_raw == 1

    def test_t02_applicable_but_unauthorized_stays_raw(self):
        """Verify applicable T02 candidate delivers RAW when unauthorized, with shadow savings recorded."""
        lab = FioFilterV0Lab()
        nested_path = "src/subsystem/deeply/nested/handler.py"
        lines = [f"{nested_path}:{i}:def method_{i}(): pass" for i in range(1, 20)]
        sample_rg = ("\n".join(lines) + "\n").encode("utf-8")
        evidence = RgStandardEvidence(
            command=f"rg method {nested_path}",
            command_structurally_grounded=True,
            single_search_producer=True,
            exit_code=0,
            truncated=False,
            upstream_truncation_observed=False,
            shell_failure_wrapper_observed=False,
        )
        out, outcome = lab.evaluate_representation(sample_rg, evidence, explicit_transform_authorized=False)
        assert out == sample_rg
        assert outcome is not None and outcome.applied is True
        assert lab.metrics.t02_eligible == 1
        assert lab.metrics.t02_transformed == 0
        assert lab.metrics.actual_visible_bytes_reduced == 0
        assert lab.metrics.actual_t02_bytes_reduced == 0
        assert lab.metrics.shadow_t02_bytes_avoided > 0

    def test_t02_applicable_and_authorized_transforms(self):
        """Verify applicable T02 candidate transforms and reduces bytes when explicitly authorized."""
        lab = FioFilterV0Lab()
        nested_path = "src/subsystem/deeply/nested/handler.py"
        lines = [f"{nested_path}:{i}:def method_{i}(): pass" for i in range(1, 20)]
        sample_rg = ("\n".join(lines) + "\n").encode("utf-8")
        evidence = RgStandardEvidence(
            command=f"rg method {nested_path}",
            command_structurally_grounded=True,
            single_search_producer=True,
            exit_code=0,
            truncated=False,
            upstream_truncation_observed=False,
            shell_failure_wrapper_observed=False,
        )
        out, outcome = lab.evaluate_representation(sample_rg, evidence, explicit_transform_authorized=True)
        assert out != sample_rg
        assert outcome is not None and outcome.applied is True
        assert lab.metrics.t02_eligible == 1
        assert lab.metrics.t02_transformed == 1
        assert lab.metrics.actual_visible_bytes_reduced > 0
        assert lab.metrics.actual_t02_bytes_reduced > 0

    def test_v0_config_fail_closed(self):
        """Verify V0Config fails closed on any active/unsupported configuration."""
        with pytest.raises(ValueError, match="active_suppression=True is rejected"):
            V0Config(active_suppression=True)

        with pytest.raises(ValueError, match="auto_context_selection=True is rejected"):
            V0Config(auto_context_selection=True)

        with pytest.raises(ValueError, match="network=True is rejected"):
            V0Config(network=True)

        with pytest.raises(ValueError, match="Unsupported mode"):
            V0Config(mode="AUTONOMOUS_DAEMON")

        with pytest.raises(ValueError, match="persistence='PERSISTENT' is rejected"):
            V0Config(persistence="PERSISTENT")

    def test_discovery_none_failure_accounting(self):
        """Verify DiscoveryRuntimeShadow returning None increments failure counters and records RAW."""
        lab = FioFilterV0Lab()
        ev = lab.evaluate_discovery(pathlib.Path("C:/nonexistent_repo_root_xyz"), "query")
        assert ev is None
        assert lab.metrics.discovery_failures == 1
        assert lab.metrics.fail_to_raw_counts == 1
        assert lab.metrics.discovery_orientations_produced == 0
        trace = lab.traces[-1]
        assert trace.disposition == "RAW"
        assert trace.delivered_disposition == "RAW"
        assert trace.decision == "DISCOVERY_FAILED_FAIL_OPEN"

    def test_read_trace_delivery_semantics_raw_100_percent(self):
        """Verify read shadow traces always have delivered_disposition=RAW."""
        lab = FioFilterV0Lab()
        lab.run_lab_scenario(REPO_ROOT)
        read_traces = [t for t in lab.traces if t.event_type == "FILE_READ"]
        assert len(read_traces) == 2
        for t in read_traces:
            assert t.delivered_disposition == "RAW"
            assert t.disposition == "RAW"

    def test_metric_naming_separation(self):
        """Verify read_receipt_evaluations, reference_candidates, and raw_read_decisions are separated."""
        lab = FioFilterV0Lab()
        lab.run_lab_scenario(REPO_ROOT)
        m = lab.metrics
        assert m.read_receipt_evaluations == 2
        assert m.reference_candidates == 1
        assert m.raw_read_decisions == 1
        assert m.read_receipt_evaluations != m.reference_candidates

    def test_event_id_uniqueness_rapid_loop(self):
        """Verify monotonic event IDs are collision-safe in rapid loop execution."""
        lab = FioFilterV0Lab()
        target = REPO_ROOT / "fiofilter" / "invariants.py"
        for _ in range(50):
            lab.evaluate_read_shadow(target)
        ids = [t.event_id for t in lab.traces]
        assert len(ids) == 50
        assert len(set(ids)) == 50

    def test_cli_docstring_no_phantom_commands(self):
        """Verify CLI docstring and help do not advertise unimplemented evaluate-output."""
        import fiofilter.cli as cli_mod
        assert "evaluate-output" not in cli_mod.__doc__
        assert "T02_DIRECT_CLI" in cli_mod.__doc__