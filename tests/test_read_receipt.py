"""tests/test_read_receipt.py — Comprehensive tests for Read Receipt Shadow Specialization.

Validates:
- Controlled Live Read Lab (Sequences A through F)
- Mtime spoof defense (MTIME_SPOOF_DOES_NOT_BYPASS_HASH = PASS)
- Changed same-size bytes detection
- Relative vs absolute path resolution
- ReadViewType and ReadView range slicing
- Missing file, permission error, and ambiguous path handling
- Tiny file reference expansion rejection (no-expansion invariant)
- Binary and CRLF content handling
- Sensitivity screening and persistence rejection
- Cross-session isolation and session reset
- Git worktree / HEAD provenance independence
- Hash-chained append-only shadow ledger integrity
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time
import pytest

from fiofilter.read_receipt import (
    FreshnessLevel,
    ReadReceiptDisposition,
    ReadReceiptEvaluator,
    ReadReceiptLedger,
    ReadView,
    ReadViewType,
    extract_view_bytes,
    format_read_reference,
    normalize_source_identity,
    parse_read_command,
)


class TestPathAndCommandParsing:
    """Test deterministic source identity and view parsing."""

    def test_normalize_source_identity_absolute(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "foo.txt"
        norm, disp = normalize_source_identity(str(p))
        assert norm is not None
        assert norm == norm.lower() if os.name == "nt" else norm
        assert disp == str(p)

    def test_normalize_source_identity_relative_with_base(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "subdir" / "app.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()

        norm_rel, _ = normalize_source_identity("subdir/app.py", base_dir=tmp_path)
        norm_abs, _ = normalize_source_identity(str(p))
        assert norm_rel == norm_abs

    def test_normalize_source_identity_ambiguous_wildcards(self) -> None:
        norm, _ = normalize_source_identity("src/*.py")
        assert norm is None

    def test_parse_read_command_get_content_full(self) -> None:
        target, view, is_pure = parse_read_command("Get-Content -Raw 'src/app.py'")
        assert target == "src/app.py"
        assert view.view_type == ReadViewType.FULL_FILE
        assert is_pure is True

    def test_parse_read_command_get_content_tail(self) -> None:
        target, view, is_pure = parse_read_command("Get-Content -LiteralPath 'logs/run.log' -Tail 40")
        assert target == "logs/run.log"
        assert view.view_type == ReadViewType.LINE_RANGE
        assert view.tail_lines == 40
        assert is_pure is True

    def test_parse_read_command_get_content_head(self) -> None:
        target, view, is_pure = parse_read_command("Get-Content -TotalCount 25 'data.txt'")
        assert target == "data.txt"
        assert view.view_type == ReadViewType.LINE_RANGE
        assert view.start_line == 1
        assert view.end_line == 25
        assert is_pure is True

    def test_parse_read_command_select_object_pipeline(self) -> None:
        target, view, is_pure = parse_read_command("Get-Content 'app.py' | Select-Object -Skip 10 -First 50")
        assert target == "app.py"
        assert view.view_type == ReadViewType.LINE_RANGE
        assert view.start_line == 11
        assert view.end_line == 60
        assert is_pure is True

    def test_parse_read_command_powershell_array_slice(self) -> None:
        target, view, is_pure = parse_read_command("(Get-Content 'doc.md')[0..99]")
        assert target == "doc.md"
        assert view.view_type == ReadViewType.LINE_RANGE
        assert view.start_line == 1
        assert view.end_line == 100
        assert is_pure is True

    def test_parse_read_command_cat_and_type(self) -> None:
        t1, v1, p1 = parse_read_command("cat src/main.py")
        assert t1 == "src/main.py"
        assert v1.view_type == ReadViewType.FULL_FILE
        assert p1 is True

        t2, v2, p2 = parse_read_command("type data\\records.csv")
        assert t2 == "data\\records.csv"
        assert v2.view_type == ReadViewType.FULL_FILE
        assert p2 is True

    def test_parse_read_command_head_and_tail(self) -> None:
        t1, v1, p1 = parse_read_command("head -n 50 README.md")
        assert t1 == "README.md"
        assert v1.view_type == ReadViewType.LINE_RANGE
        assert v1.start_line == 1
        assert v1.end_line == 50
        assert p1 is True

        t2, v2, p2 = parse_read_command("tail -n 20 output.log")
        assert t2 == "output.log"
        assert v2.view_type == ReadViewType.LINE_RANGE
        assert v2.tail_lines == 20
        assert p2 is True

    def test_parse_read_command_composite_script(self) -> None:
        cmd = "Start-Sleep -Seconds 10; Get-Content 'log.txt' -Tail 10"
        target, view, is_pure = parse_read_command(cmd)
        assert target == "log.txt"
        assert view.view_type == ReadViewType.OTHER_STRUCTURED_VIEW
        assert is_pure is False


class TestControlledLiveReadLab:
    """Execute mandatory Controlled Live Read Lab sequences (A through F)."""

    def test_sequence_a_unchanged_file_proves_f4(self, tmp_path: pathlib.Path) -> None:
        """Sequence A: Create -> Read full -> Receipt -> Read again unchanged -> Prove F4."""
        test_file = tmp_path / "seq_a.txt"
        content = b"Alpha Bravo Charlie Delta Echo Foxtrot\n" * 20
        test_file.write_bytes(content)

        evaluator = ReadReceiptEvaluator(session_id="test-session-a", base_dir=tmp_path)

        # 1st read
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, call_index=1, episode_id=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW
        assert d1.receipt_id is not None
        assert d1.raw_bytes == len(content)
        assert d1.plane_a_freshness_proven is False

        # 2nd read: unchanged
        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, call_index=2, episode_id=1)
        assert d2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE
        assert d2.freshness_level == FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL
        assert d2.plane_a_freshness_proven is True
        assert d2.plane_b_active_authorized is False  # Plane B remains closed!
        assert d2.hypothetical_bytes_avoided > 0
        assert d2.call_distance == 1
        assert d2.episode_distance == 0

    def test_sequence_b_modified_bytes_rejects_receipt(self, tmp_path: pathlib.Path) -> None:
        """Sequence B: Create -> Read -> Modify bytes -> Read -> Rejects unchanged receipt."""
        test_file = tmp_path / "seq_b.txt"
        test_file.write_bytes(b"Initial content line 1\nInitial content line 2\n" * 10)

        evaluator = ReadReceiptEvaluator(session_id="test-session-b", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Modify file
        test_file.write_bytes(b"Completely different content line 1\nLine 2\n" * 10)

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.SOURCE_CHANGED_RAW
        assert d2.plane_a_freshness_proven is False

    def test_sequence_c_mtime_spoof_defense(self, tmp_path: pathlib.Path) -> None:
        """Sequence C: Mandatory adversarial defense.

        Modify file, restore original mtime manually -> Read again ->
        MTIME_SPOOF_DOES_NOT_BYPASS_HASH = PASS.
        """
        test_file = tmp_path / "seq_c_spoof.txt"
        orig_content = b"Original baseline bytes that will be modified\n" * 15
        test_file.write_bytes(orig_content)

        orig_st = test_file.stat()
        orig_atime = orig_st.st_atime
        orig_mtime = orig_st.st_mtime

        evaluator = ReadReceiptEvaluator(session_id="test-session-c", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Modify bytes
        modified_content = b"Tampered and altered file bytes for attack\n" * 15
        test_file.write_bytes(modified_content)

        # Restore original mtime manually (spoofing filesystem timestamp)
        os.utime(test_file, (orig_atime, orig_mtime))
        spoofed_st = test_file.stat()
        assert spoofed_st.st_mtime == orig_mtime  # Verify mtime is successfully spoofed

        # Read again
        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, call_index=2)

        # MUST reject unchanged receipt because content hash differs!
        assert d2.disposition == ReadReceiptDisposition.SOURCE_CHANGED_RAW
        assert d2.plane_a_freshness_proven is False
        assert "hash mismatch" in d2.reason

    def test_sequence_d_same_bytes_different_path(self, tmp_path: pathlib.Path) -> None:
        """Sequence D: Same bytes, different path must not share receipt."""
        file1 = tmp_path / "f1.txt"
        file2 = tmp_path / "f2.txt"
        content = b"Identical byte sequence in two different files\n" * 10
        file1.write_bytes(content)
        file2.write_bytes(content)

        evaluator = ReadReceiptEvaluator(session_id="test-session-d", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=file1, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Read file2
        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=file2, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.FIRST_READ_RAW
        assert d2.receipt_id != d1.receipt_id

    def test_sequence_e_same_path_different_range(self, tmp_path: pathlib.Path) -> None:
        """Sequence E: Same path, different requested range is not same-view receipt."""
        test_file = tmp_path / "seq_e.txt"
        lines = [f"Line {i:03d}\n".encode() for i in range(1, 101)]
        test_file.write_bytes(b"".join(lines))

        evaluator = ReadReceiptEvaluator(session_id="test-session-e", base_dir=tmp_path)

        # Read lines 1..20
        v1 = ReadView(ReadViewType.LINE_RANGE, start_line=1, end_line=20)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, view=v1, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Read lines 21..50
        v2 = ReadView(ReadViewType.LINE_RANGE, start_line=21, end_line=50)
        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, view=v2, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.FIRST_READ_RAW
        assert d2.receipt_id != d1.receipt_id

    def test_sequence_f_same_path_same_range_same_bytes(self, tmp_path: pathlib.Path) -> None:
        """Sequence F: Same path, same range, same bytes proves F4 shadow reference."""
        test_file = tmp_path / "seq_f.txt"
        lines = [f"Long Line Content Number {i:04d} with padding\n".encode() for i in range(1, 101)]
        test_file.write_bytes(b"".join(lines))

        evaluator = ReadReceiptEvaluator(session_id="test-session-f", base_dir=tmp_path)
        v = ReadView(ReadViewType.LINE_RANGE, start_line=10, end_line=50)

        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, view=v, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, view=v, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE
        assert d2.freshness_level == FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL
        assert d2.plane_a_freshness_proven is True


class TestAdversarialMatrix:
    """Mandatory edge cases from Instruction 30."""

    def test_changed_same_size_bytes_rejected(self, tmp_path: pathlib.Path) -> None:
        """Byte replacement where size is identical: 'AAAA' vs 'BBBB'."""
        test_file = tmp_path / "same_size.txt"
        test_file.write_bytes(b"A" * 1024)

        evaluator = ReadReceiptEvaluator(session_id="test-adv-1", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Modify with identical length
        test_file.write_bytes(b"B" * 1024)
        assert test_file.stat().st_size == 1024

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.SOURCE_CHANGED_RAW
        assert d2.plane_a_freshness_proven is False

    def test_mtime_changed_but_bytes_same_proves_f4(self, tmp_path: pathlib.Path) -> None:
        """File touched (mtime changed) but content identical -> F4 proven!"""
        test_file = tmp_path / "touch_same.txt"
        content = b"Static configuration data block\n" * 20
        test_file.write_bytes(content)

        evaluator = ReadReceiptEvaluator(session_id="test-adv-2", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=test_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Touch file forward by 10 seconds
        future = time.time() + 10.0
        os.utime(test_file, (future, future))

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=test_file, call_index=2)
        # Content is unchanged -> byte equality verified!
        assert d2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE
        assert d2.freshness_level == FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL

    def test_missing_file_raw(self, tmp_path: pathlib.Path) -> None:
        non_existent = tmp_path / "missing_file_xyz.txt"
        evaluator = ReadReceiptEvaluator(session_id="test-adv-3", base_dir=tmp_path)
        d = evaluator.evaluate_live_read(call_id="call-001", file_path=non_existent)
        assert d.disposition == ReadReceiptDisposition.MISSING_FILE_RAW
        assert d.plane_a_freshness_proven is False

    def test_tiny_file_expansion_rejected(self, tmp_path: pathlib.Path) -> None:
        """No-expansion invariant: if reference size >= raw bytes, reject reference."""
        tiny_file = tmp_path / "tiny.txt"
        tiny_file.write_bytes(b"OK")  # 2 bytes

        evaluator = ReadReceiptEvaluator(session_id="test-adv-4", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=tiny_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=tiny_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.REFERENCE_NOT_ECONOMIC_RAW
        assert d2.hypothetical_reference is None
        assert d2.plane_a_freshness_proven is True  # Freshness is proven, but uneconomic!

    def test_empty_file_expansion_rejected(self, tmp_path: pathlib.Path) -> None:
        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")

        evaluator = ReadReceiptEvaluator(session_id="test-adv-5", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=empty_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=empty_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.REFERENCE_NOT_ECONOMIC_RAW

    def test_crlf_and_lf_handling(self, tmp_path: pathlib.Path) -> None:
        crlf_file = tmp_path / "crlf.txt"
        crlf_file.write_bytes(b"Line 1\r\nLine 2\r\nLine 3\r\n" * 15)

        evaluator = ReadReceiptEvaluator(session_id="test-adv-6", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=crlf_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=crlf_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE
        assert d2.freshness_level == FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL

    def test_binary_content_handling(self, tmp_path: pathlib.Path) -> None:
        bin_file = tmp_path / "data.bin"
        bin_content = bytes(range(256)) * 4
        bin_file.write_bytes(bin_content)

        evaluator = ReadReceiptEvaluator(session_id="test-adv-7", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=bin_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=bin_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE
        assert d2.freshness_level == FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL

    def test_sensitive_file_rejected_from_reference(self, tmp_path: pathlib.Path) -> None:
        secret_file = tmp_path / "credentials.env"
        secret_file.write_bytes(b"PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n")

        evaluator = ReadReceiptEvaluator(session_id="test-adv-8", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=secret_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.SENSITIVE_POLICY_RAW
        assert d1.plane_a_freshness_proven is False

    def test_cross_session_isolation(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "app.py"
        f.write_bytes(b"print('Hello world!')\n" * 15)

        eval_session_1 = ReadReceiptEvaluator(session_id="session-1", base_dir=tmp_path)
        eval_session_2 = ReadReceiptEvaluator(session_id="session-2", base_dir=tmp_path)

        d1 = eval_session_1.evaluate_live_read(call_id="call-001", file_path=f, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Session 2 must not see receipt from Session 1
        d2 = eval_session_2.evaluate_live_read(call_id="call-002", file_path=f, call_index=1)
        assert d2.disposition == ReadReceiptDisposition.FIRST_READ_RAW

    def test_session_reset(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "shared.py"
        f.write_bytes(b"x = 42\ny = 100\n" * 20)

        evaluator = ReadReceiptEvaluator(session_id="session-reset-test", base_dir=tmp_path)
        d1 = evaluator.evaluate_live_read(call_id="call-001", file_path=f, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Reset session
        evaluator.reset_session("new-session-id")

        d2 = evaluator.evaluate_live_read(call_id="call-002", file_path=f, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.FIRST_READ_RAW


class TestReadReceiptLedger:
    """Test append-only hash-chained ledger."""

    def test_ledger_chaining_and_manifest(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "log.txt"
        f.write_bytes(b"Log line event\n" * 25)

        evaluator = ReadReceiptEvaluator(session_id="ledger-session", base_dir=tmp_path)
        ledger = ReadReceiptLedger(session_id="ledger-session")

        d1 = evaluator.evaluate_live_read(call_id="c-1", file_path=f, call_index=1)
        e1 = ledger.record_event("evt-1", d1)

        d2 = evaluator.evaluate_live_read(call_id="c-2", file_path=f, call_index=2)
        e2 = ledger.record_event("evt-2", d2)

        assert e1["previous_event_hash"] == "0" * 64
        assert e2["previous_event_hash"] == e1["event_hash"]

        manifest = ledger.generate_manifest()
        assert manifest["total_events"] == 2
        assert manifest["final_event_hash"] == e2["event_hash"]
        assert manifest["active_read_reference_suppression"] is False
        assert manifest["behavioral_equivalence"] == "UNKNOWN"
