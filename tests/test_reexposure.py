"""Unit and adversarial tests for fiofilter.reexposure (M06).

Tests cover:
- Receipt registration and lifecycle
- Reference contract formatting and parsing
- Scoped session boundaries (CROSS_SESSION_REFERENCE=FORBIDDEN)
- Hash-collision defense (hash equality AND byte equality)
- Reference before first delivery prevention
- Critical inline evidence gates (AUTHORITY, SECURITY, FAILURE, DIAGNOSTIC, CANONICAL_STATE, UNKNOWN)
- Sensitivity boundaries (SENSITIVE, DO_NOT_PERSIST)
- Economic non-expansion gate (tiny repeats rejected)
- Same-source vs cross-source distinction
- Shadow ledger append-only hash chaining and tamper detection
"""

import hashlib
import json
import pytest

from fiofilter.reexposure import (
    DeliveryReceipt,
    ReceiptRegistry,
    ReexposureShadowEvaluator,
    ShadowDecision,
    ShadowDisposition,
    ShadowLedger,
    ShadowReference,
    _classify_episode_bucket,
    _classify_recency_bucket,
)


class TestShadowReferenceContract:
    def test_format_and_parse_roundtrip(self):
        sha = hashlib.sha256(b"hello world").hexdigest()
        ref = ShadowReference(sha256=sha, byte_length=11, receipt_id="RCP-test001-000001")
        text = ref.format_text()
        raw_b = ref.format_bytes()
        assert b"[[FIOFILTER:REF:v1" in raw_b
        assert f"sha256={sha}".encode() in raw_b
        assert b"bytes=11" in raw_b
        assert b"receipt=RCP-test001-000001" in raw_b

        parsed = ShadowReference.parse(text)
        assert parsed is not None
        assert parsed.sha256 == sha
        assert parsed.byte_length == 11
        assert parsed.receipt_id == "RCP-test001-000001"
        assert parsed.version == "v1"

    def test_invalid_reference_parse_returns_none(self):
        assert ShadowReference.parse("random text") is None
        assert ShadowReference.parse("[[FIOFILTER:REF:v1\nsha256=short\nbytes=1\nreceipt=r\n]]") is None


class TestReceiptRegistry:
    def test_session_scoping_and_cross_session_forbidden(self):
        reg = ReceiptRegistry("session-alpha")
        receipt = reg.register_first_delivery(
            source_kind="FILE_READ",
            source_identity="src/app.py",
            content_sha256="aaa",
            raw_bytes=b"content",
            call_id="call-1",
            call_index=1,
        )
        assert receipt.session_id == "session-alpha"
        assert receipt.receipt_id.startswith("RCP-session-")
        assert receipt.reference_count == 0

        # Attempt to evaluate in wrong session
        evaluator = ReexposureShadowEvaluator("session-alpha")
        with pytest.raises(ValueError, match="CROSS_SESSION_REFERENCE=FORBIDDEN"):
            evaluator.evaluate(
                call_id="c2",
                call_index=2,
                source_kind="FILE_READ",
                source_identity="src/app.py",
                raw_bytes=b"content",
                session_id="session-beta",
            )


