"""
tests/test_v0_integration.py
M12: Tests for the FioFilter V0 Explicit Integration Spine.
"""
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
        assert results["step_4_search_representation"]["delivered_bytes"] == 78
        assert results["step_4_search_representation"]["t02_candidate_eligible"] is True

        # Step 5: Metrics accounting
        m = results["step_5_metrics"]
        assert m["events_seen"] == 4
        assert m["discovery_shadow_queries"] == 1
        assert m["t02_eligible"] == 1
        assert m["t02_transformed"] == 0  # Not applied without explicit authorization
        assert m["t02_raw"] == 1
        assert m["read_receipt_candidates"] == 2
        assert m["actual_visible_bytes_reduced"] == 0
        assert m["shadow_hypothetical_bytes_avoided"] > 0

    def test_explicit_transform_authorized(self):
        lab = FioFilterV0Lab()
        sample_rg = (
            b"src/main.py:10:import os\n"
            b"src/main.py:11:import sys\n"
            b"src/main.py:12:import time\n"
            b"src/main.py:13:import json\n"
            b"src/main.py:14:import hashlib\n"
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
        out, outcome = lab.evaluate_representation(
            sample_rg, evidence, explicit_transform_authorized=True
        )
        if outcome and outcome.applied:
            assert out != sample_rg
            assert b"[[FIOFILTER:T02_RG_STANDARD_GROUP:v1" in out
            assert lab.metrics.actual_visible_bytes_reduced > 0
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