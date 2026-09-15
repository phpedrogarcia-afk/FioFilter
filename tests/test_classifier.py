"""
tests/test_classifier.py — Evidence classifier tests.

Tests: UNKNOWN→RAW routing, evidence class assignment, confidence threshold.
"""

import pytest

from fiofilter.classifier import MIN_CONFIDENCE, classify
from fiofilter.types import EvidenceClass


class TestUnknownDefault:
    def test_empty_is_unknown(self):
        result = classify(b"")
        assert result.evidence_class == EvidenceClass.UNKNOWN

    def test_random_text_is_unknown(self):
        result = classify(b"xyzzy frobnicator quux\nplugh\n")
        assert result.evidence_class == EvidenceClass.UNKNOWN

    def test_unknown_has_high_confidence(self):
        result = classify(b"")
        assert result.evidence_class == EvidenceClass.UNKNOWN
        assert result.confidence >= MIN_CONFIDENCE


class TestSecurityClassification:
    def test_rsa_private_key(self):
        content = b"-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.SECURITY

    def test_bearer_token(self):
        content = b"Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.abc123\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.SECURITY

    def test_github_token(self):
        content = b"GHP_abcdefghijklmnopqrstuvwxyz123456789\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.SECURITY


class TestFailureClassification:
    def test_nonzero_exit_is_failure(self):
        result = classify(b"some output", exit_code=1)
        assert result.evidence_class == EvidenceClass.FAILURE
        assert result.confidence >= 0.9

    def test_traceback_is_failure(self):
        content = (
            b"Traceback (most recent call last):\n"
            b"  File 'test.py', line 5\n"
            b"AssertionError\n"
        )
        result = classify(content)
        assert result.evidence_class == EvidenceClass.FAILURE

    def test_assertion_error_is_failure(self):
        content = b"AssertionError: expected 1 got 2\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.FAILURE


class TestCanonicalStateClassification:
    def test_git_commit_is_canonical(self):
        content = (
            b"commit abc1234def5678901234567890abcdef12345678\n"
            b"Author: Dev <dev@example.com>\n"
        )
        result = classify(content)
        assert result.evidence_class == EvidenceClass.CANONICAL_STATE

    def test_git_branch_is_canonical(self):
        content = b"On branch main\nnothing to commit, working tree clean\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.CANONICAL_STATE

    def test_canonical_facts_extracted(self):
        content = (
            b"commit abc1234def5678\n"
            b"On branch main\n"
        )
        result = classify(content)
        assert result.evidence_class == EvidenceClass.CANONICAL_STATE
        # Inline-required facts should include the commit and branch
        assert any("commit" in f for f in result.inline_required_facts)


class TestMachineDataClassification:
    def test_json_object_is_machine_data(self):
        content = b'{"key": "value", "number": 42}\n'
        result = classify(content)
        assert result.evidence_class == EvidenceClass.MACHINE_DATA

    def test_json_array_is_machine_data(self):
        content = b'[1, 2, 3, {"nested": true}]\n'
        result = classify(content)
        assert result.evidence_class == EvidenceClass.MACHINE_DATA

    def test_invalid_json_not_machine_data(self):
        content = b'{invalid json: here}\n'
        result = classify(content)
        assert result.evidence_class != EvidenceClass.MACHINE_DATA


class TestNoiseClassification:
    def test_high_duplicate_lines_is_noise(self):
        lines = ["Building... [   OK   ]\n"] * 20
        content = "".join(lines).encode("utf-8")
        result = classify(content)
        assert result.evidence_class == EvidenceClass.NOISE

    def test_low_duplicate_lines_not_noise(self):
        content = b"line1\nline2\nline3\nline4\nline5\n"
        result = classify(content)
        assert result.evidence_class != EvidenceClass.NOISE


class TestSuccessSummaryClassification:
    def test_all_passed_is_success(self):
        content = b"5 tests, 0 failures\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.SUCCESS_SUMMARY

    def test_passed_count_is_success(self):
        content = b"10 passed in 0.5s\n"
        result = classify(content)
        assert result.evidence_class == EvidenceClass.SUCCESS_SUMMARY


class TestDiscoveryClassification:
    def test_directory_listing_is_discovery(self):
        content = (
            b"total 48\n"
            b"drwxr-xr-x  5 user staff  160 Sep 15 12:00 .\n"
            b"drwxr-xr-x 20 user staff  640 Sep 15 11:00 ..\n"
        )
        result = classify(content)
        assert result.evidence_class == EvidenceClass.DISCOVERY

    def test_tree_output_is_discovery(self):
        content = ".\n\u251c\u2500\u2500 src\n\u2502   \u2514\u2500\u2500 main.py\n\u2514\u2500\u2500 tests\n".encode("utf-8")
        result = classify(content)
        assert result.evidence_class == EvidenceClass.DISCOVERY
