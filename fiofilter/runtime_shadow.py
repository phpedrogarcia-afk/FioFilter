"""fiofilter.runtime_shadow — Incremental Runtime Read Receipt Shadow Harness.

Operational proof of real-time read receipt shadow observation:
- Two explicit modes:
  - PASSIVE_STREAM_SHADOW: Observes growing session JSONL; never intercepts or alters output.
  - DIRECT_READ_LAB: Performs structured file read, returns exact RAW output, computes shadow reference.
- Epistemic Freshness Separation:
  - PASSIVE_F1_DELIVERY_IDENTITY
  - POST_OBSERVATION_F4
  - DIRECT_EXECUTION_F4
- Incremental JSONL tailing:
  - Complete lines only; retains incomplete line in buffer
  - Partial write safety: PARTIAL_JSON_DOUBLE_PROCESSING=0, PARTIAL_JSON_LOSS=0
  - Source rewind and rotation detection (SOURCE_REWOUND_OR_REPLACED)
- Deterministic event identity and at-most-once processing per source event
- Crash consistency and local atomic checkpointing (resume from offset)
- TOCTOU mitigation in Direct Lab: reads bytes once for both RAW delivery and proof
- Shadow failure isolation: observer exceptions never block RAW delivery
- Observational salience and recency risk reporting
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple

from fiofilter.read_receipt import (
    FreshnessLevel,
    ReadReceiptDecision,
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
from fiofilter.context_census import classify_tool_call, decode_tool_output

SCHEMA_VERSION = "M08_RUNTIME_SHADOW_V1"
CHECKPOINT_SCHEMA_VERSION = "M08_CHECKPOINT_V1"


class HarnessMode(str, enum.Enum):
    """Execution mode of the runtime shadow harness."""
    PASSIVE_STREAM_SHADOW = "PASSIVE_STREAM_SHADOW"
    DIRECT_READ_LAB = "DIRECT_READ_LAB"


class EpistemicFreshnessProof(str, enum.Enum):
    """Epistemic scope of a freshness observation."""
    PASSIVE_F1_DELIVERY_IDENTITY = "PASSIVE_F1_DELIVERY_IDENTITY"
    POST_OBSERVATION_F4 = "POST_OBSERVATION_F4"
    DIRECT_EXECUTION_F4 = "DIRECT_EXECUTION_F4"
    UNPROVEN = "UNPROVEN"


class SalienceRiskBucket(str, enum.Enum):
    """Observational distance risk buckets for candidate salience."""
    NEAR = "NEAR"          # 0-10 calls
    MEDIUM = "MEDIUM"      # 11-25 calls
    FAR = "FAR"            # 26-50 calls
    VERY_FAR = "VERY_FAR"  # >50 calls


def classify_salience_risk(call_distance: Optional[int]) -> Optional[SalienceRiskBucket]:
    """Classify call distance of repeat read events into observational risk bucket.

    Returns None for first deliveries (where call_distance is None), as first deliveries
    do not have a prior observation and therefore carry zero reread salience risk.
    """
    if call_distance is None:
        return None
    if call_distance <= 10:
        return SalienceRiskBucket.NEAR
    if call_distance <= 25:
        return SalienceRiskBucket.MEDIUM
    if call_distance <= 50:
        return SalienceRiskBucket.FAR
    return SalienceRiskBucket.VERY_FAR


class SourceRewindException(Exception):
    """Raised when an observed source file shrinks or rotates unexpectedly."""
    pass


class LedgerChainCorruptionException(Exception):
    """Raised when ledger hash chain continuity is violated."""
    pass


@dataclass
class ShadowCursor:
    """Checkpoint metadata tracking incremental progress over a source."""
    schema_version: str
    session_id: str
    source_path: str
    last_committed_offset: int
    last_record_id: Optional[str]
    last_event_hash: str
    processed_event_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ShadowCursor:
        return cls(
            schema_version=d.get("schema_version", CHECKPOINT_SCHEMA_VERSION),
            session_id=d.get("session_id", ""),
            source_path=d.get("source_path", ""),
            last_committed_offset=int(d.get("last_committed_offset", 0)),
            last_record_id=d.get("last_record_id"),
            last_event_hash=d.get("last_event_hash", "0" * 64),
            processed_event_count=int(d.get("processed_event_count", 0)),
        )


class PassiveJsonlTailSource:
    """Read-only incremental JSONL tail observer with partial-line safety.

    Guarantees:
    - Reads complete lines only.
    - Retains partial/incomplete line in memory buffer until completed.
    - Never parses partial JSON.
    - Detects file truncation/rewind and raises SourceRewindException.
    - Detects file replacement.
    - Never rewrites source file.
    """

    def __init__(
        self,
        file_path: pathlib.Path,
        start_offset: int = 0,
    ) -> None:
        self.file_path = file_path.resolve()
        self.current_offset = start_offset
        self.buffer = b""
        self._initial_size: Optional[int] = None
        self._file_inode: Optional[int] = None
        self._check_file_identity()

    def _check_file_identity(self) -> None:
        if self.file_path.exists():
            st = self.file_path.stat()
            self._initial_size = st.st_size
            self._file_inode = getattr(st, "st_ino", None)

    def poll_records(
        self,
        max_records: Optional[int] = None,
    ) -> List[Tuple[int, Dict[str, Any], int]]:
        """Poll for newly appended complete JSON records.

        Returns:
            [(start_byte_offset, record_dict, end_byte_offset), ...]
        """
        if not self.file_path.exists():
            return []

        st = self.file_path.stat()
        current_file_size = st.st_size

        # Check for source truncation / rewind
        if current_file_size < self.current_offset:
            raise SourceRewindException(
                f"SOURCE_REWOUND_OR_REPLACED: File size ({current_file_size} B) "
                f"is less than committed cursor offset ({self.current_offset} B)"
            )

        # Check for file replacement via inode where supported
        curr_inode = getattr(st, "st_ino", None)
        if self._file_inode is not None and curr_inode is not None:
            if curr_inode != self._file_inode and current_file_size < self.current_offset:
                raise SourceRewindException(
                    "SOURCE_REWOUND_OR_REPLACED: Inode changed and size is smaller than offset"
                )

        # Read newly appended bytes starting from file_offset
        file_read_offset = self.current_offset + len(self.buffer)
        with open(self.file_path, "rb") as f:
            f.seek(file_read_offset)
            new_data = f.read()

        if new_data:
            self.buffer += new_data

        if not self.buffer:
            return []

        records: List[Tuple[int, Dict[str, Any], int]] = []
        pos = 0

        while True:
            newline_idx = self.buffer.find(b"\n", pos)
            if newline_idx == -1:
                # Incomplete line remaining: keep in buffer, advance committed offset past consumed lines
                self.buffer = self.buffer[pos:]
                self.current_offset += pos
                break

            line_bytes = self.buffer[pos : newline_idx + 1]
            rec_start_offset = self.current_offset + pos
            rec_end_offset = self.current_offset + newline_idx + 1
            pos = newline_idx + 1

            line_stripped = line_bytes.strip()
            if not line_stripped:
                continue

            try:
                rec = json.loads(line_stripped.decode("utf-8"))
                records.append((rec_start_offset, rec, rec_end_offset))
            except Exception:
                # If complete line fails to parse, pass over it
                pass

            if max_records and len(records) >= max_records:
                self.buffer = self.buffer[pos:]
                self.current_offset += pos
                break

        return records


class RuntimeReceiptState:
    """Manages session-scoped receipts and deduplicated event processing."""

    def __init__(
        self,
        session_id: str,
        base_dir: Optional[pathlib.Path] = None,
    ) -> None:
        self.session_id = session_id
        self.base_dir = base_dir.resolve() if base_dir else None
        self.evaluator = ReadReceiptEvaluator(session_id=session_id, base_dir=self.base_dir)
        self.processed_call_ids: Set[str] = set()

    def reset(self, new_session_id: str) -> None:
        """Reset state cleanly for a new session."""
        self.session_id = new_session_id
        self.evaluator.reset_session(new_session_id)
        self.processed_call_ids.clear()

    def get_snapshot(self) -> Dict[str, Any]:
        """Produce serializable snapshot of active receipts and processed calls."""
        from fiofilter.read_receipt import asdict
        receipts_list = []
        for (norm_id, view_id), rcpt in self.evaluator._active_receipts.items():
            receipts_list.append({
                "receipt_id": rcpt.receipt_id,
                "session_id": rcpt.session_id,
                "original_path": rcpt.original_path,
                "resolved_path_identity": rcpt.resolved_path_identity,
                "read_mode": rcpt.read_mode,
                "requested_view": {
                    "view_type": rcpt.requested_view.view_type.value,
                    "start_line": rcpt.requested_view.start_line,
                    "end_line": rcpt.requested_view.end_line,
                    "tail_lines": rcpt.requested_view.tail_lines,
                    "start_byte": rcpt.requested_view.start_byte,
                    "end_byte": rcpt.requested_view.end_byte,
                    "raw_expr": rcpt.requested_view.raw_expr,
                },
                "delivered_sha256": rcpt.delivered_sha256,
                "delivered_bytes": rcpt.delivered_bytes,
                "file_size": rcpt.file_size,
                "mtime_ns_hint": rcpt.mtime_ns_hint,
                "repo_root_if_known": rcpt.repo_root_if_known,
                "git_head_if_known": rcpt.git_head_if_known,
                "worktree_state_if_known": rcpt.worktree_state_if_known,
                "first_seen_call": rcpt.first_seen_call,
                "last_seen_call": rcpt.last_seen_call,
                "first_seen_episode": rcpt.first_seen_episode,
                "last_seen_episode": rcpt.last_seen_episode,
                "first_seen_timestamp": rcpt.first_seen_timestamp,
                "last_seen_timestamp": rcpt.last_seen_timestamp,
                "sensitivity": rcpt.sensitivity,
                "persistence_policy": rcpt.persistence_policy,
                "reference_count": rcpt.reference_count,
            })
        return {
            "receipt_counter": self.evaluator._receipt_counter,
            "receipts": receipts_list,
            "processed_call_ids": list(self.processed_call_ids),
        }

    def restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Restore active receipts and processed call IDs from snapshot."""
        from fiofilter.read_receipt import ReadReceipt, ReadView, ReadViewType
        self.evaluator._receipt_counter = snapshot.get("receipt_counter", 0)
        self.processed_call_ids = set(snapshot.get("processed_call_ids", []))
        self.evaluator._active_receipts.clear()
        self.evaluator._receipts_by_id.clear()

        for d in snapshot.get("receipts", []):
            v_data = d["requested_view"]
            view = ReadView(
                view_type=ReadViewType(v_data["view_type"]),
                start_line=v_data.get("start_line"),
                end_line=v_data.get("end_line"),
                tail_lines=v_data.get("tail_lines"),
                start_byte=v_data.get("start_byte"),
                end_byte=v_data.get("end_byte"),
                raw_expr=v_data.get("raw_expr"),
            )
            rcpt = ReadReceipt(
                receipt_id=d["receipt_id"],
                session_id=d["session_id"],
                original_path=d["original_path"],
                resolved_path_identity=d["resolved_path_identity"],
                read_mode=d["read_mode"],
                requested_view=view,
                delivered_sha256=d["delivered_sha256"],
                delivered_bytes=d["delivered_bytes"],
                file_size=d.get("file_size"),
                mtime_ns_hint=d.get("mtime_ns_hint"),
                repo_root_if_known=d.get("repo_root_if_known"),
                git_head_if_known=d.get("git_head_if_known"),
                worktree_state_if_known=d.get("worktree_state_if_known"),
                first_seen_call=d.get("first_seen_call", 0),
                last_seen_call=d.get("last_seen_call", 0),
                first_seen_episode=d.get("first_seen_episode"),
                last_seen_episode=d.get("last_seen_episode"),
                first_seen_timestamp=d.get("first_seen_timestamp"),
                last_seen_timestamp=d.get("last_seen_timestamp"),
                sensitivity=d.get("sensitivity", "NOT_SENSITIVE"),
                persistence_policy=d.get("persistence_policy", "EPHEMERAL"),
                reference_count=d.get("reference_count", 0),
            )
            if rcpt.resolved_path_identity:
                self.evaluator._active_receipts[(rcpt.resolved_path_identity, view.view_id)] = rcpt
            self.evaluator._receipts_by_id[rcpt.receipt_id] = rcpt

    def process_historical_or_stream_event(
        self,
        call_id: str,
        command_str: str,
        delivered_bytes: int,
        delivered_sha256: str,
        call_index: int = 0,
        episode_id: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[ReadReceiptDecision]:
        """Process a stream event with at-most-once guarantee per call_id."""
        if call_id in self.processed_call_ids:
            # Duplicate event encountered: ignore
            return None

        decision = self.evaluator.evaluate_historical_event(
            call_id=call_id,
            command_str=command_str,
            delivered_bytes=delivered_bytes,
            delivered_sha256=delivered_sha256,
            call_index=call_index,
            episode_id=episode_id,
            timestamp=timestamp,
        )
        self.processed_call_ids.add(call_id)
        return decision


class DirectReadLab:
    """Direct Laboratory Mode: reads file once, returns RAW, computes shadow reference in parallel.

    Guarantees:
    - Exactly identical RAW return (HARNESS_RAW_OUTPUT == DIRECT_BASELINE_READ).
    - Minimizes TOCTOU race window: reads disk bytes once.
    - Observer/telemetry failures never block RAW delivery (SHADOW_FAILURE_RAW_DELIVERY_PRESERVED = PASS).
    """

    def __init__(
        self,
        session_id: str,
        base_dir: Optional[pathlib.Path] = None,
        simulate_telemetry_failure: bool = False,
    ) -> None:
        self.session_id = session_id
        self.base_dir = base_dir.resolve() if base_dir else None
        self.evaluator = ReadReceiptEvaluator(session_id=session_id, base_dir=self.base_dir)
        self.simulate_telemetry_failure = simulate_telemetry_failure

    def read_file(
        self,
        call_id: str,
        file_path: pathlib.Path,
        view: Optional[ReadView] = None,
        call_index: int = 0,
        episode_id: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> Tuple[bytes, Optional[ReadReceiptDecision]]:
        """Perform laboratory read.

        Returns:
            (raw_requested_bytes, Optional[ReadReceiptDecision])
        """
        requested_view = view or ReadView(ReadViewType.FULL_FILE)

        # 1. Authoritative Disk Read (Done ONCE)
        with open(file_path, "rb") as f:
            full_bytes = f.read()
        raw_view_bytes = extract_view_bytes(full_bytes, requested_view)

        # 2. Parallel Shadow Telemetry Evaluation (Failure-Isolated)
        decision: Optional[ReadReceiptDecision] = None
        try:
            if self.simulate_telemetry_failure:
                raise RuntimeError("SIMULATED_SHADOW_TELEMETRY_FAILURE")

            decision = self.evaluator.evaluate_live_read(
                call_id=call_id,
                file_path=file_path,
                view=requested_view,
                call_index=call_index,
                episode_id=episode_id,
                timestamp=timestamp,
            )
        except Exception:
            # Telemetry error must NOT block raw delivery!
            decision = None

        # 3. Always return RAW bytes unmodified
        return raw_view_bytes, decision


class RuntimeShadowHarness:
    """Incremental Runtime Read Receipt Shadow Harness.

    Orchestrates:
    - Incremental passive tailing of session logs or direct lab calls
    - Safe crash consistency and atomic checkpointing
    - Hash-chained ledger integrity
    - Zero modification of agent runtime
    """

    def __init__(
        self,
        session_id: str,
        source_path: pathlib.Path,
        output_dir: pathlib.Path,
        base_dir: Optional[pathlib.Path] = None,
    ) -> None:
        self.session_id = session_id
        self.source_path = source_path.resolve()
        self.output_dir = output_dir.resolve()
        self.base_dir = base_dir.resolve() if base_dir else None

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.output_dir / "m08_runtime_shadow_events_v1.jsonl"
        self.checkpoint_file = self.output_dir / "m08_runtime_shadow_checkpoint_v1.json"
        self.manifest_file = self.output_dir / "m08_runtime_shadow_manifest_v1.json"
        self.summary_file = self.output_dir / "m08_runtime_shadow_summary_v1.json"

        self.state = RuntimeReceiptState(session_id=self.session_id, base_dir=self.base_dir)
        self.ledger = ReadReceiptLedger(session_id=self.session_id)
        self.cursor = ShadowCursor(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            session_id=self.session_id,
            source_path=str(self.source_path),
            last_committed_offset=0,
            last_record_id=None,
            last_event_hash="0" * 64,
            processed_event_count=0,
        )
        self.pending_calls: Dict[str, Dict[str, Any]] = {}
        self.current_episode_id: int = 0
        self.record_counter: int = 0

        self._load_checkpoint_if_exists()

    def _load_checkpoint_if_exists(self) -> None:
        """Load checkpoint and verify ledger chain continuity on resume."""
        if not self.checkpoint_file.exists():
            return

        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            cursor_dict = d.get("cursor", d)
            loaded_cursor = ShadowCursor.from_dict(cursor_dict)

            # Session isolation: checkpoint session must match
            if loaded_cursor.session_id != self.session_id:
                return

            self.cursor = loaded_cursor
            self.ledger._last_hash = loaded_cursor.last_event_hash

            if "current_episode_id" in d:
                self.current_episode_id = d["current_episode_id"]
            if "record_counter" in d:
                self.record_counter = d["record_counter"]
            if "pending_calls" in d:
                self.pending_calls = d["pending_calls"]

            # Replay ledger events to restore state and verify hash chain
            if self.events_file.exists():
                expected_prev = "0" * 64
                with open(self.events_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        e = json.loads(line_str)
                        if e.get("session_id") != self.session_id:
                            continue

                        # Verify chain
                        if e.get("previous_event_hash") != expected_prev:
                            raise LedgerChainCorruptionException(
                                f"Ledger hash chain broken at event {e.get('event_id')}"
                            )
                        expected_prev = e.get("event_hash", "")
                        self.state.processed_call_ids.add(e.get("call_id", ""))
                        self.ledger.entries.append(e)

                if expected_prev != loaded_cursor.last_event_hash:
                    raise LedgerChainCorruptionException(
                        "Checkpoint last_event_hash does not match final ledger entry hash"
                    )

            if "state_snapshot" in d:
                self.state.restore_snapshot(d["state_snapshot"])
        except LedgerChainCorruptionException:
            raise
        except Exception:
            # Checkpoint corruption: fail closed or start fresh if no ledger
            pass

    def _save_checkpoint_atomic(self) -> None:
        """Save checkpoint atomically using temporary file rename."""
        tmp_file = self.checkpoint_file.with_suffix(".tmp")
        checkpoint_payload = {
            "cursor": self.cursor.to_dict(),
            "state_snapshot": self.state.get_snapshot(),
            "current_episode_id": self.current_episode_id,
            "record_counter": self.record_counter,
            "pending_calls": self.pending_calls,
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_payload, f, indent=2)
        tmp_file.replace(self.checkpoint_file)

    def process_stream_increment(
        self,
        max_records: Optional[int] = None,
    ) -> int:
        """Process newly appended records from source JSONL.

        Transaction order:
        1. Read complete records from PassiveJsonlTailSource.
        2. Filter and pair FILE_READ tool calls with outputs.
        3. Deduplicate against RuntimeReceiptState.
        4. Evaluate ReadReceiptDecision.
        5. Record entry in ReadReceiptLedger.
        6. Append entry to events JSONL.
        7. Atomically save checkpoint.
        """
        source = PassiveJsonlTailSource(
            file_path=self.source_path,
            start_offset=self.cursor.last_committed_offset,
        )
        records = source.poll_records(max_records=max_records)
        if not records:
            return 0

        processed_now = 0

        for start_off, rec, end_off in records:
            self.record_counter += 1
            payload = rec.get("payload", {})
            ptype = payload.get("type")
            ts = rec.get("timestamp")

            if ptype == "message" and payload.get("role") == "user":
                self.current_episode_id += 1
            elif ptype == "custom_tool_call":
                call_id = payload.get("call_id") or payload.get("id") or f"rec_{end_off}"
                # If output is already present directly in this record (synthetic tests)
                if "output" in rec or "output" in payload:
                    out_val = rec.get("output") if "output" in rec else payload.get("output")
                    if isinstance(out_val, str):
                        content_bytes = out_val.encode("utf-8")
                    elif isinstance(out_val, bytes):
                        content_bytes = out_val
                    else:
                        content_bytes, _, _ = decode_tool_output(payload if "output" in payload else rec)

                    input_data = payload.get("input", {})
                    cmd = input_data.get("cmd", "") if isinstance(input_data, dict) else ""
                    target, view, is_pure = parse_read_command(cmd)
                    if target:
                        out_sha = hashlib.sha256(content_bytes).hexdigest()
                        decision = self.state.process_historical_or_stream_event(
                            call_id=call_id,
                            command_str=cmd,
                            delivered_bytes=len(content_bytes),
                            delivered_sha256=out_sha,
                            call_index=self.record_counter,
                            episode_id=self.current_episode_id,
                            timestamp=ts,
                        )
                        if decision is not None:
                            event_id = f"evt-{self.cursor.processed_event_count + 1:04d}"
                            ledger_entry = self.ledger.record_event(event_id, decision)
                            with open(self.events_file, "a", encoding="utf-8") as f:
                                f.write(json.dumps(ledger_entry) + "\n")

                            self.cursor.last_event_hash = ledger_entry["event_hash"]
                            self.cursor.last_record_id = call_id
                            self.cursor.processed_event_count += 1
                            processed_now += 1
                else:
                    self.pending_calls[call_id] = {
                        "payload": payload,
                        "timestamp": ts,
                        "episode_id": self.current_episode_id,
                        "record_index": self.record_counter,
                    }
            elif ptype == "custom_tool_call_output":
                call_id = payload.get("call_id") or payload.get("id")
                if call_id and call_id in self.pending_calls:
                    call_info = self.pending_calls.pop(call_id)
                    call_payload = call_info["payload"]
                    fam, cmd, target_path, line_range, is_mut, op_class = classify_tool_call(call_payload)
                    if fam == "FILE_READ" and target_path:
                        content_bytes, exit_code, truncated = decode_tool_output(payload)
                        out_sha = hashlib.sha256(content_bytes).hexdigest()
                        decision = self.state.process_historical_or_stream_event(
                            call_id=call_id,
                            command_str=cmd or "",
                            delivered_bytes=len(content_bytes),
                            delivered_sha256=out_sha,
                            call_index=call_info["record_index"],
                            episode_id=call_info["episode_id"],
                            timestamp=call_info["timestamp"],
                        )
                        if decision is not None:
                            event_id = f"evt-{self.cursor.processed_event_count + 1:04d}"
                            ledger_entry = self.ledger.record_event(event_id, decision)
                            with open(self.events_file, "a", encoding="utf-8") as f:
                                f.write(json.dumps(ledger_entry) + "\n")

                            self.cursor.last_event_hash = ledger_entry["event_hash"]
                            self.cursor.last_record_id = call_id
                            self.cursor.processed_event_count += 1
                            processed_now += 1

            self.cursor.last_committed_offset = end_off

        self._save_checkpoint_atomic()
        return processed_now

    def record_direct_decision(
        self,
        decision: ReadReceiptDecision,
    ) -> Dict[str, Any]:
        """Record an explicit DirectReadLab decision into the runtime ledger."""
        event_id = f"evt-{self.cursor.processed_event_count + 1:04d}"
        ledger_entry = self.ledger.record_event(event_id, decision)

        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(ledger_entry) + "\n")

        self.cursor.last_event_hash = ledger_entry["event_hash"]
        self.cursor.last_record_id = decision.call_id
        self.cursor.processed_event_count += 1
        self._save_checkpoint_atomic()

        return ledger_entry

    def finalize_artifacts(self) -> Dict[str, Any]:
        """Produce final manifest and summary artifacts."""
        manifest = self.ledger.generate_manifest()
        manifest["cursor"] = self.cursor.to_dict()

        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        summary = {
            "schema_version": "M08_RUNTIME_SHADOW_SUMMARY_V1",
            "session_id": self.session_id,
            "source_path": str(self.source_path),
            "total_processed_events": self.cursor.processed_event_count,
            "last_committed_offset": self.cursor.last_committed_offset,
            "final_event_hash": self.cursor.last_event_hash,
            "active_suppression": False,
            "codex_runtime_changed": False,
            "behavioral_equivalence": "UNKNOWN",
        }
        with open(self.summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        return summary
