"""tests/test_runtime_shadow.py — Tests for M08 Runtime Read Receipt Shadow Harness.

Validates:
- Partial write safety: partial JSON never processed or dropped
- Incremental JSONL tailing and multi-record chunking
- Restart/resume equivalence and at-most-once event deduplication
- Source rewind and replacement fail-closed defense (SourceRewindException)
- Session isolation (no cross-session receipt sharing)
- Ledger hash-chain continuity and corruption detection
- DirectReadLab RAW transparency (exact byte equality with direct baseline read)
- Telemetry failure isolation: shadow errors never block RAW delivery
- Mtime spoof defense in direct lab
- Salience risk bucket classification
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import time
import pytest

from fiofilter.read_receipt import (
    FreshnessLevel,
    ReadReceiptDisposition,
    ReadView,
    ReadViewType,
)
from fiofilter.runtime_shadow import (
    CHECKPOINT_SCHEMA_VERSION,
    DirectReadLab,
    EpistemicFreshnessProof,
    HarnessMode,
    LedgerChainCorruptionException,
    PassiveJsonlTailSource,
    RuntimeReceiptState,
    RuntimeShadowHarness,
    SalienceRiskBucket,
    ShadowCursor,
    SourceRewindException,
    classify_salience_risk,
)


class TestPartialWriteSafety:
    """Mandatory Partial Write Safety Laboratory (Instruction 10)."""

    def test_partial_json_safety_no_double_no_loss(self, tmp_path: pathlib.Path) -> None:
        """Write half a JSON record -> observer runs (no event emitted).

        Append remainder + newline -> observer runs (exactly ONE event emitted).
        PARTIAL_JSON_DOUBLE_PROCESSING=0, PARTIAL_JSON_LOSS=0.
        """
        jsonl_file = tmp_path / "streaming_session.jsonl"
        observer = PassiveJsonlTailSource(file_path=jsonl_file, start_offset=0)

        # 1. Write half of a valid record (incomplete JSON line)
        half_record = b'{"payload": {"type": "custom_tool_call", "name": "exec", "input": {"cmd": "Get-Content'
        jsonl_file.write_bytes(half_record)

        # Observer polls
        records_step1 = observer.poll_records()
        assert len(records_step1) == 0, "Partial record must not emit any event"
        assert observer.buffer == half_record, "Partial line must be retained in buffer"

        # 2. Append the remainder + newline
        remainder = b' \'app.py\'"}}, "output": "print(1)\\n"}\n'
        with open(jsonl_file, "ab") as f:
            f.write(remainder)

        # Observer polls again
        records_step2 = observer.poll_records()
        assert len(records_step2) == 1, "Exactly ONE event must be emitted after line completion"

        rec_start, rec, rec_end = records_step2[0]
        assert rec["payload"]["name"] == "exec"
        assert rec["output"] == "print(1)\n"
        assert observer.buffer == b"", "Buffer must be empty after complete record consumption"

        # 3. Subsequent poll with no new data emits 0
        records_step3 = observer.poll_records()
        assert len(records_step3) == 0

        # Invariants:
        # PARTIAL_JSON_DOUBLE_PROCESSING = 0
        # PARTIAL_JSON_LOSS = 0


class TestIncrementalTailingAndChunks:
    """Test multi-record streaming, full lines, and clean EOF."""

    def test_multi_record_chunks(self, tmp_path: pathlib.Path) -> None:
        jsonl_file = tmp_path / "chunks.jsonl"
        observer = PassiveJsonlTailSource(file_path=jsonl_file)

        # Write 3 complete records at once
        lines = [
            b'{"call_id": "c1", "payload": {"type": "custom_tool_call", "name": "exec"}}\n',
            b'{"call_id": "c2", "payload": {"type": "custom_tool_call", "name": "exec"}}\n',
            b'{"call_id": "c3", "payload": {"type": "custom_tool_call", "name": "exec"}}\n',
        ]
        jsonl_file.write_bytes(b"".join(lines))

        # Read with max_records=2
        batch1 = observer.poll_records(max_records=2)
        assert len(batch1) == 2
        assert batch1[0][1]["call_id"] == "c1"
        assert batch1[1][1]["call_id"] == "c2"

        # Read remainder
        batch2 = observer.poll_records()
        assert len(batch2) == 1
        assert batch2[0][1]["call_id"] == "c3"

    def test_paired_tool_call_stream_evaluation(self, tmp_path: pathlib.Path) -> None:
        source_file = tmp_path / "stream_session.jsonl"
        out_dir = tmp_path / "shadow_out"

        records = [
            {"payload": {"type": "message", "role": "user", "id": "u1"}},
            {"payload": {"type": "custom_tool_call", "name": "exec", "call_id": "c1", "input": {"cmd": "Get-Content -Raw 'alpha.py'"}}},
            {"payload": {"type": "custom_tool_call_output", "call_id": "c1", "output": "print('hello world of python code')\n" * 50}},
            {"payload": {"type": "message", "role": "user", "id": "u2"}},
            {"payload": {"type": "custom_tool_call", "name": "exec", "call_id": "c2", "input": {"cmd": "Get-Content -Raw 'alpha.py'"}}},
            {"payload": {"type": "custom_tool_call_output", "call_id": "c2", "output": "print('hello world of python code')\n" * 50}},
        ]
        with open(source_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        harness = RuntimeShadowHarness("paired-sess", source_file, out_dir)
        processed = harness.process_stream_increment()
        assert processed == 2

        # Verify decisions in events file
        with open(harness.events_file, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        assert len(events) == 2
        assert events[0]["call_id"] == "c1"
        assert events[0]["disposition"] == "FIRST_READ_RAW"
        assert events[1]["call_id"] == "c2"
        assert events[1]["disposition"] == "HISTORICAL_IDENTICAL_READ_CANDIDATE"
        assert events[1]["episode_distance"] == 1


class TestRestartResumeAndSourceRewind:
    """Test crash consistency, checkpointing, and source rewind defense."""

    def test_restart_resume_equivalence(self, tmp_path: pathlib.Path) -> None:
        """Process N events, stop, restart from checkpoint, continue N+1.

        Must produce identical state to uninterrupted run.
        """
        source_file = tmp_path / "source.jsonl"
        records = [
            {"payload": {"type": "custom_tool_call", "name": "exec", "call_id": f"call_{i}", "input": {"cmd": f"Get-Content -Raw 'f{i % 2}.txt'"}}, "output": f"Content of f{i % 2}\n" * 10}
            for i in range(1, 11)
        ]
        with open(source_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        out_dir_a = tmp_path / "run_uninterrupted"
        out_dir_b = tmp_path / "run_interrupted"

        # Uninterrupted run
        harness_a = RuntimeShadowHarness(
            session_id="session-test",
            source_path=source_file,
            output_dir=out_dir_a,
        )
        harness_a.process_stream_increment()
        summary_a = harness_a.finalize_artifacts()

        # Interrupted run: process 5, close, restart, process remaining
        harness_b1 = RuntimeShadowHarness(
            session_id="session-test",
            source_path=source_file,
            output_dir=out_dir_b,
        )
        harness_b1.process_stream_increment(max_records=5)
        assert harness_b1.cursor.processed_event_count == 5

        # Restart in fresh harness instance
        harness_b2 = RuntimeShadowHarness(
            session_id="session-test",
            source_path=source_file,
            output_dir=out_dir_b,
        )
        assert harness_b2.cursor.processed_event_count == 5
        harness_b2.process_stream_increment()
        summary_b = harness_b2.finalize_artifacts()

        # State equivalence
        assert summary_a["total_processed_events"] == summary_b["total_processed_events"] == 10
        assert summary_a["final_event_hash"] == summary_b["final_event_hash"]
        assert summary_a["last_committed_offset"] == summary_b["last_committed_offset"]

    def test_source_rewind_fail_closed(self, tmp_path: pathlib.Path) -> None:
        """If source file shrinks below committed offset, raise SourceRewindException."""
        source_file = tmp_path / "shrinking.jsonl"
        source_file.write_bytes(b'{"record": 1}\n{"record": 2}\n{"record": 3}\n' * 5)

        observer = PassiveJsonlTailSource(file_path=source_file)
        recs = observer.poll_records(max_records=2)
        assert len(recs) == 2
        committed_offset = observer.current_offset

        # File is truncated/shrunk externally
        source_file.write_bytes(b'{"record": 1}\n')
        assert source_file.stat().st_size < committed_offset

        with pytest.raises(SourceRewindException) as exc_info:
            observer.poll_records()
        assert "SOURCE_REWOUND_OR_REPLACED" in str(exc_info.value)

    def test_at_most_once_duplicate_event_deduplication(self, tmp_path: pathlib.Path) -> None:
        """Encountering same event twice must not create two ledger decisions."""
        state = RuntimeReceiptState(session_id="dedup-session")

        d1 = state.process_historical_or_stream_event(
            call_id="call-dup-1",
            command_str="Get-Content -Raw 'app.py'",
            delivered_bytes=100,
            delivered_sha256="abc123sha",
        )
        assert d1 is not None
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Re-processing same call_id
        d2 = state.process_historical_or_stream_event(
            call_id="call-dup-1",
            command_str="Get-Content -Raw 'app.py'",
            delivered_bytes=100,
            delivered_sha256="abc123sha",
        )
        assert d2 is None, "Duplicate call_id must be ignored under at-most-once guarantee"


class TestSessionIsolationAndLedgerChain:
    """Test cross-session boundary isolation and ledger chain integrity."""

    def test_session_isolation_resets_receipts(self, tmp_path: pathlib.Path) -> None:
        state = RuntimeReceiptState(session_id="session-alpha")
        d1 = state.process_historical_or_stream_event(
            call_id="c1",
            command_str="Get-Content 'app.py'",
            delivered_bytes=200,
            delivered_sha256="sha-xyz",
        )
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Reset to new session
        state.reset("session-beta")
        d2 = state.process_historical_or_stream_event(
            call_id="c2",
            command_str="Get-Content 'app.py'",
            delivered_bytes=200,
            delivered_sha256="sha-xyz",
        )
        # In session-beta, this must be FIRST_READ_RAW again!
        assert d2.disposition == ReadReceiptDisposition.FIRST_READ_RAW

    def test_ledger_corruption_detection(self, tmp_path: pathlib.Path) -> None:
        source_file = tmp_path / "test.jsonl"
        source_file.write_bytes(b'{"payload": {"type": "custom_tool_call", "name": "exec", "call_id": "c1", "input": {"cmd": "Get-Content \'a.txt\'"}}, "output": "hello"}\n')

        out_dir = tmp_path / "corrupt_ledger"
        harness = RuntimeShadowHarness("sess-1", source_file, out_dir)
        harness.process_stream_increment()

        # Tamper with the committed events file
        events_file = out_dir / "m08_runtime_shadow_events_v1.jsonl"
        with open(events_file, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        entry["previous_event_hash"] = "tampered_bad_hash"
        with open(events_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        # Restart harness: must raise LedgerChainCorruptionException
        with pytest.raises(LedgerChainCorruptionException):
            RuntimeShadowHarness("sess-1", source_file, out_dir)


class TestDirectReadLabMode:
    """Test Mode B: DIRECT_READ_LAB properties."""

    def test_direct_raw_transparency_byte_for_byte(self, tmp_path: pathlib.Path) -> None:
        """DIRECT_READ_LAB must return exact byte-for-byte baseline output."""
        lab = DirectReadLab(session_id="lab-direct-session", base_dir=tmp_path)

        # Test UTF-8, CRLF, LF, binary, empty, range
        test_cases = [
            ("utf8.txt", "UTF-8 Content with special characters: é, à, ç, ñ\n".encode("utf-8")),
            ("crlf.txt", b"Line 1\r\nLine 2\r\nLine 3\r\n"),
            ("lf.txt", b"Line 1\nLine 2\nLine 3\n"),
            ("binary.bin", bytes(range(256))),
            ("empty.txt", b""),
        ]

        for filename, data in test_cases:
            fpath = tmp_path / filename
            fpath.write_bytes(data)

            # Baseline direct read
            with open(fpath, "rb") as f:
                baseline_bytes = f.read()

            # Harness read
            raw_out, decision = lab.read_file(call_id=f"c_{filename}", file_path=fpath)
            assert raw_out == baseline_bytes, f"RAW mismatch for {filename}"
            assert raw_out == data

    def test_direct_lab_range_slicing_transparency(self, tmp_path: pathlib.Path) -> None:
        lines = [f"Line {i:03d}\n".encode("utf-8") for i in range(1, 101)]
        fpath = tmp_path / "range_test.txt"
        fpath.write_bytes(b"".join(lines))

        lab = DirectReadLab(session_id="lab-range-session", base_dir=tmp_path)
        view = ReadView(ReadViewType.LINE_RANGE, start_line=10, end_line=25)

        raw_out, decision = lab.read_file(call_id="c_range", file_path=fpath, view=view)
        expected = b"".join(lines[9:25])
        assert raw_out == expected

    def test_shadow_failure_raw_delivery_preserved(self, tmp_path: pathlib.Path) -> None:
        """Mandatory resilience test: Observer/telemetry exception MUST NOT block raw delivery.

        SHADOW_FAILURE_RAW_DELIVERY_PRESERVED = PASS.
        """
        fpath = tmp_path / "critical.txt"
        fpath.write_bytes(b"Critical business logic source code\n")

        # Lab configured with simulated telemetry failure
        faulty_lab = DirectReadLab(
            session_id="fault-session",
            base_dir=tmp_path,
            simulate_telemetry_failure=True,
        )

        raw_out, decision = faulty_lab.read_file(call_id="c_fail", file_path=fpath)
        # RAW bytes must still be delivered perfectly!
        assert raw_out == b"Critical business logic source code\n"
        # Decision failed gracefully to None
        assert decision is None

    def test_mtime_spoof_defense_in_direct_lab(self, tmp_path: pathlib.Path) -> None:
        """Mtime spoof defense in DirectReadLab."""
        test_file = tmp_path / "spoof_direct.txt"
        orig_content = b"Original baseline data for direct lab\n" * 15
        test_file.write_bytes(orig_content)

        st = test_file.stat()
        orig_atime = st.st_atime
        orig_mtime = st.st_mtime

        lab = DirectReadLab(session_id="spoof-lab", base_dir=tmp_path)
        raw1, d1 = lab.read_file(call_id="c1", file_path=test_file, call_index=1)
        assert d1.disposition == ReadReceiptDisposition.FIRST_READ_RAW

        # Tamper content and restore mtime
        test_file.write_bytes(b"Tampered attacker payload in direct lab\n" * 15)
        os.utime(test_file, (orig_atime, orig_mtime))

        raw2, d2 = lab.read_file(call_id="c2", file_path=test_file, call_index=2)
        assert d2.disposition == ReadReceiptDisposition.SOURCE_CHANGED_RAW
        assert d2.plane_a_freshness_proven is False
        assert "hash mismatch" in d2.reason


class TestSalienceRiskClassification:
    """Test observational distance risk reporting buckets."""

    def test_salience_buckets(self) -> None:
        assert classify_salience_risk(0) == SalienceRiskBucket.NEAR
        assert classify_salience_risk(5) == SalienceRiskBucket.NEAR
        assert classify_salience_risk(10) == SalienceRiskBucket.NEAR
        assert classify_salience_risk(11) == SalienceRiskBucket.MEDIUM
        assert classify_salience_risk(25) == SalienceRiskBucket.MEDIUM
        assert classify_salience_risk(26) == SalienceRiskBucket.FAR
        assert classify_salience_risk(50) == SalienceRiskBucket.FAR
        assert classify_salience_risk(51) == SalienceRiskBucket.VERY_FAR
        assert classify_salience_risk(150) == SalienceRiskBucket.VERY_FAR
        assert classify_salience_risk(None) == SalienceRiskBucket.VERY_FAR