class TestAdversarialGates:
    @pytest.fixture
    def evaluator(self):
        return ReexposureShadowEvaluator("session-test")

    def test_first_delivery_is_always_raw(self, evaluator):
        payload = b"large content repeated later " * 10
        dec = evaluator.evaluate(
            call_id="c1",
            call_index=1,
            source_kind="FILE_READ",
            source_identity="a.py",
            raw_bytes=payload,
        )
        assert dec.disposition == ShadowDisposition.FIRST_DELIVERY.value
        assert dec.hypothetical_bytes_avoided == 0
        assert dec.reference_target is None

    def test_reference_before_first_delivery_is_impossible(self, evaluator):
        # A completely new payload can never be given a reference
        new_payload = b"brand new unseen payload" * 5
        dec = evaluator.evaluate(
            call_id="c1",
            call_index=1,
            source_kind="FILE_READ",
            source_identity="a.py",
            raw_bytes=new_payload,
        )
        assert dec.disposition == ShadowDisposition.FIRST_DELIVERY.value

    def test_cross_source_identical_content_is_raw(self, evaluator):
        # File A and File B happen to share identical bytes
        payload = b"export const PI = 3.14159265358979323846;\n" * 10
        d1 = evaluator.evaluate("c1", 1, "FILE_READ", "math_a.js", payload)
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        d2 = evaluator.evaluate("c2", 2, "FILE_READ", "math_b.js", payload)
        assert d2.disposition == ShadowDisposition.CROSS_SOURCE_RAW.value
        assert d2.hypothetical_bytes_avoided == 0

    def test_same_file_changed_bytes(self, evaluator):
        # File modified between reads
        p1 = b"version = 1.0.0\n" * 10
        p2 = b"version = 1.0.1\n" * 10
        d1 = evaluator.evaluate("c1", 1, "FILE_READ", "version.py", p1)
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        d2 = evaluator.evaluate("c2", 2, "FILE_READ", "version.py", p2)
        assert d2.disposition == ShadowDisposition.FIRST_DELIVERY.value
        assert d2.content_sha256 != d1.content_sha256

    def test_hash_collision_defense_mismatched_bytes(self, evaluator):
        # Mock a receipt where sha256 matches but raw bytes differ
        payload = b"original content for test " * 10
        d1 = evaluator.evaluate("c1", 1, "FILE_READ", "target.py", payload)
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        # Artificially tamper with registry raw bytes
        receipt = evaluator.registry.get_by_hash(d1.content_sha256)
        receipt.raw_bytes = b"tampered corrupt content " * 10

        d2 = evaluator.evaluate("c2", 2, "FILE_READ", "target.py", payload)
        assert d2.disposition == ShadowDisposition.AMBIGUOUS_IDENTITY_RAW.value
        assert d2.reason == "HASH_EQUALITY_WITHOUT_BYTE_EQUALITY_DETECTED"

    def test_sensitive_content_remains_raw(self, evaluator):
        secret_payload = b"AWS_SECRET_ACCESS_KEY = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n" * 5
        d1 = evaluator.evaluate("c1", 1, "FILE_READ", "creds.env", secret_payload)
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        d2 = evaluator.evaluate("c2", 2, "FILE_READ", "creds.env", secret_payload)
        assert d2.disposition == ShadowDisposition.SENSITIVE_RAW.value
        assert d2.hypothetical_bytes_avoided == 0

    def test_failure_output_remains_raw(self, evaluator):
        fail_payload = b"Traceback (most recent call last):\n  File 'a.py', line 1\nZeroDivisionError: division by zero\n" * 3
        d1 = evaluator.evaluate("c1", 1, "SCRIPT", "python a.py", fail_payload, exit_code=1)
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        d2 = evaluator.evaluate("c2", 2, "SCRIPT", "python a.py", fail_payload, exit_code=1)
        assert d2.disposition == ShadowDisposition.UNSAFE_EVIDENCE_RAW.value

    def test_diagnostic_output_remains_raw(self, evaluator):
        diag_payload = b"DeprecationWarning: collections.Callable is deprecated\n" * 5
        d1 = evaluator.evaluate("c1", 1, "SCRIPT", "python test.py", diag_payload, exit_code=0)
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        d2 = evaluator.evaluate("c2", 2, "SCRIPT", "python test.py", diag_payload, exit_code=0)
        assert d2.disposition == ShadowDisposition.UNSAFE_EVIDENCE_RAW.value

    def test_authority_output_remains_raw(self, evaluator):
        auth_payload = b"IAM policy permissions granted by admin audit log\n" * 5
        d1 = evaluator.evaluate("c1", 1, "SCRIPT", "audit.sh", auth_payload, exit_code=0)
        d2 = evaluator.evaluate("c2", 2, "SCRIPT", "audit.sh", auth_payload, exit_code=0)
        assert d2.disposition == ShadowDisposition.UNSAFE_EVIDENCE_RAW.value

    def test_canonical_state_remains_raw(self, evaluator):
        git_payload = b"commit 1234567890abcdef1234567890abcdef12345678\nOn branch main\n" * 5
        d1 = evaluator.evaluate("c1", 1, "GIT", "git log -1", git_payload, exit_code=0)
        d2 = evaluator.evaluate("c2", 2, "GIT", "git log -1", git_payload, exit_code=0)
        assert d2.disposition == ShadowDisposition.UNSAFE_EVIDENCE_RAW.value

    def test_tiny_output_fails_economic_gate_no_expansion(self, evaluator):
        # 4-byte payload: "ok\n\n"
        # Reference string is >100 bytes!
        tiny_payload = b"1\n"
        d1 = evaluator.evaluate("c1", 1, "SCRIPT", "check.sh", tiny_payload, exit_code=0)
        d2 = evaluator.evaluate("c2", 2, "SCRIPT", "check.sh", tiny_payload, exit_code=0)
        # Even if unknown or noise, must not expand
        assert d2.disposition in (
            ShadowDisposition.SHADOW_REFERENCE_NOT_ECONOMIC.value,
            ShadowDisposition.UNKNOWN_RAW.value,
        )
        assert d2.hypothetical_bytes_avoided == 0

    def test_truncated_stream_fails_open_to_raw(self, evaluator):
        payload = b"Some partial stream that got cut off " * 10
        d1 = evaluator.evaluate("c1", 1, "FILE_READ", "big.log", payload, truncated=True)
        d2 = evaluator.evaluate("c2", 2, "FILE_READ", "big.log", payload, truncated=True)
        assert d2.disposition == ShadowDisposition.AMBIGUOUS_IDENTITY_RAW.value

    def test_safe_same_source_redelivery_succeeds(self, evaluator):
        # Standard clean file read with benign source code
        safe_payload = b"total = sum(x * 2 for x in range(100))\nresult = total / 2\n" * 10
        d1 = evaluator.evaluate("c1", 1, "FILE_READ", "src/calc.py", safe_payload, exit_code=0, target_path="src/calc.py")
        assert d1.disposition == ShadowDisposition.FIRST_DELIVERY.value

        d2 = evaluator.evaluate("c2", 2, "FILE_READ", "src/calc.py", safe_payload, exit_code=0, target_path="src/calc.py")
        assert d2.disposition == ShadowDisposition.EXACT_REDELIVERY_SHADOW_REFERENCE.value
        assert d2.hypothetical_bytes_avoided > 0
        assert d2.reference_target is not None
        assert d2.is_read_receipt_candidate is True


class TestDistanceBuckets:
    def test_recency_buckets(self):
        assert _classify_recency_bucket(1) == "0-2"
        assert _classify_recency_bucket(2) == "0-2"
        assert _classify_recency_bucket(4) == "3-5"
        assert _classify_recency_bucket(8) == "6-10"
        assert _classify_recency_bucket(20) == "11-25"
        assert _classify_recency_bucket(45) == "26-50"
        assert _classify_recency_bucket(75) == "51-100"
        assert _classify_recency_bucket(150) == ">100"

    def test_episode_buckets(self):
        assert _classify_episode_bucket(None) == "unknown"
        assert _classify_episode_bucket(0) == "0_same_episode"
        assert _classify_episode_bucket(1) == "1_episode"
        assert _classify_episode_bucket(3) == "2-5_episodes"
        assert _classify_episode_bucket(10) == ">5_episodes"


class TestShadowLedger:
    def test_ledger_hash_chaining_and_integrity(self, tmp_path):
        ledger = ShadowLedger(tmp_path / "shadow")
        decisions = [
            ShadowDecision(
                call_id="c1",
                call_index=1,
                session_id="s1",
                disposition="FIRST_DELIVERY",
                original_bytes=500,
                hypothetical_visible_bytes=500,
                hypothetical_bytes_avoided=0,
                reference_target=None,
                reference_bytes=0,
                reason="FIRST_DELIVERY",
                confidence="PROVEN",
                source_kind="FILE_READ",
                source_identity="src/a.py",
                same_source=False,
                evidence_class="CONTENT_EVIDENCE",
            ),
            ShadowDecision(
                call_id="c2",
                call_index=2,
                session_id="s1",
                disposition="EXACT_REDELIVERY_SHADOW_REFERENCE",
                original_bytes=500,
                hypothetical_visible_bytes=100,
                hypothetical_bytes_avoided=400,
                reference_target="RCP-s1-000001",
                reference_bytes=100,
                reason="SAME_SOURCE",
                confidence="PROVEN",
                source_kind="FILE_READ",
                source_identity="src/a.py",
                same_source=True,
                evidence_class="CONTENT_EVIDENCE",
                call_distance_from_first=1,
            ),
        ]
        ledger.write_events(decisions)
        ledger.write_manifest_and_summary({"test": True}, {"savings": 400})

        # Verify chaining in events file
        lines = (tmp_path / "shadow" / "m06_reexposure_shadow_events_v1.jsonl").read_text().splitlines()
        assert len(lines) == 2
        r1 = json.loads(lines[0])
        r2 = json.loads(lines[1])
        assert r1["previous_event_hash"] == "0" * 64
        assert r2["previous_event_hash"] == r1["event_hash"]

        # Verify no-clobber
        with pytest.raises(FileExistsError):
            ledger.write_events(decisions)
